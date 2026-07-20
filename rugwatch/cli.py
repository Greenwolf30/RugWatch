"""RugWatch command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __app_name__, __version__
from .alerts import format_alert
from .config import load_dotenv
from .db import RugWatchDB
from .ingest.scan_mint import scan_and_ingest_mint
from .monitor.launches import monitor_once, run_monitor_loop


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(
        prog="rugwatch",
        description="RugWatch — serial rugger wallet DB + Solana launch monitor",
    )
    p.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create / migrate the SQLite database")

    s = sub.add_parser("stats", help="Show DB counts")
    s.add_argument("--json", action="store_true")

    a = sub.add_parser("add-wallet", help="Manually flag a wallet")
    a.add_argument("address")
    a.add_argument("--score", type=int, default=70)
    a.add_argument("--label", default="manual")
    a.add_argument("--notes", default="")
    a.add_argument("--chain", default="solana")

    l = sub.add_parser("list-wallets", help="List flagged wallets")
    l.add_argument("--min-score", type=int, default=0)
    l.add_argument("--limit", type=int, default=50)
    l.add_argument("--json", action="store_true")

    sc = sub.add_parser(
        "scan",
        help="Scan a mint (manual-only by default: suggests wallets, does not auto-save)",
    )
    sc.add_argument("mint", help="Token mint address")
    sc.add_argument("--no-deep", action="store_true", help="Skip Helius early-signer fan-out")
    sc.add_argument("--label", default=None)
    sc.add_argument("--json", action="store_true")
    sc.add_argument(
        "--auto-flag",
        action="store_true",
        help="Override: save suggested wallets (or set RUGWATCH_AUTO_FLAG=1)",
    )

    m = sub.add_parser("monitor", help="Poll new pump launches for known wallets")
    m.add_argument("--once", action="store_true", help="Single poll then exit")
    m.add_argument("--interval", type=int, default=None, help="Seconds between polls")
    m.add_argument("--min-score", type=int, default=40)
    m.add_argument("--limit", type=int, default=25)
    m.add_argument("--ticks", type=int, default=None, help="Stop after N polls")

    al = sub.add_parser("alerts", help="Show recent alerts")
    al.add_argument("--limit", type=int, default=30)
    al.add_argument("--unacked", action="store_true")
    al.add_argument("--json", action="store_true")

    cl = sub.add_parser("clear-db", help="Delete ALL wallets / incidents / alerts from local DB")
    cl.add_argument("--yes", action="store_true", help="Required confirmation flag")

    ex = sub.add_parser("export-wallets", help="Export wallets to JSON (for Gist / cloud)")
    ex.add_argument("-o", "--output", default="wallets_export.json")
    ex.add_argument("--min-score", type=int, default=0)

    im = sub.add_parser("import-wallets", help="Import wallets from a local JSON file")
    im.add_argument("path", help="Path to wallets JSON")

    pu = sub.add_parser(
        "pull-remote",
        help="Download wallets from RUGWATCH_WALLETS_URL or --url (manual list merge)",
    )
    pu.add_argument("--url", default=None, help="Override RUGWATCH_WALLETS_URL")

    sub.add_parser(
        "push-cloud",
        help="Upload wallet list to GitHub repo / Gist cloud (needs GITHUB_TOKEN)",
    )
    sub.add_parser(
        "pull-cloud",
        help="Download wallet list from GitHub Gist / RUGWATCH_WALLETS_URL into local DB",
    )
    sub.add_parser("cloud-status", help="Show cloud (Gist) configuration status")
    sub.add_parser(
        "cloud-init",
        help="Pull cloud into local cache (or create Gist) — use after setting GITHUB_TOKEN",
    )

    args = p.parse_args(argv)
    db = RugWatchDB()

    if args.cmd == "init-db":
        print(f"OK · database ready at {db.path}")
        print(json.dumps(db.stats(), indent=2))
        return 0

    if args.cmd == "stats":
        st = db.stats()
        if args.json:
            print(json.dumps(st, indent=2))
        else:
            print(f"wallets (in DB now):     {st.get('wallets_logged', st.get('wallets'))}")
            print(f"wallets logged lifetime: {st.get('wallets_logged_lifetime')}")
            print(f"high_risk_wallets:       {st.get('high_risk_wallets')}")
            print(f"incidents:               {st.get('incidents')}")
            print(f"links:                   {st.get('links')}")
            print(f"seen_mints:              {st.get('seen_mints')}")
            print(f"alerts:                  {st.get('alerts')}")
            print(f"unacked_alerts:          {st.get('unacked_alerts')}")
            print(f"db_path:                 {st.get('db_path')}")
        return 0

    if args.cmd == "add-wallet":
        db.upsert_wallet(
            args.address,
            chain_id=args.chain,
            label=args.label,
            risk_score=args.score,
            notes=args.notes or "manual add",
            source="manual",
        )
        w = db.get_wallet(args.address)
        print(json.dumps(w, indent=2, default=str))
        try:
            from .cloud_store import sync_after_manual_change

            sync = sync_after_manual_change(db)
            if sync:
                print("Cloud sync:", json.dumps(sync, indent=2, default=str))
        except Exception as exc:  # noqa: BLE001
            print(f"Cloud sync skipped: {exc}")
        return 0

    if args.cmd == "list-wallets":
        rows = db.list_wallets(min_score=args.min_score, limit=args.limit)
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
            return 0
        if not rows:
            print("No wallets yet. Add manually: python -m rugwatch add-wallet <ADDR>")
            return 0
        for w in rows:
            print(
                f"{w.get('risk_score'):3}  times={w.get('times_seen')}  "
                f"{w.get('address')}  [{w.get('label') or ''}]  "
                f"{(w.get('notes') or '')[:60]}"
            )
        return 0

    if args.cmd == "clear-db":
        if not args.yes:
            print("Refusing: re-run with --yes to wipe ALL wallets/incidents/alerts.")
            return 2
        cleared = db.clear_all()
        print("Database cleared.")
        print(json.dumps(cleared, indent=2))
        print(f"DB path: {db.path}")
        return 0

    if args.cmd == "export-wallets":
        from .remote_wallets import export_wallets_to_file

        r = export_wallets_to_file(args.output, db, min_score=args.min_score)
        print(json.dumps(r, indent=2))
        return 0

    if args.cmd == "import-wallets":
        from .remote_wallets import import_wallets_from_file

        r = import_wallets_from_file(args.path, db)
        print(json.dumps(r, indent=2))
        return 0

    if args.cmd == "pull-remote":
        from .remote_wallets import pull_remote_into_db

        r = pull_remote_into_db(db, url=args.url)
        print(json.dumps(r, indent=2))
        return 0 if r.get("ok") else 1

    if args.cmd == "push-cloud":
        from .cloud_store import push_to_cloud

        try:
            r = push_to_cloud(db)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1
        print(json.dumps(r, indent=2, default=str))
        return 0 if r.get("ok") else 1

    if args.cmd == "pull-cloud":
        from .cloud_store import pull_from_cloud

        try:
            r = pull_from_cloud(db)
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
            return 1
        print(json.dumps(r, indent=2, default=str))
        return 0 if r.get("ok") else 1

    if args.cmd == "cloud-status":
        from .cloud_store import cloud_status

        print(json.dumps(cloud_status(), indent=2, default=str))
        return 0

    if args.cmd == "cloud-init":
        from .cloud_store import ensure_cloud_cache

        r = ensure_cloud_cache(db)
        print(json.dumps(r, indent=2, default=str))
        return 0 if r.get("ok") or r.get("skipped") else 1

    if args.cmd == "scan":
        if getattr(args, "auto_flag", False):
            import os

            os.environ["RUGWATCH_AUTO_FLAG"] = "1"
        result = scan_and_ingest_mint(
            args.mint,
            db=db,
            deep=not args.no_deep,
            label_hint=args.label,
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
            return 0 if result.get("ok") else 1
        print(f"Mint: {result.get('mint')}")
        print(f"Symbol: {result.get('symbol')}  type={result.get('incident_type')}")
        print(f"Incident id: {result.get('incident_id')}")
        mode = "AUTO-SAVE" if result.get("auto_flag") else "MANUAL-ONLY (not saved)"
        print(f"Mode: {mode}")
        print(f"Wallets suggested: {len(result.get('wallets_flagged') or [])}")
        for f in result.get("wallets_flagged") or []:
            saved = "saved" if f.get("saved") else "suggest"
            print(
                f"  · [{saved}] {f.get('role'):12} score={f.get('risk_score')}  {f.get('wallet')}"
            )
        if result.get("note"):
            print(f"Note: {result.get('note')}")
        if result.get("errors"):
            print("Errors:")
            for e in result["errors"]:
                print(f"  ! {e}")
        print("Sources:", json.dumps(result.get("sources"), indent=2, default=str))
        print("Stats:", result.get("stats"))
        return 0 if result.get("ok") else 1

    if args.cmd == "monitor":
        if args.once:
            result = monitor_once(db, limit=args.limit, min_score=args.min_score)
            print(json.dumps(_public_monitor(result), indent=2, default=str))
            for a in result.get("alerts") or []:
                print("ALERT:", a.get("message"))
            return 0
        run_monitor_loop(
            interval=args.interval,
            min_score=args.min_score,
            limit=args.limit,
            max_ticks=args.ticks,
        )
        return 0

    if args.cmd == "alerts":
        rows = db.list_alerts(limit=args.limit, unacked_only=args.unacked)
        if args.json:
            print(json.dumps(rows, indent=2, default=str))
            return 0
        if not rows:
            print("No alerts yet.")
            return 0
        for a in rows:
            print(format_alert(a))
        return 0

    p.error(f"Unknown command {args.cmd}")
    return 2


def _public_monitor(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": result.get("ok"),
        "launches_scanned": result.get("launches_scanned"),
        "known_wallets": result.get("known_wallets"),
        "alert_count": result.get("alert_count"),
        "alerts": result.get("alerts"),
        "stats": result.get("stats"),
        "error": result.get("error"),
    }


if __name__ == "__main__":
    sys.exit(main())
