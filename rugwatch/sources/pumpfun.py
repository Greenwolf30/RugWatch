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
    """Recent pump.fun / pumpswap pairs via DexScreener search."""
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
    # de-dupe by pairAddress / base token
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in pairs:
        base = (p.get("baseToken") or {})
        mint = base.get("address") or p.get("pairAddress") or ""
        if not mint or mint in seen:
            continue
        seen.add(mint)
        out.append(p)
        if len(out) >= limit:
            break
    return out


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
    pairs = fetch_pumpfun_pairs(limit=limit * 2)
    launches = [pair_to_launch(p) for p in pairs]
    launches = [x for x in launches if x.get("mint")]
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
