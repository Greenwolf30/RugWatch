"""Watch new pump.fun / Solana launches for known bad wallets."""

from __future__ import annotations

import time
from typing import Any, Callable

from ..alerts import emit_alert
from ..config import poll_seconds
from ..db import RugWatchDB
from ..sources import pumpfun, rugcheck


def check_launch_against_db(
    launch: dict[str, Any],
    known: dict[str, dict[str, Any]],
    *,
    db: RugWatchDB,
    resolve_creator: bool = True,
) -> list[dict[str, Any]]:
    """
    Compare launch creator (and optional rugcheck creator) to known wallets.
    Returns list of alert dicts fired.
    """
    mint = (launch.get("mint") or "").strip()
    if not mint:
        return []

    symbol = launch.get("symbol") or ""
    name = launch.get("name") or ""
    is_new = db.mark_mint_seen(
        mint,
        symbol=symbol,
        name=name,
        creator=launch.get("creator"),
        meta={"source": launch.get("source")},
    )

    candidates: list[tuple[str, str]] = []  # wallet, role

    # Creator from launch payload if present
    if launch.get("creator"):
        candidates.append((str(launch["creator"]), "creator"))

    if resolve_creator:
        pf = pumpfun.fetch_coin_meta(mint)
        if pf.get("creator"):
            candidates.append((str(pf["creator"]), "creator"))
            db.mark_mint_seen(mint, symbol=symbol, name=name, creator=str(pf["creator"]))

        # Light rugcheck for creator only on *new* mints (saves rate limit)
        if is_new:
            try:
                rc = rugcheck.fetch_report(mint)
                if rc.get("creator"):
                    candidates.append((str(rc["creator"]), "creator"))
                for h in (rc.get("holders") or [])[:5]:
                    if h.get("insider") and h.get("wallet"):
                        candidates.append((str(h["wallet"]), "insider"))
            except Exception:  # noqa: BLE001
                pass

    alerts: list[dict[str, Any]] = []
    seen_w: set[str] = set()
    for wallet, role in candidates:
        wallet = wallet.strip()
        if not wallet or wallet in seen_w:
            continue
        seen_w.add(wallet)
        hit = known.get(wallet)
        if not hit:
            continue
        score = int(hit.get("risk_score") or 0)
        token_lab = f"${symbol}" if symbol else (name or mint)
        msg = (
            f"SERIAL WATCH HIT: known wallet ({role}) on new launch "
            f"{token_lab} — prior score {score}, "
            f"label={hit.get('label') or 'n/a'}, times_seen={hit.get('times_seen')}. "
            f"Full mint: {mint}. "
            f"Solscan: https://solscan.io/token/{mint} · "
            f"Dex: https://dexscreener.com/solana/{mint}"
        )
        alert = emit_alert(
            db,
            wallet=wallet,
            mint=mint,
            message=msg,
            role=role,
            risk_score=score,
            symbol=symbol or None,
            name=name or None,
        )
        # bump wallet activity
        db.upsert_wallet(
            wallet,
            risk_score=score,
            notes=f"seen on new launch {token_lab} mint={mint}",
            source="monitor",
            label=hit.get("label") or "serial_suspect",
        )
        db.link_wallet_mint(wallet, mint, f"watch_{role}", evidence=msg)
        alerts.append(alert)

    return alerts


def monitor_once(
    db: RugWatchDB | None = None,
    *,
    limit: int = 25,
    min_score: int = 40,
    resolve_creator: bool = True,
) -> dict[str, Any]:
    """Single poll of recent launches → check DB → alerts."""
    db = db or RugWatchDB()
    known = db.known_wallet_set(min_score=min_score)
    launches = pumpfun.fetch_recent_launches(limit=limit)

    all_alerts: list[dict[str, Any]] = []
    for launch in launches:
        alerts = check_launch_against_db(
            launch, known, db=db, resolve_creator=resolve_creator
        )
        if alerts:
            all_alerts.extend(alerts)

    return {
        "ok": True,
        "launches_scanned": len(launches),
        "known_wallets": len(known),
        "alerts": all_alerts,
        "alert_count": len(all_alerts),
        "stats": db.stats(),
    }


def run_monitor_loop(
    *,
    interval: int | None = None,
    min_score: int = 40,
    limit: int = 25,
    on_tick: Callable[[dict[str, Any]], None] | None = None,
    max_ticks: int | None = None,
) -> None:
    """Blocking poll loop. Ctrl+C to stop."""
    db = RugWatchDB()
    interval = interval or poll_seconds()
    tick = 0
    print(f"RugWatch monitor started · every {interval}s · min_score={min_score}")
    print(f"DB: {db.path}")
    try:
        while True:
            tick += 1
            try:
                result = monitor_once(
                    db, limit=limit, min_score=min_score, resolve_creator=True
                )
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc), "alerts": []}
            if on_tick:
                on_tick(result)
            else:
                ac = result.get("alert_count") or len(result.get("alerts") or [])
                print(
                    f"[{tick}] scanned={result.get('launches_scanned')} "
                    f"known={result.get('known_wallets')} alerts={ac}"
                )
                for a in result.get("alerts") or []:
                    print("  ALERT:", a.get("message"))
            if max_ticks is not None and tick >= max_ticks:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
