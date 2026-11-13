"""Exact planet names. A shorter name is a candidate, not a different planet."""
from __future__ import annotations

import re

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .'+\-]{0,79}\Z")
CONFIRMED = "confirmed planet"
DAY = "d"


def clean_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 80 or ".." in text:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        return None
    if _NAME.fullmatch(text) is None:
        return None
    return text


def fold(value: str) -> str:
    return " ".join(value.casefold().split())


def compact(value: str) -> str:
    return fold(value).replace(" ", "")


def names_exact(query: str, canonical: object, aliases: object) -> bool:
    if not isinstance(canonical, str) or not canonical.strip():
        return False
    names = [canonical]
    if isinstance(aliases, list):
        names.extend(item for item in aliases if isinstance(item, str))
    folded = fold(query)
    packed = compact(query)
    for name in names:
        if fold(name) == folded or compact(name) == packed:
            return True
    return False


def _period(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def select_row(rows: object, canonical: str) -> dict | None:
    """Latest confirmed row in days. A tie keeps the earlier catalog name."""
    if not isinstance(rows, list):
        return None
    picked: list[tuple[str, str, float]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not names_exact(canonical, row.get("canonical_name"), []):
            continue
        if row.get("disposition") != CONFIRMED:
            continue
        if row.get("orbital_period_unit") != DAY:
            continue
        period = _period(row.get("orbital_period"))
        modified = row.get("modified_date")
        catalog = row.get("catalog_name")
        if period is None or not isinstance(modified, str) or not modified:
            continue
        if not isinstance(catalog, str) or not catalog:
            continue
        picked.append((modified, catalog, period))
    if not picked:
        return None
    latest = max(item[0] for item in picked)
    tied = sorted(item for item in picked if item[0] == latest)
    modified, catalog, period = tied[0]
    return {
        "canonical_name": canonical,
        "disposition": CONFIRMED,
        "orbital_period_days": period,
        "catalog_name": catalog,
        "modified_date": modified,
    }
