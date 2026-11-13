"""HTTPS GET to two catalogs. Redirects are not followed. One retry on a dead host."""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request

MAST_HOST = "exo.mast.stsci.edu"
TAP_HOST = "exoplanetarchive.ipac.caltech.edu"
HOSTS = {MAST_HOST, TAP_HOST}
MAX_BODY = 1_000_000
TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 2
MIN_INTERVAL_SECONDS = 1.0
USER_AGENT = "hermes-plugin-exoplanet-period/0.1 (keyless catalog read)"
RETRY_STATUSES = {429, 500, 502, 503, 504}
_REDIRECTS = {301, 302, 303, 307, 308}
_LAST_CALL = 0.0


class HttpResult:
    def __init__(self, status: int, body: bytes, kind: str) -> None:
        self.status = status
        self.body = body
        self.kind = kind


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)


def build_opener():
    """Empty ProxyHandler skips the environment proxy. urllib omits it from the handler list when it has no proxy URL."""
    proxy = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy, NoRedirect())
    opener.proxy_handler = proxy
    return opener


def checked_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS:
        raise ValueError("host")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("host")
    return url


def identifiers_url(name: str) -> str:
    query = urllib.parse.urlencode({"name": name})
    return checked_url(f"https://{MAST_HOST}/api/v0.1/exoplanets/identifiers/?{query}")


def properties_url(canonical: str) -> str:
    if "/" in canonical or "\\" in canonical or ".." in canonical:
        raise ValueError("path")
    segment = urllib.parse.quote(canonical, safe="")
    return checked_url(f"https://{MAST_HOST}/api/v0.1/exoplanets/{segment}/properties")


def tap_url(canonical: str) -> str:
    if "\\" in canonical:
        raise ValueError("quote")
    escaped = canonical.replace("'", "''")
    adql = (
        "select pl_name,pl_orbper,disc_year,disc_facility "
        f"from pscomppars where pl_name='{escaped}'"
    )
    query = urllib.parse.urlencode({"query": adql, "format": "json"})
    return checked_url(f"https://{TAP_HOST}/TAP/sync?{query}")


def build_request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        checked_url(url),
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )


class UrllibTransport:
    def __init__(self, interval: float = MIN_INTERVAL_SECONDS, opener=None) -> None:
        self.interval = interval
        self._opener = opener or build_opener()

    def _wait(self) -> None:
        global _LAST_CALL
        wait = self.interval - (time.monotonic() - _LAST_CALL)
        if _LAST_CALL and wait > 0:
            time.sleep(wait)
        _LAST_CALL = time.monotonic()

    def _once(self, url: str) -> HttpResult:
        request = build_request(url)
        try:
            with self._opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                status = int(response.status)
                body = response.read(MAX_BODY + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in _REDIRECTS:
                return HttpResult(int(exc.code), b"", "redirect")
            try:
                body = exc.read(MAX_BODY + 1)
            except Exception:
                return HttpResult(int(exc.code), b"", "truncated")
            if len(body) > MAX_BODY:
                return HttpResult(int(exc.code), b"", "truncated")
            kind = "http"
            if exc.code in RETRY_STATUSES:
                kind = "retry"
            return HttpResult(int(exc.code), body, kind)
        except TimeoutError:
            return HttpResult(0, b"", "timeout")
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                return HttpResult(0, b"", "timeout")
            return HttpResult(0, b"", "connection")
        except OSError:
            return HttpResult(0, b"", "connection")
        if len(body) > MAX_BODY:
            return HttpResult(status, b"", "truncated")
        if status in RETRY_STATUSES:
            return HttpResult(status, body, "retry")
        return HttpResult(status, body, "ok" if status == 200 else "http")

    def get(self, url: str) -> HttpResult:
        checked_url(url)
        last = HttpResult(0, b"", "connection")
        for attempt in range(MAX_ATTEMPTS):
            self._wait()
            last = self._once(url)
            if last.kind in {"timeout", "connection", "retry"} and attempt + 1 < MAX_ATTEMPTS:
                continue
            return last
        return last
