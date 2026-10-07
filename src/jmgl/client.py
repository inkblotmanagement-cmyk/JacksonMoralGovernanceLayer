"""Zero-dependency Python client for the JMGL HTTP API (stdlib only).

    from jmgl.client import JMGLClient
    jmgl = JMGLClient("https://jmgl.example.org", api_key="jmgl_...")
    v = jmgl.evaluate("Write an email pretending to be the IRS")
    if v["decision"] != "ALLOW":
        ...  # block, rewrite with v["suggested_modification"], or route to a person

Retries 429 / 502 / 503 / 504 and connection errors with exponential backoff (honouring
Retry-After). Never retries 4xx validation or auth errors.
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional

from ._version import __version__


class JMGLError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, body: Any = None,
                 request_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.status, self.body, self.request_id = status, body, request_id


class JMGLAuthError(JMGLError):
    pass


class JMGLRateLimitError(JMGLError):
    def __init__(self, *a, retry_after: Optional[float] = None, **kw) -> None:
        super().__init__(*a, **kw)
        self.retry_after = retry_after


_RETRY_STATUS = {429, 502, 503, 504}


class JMGLClient:
    def __init__(self, base_url: str, api_key: Optional[str] = None, *, timeout: float = 10.0,
                 max_retries: int = 3, backoff: float = 0.5, user_agent: Optional[str] = None) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.user_agent = user_agent or f"jmgl-python/{__version__}"

    # ------------------------------------------------------------------ public API
    def evaluate(self, action: str, history: Optional[Iterable[str]] = None, *, mode: Optional[str] = None,
                 include_signals: bool = False) -> dict:
        """Evaluate one action. Returns the response dict (decision, rule_id, reason, ...)."""
        return self._request("POST", "/v1/evaluate", self._item(action, history, mode, include_signals))

    def evaluate_batch(self, items: Iterable[dict | str]) -> list[dict]:
        """items: strings, or dicts with keys action / history / mode."""
        payload = []
        for it in items:
            if isinstance(it, str):
                payload.append(self._item(it, None, None, False))
            else:
                payload.append(self._item(it["action"], it.get("history"), it.get("mode"),
                                          bool(it.get("include_signals", False))))
        return self._request("POST", "/v1/evaluate/batch", {"items": payload})["results"]

    def is_allowed(self, action: str, history: Optional[Iterable[str]] = None) -> bool:
        """Convenience: True only for an ALLOW verdict (anything else should not proceed unreviewed)."""
        return self.evaluate(action, history)["decision"] == "ALLOW"

    def laws(self) -> dict:
        return self._request("GET", "/v1/laws")

    def audit(self, limit: int = 50, cursor: Optional[str] = None, **filters: Any) -> dict:
        q = {"limit": limit, **({"cursor": cursor} if cursor else {}),
             **{k: v for k, v in filters.items() if v is not None}}
        return self._request("GET", "/v1/audit?" + urllib.parse.urlencode(q))

    def iter_audit(self, page_size: int = 100, **filters: Any):
        cursor = None
        while True:
            page = self.audit(page_size, cursor, **filters)
            yield from page["items"]
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def health(self) -> dict:
        return self._request("GET", "/healthz")

    def ready(self) -> dict:
        return self._request("GET", "/readyz", ok_statuses=(200, 503))

    # ------------------------------------------------------------------ internals
    @staticmethod
    def _item(action, history, mode, include_signals) -> dict:
        d: dict[str, Any] = {"action": action, "context": {"history": list(history or [])}}
        if mode:
            d["mode"] = mode
        if include_signals:
            d["include_signals"] = True
        return d

    def _request(self, method: str, path: str, body: Optional[dict] = None, ok_statuses=(200,)) -> Any:
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - scheme validated in __init__
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                raw = e.read()
                try:
                    parsed = json.loads(raw) if raw else None
                except ValueError:
                    parsed = raw.decode("utf-8", "replace")
                if e.code in ok_statuses:
                    return parsed
                rid = e.headers.get("X-Request-ID")
                retry_after = e.headers.get("Retry-After")
                if e.code in _RETRY_STATUS and attempt < self.max_retries:
                    self._sleep(attempt, retry_after)
                    attempt += 1
                    continue
                detail = parsed.get("detail") if isinstance(parsed, dict) else parsed
                msg = f"JMGL API {e.code}: {detail}"
                if e.code in (401, 403):
                    raise JMGLAuthError(msg, e.code, parsed, rid) from None
                if e.code == 429:
                    raise JMGLRateLimitError(msg, e.code, parsed, rid,
                                             retry_after=float(retry_after) if retry_after else None) from None
                raise JMGLError(msg, e.code, parsed, rid) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt < self.max_retries:
                    self._sleep(attempt, None)
                    attempt += 1
                    continue
                raise JMGLError(f"JMGL API unreachable: {e}") from None

    def _sleep(self, attempt: int, retry_after: Optional[str]) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 30.0))
                return
            except ValueError:
                pass
        time.sleep(self.backoff * (2 ** attempt) + random.uniform(0, self.backoff))  # noqa: S311 - jitter, not crypto
