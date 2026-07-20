"""SQLite warehouse for bad wallets, incidents, links, alerts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import db_path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RugWatchDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.session() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS wallets (
                    address       TEXT PRIMARY KEY,
                    chain_id      TEXT NOT NULL DEFAULT 'solana',
                    label         TEXT,
                    risk_score    INTEGER NOT NULL DEFAULT 0,
                    times_seen    INTEGER NOT NULL DEFAULT 0,
                    notes         TEXT,
                    first_seen_at TEXT,
                    last_seen_at  TEXT,
                    source        TEXT,
                    meta_json     TEXT
                );

                CREATE TABLE IF NOT EXISTS incidents (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    mint          TEXT NOT NULL,
                    chain_id      TEXT NOT NULL DEFAULT 'solana',
                    symbol        TEXT,
                    name          TEXT,
                    incident_type TEXT NOT NULL,
                    confidence    INTEGER NOT NULL DEFAULT 50,
                    evidence_json TEXT,
                    source        TEXT,
                    created_at    TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_incidents_mint ON incidents(mint);

                CREATE TABLE IF NOT EXISTS wallet_mint_links (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet     TEXT NOT NULL,
                    mint       TEXT NOT NULL,
                    role       TEXT NOT NULL,
                    evidence   TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(wallet, mint, role),
                    FOREIGN KEY(wallet) REFERENCES wallets(address)
                );
                CREATE INDEX IF NOT EXISTS idx_links_wallet ON wallet_mint_links(wallet);
                CREATE INDEX IF NOT EXISTS idx_links_mint ON wallet_mint_links(mint);

                CREATE TABLE IF NOT EXISTS seen_mints (
                    mint       TEXT PRIMARY KEY,
                    chain_id   TEXT NOT NULL DEFAULT 'solana',
                    symbol     TEXT,
                    name       TEXT,
                    creator    TEXT,
                    first_seen TEXT NOT NULL,
                    last_checked TEXT,
                    meta_json  TEXT
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet     TEXT NOT NULL,
                    mint       TEXT NOT NULL,
                    role       TEXT,
                    risk_score INTEGER,
                    message    TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    acked      INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);

                -- App counters (survive wallet clear; like a view-count style total)
                CREATE TABLE IF NOT EXISTS app_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            # Seed lifetime counter if missing
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?",
                ("wallets_logged_lifetime",),
            ).fetchone()
            if row is None:
                # Bootstrap from current wallet count so existing DBs don't show 0 forever
                try:
                    n = int(conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
                except sqlite3.Error:
                    n = 0
                conn.execute(
                    "INSERT INTO app_meta(key, value) VALUES (?, ?)",
                    ("wallets_logged_lifetime", str(n)),
                )

    # ── wallets ────────────────────────────────────────────────────────

    def upsert_wallet(
        self,
        address: str,
        *,
        chain_id: str = "solana",
        label: str | None = None,
        risk_score: int = 0,
        notes: str | None = None,
        source: str | None = None,
        meta: dict[str, Any] | None = None,
        bump_seen: bool = True,
    ) -> None:
        address = address.strip()
        if not address:
            return
        now = utc_now()
        with self.session() as conn:
            row = conn.execute(
                "SELECT address, risk_score, times_seen FROM wallets WHERE address = ?",
                (address,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO wallets(
                        address, chain_id, label, risk_score, times_seen,
                        notes, first_seen_at, last_seen_at, source, meta_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        address,
                        chain_id,
                        label,
                        max(0, min(100, int(risk_score))),
                        1 if bump_seen else 0,
                        notes,
                        now,
                        now,
                        source,
                        json.dumps(meta or {}),
                    ),
                )
                # Lifetime "wallets logged" counter (like a view counter — not reset on clear)
                conn.execute(
                    """
                    INSERT INTO app_meta(key, value) VALUES ('wallets_logged_lifetime', '1')
                    ON CONFLICT(key) DO UPDATE SET
                        value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
                    """
                )
                return
            new_score = max(int(row["risk_score"] or 0), int(risk_score or 0))
            times = int(row["times_seen"] or 0) + (1 if bump_seen else 0)
            conn.execute(
                """
                UPDATE wallets SET
                    risk_score = ?,
                    times_seen = ?,
                    last_seen_at = ?,
                    label = COALESCE(?, label),
                    notes = CASE
                        WHEN ? IS NOT NULL AND ? != '' THEN
                            CASE WHEN notes IS NULL OR notes = '' THEN ?
                            ELSE notes || ' | ' || ? END
                        ELSE notes END,
                    source = COALESCE(?, source),
                    meta_json = COALESCE(?, meta_json)
                WHERE address = ?
                """,
                (
                    new_score,
                    times,
                    now,
                    label,
                    notes,
                    notes,
                    notes,
                    notes,
                    source,
                    json.dumps(meta) if meta is not None else None,
                    address,
                ),
            )

    def get_wallet(self, address: str) -> dict[str, Any] | None:
        with self.session() as conn:
            row = conn.execute(
                "SELECT * FROM wallets WHERE address = ?", (address.strip(),)
            ).fetchone()
            return dict(row) if row else None

    def list_wallets(
        self, *, min_score: int = 0, limit: int = 200
    ) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                """
                SELECT * FROM wallets
                WHERE risk_score >= ?
                ORDER BY risk_score DESC, times_seen DESC, last_seen_at DESC
                LIMIT ?
                """,
                (min_score, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def known_wallet_set(self, *, min_score: int = 40) -> dict[str, dict[str, Any]]:
        """address -> wallet row for fast launch checks."""
        out: dict[str, dict[str, Any]] = {}
        for w in self.list_wallets(min_score=min_score, limit=50_000):
            out[w["address"]] = w
        return out

    # ── incidents & links ──────────────────────────────────────────────

    def add_incident(
        self,
        mint: str,
        incident_type: str,
        *,
        chain_id: str = "solana",
        symbol: str | None = None,
        name: str | None = None,
        confidence: int = 50,
        evidence: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> int:
        now = utc_now()
        with self.session() as conn:
            cur = conn.execute(
                """
                INSERT INTO incidents(
                    mint, chain_id, symbol, name, incident_type,
                    confidence, evidence_json, source, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    mint,
                    chain_id,
                    symbol,
                    name,
                    incident_type,
                    max(0, min(100, confidence)),
                    json.dumps(evidence or {}),
                    source,
                    now,
                ),
            )
            return int(cur.lastrowid or 0)

    def link_wallet_mint(
        self,
        wallet: str,
        mint: str,
        role: str,
        *,
        evidence: str | None = None,
    ) -> None:
        wallet = wallet.strip()
        mint = mint.strip()
        if not wallet or not mint:
            return
        now = utc_now()
        with self.session() as conn:
            # ensure wallet row exists (minimal)
            exists = conn.execute(
                "SELECT 1 FROM wallets WHERE address = ?", (wallet,)
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO wallets(address, chain_id, risk_score, times_seen,
                        first_seen_at, last_seen_at, source)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (wallet, "solana", 0, 0, now, now, "link"),
                )
            conn.execute(
                """
                INSERT INTO wallet_mint_links(wallet, mint, role, evidence, created_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(wallet, mint, role) DO UPDATE SET
                    evidence = COALESCE(excluded.evidence, wallet_mint_links.evidence)
                """,
                (wallet, mint, role, evidence, now),
            )

    # ── seen mints ─────────────────────────────────────────────────────

    def mark_mint_seen(
        self,
        mint: str,
        *,
        chain_id: str = "solana",
        symbol: str | None = None,
        name: str | None = None,
        creator: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Return True if this mint is brand new to the DB."""
        now = utc_now()
        with self.session() as conn:
            row = conn.execute(
                "SELECT mint FROM seen_mints WHERE mint = ?", (mint,)
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE seen_mints SET last_checked = ?, symbol = COALESCE(?, symbol),
                        name = COALESCE(?, name), creator = COALESCE(?, creator)
                    WHERE mint = ?
                    """,
                    (now, symbol, name, creator, mint),
                )
                return False
            conn.execute(
                """
                INSERT INTO seen_mints(mint, chain_id, symbol, name, creator, first_seen, last_checked, meta_json)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (mint, chain_id, symbol, name, creator, now, now, json.dumps(meta or {})),
            )
            return True

    # ── alerts ─────────────────────────────────────────────────────────

    def add_alert(
        self,
        wallet: str,
        mint: str,
        message: str,
        *,
        role: str | None = None,
        risk_score: int | None = None,
    ) -> int:
        now = utc_now()
        with self.session() as conn:
            # de-dupe same wallet+mint in last hour-ish by exact match unacked
            existing = conn.execute(
                """
                SELECT id FROM alerts
                WHERE wallet = ? AND mint = ? AND acked = 0
                ORDER BY id DESC LIMIT 1
                """,
                (wallet, mint),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cur = conn.execute(
                """
                INSERT INTO alerts(wallet, mint, role, risk_score, message, created_at, acked)
                VALUES (?,?,?,?,?,?,0)
                """,
                (wallet, mint, role, risk_score, message, now),
            )
            return int(cur.lastrowid or 0)

    def list_alerts(self, *, limit: int = 50, unacked_only: bool = False) -> list[dict[str, Any]]:
        with self.session() as conn:
            q = "SELECT * FROM alerts"
            if unacked_only:
                q += " WHERE acked = 0"
            q += " ORDER BY id DESC LIMIT ?"
            return [dict(r) for r in conn.execute(q, (limit,)).fetchall()]

    def _meta_int(self, conn: sqlite3.Connection, key: str, default: int = 0) -> int:
        try:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            return int(row[0] or default)
        except (TypeError, ValueError, sqlite3.Error):
            return default

    def stats(self) -> dict[str, Any]:
        with self.session() as conn:
            def _c(sql: str) -> int:
                return int(conn.execute(sql).fetchone()[0])

            wallets_now = _c("SELECT COUNT(*) FROM wallets")
            lifetime = self._meta_int(conn, "wallets_logged_lifetime", wallets_now)
            # Lifetime never below current list size
            if lifetime < wallets_now:
                lifetime = wallets_now
                conn.execute(
                    """
                    INSERT INTO app_meta(key, value) VALUES ('wallets_logged_lifetime', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(lifetime),),
                )

            return {
                "wallets": wallets_now,
                "wallets_logged": wallets_now,  # currently in DB (view-count style)
                "wallets_logged_lifetime": lifetime,  # ever logged (survives Clear DB)
                "high_risk_wallets": _c("SELECT COUNT(*) FROM wallets WHERE risk_score >= 70"),
                "incidents": _c("SELECT COUNT(*) FROM incidents"),
                "links": _c("SELECT COUNT(*) FROM wallet_mint_links"),
                "seen_mints": _c("SELECT COUNT(*) FROM seen_mints"),
                "alerts": _c("SELECT COUNT(*) FROM alerts"),
                "unacked_alerts": _c("SELECT COUNT(*) FROM alerts WHERE acked = 0"),
                "db_path": str(self.path),
            }

    def clear_all(self, *, sync_cloud: bool = True) -> dict[str, Any]:
        """Wipe wallets, links, incidents, alerts, seen mints. Returns counts before delete."""
        before = self.stats()
        with self.session() as conn:
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM wallet_mint_links")
            conn.execute("DELETE FROM wallets")
            conn.execute("DELETE FROM incidents")
            conn.execute("DELETE FROM seen_mints")
        out: dict[str, Any] = {
            "wallets_removed": int(before.get("wallets") or 0),
            "incidents_removed": int(before.get("incidents") or 0),
            "links_removed": int(before.get("links") or 0),
            "alerts_removed": int(before.get("alerts") or 0),
            "seen_mints_removed": int(before.get("seen_mints") or 0),
        }
        if sync_cloud:
            try:
                from .cloud_store import sync_after_manual_change

                cloud = sync_after_manual_change(self)
                if cloud:
                    out["cloud"] = cloud
            except Exception as exc:  # noqa: BLE001
                out["cloud"] = {"ok": False, "error": str(exc)}
        return out

    def export_wallets(self, *, min_score: int = 0, limit: int = 100_000) -> list[dict[str, Any]]:
        """Portable list for GitHub Gist / cloud JSON (no local paths)."""
        rows = self.list_wallets(min_score=min_score, limit=limit)
        out: list[dict[str, Any]] = []
        for w in rows:
            out.append(
                {
                    "address": w.get("address"),
                    "chain_id": w.get("chain_id") or "solana",
                    "label": w.get("label") or "manual",
                    "risk_score": int(w.get("risk_score") or 0),
                    "notes": w.get("notes") or "",
                    "source": w.get("source") or "manual",
                }
            )
        return out

    def import_wallets(
        self,
        items: list[dict[str, Any]],
        *,
        source_default: str = "import",
    ) -> dict[str, int]:
        """Merge wallet dicts (manual / remote). Only upserts wallets — no auto scan."""
        added = 0
        skipped = 0
        for it in items or []:
            if not isinstance(it, dict):
                skipped += 1
                continue
            addr = (it.get("address") or it.get("wallet") or "").strip()
            if not addr or len(addr) < 32:
                skipped += 1
                continue
            try:
                score = int(it.get("risk_score") if it.get("risk_score") is not None else 70)
            except (TypeError, ValueError):
                score = 70
            self.upsert_wallet(
                addr,
                chain_id=str(it.get("chain_id") or "solana"),
                label=str(it.get("label") or "manual"),
                risk_score=score,
                notes=str(it.get("notes") or "imported"),
                source=str(it.get("source") or source_default),
            )
            added += 1
        return {"imported": added, "skipped": skipped}
