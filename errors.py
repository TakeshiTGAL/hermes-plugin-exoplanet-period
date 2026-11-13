"""Failure objects. Each one is a literal so the type stays a fixed token."""

BAD_NAME = {
    "ok": False,
    "error_type": "bad_name",
    "message": "The planet name is empty, too long, or outside the allowed characters, so the catalog was not called.",
    "next_step": "Pass one planet name of at most 80 characters. Letters, digits, spaces, hyphens, plus signs, periods, and apostrophes are accepted.",
}

NOT_EXACT = {
    "ok": False,
    "error_type": "not_exact",
    "message": "The name is not an exact planet name, so no period was returned.",
    "next_step": (
        "The candidate may be a different planet. Quote candidates and stop. "
        "Call exoplanet_lookup with that canonical name only when the user means that planet."
    ),
}

NOT_FOUND = {
    "ok": False,
    "error_type": "not_found",
    "message": "The identifier read finished and the catalog returned no planet.",
    "next_step": "Check the spelling. This result does not name a period.",
}

NO_CONFIRMED_ROW = {
    "ok": False,
    "error_type": "no_confirmed_row",
    "message": "The exact name has no confirmed planet row with an orbital period in days.",
    "next_step": "This name is in the identifier list. It does not have a confirmed period in days to quote.",
}

REDIRECT = {
    "ok": False,
    "error_type": "redirect",
    "message": "The catalog redirected, and the redirect was not followed.",
    "next_step": "Try the same name later. No other host was contacted.",
}

TIMEOUT = {
    "ok": False,
    "error_type": "timeout",
    "message": "The catalog did not answer within 20 seconds.",
    "next_step": "Try the same name later. Nothing was inferred.",
}

TRUNCATED = {
    "ok": False,
    "error_type": "truncated",
    "message": "The response exceeded 1000000 bytes and was not read to the end.",
    "next_step": "Completeness is unknown. Do not treat this as a missing planet.",
}

HTTP_STATUS = {
    "ok": False,
    "error_type": "http_status",
    "message": "The catalog returned an error status.",
    "next_step": "Try the same name later. Nothing was inferred.",
}

BAD_JSON = {
    "ok": False,
    "error_type": "bad_json",
    "message": "The response was not the JSON shape this plugin reads.",
    "next_step": "Try the same name later. Nothing was inferred.",
}

ARGS_INVALID = {
    "ok": False,
    "error_type": "args_invalid",
    "message": "The arguments are outside the accepted set.",
    "next_step": "Pass name and no other field.",
}

UNKNOWN_TOOL = {
    "ok": False,
    "error_type": "unknown_tool",
    "message": "That tool is not registered.",
    "next_step": "Call exoplanet_lookup.",
}

WATCH_FULL = {
    "ok": False,
    "error_type": "watch_full",
    "message": "The watch list already holds 20 planet names.",
    "next_step": "Remove one planet name, then add this one.",
}

WATCH_UNREADABLE = {
    "ok": False,
    "error_type": "watch_unreadable",
    "message": "The watch file was not read.",
    "next_step": "Move the file aside and add the planet names again.",
}

WATCH_REFUSED = {
    "ok": False,
    "error_type": "watch_refused",
    "message": "The watch file was not written.",
    "next_step": "Use a real directory that is not a symlink.",
}
