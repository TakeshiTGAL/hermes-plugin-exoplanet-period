"""One confirmed exoplanet. A different name stays a candidate."""
from __future__ import annotations

import json

if __package__:
    from . import errors
    from .client import UrllibTransport, identifiers_url, properties_url, tap_url
    from .match import clean_name, names_exact, select_row
else:
    import errors
    from client import UrllibTransport, identifiers_url, properties_url, tap_url
    from match import clean_name, names_exact, select_row

DISCOVERY_MISSED = "Discovery year and facility could not be retrieved."
ARCHIVE_EMPTY = "The archive returned no row for that exact name."
ARCHIVE_MULTI = "The archive returned more than one row for that exact name."
YEAR_ABSENT = "Discovery year is absent."
FACILITY_ABSENT = "Discovery facility is absent."
QUOTE_ALL = (
    "Quote the period in days, the discovery year, and the discovery facility from this object."
)
QUOTE_PERIOD = "Quote the period in days from this object."
QUOTE_PERIOD_YEAR = "Quote the period in days and the discovery year from this object."
QUOTE_PERIOD_FACILITY = "Quote the period in days and the discovery facility from this object."

_TRANSPORT = None


def default_transport():
    global _TRANSPORT
    if _TRANSPORT is None:
        _TRANSPORT = UrllibTransport()
    return _TRANSPORT


def fail(template: dict, **extra) -> dict:
    out = dict(template)
    out.update(extra)
    return out


def dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _blank(query: str) -> dict:
    return {
        "query": query,
        "canonical_name": None,
        "disposition": None,
        "orbital_period_days": None,
        "discovery_year": None,
        "discovery_facility": None,
        "source_url": None,
        "catalog_name": None,
        "modified_date": None,
        "discovery_source_url": None,
        "discovery_note": "",
        "candidates": [],
    }


def _read_json(result, expect: str):
    if result.kind == "redirect":
        return None, fail(errors.REDIRECT)
    if result.kind == "timeout":
        return None, fail(errors.TIMEOUT)
    if result.kind == "truncated":
        return None, fail(errors.TRUNCATED)
    if result.kind == "connection":
        return None, fail(errors.HTTP_STATUS, message="The catalog connection failed.")
    if result.kind == "retry" or result.status != 200 or result.kind != "ok":
        status = result.status or 0
        return None, fail(errors.HTTP_STATUS, message=f"The catalog returned HTTP {status}.")
    try:
        payload = json.loads(result.body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None, fail(errors.BAD_JSON)
    if expect == "object" and not isinstance(payload, dict):
        return None, fail(errors.BAD_JSON)
    if expect == "list" and not isinstance(payload, list):
        return None, fail(errors.BAD_JSON)
    return payload, None


def _year(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    return None


def _facility(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _discovery_note(year: int | None, facility: str | None, archive_note: str) -> str:
    if archive_note:
        return archive_note
    parts = []
    if year is None:
        parts.append(YEAR_ABSENT)
    if facility is None:
        parts.append(FACILITY_ABSENT)
    return " ".join(parts)


def _next_step(year: int | None, facility: str | None, note: str) -> str:
    """Repeat the discovery note. Name a field in the quote only when this object holds it."""
    if not note:
        return QUOTE_ALL
    if year is not None and facility is not None:
        return f"{note} {QUOTE_ALL}"
    if year is not None:
        return f"{note} {QUOTE_PERIOD_YEAR}"
    if facility is not None:
        return f"{note} {QUOTE_PERIOD_FACILITY}"
    return f"{note} {QUOTE_PERIOD}"


def _from_archive(canonical: str, payload: object) -> tuple[int | None, str | None, str]:
    if not isinstance(payload, list):
        return None, None, DISCOVERY_MISSED
    matched = []
    for row in payload:
        if isinstance(row, dict) and names_exact(canonical, row.get("pl_name"), []):
            matched.append(row)
    if not matched:
        return None, None, ARCHIVE_EMPTY
    if len(matched) > 1:
        return None, None, ARCHIVE_MULTI
    row = matched[0]
    return _year(row.get("disc_year")), _facility(row.get("disc_facility")), ""


def lookup(name: object, transport=None) -> dict:
    query = clean_name(name)
    if query is None:
        return fail(errors.BAD_NAME, **_blank(""))
    base = _blank(query)
    holder = transport or default_transport()
    try:
        ident_url = identifiers_url(query)
    except ValueError:
        return fail(errors.BAD_NAME, **base)
    ident, problem = _read_json(holder.get(ident_url), "object")
    if problem:
        return fail(problem, **base)
    if ident == {}:
        return fail(errors.NOT_FOUND, **base)
    canonical = ident.get("canonicalName")
    aliases = ident.get("planetNames")
    if not isinstance(canonical, str) or clean_name(canonical) is None:
        return fail(errors.BAD_JSON, **base)
    if not names_exact(query, canonical, aliases):
        base["candidates"] = [{"canonical_name": canonical}]
        return fail(errors.NOT_EXACT, **base)
    try:
        source = properties_url(canonical)
    except ValueError:
        return fail(errors.BAD_JSON, **base)
    rows, problem = _read_json(holder.get(source), "list")
    if problem:
        return fail(problem, **base)
    chosen = select_row(rows, canonical)
    if chosen is None:
        base["canonical_name"] = canonical
        base["source_url"] = source
        return fail(errors.NO_CONFIRMED_ROW, **base)
    year = None
    facility = None
    archive_note = DISCOVERY_MISSED
    discovery_url = None
    try:
        discovery_url = tap_url(canonical)
    except ValueError:
        discovery_url = None
    if discovery_url:
        archive, problem = _read_json(holder.get(discovery_url), "list")
        if problem:
            archive_note = DISCOVERY_MISSED
        else:
            year, facility, archive_note = _from_archive(canonical, archive)
    note = _discovery_note(year, facility, archive_note)
    return {
        "ok": True,
        "query": query,
        "canonical_name": chosen["canonical_name"],
        "disposition": chosen["disposition"],
        "orbital_period_days": chosen["orbital_period_days"],
        "discovery_year": year,
        "discovery_facility": facility,
        "source_url": source,
        "catalog_name": chosen["catalog_name"],
        "modified_date": chosen["modified_date"],
        "discovery_source_url": discovery_url,
        "discovery_note": note,
        "candidates": [],
        "next_step": _next_step(year, facility, note),
    }


def invoke(name: object, args: object, transport=None) -> dict:
    if name != "exoplanet_lookup":
        return fail(errors.UNKNOWN_TOOL)
    if not isinstance(args, dict) or set(args) != {"name"}:
        return fail(errors.ARGS_INVALID)
    return lookup(args.get("name"), transport)


TOOLS = {"exoplanet_lookup": lookup}
