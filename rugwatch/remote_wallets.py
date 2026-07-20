"""Load / save wallet lists from external JSON (Gist, raw GitHub, your host)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .config import wallets_remote_url
from .db import RugWatchDB
from .http_util import DEFAULT_HEADERS


def parse_wallet_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for x in data:
            if isinstance(x, dict):
                out.append(x)
            elif isinstance(x, str) and x.strip():
                out.append({"address": x.strip(), "label": "manual", "source": "import"})
        return out
    if isinstance(data, dict):
        for key in ("wallets", "items", "data"):
            if isinstance(data.get(key), list):
                return parse_wallet_payload(data[key])
    return []


def parse_wallet_text(raw: str, *, source_default: str = "manual_upload") -> list[dict[str, Any]]:
    """
    Parse pasted / file text into wallet dicts.

    Accepts:
      - rugwatch_wallets_v1 / ADTC Ruggers export JSON
      - plain text: one address per line (optional score after comma/space)
      - mixed notes with base58 / 0x addresses embedded
    """
    text = (raw or "").strip()
    if not text:
        return []

    # JSON file / paste
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            items = parse_wallet_payload(data)
            if items:
                return items
        except json.JSONDecodeError:
            pass

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Solana base58 (32–44) or EVM 0x…
    addr_re = re.compile(
        r"\b(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b"
    )
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        # "address,score" or "address score"
        parts = re.split(r"[\s,;|]+", line)
        score = 75
        label = "manual_upload"
        notes = "uploaded manually"
        addr = ""
        for p in parts:
            if addr_re.fullmatch(p):
                addr = p
            elif p.isdigit() and 0 <= int(p) <= 100:
                score = int(p)
        if not addr:
            m = addr_re.search(line)
            if m:
                addr = m.group(1)
        if not addr or addr in seen:
            continue
        seen.add(addr)
        items.append(
            {
                "address": addr,
                "wallet": addr,
                "label": label,
                "risk_score": score,
                "notes": notes,
                "source": source_default,
            }
        )
    return items


def fetch_wallets_from_url(url: str, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    req = Request(url, headers={**DEFAULT_HEADERS, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — user-configured URL
        raw = resp.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    return parse_wallet_payload(data)


def pull_remote_into_db(
    db: RugWatchDB | None = None,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    """
    Download JSON wallet list and merge as manual/import entries.
    URL from arg or RUGWATCH_WALLETS_URL.
    """
    db = db or RugWatchDB()
    u = (url or wallets_remote_url() or "").strip()
    if not u:
        return {
            "ok": False,
            "error": "Set RUGWATCH_WALLETS_URL or pass --url",
            "imported": 0,
        }
    try:
        items = fetch_wallets_from_url(u)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "imported": 0, "url": u}
    stats = db.import_wallets(items, source_default="remote_url")
    return {
        "ok": True,
        "url": u,
        "imported": stats["imported"],
        "skipped": stats["skipped"],
        "db_wallets": db.stats().get("wallets"),
    }


def export_wallets_to_file(
    path: str | Path,
    db: RugWatchDB | None = None,
    *,
    min_score: int = 0,
) -> dict[str, Any]:
    db = db or RugWatchDB()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wallets = db.export_wallets(min_score=min_score)
    payload = {
        "format": "rugwatch_wallets_v1",
        "wallets": wallets,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(p), "count": len(wallets)}


def import_wallets_from_file(path: str | Path, db: RugWatchDB | None = None) -> dict[str, Any]:
    db = db or RugWatchDB()
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    # Prefer JSON parse for .json; always fall back to text address scrape
    items: list[dict[str, Any]] = []
    if p.suffix.lower() == ".json" or raw.lstrip().startswith(("{", "[")):
        try:
            data = json.loads(raw)
            items = parse_wallet_payload(data)
        except json.JSONDecodeError:
            items = []
    if not items:
        items = parse_wallet_text(raw, source_default="import_file")
    if not items:
        return {"ok": False, "path": str(p), "imported": 0, "skipped": 0, "error": "No wallets found in file"}
    stats = db.import_wallets(items, source_default="import_file")
    return {"ok": True, "path": str(p), **stats}


def import_wallets_from_text(
    raw: str,
    db: RugWatchDB | None = None,
    *,
    source_default: str = "manual_upload",
) -> dict[str, Any]:
    """Import wallets from paste box (JSON or plain addresses)."""
    db = db or RugWatchDB()
    items = parse_wallet_text(raw, source_default=source_default)
    if not items:
        return {"ok": False, "imported": 0, "skipped": 0, "error": "No wallet addresses found"}
    stats = db.import_wallets(items, source_default=source_default)
    return {"ok": True, **stats}
