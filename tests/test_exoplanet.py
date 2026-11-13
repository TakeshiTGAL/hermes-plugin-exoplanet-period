"""Offline checks. The network is not required."""
from __future__ import annotations

import ast
import io
import json
import os
import re
import sys
import types
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

import client
import match
import prefix
import public_cron
import service
import watch
from client import (
    TIMEOUT_SECONDS,
    USER_AGENT,
    HttpResult,
    UrllibTransport,
    build_opener,
    build_request,
    checked_url,
    identifiers_url,
    properties_url,
    tap_url,
)
from cli import (
    GONE,
    PROMPT,
    SCRIPT_NAME,
    handle,
    job_status,
    schedule_job,
    unschedule_job,
)
from public_cron import Cmd, Store
from safe_write import HARD_LINK_CUT, WriteRefused, write_bytes
from service import (
    ARCHIVE_EMPTY,
    ARCHIVE_MULTI,
    DISCOVERY_MISSED,
    FACILITY_ABSENT,
    QUOTE_ALL,
    QUOTE_PERIOD,
    QUOTE_PERIOD_FACILITY,
    QUOTE_PERIOD_YEAR,
    YEAR_ABSENT,
    lookup,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CANON = "WASP-12 b"


@pytest.fixture(autouse=True)
def _reset_state():
    watch.set_data_dir(None)
    client._LAST_CALL = 0.0
    prefix.remember_profile_name(None)
    yield
    watch.set_data_dir(None)
    client._LAST_CALL = 0.0
    prefix.remember_profile_name(None)


def load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class MapTransport:
    def __init__(self, table: dict[str, tuple[int, bytes, str]]) -> None:
        self.table = table
        self.calls: list[str] = []

    def get(self, url: str) -> HttpResult:
        self.calls.append(url)
        if url not in self.table:
            raise AssertionError(url)
        status, body, kind = self.table[url]
        return HttpResult(status, body, kind)


def exact_table(**extra) -> dict:
    table = {
        identifiers_url(CANON): (200, load("ident_wasp12b.json"), "ok"),
        identifiers_url("WASP-12b"): (200, load("ident_wasp12b.json"), "ok"),
        properties_url(CANON): (200, load("props_wasp12b.json"), "ok"),
        tap_url(CANON): (200, load("tap_exact.json"), "ok"),
    }
    table.update(extra)
    return table


def test_wasp12b_uses_the_confirmed_mast_row_and_one_archive_row():
    transport = MapTransport(exact_table())
    body = lookup(CANON, transport)
    props = json.loads(load("props_wasp12b.json"))
    chosen = next(row for row in props if row["catalog_name"] == "exoplanets.org")
    assert body["ok"] is True
    assert body["canonical_name"] == CANON
    assert body["disposition"] == "confirmed planet"
    assert body["orbital_period_days"] == chosen["orbital_period"]
    assert body["catalog_name"] == "exoplanets.org"
    assert body["modified_date"] == chosen["modified_date"]
    assert body["discovery_year"] == 2008
    assert body["discovery_facility"] == "SuperWASP"
    assert body["discovery_note"] == ""
    assert body["next_step"] == QUOTE_ALL
    assert body["source_url"].endswith("/WASP-12%20b/properties")
    assert not body["source_url"].endswith("/")
    assert body["orbital_period_days"] != 1.0914304469578493
    assert "pscomppars" in body["discovery_source_url"]
    assert " like " not in body["discovery_source_url"]
    assert transport.calls == [
        identifiers_url(CANON),
        properties_url(CANON),
        tap_url(CANON),
    ]


def test_wasp12_is_a_candidate_and_wasp120_is_absent():
    transport = MapTransport({identifiers_url("WASP-12"): (200, load("ident_wasp12.json"), "ok")})
    body = lookup("WASP-12", transport)
    text = json.dumps(body)
    assert body["ok"] is False
    assert body["error_type"] == "not_exact"
    assert body["orbital_period_days"] is None
    assert body["candidates"] == [{"canonical_name": CANON}]
    assert "different planet" in body["next_step"]
    assert "stop" in body["next_step"]
    assert "WASP-120" not in text
    assert transport.calls == [identifiers_url("WASP-12")]


def test_wasp12_with_wasp120_identifier_stays_a_candidate():
    transport = MapTransport({identifiers_url("WASP-12"): (200, load("ident_wasp120.json"), "ok")})
    body = lookup("WASP-12", transport)
    assert body["ok"] is False
    assert body["error_type"] == "not_exact"
    assert body["candidates"] == [{"canonical_name": "WASP-120 b"}]
    assert body["orbital_period_days"] is None
    assert len(transport.calls) == 1


def test_wasp1_candidate_is_wasp100_not_a_period():
    transport = MapTransport({identifiers_url("WASP-1"): (200, load("ident_wasp1.json"), "ok")})
    body = lookup("WASP-1", transport)
    assert body["candidates"] == [{"canonical_name": "WASP-100 b"}]
    assert body["orbital_period_days"] is None
    assert body["ok"] is False


def test_compact_wasp12b_matches_the_official_name():
    body = lookup("WASP-12b", MapTransport(exact_table()))
    assert body["ok"] is True
    assert body["canonical_name"] == CANON
    assert body["discovery_year"] == 2008


def test_missing_name_is_a_finished_miss():
    transport = MapTransport({identifiers_url("NotAPlanetZZZ"): (200, load("ident_missing.json"), "ok")})
    body = lookup("NotAPlanetZZZ", transport)
    assert body["ok"] is False
    assert body["error_type"] == "not_found"
    assert body["orbital_period_days"] is None
    assert transport.calls == [identifiers_url("NotAPlanetZZZ")]


def test_empty_properties_is_not_a_missing_planet():
    table = exact_table()
    table[properties_url(CANON)] = (200, load("props_missing.json"), "ok")
    body = lookup(CANON, MapTransport(table))
    assert body["error_type"] == "no_confirmed_row"
    assert body["canonical_name"] == CANON
    assert "returned no planet" not in body["message"]


def test_tap_503_keeps_the_mast_period_and_the_miss_sentence():
    table = exact_table()
    table[tap_url(CANON)] = (503, b"", "retry")
    body = lookup(CANON, MapTransport(table))
    assert body["ok"] is True
    assert body["orbital_period_days"] == json.loads(load("props_wasp12b.json"))[0]["orbital_period"]
    assert body["discovery_year"] is None
    assert body["discovery_facility"] is None
    assert body["discovery_note"] == DISCOVERY_MISSED
    assert body["next_step"] == f"{DISCOVERY_MISSED} {QUOTE_PERIOD}"
    assert QUOTE_ALL not in body["next_step"]


def test_empty_archive_row_does_not_use_the_503_sentence():
    table = exact_table()
    table[tap_url(CANON)] = (200, load("tap_missing.json"), "ok")
    body = lookup(CANON, MapTransport(table))
    assert body["ok"] is True
    assert body["discovery_note"] == ARCHIVE_EMPTY
    assert body["next_step"] == f"{ARCHIVE_EMPTY} {QUOTE_PERIOD}"
    assert DISCOVERY_MISSED not in body["discovery_note"]
    assert QUOTE_ALL not in body["next_step"]
    assert body["orbital_period_days"] is not None


def test_two_archive_rows_do_not_pick_a_year():
    table = exact_table()
    table[tap_url(CANON)] = (200, load("tap_like.json"), "ok")
    body = lookup(CANON, MapTransport(table))
    text = json.dumps(body)
    assert body["ok"] is True
    assert body["discovery_year"] is None
    assert body["discovery_facility"] is None
    assert body["discovery_note"] == ARCHIVE_MULTI
    assert body["next_step"] == f"{ARCHIVE_MULTI} {QUOTE_PERIOD}"
    assert QUOTE_ALL not in body["next_step"]
    assert "2016" not in text
    assert "3.611" not in text


def test_absent_year_is_not_the_503_sentence():
    raw = json.dumps([
        {"pl_name": CANON, "pl_orbper": 1.0, "disc_year": None, "disc_facility": "SuperWASP"}
    ]).encode()
    table = exact_table()
    table[tap_url(CANON)] = (200, raw, "ok")
    body = lookup(CANON, MapTransport(table))
    assert body["discovery_year"] is None
    assert body["discovery_facility"] == "SuperWASP"
    assert body["discovery_note"] == YEAR_ABSENT
    assert body["next_step"] == f"{YEAR_ABSENT} {QUOTE_PERIOD_FACILITY}"
    assert QUOTE_ALL not in body["next_step"]
    assert DISCOVERY_MISSED not in body["discovery_note"]


def _quote_tail(body: dict) -> str:
    note = body["discovery_note"]
    assert body["next_step"].startswith(note)
    return body["next_step"][len(note):].lstrip()


def test_next_step_follows_each_archive_shape():
    """Each archive shape repeats its note and quotes only fields that are present."""
    rows = [
        ("timeout", (0, b"", "timeout"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("redirect", (307, b"", "redirect"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("truncated", (200, b"", "truncated"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("connection", (0, b"", "connection"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("http-404", (404, b"", "http"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("bad-json", (200, b"not-json", "ok"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        ("not-a-list", (200, b'{"pl_name":"WASP-12 b"}', "ok"), None, None, DISCOVERY_MISSED, QUOTE_PERIOD),
        (
            "blank-facility",
            (200, json.dumps([{
                "pl_name": CANON, "pl_orbper": 1.0, "disc_year": 2008, "disc_facility": "  ",
            }]).encode(), "ok"),
            2008, None, FACILITY_ABSENT, QUOTE_PERIOD_YEAR,
        ),
        (
            "bool-year",
            (200, json.dumps([{
                "pl_name": CANON, "pl_orbper": 1.0, "disc_year": True, "disc_facility": "SuperWASP",
            }]).encode(), "ok"),
            None, "SuperWASP", YEAR_ABSENT, QUOTE_PERIOD_FACILITY,
        ),
        (
            "both-absent",
            (200, json.dumps([{
                "pl_name": CANON, "pl_orbper": 1.0, "disc_year": None, "disc_facility": None,
            }]).encode(), "ok"),
            None, None, f"{YEAR_ABSENT} {FACILITY_ABSENT}", QUOTE_PERIOD,
        ),
    ]
    for label, tap, year, facility, note, tail in rows:
        table = exact_table()
        table[tap_url(CANON)] = tap
        body = lookup(CANON, MapTransport(table))
        assert body["ok"] is True, label
        assert body["orbital_period_days"] is not None, label
        assert body["discovery_year"] == year, label
        assert body["discovery_facility"] == facility, label
        assert body["discovery_note"] == note, label
        assert _quote_tail(body) == tail, label
        assert QUOTE_ALL not in body["next_step"], label


def test_apostrophe_name_reaches_tap_with_a_doubled_quote():
    canonical = "Barnard's Star b"
    ident = json.dumps({
        "canonicalName": canonical,
        "planetNames": [canonical],
    }).encode()
    props = json.dumps([{
        "canonical_name": canonical,
        "disposition": "confirmed planet",
        "orbital_period": 233.0,
        "orbital_period_unit": "d",
        "modified_date": "2026-01-01 00:00:00.000000",
        "catalog_name": "exoplanets.org",
    }]).encode()
    archive = json.dumps([{
        "pl_name": canonical,
        "pl_orbper": 233.0,
        "disc_year": 2018,
        "disc_facility": "European Southern Observatory",
    }]).encode()
    source = tap_url(canonical)
    adql = urllib.parse.parse_qs(urllib.parse.urlsplit(source).query)["query"][0]
    assert adql.endswith("pl_name='Barnard''s Star b'")
    assert "Barnard's Star b" not in adql
    transport = MapTransport({
        identifiers_url(canonical): (200, ident, "ok"),
        properties_url(canonical): (200, props, "ok"),
        source: (200, archive, "ok"),
    })
    body = lookup(canonical, transport)
    assert body["ok"] is True
    assert body["canonical_name"] == canonical
    assert body["orbital_period_days"] == 233.0
    assert body["discovery_year"] == 2018
    assert body["discovery_facility"] == "European Southern Observatory"
    assert body["discovery_note"] == ""
    assert body["next_step"] == QUOTE_ALL
    assert transport.calls[-1] == source


def test_bool_period_is_not_a_confirmed_row():
    raw = json.dumps([{
        "canonical_name": CANON,
        "disposition": "confirmed planet",
        "orbital_period": True,
        "orbital_period_unit": "d",
        "modified_date": "2026-10-19 22:08:28.096000",
        "catalog_name": "exoplanets.org",
    }]).encode()
    table = exact_table()
    table[properties_url(CANON)] = (200, raw, "ok")
    body = lookup(CANON, MapTransport(table))
    assert body["error_type"] == "no_confirmed_row"


def test_same_date_tie_keeps_the_earlier_catalog_name():
    rows = [
        {
            "canonical_name": CANON,
            "disposition": "confirmed planet",
            "orbital_period": 2.0,
            "orbital_period_unit": "d",
            "modified_date": "2026-01-01 00:00:00.000000",
            "catalog_name": "zeta",
        },
        {
            "canonical_name": CANON,
            "disposition": "confirmed planet",
            "orbital_period": 3.0,
            "orbital_period_unit": "d",
            "modified_date": "2026-01-01 00:00:00.000000",
            "catalog_name": "alpha",
        },
    ]
    chosen = match.select_row(rows, CANON)
    assert chosen["catalog_name"] == "alpha"
    assert chosen["orbital_period_days"] == 3.0


def test_bad_name_does_not_call():
    transport = MapTransport({})
    for name in ["", "WASP-12?", "WASP/12", "a" * 81, "WASP-12\nb", "WASP-12 b;", "José"]:
        body = lookup(name, transport)
        assert body["error_type"] == "bad_name"
    assert transport.calls == []


def test_wrong_host_is_refused():
    with pytest.raises(ValueError):
        checked_url("https://example.com/planet")
    with pytest.raises(ValueError):
        checked_url("http://exo.mast.stsci.edu/api/v0.1/exoplanets/identifiers/")
    with pytest.raises(ValueError):
        checked_url("https://user:secret-token@exo.mast.stsci.edu/api")


class ScriptOpener:
    def __init__(self, steps) -> None:
        self.steps = list(steps)
        self.urls: list[str] = []
        self.agents: list[str] = []

    def open(self, request, timeout=None):
        assert timeout == TIMEOUT_SECONDS
        self.urls.append(request.full_url)
        self.agents.append(request.get_header("User-agent"))
        step = self.steps.pop(0)
        if step == "timeout":
            raise TimeoutError("slow")
        if step == "connection":
            import urllib.error
            raise urllib.error.URLError("down")
        status, body = step
        if status != 200:
            import urllib.error
            raise urllib.error.HTTPError(request.full_url, status, "status", {}, io.BytesIO(body))
        return _Resp(status, body)


class _Resp:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self, n: int) -> bytes:
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_retry_counts_and_user_agent():
    url = identifiers_url(CANON)
    opener = ScriptOpener([(503, b""), (200, load("ident_wasp12b.json"))])
    result = UrllibTransport(interval=0, opener=opener).get(url)
    assert result.status == 200
    assert result.kind == "ok"
    assert opener.urls == [url, url]
    assert opener.agents == [USER_AGENT, USER_AGENT]

    opener = ScriptOpener([(404, b"missing")])
    result = UrllibTransport(interval=0, opener=opener).get(url)
    assert result.status == 404
    assert len(opener.urls) == 1

    opener = ScriptOpener([(307, b"")])
    result = UrllibTransport(interval=0, opener=opener).get(url)
    assert result.kind == "redirect"
    assert len(opener.urls) == 1

    opener = ScriptOpener([(503, b""), (503, b"")])
    result = UrllibTransport(interval=0, opener=opener).get(url)
    assert result.status == 503
    assert len(opener.urls) == 2


def test_truncated_body_is_not_a_miss():
    opener = ScriptOpener([(200, b"x" * (client.MAX_BODY + 1))])
    result = UrllibTransport(interval=0, opener=opener).get(identifiers_url(CANON))
    assert result.kind == "truncated"
    body = lookup(CANON, MapTransport({
        identifiers_url(CANON): (200, b"", "truncated"),
    }))
    assert body["ok"] is False
    assert body["error_type"] == "truncated"
    assert body["error_type"] != "not_found"
    assert "returned no planet" not in body["message"]


def test_opener_ignores_proxy_env(monkeypatch):
    token = "secret-token"
    for key in (
        "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "all_proxy", "no_proxy", "NO_PROXY", "ftp_proxy",
    ):
        monkeypatch.setenv(key, f"http://user:{token}@127.0.0.1:9")
    opener = build_opener()
    assert opener.proxy_handler.proxies == {}
    assert not any(
        isinstance(handler, urllib.request.ProxyHandler) and handler.proxies
        for handler in opener.handlers
    )
    request = build_request(identifiers_url(CANON))
    blob = str(request.full_url) + str(request.header_items())
    assert token not in blob
    assert USER_AGENT in blob


def test_lookup_does_not_write(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(watch, "write_bytes", lambda *args, **kwargs: called.append(args))
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    body = lookup(CANON, MapTransport(exact_table()))
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert body["ok"] is True
    assert before == after
    assert called == []


def test_unrelated_text_is_unchanged():
    sample = "unrelated tool result\nconversation stays"
    before = sample
    lookup(CANON, MapTransport(exact_table()))
    assert sample == before
    text = (ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "register_hook" not in text
    assert "register_middleware" not in text


def test_watch_same_newer_older_and_cap(tmp_path):
    transport = MapTransport(exact_table())
    added = watch.add_planet(CANON, tmp_path, transport)
    assert added["ok"] is True
    assert watch.run_watch(tmp_path, transport) == ""
    state = json.loads((tmp_path / "watch.json").read_text(encoding="utf-8"))
    state["planets"][CANON]["modified_date"] = "2020-01-01 00:00:00.000000"
    (tmp_path / "watch.json").write_text(json.dumps(state), encoding="utf-8")
    forward = watch.run_watch(tmp_path, transport)
    assert "moved forward" in forward
    assert "2020-01-01 00:00:00.000000" in forward
    assert "2026-10-19 22:08:28.096000" in forward
    assert "exoplanets.org" in forward
    state = json.loads((tmp_path / "watch.json").read_text(encoding="utf-8"))
    state["planets"][CANON]["modified_date"] = "2027-01-01 00:00:00.000000"
    (tmp_path / "watch.json").write_text(json.dumps(state), encoding="utf-8")
    backward = watch.run_watch(tmp_path, transport)
    assert "moved backward" in backward
    assert "2027-01-01 00:00:00.000000" in backward
    failed = MapTransport({identifiers_url(CANON): (503, b"", "retry")})
    kept = json.loads((tmp_path / "watch.json").read_text(encoding="utf-8"))["planets"][CANON]["modified_date"]
    text = watch.run_watch(tmp_path, failed)
    assert "could not be read" in text
    assert json.loads((tmp_path / "watch.json").read_text(encoding="utf-8"))["planets"][CANON]["modified_date"] == kept
    odd = MapTransport({identifiers_url(CANON): (200, load("ident_wasp120.json"), "ok")})
    text = watch.run_watch(tmp_path, odd)
    assert "not an exact planet name" in text
    assert "No date was compared" in text
    planets = {f"Planet-{index} b": {"catalog_name": "exoplanets.org", "modified_date": "2020-01-01 00:00:00.000000"} for index in range(20)}
    (tmp_path / "watch.json").write_text(json.dumps({"version": 1, "planets": planets}), encoding="utf-8")
    refused = watch.add_planet(CANON, tmp_path, MapTransport({}))
    assert refused["error_type"] == "watch_full"
    assert refused["message"].startswith("The watch list already holds 20")


def test_watch_byte_cap_and_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(watch, "MAX_BYTES", 40)
    body = watch.add_planet(CANON, tmp_path, MapTransport(exact_table()))
    assert body["error_type"] == "watch_full"
    assert "8192" in body["message"]
    assert not (tmp_path / "watch.json").exists()

    monkeypatch.setattr(watch, "MAX_BYTES", 8192)
    target = tmp_path / "other.json"
    target.write_text("{}\n", encoding="utf-8")
    (tmp_path / "watch.json").symlink_to(target)
    body = watch.add_planet(CANON, tmp_path, MapTransport({}))
    assert body["error_type"] == "watch_unreadable"
    assert target.read_text(encoding="utf-8") == "{}\n"

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    body = watch.add_planet(CANON, link, MapTransport({}))
    assert body["error_type"] == "watch_unreadable"
    assert list(real.iterdir()) == []


def test_safe_write_refuses_symlink_parent_and_dotdot(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    with pytest.raises(WriteRefused) as raised:
        write_bytes(tmp_path, "../escape.json", b"no")
    assert raised.value.kind == "outside"
    path = nested / "row.json"
    path.write_bytes(b"one")
    other = nested / "alias.json"
    os.link(path, other)
    with pytest.raises(WriteRefused) as raised:
        write_bytes(tmp_path, "nested/row.json", b"two", cut_hardlink=False)
    assert raised.value.kind == "hardlink"
    note = write_bytes(tmp_path, "nested/row.json", b"two", cut_hardlink=True)
    assert note == HARD_LINK_CUT
    assert path.read_bytes() == b"two"
    assert other.read_bytes() == b"one"


def test_schedule_is_local_and_prints_the_profile_prefix(tmp_path):
    calls = []

    def run(args):
        calls.append(list(args))
        if args[:1] == ["list"]:
            return Cmd(0, "", "")
        return Cmd(0, "Created job: abc123\n", "")

    refused, text = schedule_job(Store(run), "telegram", home=tmp_path)
    assert refused == 1
    assert "local only" in text
    assert calls == []
    assert not (tmp_path / "scripts" / SCRIPT_NAME).exists()

    prefix.remember_profile_name("harnessprof")
    code, text = schedule_job(Store(run), "local", home=tmp_path)
    assert code == 0
    assert "--no-agent" in calls[-1]
    assert "--script" in calls[-1]
    assert SCRIPT_NAME in calls[-1]
    assert "hermes -p harnessprof cron remove abc123" in text
    assert "\nhermes cron " not in text
    script = (tmp_path / "scripts" / SCRIPT_NAME).read_text(encoding="utf-8")
    assert "import cron" not in script
    assert "[SILENT]" in PROMPT
    for banned in ("say nothing", "stay silent", "reply with nothing", "do not reply", "output nothing"):
        assert banned not in PROMPT
    assert job_status(Store(lambda args: Cmd(0, "", "")))[1] == GONE
    gone, text = unschedule_job(Store(lambda args: Cmd(0, "", "")), home=tmp_path)
    assert gone == 0
    assert GONE in text
    assert not (tmp_path / "scripts" / SCRIPT_NAME).exists()


def test_sources_do_not_import_cron():
    for path in ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^\s*(from cron\b|import cron\b)", text) is None
        assert "cron.jobs" not in text
        assert "cron.execution_identity" not in text


def test_register_records_only_the_tool_the_cli_and_the_skill(monkeypatch):
    module = types.ModuleType("exoplanet_period_init")
    module.__package__ = ""
    module.__file__ = str(ROOT / "__init__.py")
    sys.modules[module.__name__] = module
    exec(compile((ROOT / "__init__.py").read_text(encoding="utf-8"), module.__file__, "exec"), module.__dict__)

    class Ctx:
        profile_name = "harnessprof"

        def __init__(self):
            self.tools = []
            self.cli = None
            self.skills = []

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

        def register_cli_command(self, **kwargs):
            self.cli = kwargs

        def register_skill(self, *args, **kwargs):
            self.skills.append((args, kwargs))

        def register_hook(self, *args, **kwargs):
            raise AssertionError("hook")

    ctx = Ctx()
    module.register(ctx)
    assert [item["name"] for item in ctx.tools] == ["exoplanet_lookup"]
    assert ctx.cli["name"] == "exoplanet-period"
    assert len(ctx.skills) == 1
    monkeypatch.setattr(service, "default_transport", lambda: MapTransport(exact_table()))
    text = ctx.tools[0]["handler"]({"name": CANON})
    assert isinstance(text, str)
    assert json.loads(text)["ok"] is True


def test_call_cli_prints_json(capsys):
    class Args:
        command = "call"
        tool = "exoplanet_lookup"
        json = json.dumps({"name": CANON, "extra": 1})

    assert handle(Args(), store=Store(lambda args: Cmd(0, "", ""))) == 1
    assert json.loads(capsys.readouterr().out)["error_type"] == "args_invalid"


def test_readme_skill_and_manifest_agree():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first = [line for line in readme.splitlines() if line.strip()][1]
    assert first.startswith("A confirmed exoplanet name returns")
    assert "orbital period in days" in first
    assert "discovery year" in first
    assert "discovery facility" in first
    assert "hermes cron remove" in readme
    assert "lightkurve" in readme
    assert "FITS" in readme
    assert "pip install" not in readme
    skill = (ROOT / "skills" / "exoplanet-period" / "SKILL.md").read_text(encoding="utf-8")
    assert "## When a read fails" in skill
    assert "before web_search" in skill
    assert "tool_search" in skill
    assert "does not set approval-card text" in skill
    description = skill.split("description: ", 1)[1].split("\n", 1)[0].strip().strip('"')
    assert len(description) <= 223
    manifest = (ROOT / "plugin.yaml").read_text(encoding="utf-8")
    assert "provides_hooks: []" in manifest
    tree = ast.parse((ROOT / "schemas.py").read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            fields = {}
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant) and isinstance(value.value, str):
                    fields[key.value] = value.value
            if "name" in fields and "description" in fields:
                found.append(fields)
    assert len(found) == 1
    sentence = found[0]["description"].split(". ")[0] + "."
    assert len(sentence) <= 60
    assert not sentence.lower().startswith("read-only")
