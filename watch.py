"""Local watch list. A morning line prints when a modified date moves or cannot be read."""
from __future__ import annotations

import json
import stat
from pathlib import Path

if __package__:
    from . import errors
    from .match import clean_name, compact, fold
    from .safe_write import WriteRefused, directory_is_real, write_bytes
    from .service import fail, lookup
else:
    import errors
    from match import clean_name, compact, fold
    from safe_write import WriteRefused, directory_is_real, write_bytes
    from service import fail, lookup

PLUGIN_REL = "plugin-data/exoplanet-period/watch.json"
STATE_NAME = "watch.json"
MAX_PLANETS = 20
MAX_BYTES = 8192
_DATA_DIR: Path | None = None


def set_data_dir(path: Path | None) -> None:
    global _DATA_DIR
    _DATA_DIR = path


def _empty() -> dict:
    return {"version": 1, "planets": {}}


def _root_and_rel(directory: Path | None) -> tuple[Path, str]:
    if directory is not None:
        return directory, STATE_NAME
    if _DATA_DIR is not None:
        return _DATA_DIR, STATE_NAME
    from hermes_constants import get_hermes_home

    return Path(get_hermes_home()), PLUGIN_REL


def _state_path(directory: Path | None) -> tuple[Path, Path, str]:
    root, relative = _root_and_rel(directory)
    return root.joinpath(*Path(relative).parts), root, relative


class WatchFileError(Exception):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


def load_state(directory: Path | None = None) -> dict:
    path, _root, _relative = _state_path(directory)
    try:
        directory_is_real(path.parent)
    except WriteRefused as exc:
        raise WatchFileError("watch_unreadable") from exc
    try:
        info = path.lstat()
    except FileNotFoundError:
        return _empty()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise WatchFileError("watch_unreadable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WatchFileError("watch_unreadable") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("planets"), dict):
        raise WatchFileError("watch_unreadable")
    return payload


def save_state(payload: dict, directory: Path | None = None) -> None:
    _path, root, relative = _state_path(directory)
    raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise WatchFileError("watch_full")
    try:
        write_bytes(root, relative, raw, create=True)
    except WriteRefused as exc:
        raise WatchFileError("watch_refused") from exc
    except (OSError, RuntimeError) as exc:
        raise WatchFileError("watch_refused") from exc


def _file_error(exc: WatchFileError) -> dict:
    if exc.error_type == "watch_full":
        return fail(errors.WATCH_FULL, message="The watch file would pass 8192 bytes.")
    if exc.error_type == "watch_refused":
        return fail(errors.WATCH_REFUSED)
    return fail(errors.WATCH_UNREADABLE)


def _planets(payload: dict) -> dict:
    planets = payload.get("planets")
    return planets if isinstance(planets, dict) else {}


def _stored_key(planets: dict, query: str) -> str | None:
    folded = fold(query)
    packed = compact(query)
    for key in planets:
        if isinstance(key, str) and (fold(key) == folded or compact(key) == packed):
            return key
    return None


def add_planet(name: object, directory: Path | None = None, transport=None) -> dict:
    query = clean_name(name)
    if query is None:
        return fail(errors.BAD_NAME)
    try:
        state = load_state(directory)
    except WatchFileError as exc:
        return _file_error(exc)
    except (OSError, RuntimeError):
        return fail(errors.WATCH_UNREADABLE)
    planets = _planets(state)
    existing = _stored_key(planets, query)
    if existing:
        return {
            "ok": True,
            "message": f"{existing} is already on the watch list.",
            "planets": sorted(planets),
            "next_step": "Run the morning job, or add a different planet name.",
        }
    if len(planets) >= MAX_PLANETS:
        return fail(errors.WATCH_FULL)
    record = lookup(query, transport)
    if not record.get("ok"):
        return record
    canonical = record.get("canonical_name")
    modified = record.get("modified_date")
    catalog = record.get("catalog_name")
    if not isinstance(canonical, str) or not isinstance(modified, str) or not isinstance(catalog, str):
        return fail(errors.BAD_JSON)
    planets[canonical] = {"catalog_name": catalog, "modified_date": modified}
    state["planets"] = planets
    state["version"] = 1
    try:
        save_state(state, directory)
    except WatchFileError as exc:
        return _file_error(exc)
    return {
        "ok": True,
        "message": f"Added {canonical}. The same modified date prints no line.",
        "planets": sorted(planets),
        "next_step": "Run schedule when the names, the 08:00 job, and local delivery are what you want.",
    }


def remove_planet(name: object, directory: Path | None = None) -> dict:
    query = clean_name(name)
    if query is None:
        return fail(errors.BAD_NAME)
    try:
        state = load_state(directory)
    except WatchFileError as exc:
        return _file_error(exc)
    except (OSError, RuntimeError):
        return fail(errors.WATCH_UNREADABLE)
    planets = _planets(state)
    existing = _stored_key(planets, query)
    if existing is None:
        return {
            "ok": True,
            "message": f"{query} was not on the watch list.",
            "planets": sorted(planets),
            "next_step": "List the watched planet names before adding one.",
        }
    planets.pop(existing, None)
    state["planets"] = planets
    try:
        save_state(state, directory)
    except WatchFileError as exc:
        return _file_error(exc)
    return {
        "ok": True,
        "message": f"Removed {existing} from the watch list.",
        "planets": sorted(key for key in planets if isinstance(key, str)),
        "next_step": "The morning job keeps running until you unschedule it.",
    }


def list_planets(directory: Path | None = None) -> dict:
    try:
        state = load_state(directory)
    except WatchFileError as exc:
        return _file_error(exc)
    except (OSError, RuntimeError):
        return fail(errors.WATCH_UNREADABLE)
    rows = []
    for key in sorted(key for key in _planets(state) if isinstance(key, str)):
        snap = state["planets"][key]
        modified = snap.get("modified_date") if isinstance(snap, dict) else None
        rows.append({"name": key, "modified_date": modified if isinstance(modified, str) else None})
    return {
        "ok": True,
        "message": f"{len(rows)} planet names are on the watch list.",
        "planets": rows,
        "next_step": "Show this list before schedule. Delivery is local only.",
    }


def _line_for(name: str, previous: object, record: dict) -> tuple[str | None, dict | None]:
    if record.get("error_type") == "not_exact":
        return f"{name} is not an exact planet name. No date was compared.", None
    if not record.get("ok"):
        return f"{name}: the modified date could not be read. The stored date was kept.", None
    modified = record.get("modified_date")
    catalog = record.get("catalog_name")
    if not isinstance(modified, str) or not modified or not isinstance(catalog, str):
        return f"{name}: the modified date could not be read. The stored date was kept.", None
    old = previous.get("modified_date") if isinstance(previous, dict) else None
    if not isinstance(old, str) or not old:
        return f"{name}: the modified date could not be read. The stored date was kept.", None
    if modified == old:
        return None, None
    stored = {"catalog_name": catalog, "modified_date": modified}
    if modified > old:
        return f"{name} moved forward from {old} to {modified} in {catalog}.", stored
    return f"{name} moved backward from {old} to {modified} in {catalog}.", stored


def run_watch(directory: Path | None = None, transport=None) -> str:
    """Stdout for the morning job. An empty string sends no message."""
    try:
        state = load_state(directory)
    except WatchFileError:
        return "The watch file was not read. Stored dates were kept.\n"
    except (OSError, RuntimeError):
        return "The watch file was not read. Stored dates were kept.\n"
    planets = _planets(state)
    lines: list[str] = []
    dirty = False
    for name in sorted(key for key in planets if isinstance(key, str)):
        if clean_name(name) is None:
            lines.append(f"{name} is not an exact planet name. No date was compared.")
            continue
        try:
            record = lookup(name, transport)
        except Exception:
            lines.append(f"{name}: the modified date could not be read. The stored date was kept.")
            continue
        line, stored = _line_for(name, planets.get(name), record)
        if stored is not None:
            planets[name] = stored
            dirty = True
        if line:
            lines.append(line)
    if dirty:
        state["planets"] = planets
        state["version"] = 1
        try:
            save_state(state, directory)
        except WatchFileError:
            lines.append("The new date was not saved. The previous file was kept.")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def watch_stdout() -> str:
    return run_watch()
