"""Optional Solscan Pro holders (needs SOLSCAN_API_KEY)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

from ..config import load_dotenv
from ..http_util import DEFAULT_HEADERS, get_json

SOLSCAN_PRO = "https://pro-api.solscan.io/v2.0"


def solscan_key() -> str | None:
    load_dotenv()
    k = (
        os.environ.get("SOLSCAN_API_KEY")
        or os.environ.get("SOLSCAN_PRO_API_KEY")
        or ""
    ).strip()
    return k or None


def fetch_holders(mint: str, *, limit: int = 20) -> dict[str, Any]:
    key = solscan_key()
    if not key:
        return {"ok": False, "skipped": True, "error": "No SOLSCAN_API_KEY", "holders": []}
    params = urlencode({"address": mint, "page": 1, "page_size": min(limit, 40)})
    try:
        data = get_json(
            f"{SOLSCAN_PRO}/token/holders?{params}",
            headers={**DEFAULT_HEADERS, "token": key, "Authorization": key},
            timeout=18.0,
            retries=1,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "holders": []}

    items: list[Any] = []
    if isinstance(data, dict):
        d = data.get("data") if "data" in data else data
        if isinstance(d, dict):
            items = d.get("items") or d.get("result") or d.get("list") or []
        elif isinstance(d, list):
            items = d

    holders = []
    for i, row in enumerate(items[:limit]):
        if not isinstance(row, dict):
            continue
        wallet = row.get("owner") or row.get("address") or row.get("ownerAddress") or ""
        if wallet:
            holders.append({"rank": i + 1, "wallet": wallet, "provider": "solscan"})
    return {"ok": bool(holders), "holders": holders, "api": "solscan_pro"}
