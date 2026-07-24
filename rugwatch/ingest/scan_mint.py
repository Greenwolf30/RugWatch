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

    # ── Cloud list matches on this mint (full list + count) ───────────
    # Match every holder/creator we can see against the GitHub cloud list.
    # Always report count (including 0) and the complete matched address list.
    cloud_matches: list[dict[str, Any]] = []
    cloud_checked = False
    cloud_set: set[str] = set()
    try:
        from ..cloud_store import fetch_cloud_address_set

        raw_cloud = fetch_cloud_address_set() or set()
        # Normalize case for Solana base58 (usually mixed; compare exact + as stored)
        cloud_set = {str(a).strip() for a in raw_cloud if a and str(a).strip()}
        cloud_checked = True
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"cloud_match: {exc}")
        cloud_set = set()
        try:
            for row in db.list_wallets(min_score=0, limit=200_000) or []:
                a = (row.get("address") or row.get("wallet") or "").strip()
                if a:
                    cloud_set.add(a)
            if cloud_set:
                cloud_checked = True
        except Exception:  # noqa: BLE001
            pass

    # Build cloud lookup that is case-sensitive first (Solana addresses are case-sensitive)
    cloud_lookup = set(cloud_set)

    seen_on_mint: dict[str, str] = {}  # addr → role/source hint
    if creator:
        c = str(creator).strip()
        if c:
            seen_on_mint[c] = "creator"
    for h in rc.get("holders") or []:
        wa = (h.get("wallet") or h.get("address") or "").strip()
        if not wa or len(wa) < 32:
            continue
        role = "insider" if h.get("insider") else "holder"
        seen_on_mint.setdefault(wa, role)
    # Solscan: pull more holders when possible
    sc_full = solscan.fetch_holders(mint, limit=50)
    if sc_full.get("ok"):
        report["sources"]["solscan_cloud_match"] = {
            "ok": True,
            "count": len(sc_full.get("holders") or []),
        }
        for h in sc_full.get("holders") or []:
            wa = (h.get("wallet") or h.get("address") or "").strip()
            if wa and len(wa) >= 32:
                seen_on_mint.setdefault(wa, "holder")
    if sc.get("ok"):
        for h in sc.get("holders") or []:
            wa = (h.get("wallet") or h.get("address") or "").strip()
            if wa and len(wa) >= 32:
                seen_on_mint.setdefault(wa, "holder")
    # RPC top holders (up to 20 largest token accounts)
    if config.solana_rpc_url():
        try:
            rpc_holders = sol_rpc.top_holders(mint, limit=20)
            report["sources"]["rpc_holders"] = {"count": len(rpc_holders)}
            for h in rpc_holders:
                wa = (h.get("wallet") or h.get("owner") or "").strip()
                if wa and len(wa) >= 32:
                    seen_on_mint.setdefault(wa, "holder")
        except Exception as exc:  # noqa: BLE001
            report["sources"]["rpc_holders"] = {"ok": False, "error": str(exc)}
    for f in flagged:
        wa = (f.get("wallet") or "").strip()
        if wa:
            seen_on_mint.setdefault(wa, f.get("role") or "scan")

    # Local DB rows already linked to this mint (from prior imports / pulls)
    try:
        if hasattr(db, "wallets_for_mint"):
            for row in db.wallets_for_mint(mint) or []:
                wa = (row.get("address") or row.get("wallet") or "").strip()
                if wa:
                    seen_on_mint.setdefault(wa, row.get("role") or "linked")
    except Exception:  # noqa: BLE001
        pass

    # ── Local DB: load full wallet index for matching ─────────────────
    db_by_addr: dict[str, dict[str, Any]] = {}
    try:
        for row in db.list_wallets(min_score=0, limit=500_000) or []:
            a = (row.get("address") or row.get("wallet") or "").strip()
            if a:
                db_by_addr[a] = dict(row)
    except Exception as exc:  # noqa: BLE001
        report["errors"].append(f"db_match_load: {exc}")

    db_matches: list[dict[str, Any]] = []
    cloud_matches = []  # reset if any prior; rebuild below

    for wa, role in sorted(seen_on_mint.items(), key=lambda x: x[0]):
        if wa in KNOWN_SKIP:
            continue
        row = db_by_addr.get(wa)
        on_cloud = wa in cloud_lookup
        in_db = row is not None or (
            hasattr(db, "wallet_exists") and bool(db.wallet_exists(wa))
        )
        if not in_db and not on_cloud:
            continue
        label = (row or {}).get("label") if row else None
        risk = (row or {}).get("risk_score") if row else None
        notes = (row or {}).get("notes") if row else None
        if row is None and in_db:
            try:
                row = db.get_wallet(wa) if hasattr(db, "get_wallet") else None
                if row:
                    label = row.get("label")
                    risk = row.get("risk_score")
                    notes = row.get("notes")
            except Exception:  # noqa: BLE001
                pass
        entry = {
            "wallet": wa,
            "address": wa,
            "role": role,
            "label": label,
            "risk_score": risk,
            "notes": (str(notes)[:200] if notes else None),
            "on_cloud": on_cloud,
            "in_local_db": bool(in_db),
        }
        if in_db:
            db_matches.append(entry)
        if on_cloud:
            cloud_matches.append({**entry, "on_cloud": True})

    n_db = len(db_matches)
    db_addrs = [m["wallet"] for m in db_matches if m.get("wallet")]
    report["db_wallets_found"] = n_db
    report["db_wallets_count"] = n_db
    report["db_wallets"] = db_matches  # full local DB match list
    report["db_wallets_list"] = db_addrs
    report["db_wallets_text"] = "\n".join(db_addrs)
    report["db_list_size"] = len(db_by_addr)
    if n_db == 0:
        report["db_found_message"] = "0 wallets found from DB"
    else:
        report["db_found_message"] = (
            f"{n_db} wallet{'s' if n_db != 1 else ''} found from DB"
        )

    n_cloud = len(cloud_matches)
    addrs_only = [m["wallet"] for m in cloud_matches if m.get("wallet")]
    report["cloud_wallets_found"] = n_cloud
    report["cloud_wallets_count"] = n_cloud  # alias
    report["cloud_wallets"] = cloud_matches  # full list of match objects
    report["cloud_wallets_list"] = addrs_only  # plain address array
    report["cloud_wallets_text"] = "\n".join(addrs_only)  # pasteable full list
    report["cloud_checked"] = cloud_checked
    report["cloud_list_size"] = len(cloud_set)
    report["holders_checked"] = len(seen_on_mint)
    if n_cloud == 0:
        report["cloud_found_message"] = "0 wallets found from cloud"
    else:
        report["cloud_found_message"] = (
            f"{n_cloud} wallet{'s' if n_cloud != 1 else ''} found from cloud"
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
    # Always include DB + cloud lines in note
    report["note"] = (
        ((report.get("note") or "").rstrip() + " · " if report.get("note") else "")
        + report["db_found_message"]
        + " · "
        + report["cloud_found_message"]
    )
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
