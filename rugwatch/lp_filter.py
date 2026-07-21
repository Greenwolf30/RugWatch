"""
Exclude Pump.fun / DEX liquidity program accounts from RugWatch DB and cloud.

These are pool vaults / bonding-curve PDAs / AMM authorities — not ruggers.
"""

from __future__ import annotations

import re
from typing import Any

# Global Solana program / authority addresses (not per-mint PDAs)
KNOWN_LP_PROGRAMS: dict[str, str] = {
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1": "Raydium Authority V4",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "Raydium CLMM",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter v6",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "Token Program",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022 Program",
    "11111111111111111111111111111111": "System Program",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "Associated Token Account Program",
    "ComputeBudget111111111111111111111111111111": "Compute Budget",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium AMM v4",
    "5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h": "Raydium AMM Authority",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "Raydium CPMM",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "Meteora DLMM",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "Meteora Pools",
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG": "Meteora DAMM",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "Pump.fun AMM (PumpSwap)",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun Program",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s": "Metaplex Token Metadata",
}

_LP_TEXT_RE = re.compile(
    r"\b("
    r"pump\.fun|pumpfun|pumpswap|bonding\s*curve|associated\s*bonding|"
    r"liquidity\s*pair|liquidity\s*pool|known\s*liquidity|"
    r"raydium\s*pool|raydium\s*authority|raydium\s*amm|raydium\s*clmm|"
    r"orca\s*whirlpool|meteora|pump\s*swap|"
    r"\blp\b|\bamm\b|\bclmm\b|\bdlmm\b|\bcpmm\b|"
    r"pool\s*\(liquidity\)|bonding\s*curve"
    r")\b",
    re.I,
)

_MINT_IN_NOTES_RE = re.compile(
    r"\bmint\s+([1-9A-HJ-NP-Za-km-z]{32,44})\b",
    re.I,
)


def is_lp_text(*parts: Any) -> bool:
    blob = " ".join(str(p or "") for p in parts)
    if not blob.strip():
        return False
    return bool(_LP_TEXT_RE.search(blob))


def is_known_program_address(addr: str | None) -> bool:
    a = (addr or "").strip()
    return bool(a and a in KNOWN_LP_PROGRAMS)


def pump_lp_addresses_for_mint(mint: str | None) -> set[str]:
    """Best-effort per-mint Pump.fun curve/pool PDAs from public API."""
    m = (mint or "").strip()
    if not m or not m.lower().endswith("pump"):
        return set()
    out: set[str] = set()
    try:
        from .http_util import get_json

        data = None
        for url in (
            f"https://frontend-api-v3.pump.fun/coins/{m}",
            f"https://frontend-api.pump.fun/coins/{m}",
        ):
            try:
                data = get_json(url, timeout=8.0, retries=0)
                if isinstance(data, dict) and (
                    data.get("bonding_curve")
                    or data.get("associated_bonding_curve")
                    or data.get("pump_swap_pool")
                ):
                    break
            except Exception:  # noqa: BLE001
                data = None
        if not isinstance(data, dict):
            return out
        for key in (
            "bonding_curve",
            "associated_bonding_curve",
            "pump_swap_pool",
            "raydium_pool",
        ):
            a = (str(data.get(key) or "")).strip()
            if a and len(a) >= 32:
                out.add(a)
    except Exception:  # noqa: BLE001
        return out
    return out


def is_excluded_lp_wallet(
    item: dict[str, Any] | str | None,
    *,
    pump_lp_cache: dict[str, set[str]] | None = None,
) -> bool:
    """
    True if this wallet should never be stored / uploaded (LP / program).

    item may be a wallet dict or raw address string.
    """
    if item is None:
        return False
    if isinstance(item, str):
        addr = item.strip()
        label = notes = source = ""
    elif isinstance(item, dict):
        addr = (item.get("address") or item.get("wallet") or "").strip()
        label = str(item.get("label") or "")
        notes = str(item.get("notes") or "")
        source = str(item.get("source") or "")
    else:
        return False

    if is_known_program_address(addr):
        return True
    if is_lp_text(label, notes, source):
        return True

    # Resolve per-mint Pump PDAs when notes carry "mint <addr>"
    m = _MINT_IN_NOTES_RE.search(notes or "")
    if m and addr:
        mint = m.group(1)
        cache = pump_lp_cache if pump_lp_cache is not None else {}
        if mint not in cache:
            cache[mint] = pump_lp_addresses_for_mint(mint)
        if addr in cache[mint]:
            return True
    return False


def filter_wallet_items(
    items: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (kept, skipped_lp_count)."""
    kept: list[dict[str, Any]] = []
    skipped = 0
    cache: dict[str, set[str]] = {}
    for it in items or []:
        if not isinstance(it, dict):
            skipped += 1
            continue
        if is_excluded_lp_wallet(it, pump_lp_cache=cache):
            skipped += 1
            continue
        kept.append(it)
    return kept, skipped


def scrub_lp_from_db(db: Any) -> dict[str, Any]:
    """Delete LP/program wallets from local DB. Returns {removed, addresses}."""
    rows = db.list_wallets(min_score=0, limit=5_000_000) if hasattr(db, "list_wallets") else []
    drop: list[str] = []
    cache: dict[str, set[str]] = {}
    for w in rows or []:
        if not isinstance(w, dict):
            continue
        if is_excluded_lp_wallet(w, pump_lp_cache=cache):
            a = (w.get("address") or "").strip()
            if a:
                drop.append(a)
    removed = 0
    if drop and hasattr(db, "delete_wallets"):
        stats = db.delete_wallets(drop)
        removed = int(stats.get("deleted") or stats.get("removed") or len(drop))
    elif drop and hasattr(db, "delete_wallet"):
        for a in drop:
            try:
                db.delete_wallet(a)
                removed += 1
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True, "removed": removed, "addresses": drop[:200], "count": len(drop)}
