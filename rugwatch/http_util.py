"""Small HTTP helpers (stdlib + optional certifi)."""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "RugWatch/0.1 (local research tool; market-data)",
}


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
    retries: int = 1,
) -> Any:
    hdrs = {**DEFAULT_HEADERS, **(headers or {})}
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None
            return json.loads(raw)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(0.6 * (attempt + 1))
                continue
            raise
    if last_err:
        raise last_err
    return None


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 20.0,
) -> Any:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {
        **DEFAULT_HEADERS,
        "Content-Type": "application/json",
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else None
