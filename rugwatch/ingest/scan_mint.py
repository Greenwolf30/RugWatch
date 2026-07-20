"""Scan a mint, extract suspicious wallets, write to DB."""

from __future__ import annotations

from typing import Any

from .. import config
from ..db import RugWatchDB
from ..sources import pumpfun, rugcheck, solscan
from ..sources import rpc as sol_rpc


def scan_and_ingest_mint(
    mint: str,
    *,
    db: RugWatchDB | None = None,
    chain_id: str = "solana",
    deep: bool = True,
    label_hint: str | None = None,
) -> dict[str, Any]:
    """
    Pull Rugcheck + optional RPC/Pump.fun meta for a mint.
    Upsert wallets that look risky (creator, insiders, early signers).
    """
    mint = mint.strip()
    db = db or RugWatchDB()
    report: dict[str, Any] = {
        "ok": False,
        "mint": mint,
        "wallets_flagged": [],
        "incident_id": None,
        "sources": {},
        "errors": [],
    }

    # ── Rugcheck ──────────────────────────────────────────────────────
    rc = rugcheck.fetch_report(mint)
    report["sources"]["rugcheck"] = {
        "ok": rc.get("ok"),
        "score": rc.get("score"),
        "rugged": rc.get("rugged"),
        "risks": rc.get("risks") or [],
        "holder_count": len(rc.get("holders") or []),
    }
    if not rc.get("ok"):
        report["errors"].append(f"rugcheck: {rc.get('error')}")

    # ── Pump.fun meta ─────────────────────────────────────────────────
    pf = pumpfun.fetch_coin_meta(mint)
    report["sources"]["pumpfun"] = {
        "ok": pf.get("ok"),
        "creator": pf.get("creator"),
        "error": pf.get("error"),
    }

    symbol = None
    name = None
    meta = rc.get("tokenMeta") if isinstance(rc.get("tokenMeta"), dict) else {}
    symbol = meta.get("symbol") or pf.get("symbol")
    name = meta.get("name") or pf.get("name")

    pairs = pumpfun.fetch_token_pairs(mint)
    if pairs:
        base = (pairs[0].get("baseToken") or {})
        symbol = symbol or base.get("symbol")
        name = name or base.get("name")
        report["sources"]["dexscreener"] = {"pairs": len(pairs), "url": pairs[0].get("url")}

    # Risk classification for this mint
    risks = list(rc.get("risks") or [])
    rugged = bool(rc.get("rugged"))
    risk_text = " ".join(str(r).lower() for r in risks)
    looks_bad = rugged or any(
        k in risk_text
        for k in (
            "rug",
            "honeypot",
            "mint authority",
            "freeze",
            "copycat",
            "low liquidity",
            "bundl",
            "insider",
            "dev",
        )
    )
    incident_type = "rug" if rugged or "rug" in risk_text else (
        "high_risk" if looks_bad else "watch"
    )
    confidence = 80 if rugged else (65 if looks_bad else 40)

    incident_id = db.add_incident(
        mint,
        incident_type,
        chain_id=chain_id,
        symbol=symbol,
        name=name,
        confidence=confidence,
        evidence={
            "rugcheck_score": rc.get("score"),
            "risks": risks[:20],
            "rugged": rugged,
            "pump_creator": pf.get("creator"),
            "label_hint": label_hint,
        },
        source="scan_mint",
    )
    report["incident_id"] = incident_id
    report["incident_type"] = incident_type
    report["symbol"] = symbol
    report["name"] = name

    flagged: list[dict[str, Any]] = []
    # Default: manual-only — Scan suggests wallets but does NOT write them to the DB.
    # Set RUGWATCH_AUTO_FLAG=1 to restore automatic flagging.
    auto_flag = config.auto_flag_wallets()
    report["auto_flag"] = auto_flag
    report["manual_only"] = not auto_flag

    def _flag(
        wallet: str,
        role: str,
        score: int,
        *,
        notes: str | None = None,
        source: str = "scan",
    ) -> None:
        wallet = (wallet or "").strip()
        if not wallet or len(wallet) < 32:
            return
        # skip obvious programs / burn sometimes mis-tagged — keep simple filter
        if wallet in KNOWN_SKIP:
            return
        entry = {
            "wallet": wallet,
            "role": role,
            "risk_score": score,
            "notes": notes or f"{role} on {symbol or mint[:8]} ({incident_type})",
            "source": source,
            "saved": False,
        }
        if not auto_flag:
            # Suggest only — user must Add wallet / CLI add-wallet / import
            flagged.append(entry)
            return
        db.upsert_wallet(
            wallet,
            chain_id=chain_id,
            label=label_hint or role,
            risk_score=score,
            notes=entry["notes"],
            source=source,
            meta={"mint": mint, "role": role, "symbol": symbol},
        )
        db.link_wallet_mint(wallet, mint, role, evidence=notes)
        entry["saved"] = True
        flagged.append(entry)

    # Creator
    creator = pf.get("creator") or rc.get("creator")
    if creator:
        score = config.SCORE_CREATOR_RUG if (rugged or looks_bad) else 45
        _flag(
            str(creator),
            "creator",
            score,
            notes=f"creator · rugcheck_score={rc.get('score')} · {incident_type}",
            source="pumpfun+rugcheck",
        )

    # Rugcheck holders / insiders
    for h in rc.get("holders") or []:
        w = h.get("wallet") or ""
        if h.get("insider"):
            _flag(
                w,
                "insider",
                config.SCORE_INSIDER if not rugged else 70,
                notes="rugcheck insider",
                source="rugcheck",
            )
        else:
            # only flag large holders on rugged mints
            if rugged or looks_bad:
                try:
                    pct = float(h.get("pct") or 0)
                except (TypeError, ValueError):
                    pct = 0.0
                if pct >= 5.0:
                    _flag(
                        w,
                        "large_holder",
                        55 if pct < 15 else 70,
                        notes=f"large holder ~{pct}% on risky mint",
                        source="rugcheck",
                    )

    # Optional Solscan
    sc = solscan.fetch_holders(mint, limit=15)
    report["sources"]["solscan"] = {
        "ok": sc.get("ok"),
        "skipped": sc.get("skipped"),
        "count": len(sc.get("holders") or []),
    }
    if sc.get("ok") and (rugged or looks_bad):
        for h in (sc.get("holders") or [])[:8]:
            _flag(
                h.get("wallet") or "",
                "holder",
                45,
                notes="solscan top holder on risky mint",
                source="solscan",
            )

    # Deep: early signers via Helius/RPC
    if deep and config.solana_rpc_url():
        try:
            early = sol_rpc.earliest_signers(mint, max_sigs=10)
            report["sources"]["rpc_early"] = {"count": len(early)}
            if rugged or looks_bad:
                for e in early:
                    if e.get("error"):
                        report["errors"].append(e["error"])
                        continue
                    role = e.get("role_guess") or "early_signer"
                    score = (
                        config.SCORE_EARLY_DUMPER
                        if role == "fee_payer"
                        else 50
                    )
                    _flag(
                        e.get("wallet") or "",
                        role,
                        score,
                        notes=f"early tx {e.get('signature', '')[:12]}…",
                        source="helius_rpc",
                    )
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"rpc: {exc}")
            report["sources"]["rpc_early"] = {"ok": False, "error": str(exc)}
    elif deep:
        report["sources"]["rpc_early"] = {
            "ok": False,
            "skipped": True,
            "error": "Set HELIUS_API_KEY for early-signer scan",
        }

    db.mark_mint_seen(
        mint,
        chain_id=chain_id,
        symbol=symbol,
        name=name,
        creator=str(creator) if creator else None,
        meta={"incident_type": incident_type},
    )

    report["wallets_flagged"] = flagged
    report["wallets_suggested"] = flagged  # alias
    if not auto_flag and flagged:
        report["note"] = (
            f"Manual-only mode: {len(flagged)} wallet(s) suggested, none auto-saved. "
            "Use Add wallet / python -m rugwatch add-wallet <addr> to store them."
        )
    elif not auto_flag:
        report["note"] = "Manual-only mode: no wallets suggested from this scan."
    report["ok"] = True
    report["stats"] = db.stats()
    return report


# System / known program addresses to ignore as "scammers"
KNOWN_SKIP = {
    "11111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",  # Raydium authority
    "ComputeBudget111111111111111111111111111111",
}
