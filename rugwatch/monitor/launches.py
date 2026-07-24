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
    only_new: bool = True,
    pool_size: int | None = None,
    known_source: str = "local",
) -> dict[str, Any]:
    """
    Single poll of recent launches → match against known wallets → alerts.

    known_source:
      "local" (default) — local multi-DB shards only
      "cloud" — GitHub cloud / RUGWATCH_WALLETS_URL list only
      "both" — union of cloud + local (higher score wins)

    only_new=True (default): only process mints not yet in seen_mints, aiming for
    up to `limit` brand-new launches per click (newest DexScreener first).
    """
    db = db or RugWatchDB()
    src = (known_source or "local").strip().lower()
    if src not in {"cloud", "local", "both"}:
        src = "local"

    known: dict[str, dict[str, Any]] = {}
    cloud_meta: dict[str, Any] = {"ok": False, "source": "none", "count": 0}
    if src in {"cloud", "both"}:
        try:
            from ..cloud_store import load_cloud_wallet_rows

            cloud_meta = load_cloud_wallet_rows(min_score=min_score)
            known.update(cloud_meta.get("wallets") or {})
        except Exception as exc:  # noqa: BLE001
            cloud_meta = {
                "ok": False,
                "source": "error",
                "error": str(exc),
                "count": 0,
                "count_after_score": 0,
            }
    if src in {"local", "both"}:
        local = db.known_wallet_set(min_score=min_score)
        for a, row in local.items():
            if a not in known:
                known[a] = row
            else:
                # keep higher score
                if int(row.get("risk_score") or 0) > int(known[a].get("risk_score") or 0):
                    known[a] = row

    # Cloud-only mode with empty cloud: fail clearly (do not silently use local)
    if src == "cloud" and not known:
        return {
            "ok": False,
            "error": (
                cloud_meta.get("error")
                or "Cloud wallet list empty or unreachable. "
                "Push cloud / set RUGWATCH_WALLETS_URL or GITHUB_TOKEN + repo."
            ),
            "launches_scanned": 0,
            "launches_target": limit,
            "known_wallets": 0,
            "known_source": src,
            "cloud_source": cloud_meta.get("source"),
            "cloud_wallet_count": int(cloud_meta.get("count") or 0),
            "alerts": [],
            "alert_count": 0,
            "found": 0,
            "found_message": "found 0",
            "stats": db.stats(),
        }

    if src == "local" and not known:
        return {
            "ok": False,
            "error": (
                "Local wallet list empty (score≥"
                f"{min_score}). Add wallets or Pull cloud first."
            ),
            "launches_scanned": 0,
            "launches_target": limit,
            "known_wallets": 0,
            "known_source": src,
            "alerts": [],
            "alert_count": 0,
            "found": 0,
            "found_message": "found 0",
            "stats": db.stats(),
        }

    already = db.known_mint_set() if only_new else set()

    # Wider Dex pool so we can fill `limit` never-seen mints when possible
    fetch_n = int(pool_size) if pool_size and pool_size > 0 else max(limit * 4, 100)
    candidates = pumpfun.fetch_recent_launches(limit=fetch_n)

    skipped_seen = 0
    launches: list[dict[str, Any]] = []
    for launch in candidates:
        mint = (launch.get("mint") or "").strip()
        if not mint:
            continue
        if only_new and mint in already:
            skipped_seen += 1
            continue
        launches.append(launch)
        if len(launches) >= limit:
            break

    all_alerts: list[dict[str, Any]] = []
    mints_checked: list[str] = []
    for launch in launches:
        mint = (launch.get("mint") or "").strip()
        if mint:
            mints_checked.append(mint)
        alerts = check_launch_against_db(
            launch, known, db=db, resolve_creator=resolve_creator
        )
        if alerts:
            all_alerts.extend(alerts)

    shortfall = max(0, limit - len(launches)) if only_new else 0
    found = len(all_alerts)
    # Always explicit for website UI: "found 0" or "found N match(es)"
    if found == 0:
        found_message = "found 0"
    elif found == 1:
        found_message = "found 1 match"
    else:
        found_message = f"found {found} matches"

    note_parts: list[str] = [found_message + "."]
    if src == "cloud":
        note_parts.append(
            f"Matched against cloud list ({len(known)} wallet(s) score≥{min_score}, "
            f"source={cloud_meta.get('source')})."
        )
    elif src == "both":
        note_parts.append(
            f"Matched against cloud+local union ({len(known)} wallet(s) score≥{min_score})."
        )
    else:
        note_parts.append(
            f"Matched against local DB ({len(known)} wallet(s) score≥{min_score})."
        )
    if only_new and shortfall > 0:
        note_parts.append(
            f"Only {len(launches)} never-seen mint(s) in the current DexScreener pool "
            f"(wanted {limit}; skipped {skipped_seen} already-seen). "
            f"Try again after the cooldown when more new pairs appear."
        )
    elif only_new:
        note_parts.append(f"Checked {len(launches)} never-seen launch(es) (newest first).")

    return {
        "ok": True,
        "launches_scanned": len(launches),
        "launches_target": limit,
        "launches_new": len(launches) if only_new else None,
        "skipped_already_seen": skipped_seen if only_new else 0,
        "candidates_fetched": len(candidates),
        "only_new": only_new,
        "known_wallets": len(known),
        "known_source": src,
        "cloud_source": cloud_meta.get("source"),
        "cloud_wallet_count": int(
            cloud_meta.get("count_after_score")
            if cloud_meta.get("count_after_score") is not None
            else cloud_meta.get("count")
            or 0
        ),
        "alerts": all_alerts,
        "alert_count": found,
        # Explicit match count for site log / UI
        "found": found,
        "found_message": found_message,
        "mints": mints_checked[:limit],
        "shortfall": shortfall,
        "note": " ".join(note_parts),
        "stats": db.stats(),
    }


def run_monitor_loop(
    *,
    interval: int | None = None,
    min_score: int = 40,
    limit: int = 25,
    only_new: bool = True,
    on_tick: Callable[[dict[str, Any]], None] | None = None,
    max_ticks: int | None = None,
) -> None:
    """Blocking poll loop. Ctrl+C to stop."""
    db = RugWatchDB()
    interval = interval or poll_seconds()
    tick = 0
    print(
        f"RugWatch monitor started · every {interval}s · min_score={min_score} "
        f"· only_new={only_new} · limit={limit}"
    )
    print(f"DB: {db.path}")
    try:
        while True:
            tick += 1
            try:
                result = monitor_once(
                    db,
                    limit=limit,
                    min_score=min_score,
                    resolve_creator=True,
                    only_new=only_new,
                )
            except Exception as exc:  # noqa: BLE001
                result = {"ok": False, "error": str(exc), "alerts": []}
            if on_tick:
                on_tick(result)
            else:
                ac = result.get("alert_count") or len(result.get("alerts") or [])
                print(
                    f"[{tick}] scanned={result.get('launches_scanned')} "
                    f"new_target={result.get('launches_target')} "
                    f"skipped_seen={result.get('skipped_already_seen')} "
                    f"known={result.get('known_wallets')} alerts={ac}"
                )
                if result.get("note"):
                    print(f"  note: {result.get('note')}")
                for a in result.get("alerts") or []:
                    print("  ALERT:", a.get("message"))
            if max_ticks is not None and tick >= max_ticks:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
