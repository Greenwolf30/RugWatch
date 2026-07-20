"""
RugWatch website backend.

Serves the web UI and a private API. Provider keys (Helius, etc.) load only
from server-side .env and are never sent to the browser.

  GET  /                 web UI
  GET  /health
  GET  /api/health
  GET  /api/stats
  GET  /api/wallets
  GET  /api/alerts
  POST /api/wallets      JSON: {"address","score"?,"label"?,"notes"?}
  POST /api/upload       JSON: {"text": "..."} or {"wallets":[...]}  (import)
  POST /api/scan         JSON: {"mint":"...","deep":true?}
  POST /api/monitor      JSON: {} optional
  POST /api/push-cloud   JSON: {}
  POST /api/pull-cloud   JSON: {}
  POST /api/clear-db     JSON: {"confirm": true}

Optional gate: set WEB_API_TOKEN in .env → require header X-API-Token.

Run:
  python run_web.py
  # or: python web_server.py --host 127.0.0.1 --port 8787
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rugwatch import __app_name__, __version__  # noqa: E402
from rugwatch.config import load_dotenv  # noqa: E402
from rugwatch.db import RugWatchDB  # noqa: E402

WEB_DIR = ROOT / "web"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}

_SECRET_KEY_NAMES = re.compile(
    r"(?i)^(api[_-]?key|apikey|secret|password|token|authorization|bearer|"
    r"helius_api_key|birdeye_api_key|solscan_api_key|github_token|"
    r"rpc_url|solana_rpc_url|web_api_token)$"
)


def _web_api_token() -> str | None:
    load_dotenv()
    t = (os.environ.get("WEB_API_TOKEN") or "").strip()
    return t or None


def _cors_allowed_origins() -> list[str] | None:
    load_dotenv()
    raw = (os.environ.get("WEB_CORS_ORIGINS") or "").strip()
    if not raw or raw == "*":
        return None
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def redact_text(text: str) -> str:
    """Strip secrets from any string that might reach the browser."""
    if not text:
        return text
    out = str(text)
    out = re.sub(
        r"(?i)(api[_-]?key|access[_-]?token|bearer|authorization|github_token|"
        r"helius_api_key|web_api_token)\s*[=:]\s*[^\s&,;\"']+",
        r"\1=[REDACTED]",
        out,
    )
    out = re.sub(r"(?i)helius-rpc\.com/\?api-key=[^\s\"']+", "[REDACTED_RPC]", out)
    # GitHub PATs and similar opaque secrets
    out = re.sub(r"\bghp_[A-Za-z0-9_]{20,}\b", "[REDACTED_GITHUB_TOKEN]", out)
    out = re.sub(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "[REDACTED_GITHUB_TOKEN]", out)
    out = re.sub(r"\bgho_[A-Za-z0-9_]{20,}\b", "[REDACTED_GITHUB_TOKEN]", out)
    out = re.sub(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "[REDACTED]", out)
    # Long hex-ish keys (best-effort)
    out = re.sub(r"\b[A-Fa-f0-9]{32,}\b", "[REDACTED_HEX]", out)
    return out


def sanitize_public(obj: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            ks = str(k)
            if _SECRET_KEY_NAMES.match(ks):
                continue
            if ks.lower() in {
                "rpc_url",
                "endpoint",
                "raw",
                "request_url",
                "db_path",
                "local_path",
                "local_cache",
                "content",  # base64 file blobs from GitHub
                "headers",
            }:
                continue
            out[ks] = sanitize_public(v, depth=depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [sanitize_public(x, depth=depth + 1) for x in obj[:500]]
    return redact_text(str(obj))


def provider_status() -> dict[str, Any]:
    """Which providers are configured — boolean only, never key values."""
    load_dotenv()
    keys = {
        "helius": bool((os.environ.get("HELIUS_API_KEY") or "").strip()),
        "solscan": bool((os.environ.get("SOLSCAN_API_KEY") or "").strip()),
        "birdeye": bool((os.environ.get("BIRDEYE_API_KEY") or "").strip()),
        "github_cloud": bool(
            (os.environ.get("GITHUB_TOKEN") or os.environ.get("RUGWATCH_GITHUB_TOKEN") or "").strip()
        ),
    }
    return {
        "providers_configured": keys,  # true/false only
        "any_provider": any(keys.values()),
        "site_token_required": bool(_web_api_token()),
        "security": {
            "keys_in_browser": False,
            "keys_location": "server .env only",
            "note": "Never put HELIUS/GITHUB tokens in web/config.js",
        },
    }


def public_wallet_row(
    w: dict[str, Any], *, mint: str | None = None
) -> dict[str, Any]:
    notes = (w.get("notes") or "")[:500]
    mint_out = (mint or "").strip() or None
    if not mint_out:
        mint_out = RugWatchDB.mint_from_notes(notes)
    return {
        "address": w.get("address"),
        "mint": mint_out,
        "chain_id": w.get("chain_id") or "solana",
        "label": w.get("label"),
        "risk_score": int(w.get("risk_score") or 0),
        "times_seen": int(w.get("times_seen") or 0),
        "notes": notes,
        "source": w.get("source"),
        "first_seen_at": w.get("first_seen_at"),
        "last_seen_at": w.get("last_seen_at"),
    }


def public_alert_row(a: dict[str, Any]) -> dict[str, Any]:
    mint = (a.get("mint") or "").strip()
    wallet = (a.get("wallet") or "").strip()
    return {
        "id": a.get("id"),
        "wallet": wallet,
        "mint": mint,
        "role": a.get("role"),
        "risk_score": a.get("risk_score"),
        "message": redact_text(str(a.get("message") or ""))[:2000],
        "created_at": a.get("created_at"),
        "acked": bool(a.get("acked")),
        # Full links for UI (no secrets)
        "solscan_token": f"https://solscan.io/token/{mint}" if mint else "",
        "solscan_wallet": f"https://solscan.io/account/{wallet}" if wallet else "",
        "dexscreener": f"https://dexscreener.com/solana/{mint}" if mint else "",
    }


class RugWatchHandler(BaseHTTPRequestHandler):
    server_version = f"RugWatchWeb/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin") or ""
        allowed = _cors_allowed_origins()
        if allowed is None:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
        elif origin.rstrip("/") in allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        raw = json.dumps(sanitize_public(obj), ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        self._send(code, raw, "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _check_token(self) -> bool:
        need = _web_api_token()
        if not need:
            return True
        got = (self.headers.get("X-API-Token") or "").strip()
        return got == need

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(204, b"", "text/plain")

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._handle_get()
        except Exception as exc:  # noqa: BLE001
            self._json(
                500,
                {"ok": False, "error": redact_text(str(exc)), "trace": False},
            )

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._handle_post()
        except Exception as exc:  # noqa: BLE001
            self._json(
                500,
                {
                    "ok": False,
                    "error": redact_text(str(exc)),
                    "detail": redact_text(traceback.format_exc()[-800:]),
                },
            )

    def _handle_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path in ("/health", "/api/health"):
            st = provider_status()
            self._json(
                200,
                {
                    "ok": True,
                    "app": __app_name__,
                    "version": __version__,
                    **st,
                    "note": "Provider keys never appear in API responses.",
                },
            )
            return

        if path == "/api/stats":
            db = RugWatchDB()
            stats = dict(db.stats())
            # Attach cloud wallet count (read-only; no secrets)
            try:
                from rugwatch.cloud_store import fetch_cloud_wallet_count

                cloud = fetch_cloud_wallet_count()
                stats["cloud_wallets"] = cloud.get("count")
                stats["cloud_ok"] = bool(cloud.get("ok"))
                stats["cloud_error"] = cloud.get("error")
                stats["cloud_shards"] = cloud.get("cloud_shards")
            except Exception as exc:  # noqa: BLE001
                stats["cloud_wallets"] = None
                stats["cloud_ok"] = False
                stats["cloud_error"] = str(exc)
                stats["cloud_shards"] = None
            self._json(200, {"ok": True, "stats": sanitize_public(stats)})
            return

        if path == "/api/cloud-count":
            from rugwatch.cloud_store import fetch_cloud_wallet_count

            self._json(200, sanitize_public(fetch_cloud_wallet_count()))
            return

        if path == "/api/wallets":
            qs = parse_qs(parsed.query)
            try:
                min_score = int((qs.get("min_score") or ["0"])[0])
            except ValueError:
                min_score = 0
            try:
                limit = min(500, int((qs.get("limit") or ["100"])[0]))
            except ValueError:
                limit = 100
            db = RugWatchDB()
            rows = db.list_wallets(min_score=min_score, limit=limit)
            mint_map = db.wallet_mint_map()
            wallets_out = []
            for w in rows:
                d = dict(w)
                addr = (d.get("address") or "").strip()
                wallets_out.append(
                    public_wallet_row(d, mint=mint_map.get(addr))
                )
            self._json(
                200,
                {
                    "ok": True,
                    "count": len(wallets_out),
                    "wallets": wallets_out,
                },
            )
            return

        if path == "/api/alerts":
            qs = parse_qs(parsed.query)
            try:
                limit = min(200, int((qs.get("limit") or ["50"])[0]))
            except ValueError:
                limit = 50
            db = RugWatchDB()
            rows = db.list_alerts(limit=limit)
            self._json(
                200,
                {
                    "ok": True,
                    "count": len(rows),
                    "alerts": [public_alert_row(dict(a)) for a in rows],
                },
            )
            return

        # Static files from web/ ONLY — never project root (.env, db, secrets)
        if path == "/":
            path = "/index.html"
        rel = path.lstrip("/").replace("\\", "/")
        # Block sensitive names even if someone put them under web/
        base_name = Path(rel).name.lower()
        if base_name in {
            ".env",
            ".env.local",
            ".env.example",
            "rugwatch.db",
            "wallets_cloud.json",
            "wallets_export.json",
        } or base_name.endswith(".db") or base_name.endswith(".pem"):
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        if ".." in rel or rel.startswith("/") or rel.startswith("~"):
            self._json(400, {"ok": False, "error": "bad path"})
            return
        fpath = (WEB_DIR / rel).resolve()
        try:
            fpath.relative_to(WEB_DIR.resolve())
        except ValueError:
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        if not fpath.is_file():
            self._json(404, {"ok": False, "error": "not found"})
            return
        data = fpath.read_bytes()
        ctype = STATIC_TYPES.get(fpath.suffix.lower(), "application/octet-stream")
        self._send(200, data, ctype)

    def _handle_post(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if not self._check_token():
            self._json(
                401,
                {
                    "ok": False,
                    "error": "Unauthorized. Set header X-API-Token to match WEB_API_TOKEN.",
                },
            )
            return

        body = self._read_json()
        db = RugWatchDB()

        if path == "/api/wallets":
            addr = (body.get("address") or body.get("wallet") or "").strip()
            if not addr or len(addr) < 32:
                self._json(400, {"ok": False, "error": "address required"})
                return
            try:
                score = int(body.get("score") if body.get("score") is not None else body.get("risk_score") or 75)
            except (TypeError, ValueError):
                score = 75
            label = str(body.get("label") or "manual")
            notes = str(body.get("notes") or "web add")
            db.upsert_wallet(
                addr,
                label=label,
                risk_score=score,
                notes=notes,
                source="web_manual",
            )
            self._json(200, {"ok": True, "address": addr, "risk_score": score})
            return

        if path == "/api/upload":
            from rugwatch.remote_wallets import import_wallets_from_text, parse_wallet_payload

            items: list = []
            if isinstance(body.get("wallets"), list):
                items = parse_wallet_payload(body.get("wallets"))
            text = body.get("text") or body.get("raw") or ""
            if not items and text:
                r = import_wallets_from_text(str(text), db, source_default="web_upload")
                self._json(200 if r.get("ok") else 400, r)
                return
            if not items and isinstance(body.get("format"), str):
                # Full rugwatch_wallets_v1 body
                items = parse_wallet_payload(body)
            if not items:
                self._json(400, {"ok": False, "error": "No wallets found", "imported": 0})
                return
            src = str(body.get("source") or "web_upload")
            stats = db.import_wallets(items, source_default=src)
            out: dict[str, Any] = {"ok": True, **stats, "db_wallets": db.stats().get("wallets")}
            # ATC Ruggers "Upload" sends push_cloud=true to grow the GitHub cloud list
            push_flag = body.get("push_cloud")
            if push_flag is True or str(push_flag).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }:
                try:
                    from rugwatch.cloud_store import push_to_cloud

                    pr = push_to_cloud(db)
                    out["cloud"] = {
                        "ok": bool(pr.get("ok")),
                        "wallet_count": pr.get("wallet_count"),
                        "cloud_shards": pr.get("cloud_shards"),
                        "path": pr.get("path"),
                        "index_path": pr.get("index_path"),
                        "error": pr.get("error"),
                        "note": pr.get("note"),
                    }
                    if not pr.get("ok"):
                        out["cloud_error"] = pr.get("error")
                except Exception as exc:  # noqa: BLE001
                    out["cloud"] = {"ok": False, "error": str(exc)}
            self._json(200, out)
            return

        if path == "/api/scan":
            mint = (body.get("mint") or body.get("address") or "").strip()
            if not mint:
                self._json(400, {"ok": False, "error": "mint required"})
                return
            deep = bool(body.get("deep", True))
            from rugwatch.ingest.scan_mint import scan_and_ingest_mint

            result = scan_and_ingest_mint(mint, db=db, deep=deep)
            # Strip anything sensitive
            safe = {
                "ok": True,
                "mint": result.get("mint") or mint,
                "symbol": result.get("symbol"),
                "name": result.get("name"),
                "incident_type": result.get("incident_type"),
                "auto_flag": result.get("auto_flag"),
                "note": result.get("note"),
                "wallets_flagged": sanitize_public(result.get("wallets_flagged") or []),
                "errors": sanitize_public(result.get("errors") or []),
            }
            self._json(200, safe)
            return

        if path == "/api/monitor":
            from rugwatch.monitor.launches import monitor_once

            result = monitor_once(db, limit=int(body.get("limit") or 25), min_score=int(body.get("min_score") or 40))
            safe = {
                "ok": True,
                "launches_scanned": result.get("launches_scanned"),
                "known_wallets": result.get("known_wallets"),
                "alert_count": result.get("alert_count"),
                "alerts": sanitize_public(result.get("alerts") or [])[:50],
            }
            self._json(200, safe)
            return

        if path == "/api/push-cloud":
            from rugwatch.cloud_store import push_to_cloud

            result = push_to_cloud(db)
            # Never return tokens or raw file content — booleans + counts only
            err = result.get("error")
            safe = {
                "ok": bool(result.get("ok")),
                "action": result.get("action"),
                "mode": result.get("mode"),
                "wallet_count": result.get("wallet_count"),
                "cloud_shards": result.get("cloud_shards"),
                "index_path": result.get("index_path"),
                "path": result.get("path"),  # repo-relative path, not a secret
                "repo": result.get("repo"),
                "html_url": result.get("html_url"),
                "error": redact_text(str(err)) if err else None,
                "note": result.get("note"),
            }
            self._json(200 if safe["ok"] else 400, sanitize_public(safe))
            return

        if path == "/api/pull-cloud":
            from rugwatch.cloud_store import pull_from_cloud

            result = pull_from_cloud(db)
            err = result.get("error")
            safe = {
                "ok": bool(result.get("ok")),
                "imported": result.get("imported"),
                "skipped": result.get("skipped"),
                "db_wallets": result.get("db_wallets"),
                "source": result.get("source") or result.get("mode"),
                "error": redact_text(str(err)) if err else None,
                "note": result.get("note"),
            }
            self._json(200 if safe["ok"] else 400, sanitize_public(safe))
            return

        if path in ("/api/clear-db", "/api/clear_db"):
            if not body.get("confirm") and body.get("confirm") is not True:
                # also accept confirm: "yes"
                if str(body.get("confirm") or "").strip().lower() not in {"1", "true", "yes"}:
                    self._json(
                        400,
                        {
                            "ok": False,
                            "error": 'Send JSON {"confirm": true} to wipe the local database.',
                        },
                    )
                    return
            cleared = db.clear_all()
            self._json(
                200,
                {
                    "ok": True,
                    "cleared": sanitize_public(cleared),
                    "note": "Local DB wiped. Cloud file unchanged until you Push cloud.",
                },
            )
            return

        self._json(404, {"ok": False, "error": "unknown endpoint"})


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="RugWatch web server")
    p.add_argument("--host", default=os.environ.get("WEB_HOST", "127.0.0.1"))
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8787"),
    )
    args = p.parse_args(argv)

    if not WEB_DIR.is_dir():
        print(f"Missing web UI folder: {WEB_DIR}", file=sys.stderr)
        return 1

    httpd = ThreadingHTTPServer((args.host, args.port), RugWatchHandler)
    print(f"{__app_name__} web  http://{args.host}:{args.port}/")
    print("Keys stay on the server (.env). Never put HELIUS/etc in web/config.js.")
    if _web_api_token():
        print("WEB_API_TOKEN is set — browser must send X-API-Token for POST APIs.")
    else:
        print("WARN: WEB_API_TOKEN unset — POST APIs are open on this host.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
