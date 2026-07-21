"""Pump.fun + DexScreener pump discovery."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from ..http_util import get_json

DEX_SEARCH = "https://api.dexscreener.com/latest/dex/search"
DEX_TOKENS = "https://api.dexscreener.com/latest/dex/tokens"
# Community / frontend-style endpoints (best-effort; may change)
PUMP_COIN = "https://frontend-api.pump.fun/coins"
PUMP_COIN_ALT = "https://frontend-api-v3.pump.fun/coins"


def fetch_pumpfun_pairs(limit: int = 40) -> list[dict[str, Any]]:
    """Recent pump.fun / pumpswap pairs via DexScreener search (newest first)."""
    pairs: list[dict[str, Any]] = []
    for q in ("pump.fun", "pumpswap"):
        try:
            data = get_json(f"{DEX_SEARCH}?{urlencode({'q': q})}", timeout=18.0, retries=1)
        except Exception:  # noqa: BLE001
            continue
        for p in (data or {}).get("pairs") or []:
            if not isinstance(p, dict):
                continue
            chain = (p.get("chainId") or "").lower()
            if chain not in {"solana", "sol"}:
                continue
            pairs.append(p)
    # de-dupe by base mint; keep highest pairCreatedAt when duplicate
    by_mint: dict[str, dict[str, Any]] = {}
    for p in pairs:
        base = p.get("baseToken") or {}
        mint = (base.get("address") or "").strip()
        if not mint:
            continue
        created = p.get("pairCreatedAt") or 0
        try:
            created_i = int(created)
        except (TypeError, ValueError):
            created_i = 0
        prev = by_mint.get(mint)
        if prev is None:
            by_mint[mint] = p
            continue
        prev_c = prev.get("pairCreatedAt") or 0
        try:
            prev_i = int(prev_c)
        except (TypeError, ValueError):
            prev_i = 0
        if created_i >= prev_i:
            by_mint[mint] = p
    # Newest pairs first so "new launch" scans prefer fresh mints
    ranked = sorted(
        by_mint.values(),
        key=lambda p: int(p.get("pairCreatedAt") or 0),
        reverse=True,
    )
    return ranked[: max(1, limit)]


def pair_to_launch(p: dict[str, Any]) -> dict[str, Any]:
    base = p.get("baseToken") or {}
    return {
        "mint": base.get("address") or "",
        "symbol": base.get("symbol") or "",
        "name": base.get("name") or "",
        "pair_address": p.get("pairAddress"),
        "dex_id": p.get("dexId"),
        "url": p.get("url"),
        "price_usd": _f(p.get("priceUsd")),
        "liquidity_usd": _f((p.get("liquidity") or {}).get("usd")),
        "volume_h24": _f((p.get("volume") or {}).get("h24")),
        "pair_created_at_ms": p.get("pairCreatedAt"),
        "chain_id": "solana",
        "source": "dexscreener",
    }


def fetch_recent_launches(limit: int = 30) -> list[dict[str, Any]]:
    """Up to `limit` recent Solana pump-related launches (newest first)."""
    # Pull a wider pool then slice — search APIs return a mixed set
    pairs = fetch_pumpfun_pairs(limit=max(limit * 3, limit, 80))
    launches = [pair_to_launch(p) for p in pairs]
    launches = [x for x in launches if x.get("mint")]
    # Already newest-first from fetch_pumpfun_pairs
    return launches[:limit]


def fetch_coin_meta(mint: str) -> dict[str, Any]:
    """
    Best-effort Pump.fun coin metadata (creator when available).
    Endpoints change often — failures are soft.
    """
    errors: list[str] = []
    for base in (PUMP_COIN, PUMP_COIN_ALT):
        url = f"{base}/{mint}"
        try:
            data = get_json(url, timeout=15.0, retries=0)
            if isinstance(data, dict) and (data.get("mint") or data.get("address") or data.get("creator")):
                return {
                    "ok": True,
                    "mint": data.get("mint") or data.get("address") or mint,
                    "creator": data.get("creator") or data.get("creatorAddress"),
                    "name": data.get("name"),
                    "symbol": data.get("symbol"),
                    "description": data.get("description"),
                    "created_timestamp": data.get("created_timestamp") or data.get("createdTimestamp"),
                    "complete": data.get("complete"),
                    "raw": data,
                    "api": base,
                }
            errors.append(f"{base}: unexpected shape")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{base}: {exc}")
    return {"ok": False, "mint": mint, "error": "; ".join(errors), "creator": None}


def fetch_token_pairs(mint: str) -> list[dict[str, Any]]:
    try:
        data = get_json(f"{DEX_TOKENS}/{mint}", timeout=15.0, retries=1)
    except Exception as exc:  # noqa: BLE001
        return []
    pairs = (data or {}).get("pairs") or []
    return [p for p in pairs if isinstance(p, dict)]


def _f(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
