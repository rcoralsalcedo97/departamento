"""Polite HTTP client.

* identifies itself with an honest User-Agent (no rotation, no spoofing);
* enforces a minimum delay per host;
* honours robots.txt for direct HTML collection;
* stops — never retries around — CAPTCHAs, bot challenges and egress-policy denials.
"""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

CHALLENGE_MARKERS = (
    "cf-chl", "challenge-platform", "just a moment...", "attention required",
    "captcha", "are you a robot", "px-captcha", "datadome", "access denied",
    "verifica que eres humano", "account-verification",
)


class NetworkBlocked(RuntimeError):
    """Host unreachable from this environment (egress policy / DNS / TLS)."""


class AccessBlocked(RuntimeError):
    """Site answered with a bot challenge / CAPTCHA / 403. We do not bypass it."""


class RobotsDisallowed(RuntimeError):
    """robots.txt disallows the URL for our user agent."""


class PoliteClient:
    def __init__(self, user_agent: str, timeout_s: float = 30.0, min_delay_s: float = 2.0):
        self.user_agent = user_agent
        self.min_delay_s = min_delay_s
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            },
            timeout=timeout_s,
            follow_redirects=True,
        )
        self.request_count = 0

    # ------------------------------------------------------------------ helpers
    def _throttle(self, host: str, delay: float | None) -> None:
        wait = (delay if delay is not None else self.min_delay_s) - (time.monotonic() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def robots_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self._raw_get(f"{base}/robots.txt", delay=0)
                if resp.status_code >= 400:
                    rp = None  # no robots.txt → allowed
                else:
                    rp.parse(resp.text.splitlines())
            except NetworkBlocked:
                raise
            except httpx.HTTPError:
                rp = None
            self._robots[base] = rp
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(self.user_agent, url)

    def _raw_get(self, url: str, delay: float | None = None, **kw) -> httpx.Response:
        host = urlparse(url).netloc
        self._throttle(host, delay)
        try:
            self.request_count += 1
            return self.client.get(url, **kw)
        except (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise NetworkBlocked(f"{host}: {type(exc).__name__}: {exc}") from exc

    # ------------------------------------------------------------------ public
    def get_html(self, url: str, delay: float | None = None, check_robots: bool = True) -> httpx.Response:
        if check_robots and not self.robots_allowed(url):
            raise RobotsDisallowed(url)
        resp = self._raw_get(url, delay=delay)
        if is_challenge(resp):
            raise AccessBlocked(f"{urlparse(url).netloc} returned HTTP {resp.status_code} with a bot challenge")
        return resp

    def request_json(self, method: str, url: str, **kw) -> httpx.Response:
        host = urlparse(url).netloc
        self._throttle(host, 0.3)
        try:
            self.request_count += 1
            return self.client.request(method, url, **kw)
        except (httpx.ProxyError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise NetworkBlocked(f"{host}: {type(exc).__name__}: {exc}") from exc

    def close(self) -> None:
        self.client.close()


def is_challenge(resp: httpx.Response) -> bool:
    if resp.status_code in (403, 429, 503):
        return True
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype:
        return False
    head = resp.text[:6000].lower()
    return any(m in head for m in CHALLENGE_MARKERS) and len(resp.text) < 60000


def probe(url: str, timeout_s: float = 12.0) -> tuple[bool, str]:
    """Cheap reachability probe used by the preflight gate."""
    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as c:
            r = c.head(url)
        return True, f"HTTP {r.status_code}"
    except httpx.ProxyError as exc:
        return False, f"blocked by egress proxy ({exc})"
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
