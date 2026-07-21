"""SQLite warehouse for bad wallets, incidents, links, alerts."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .config import db_path, local_db_max


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_WALLET_SCHEMA_SQL = """
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
"""

_FULL_SCHEMA_SQL = (
    _WALLET_SCHEMA_SQL
    + """
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

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
)


class RugWatchDB:
    """
    Local wallet warehouse.

    Primary file: data/rugwatch.db (incidents, alerts, meta + wallets).
    Overflow wallet shards when local cap is hit:
      data/rugwatch_002.db, rugwatch_003.db, ...
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema(self.path, primary=True)

    def connect(self, path: Path | None = None) -> sqlite3.Connection:
        p = path or self.path
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        # OFF: wallet overflow shards may hold addresses that links/alerts
        # on the primary DB still reference (multi-DB warehouse).
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def session(self, path: Path | None = None) -> Iterator[sqlite3.Connection]:
        conn = self.connect(path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self, path: Path, *, primary: bool = False) -> None:
        sql = _FULL_SCHEMA_SQL if primary else _WALLET_SCHEMA_SQL
        with self.session(path) as conn:
            conn.executescript(sql)
            if not primary:
                return
            # Seed lifetime counter if missing
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?",
                ("wallets_logged_lifetime",),
            ).fetchone()
            if row is None:
                try:
                    n = int(conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
                except sqlite3.Error:
                    n = 0
                # Include overflow shards already on disk
                for sp in self.shard_paths()[1:]:
                    try:
                        with self.connect(sp) as c2:
                            n += int(c2.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
                    except sqlite3.Error:
                        pass
                conn.execute(
                    "INSERT INTO app_meta(key, value) VALUES (?, ?)",
                    ("wallets_logged_lifetime", str(n)),
                )

    # ── multi-DB (local shards) ───────────────────────────────────────

    def shard_paths(self) -> list[Path]:
        """Primary + overflow wallet DBs, ordered."""
        import re

        primary = self.path
        parent = primary.parent
        stem = primary.stem
        out = [primary]
        pat = re.compile(rf"^{re.escape(stem)}_(\d{{3}})\.db$", re.I)
        extras: list[tuple[int, Path]] = []
        try:
            for p in parent.iterdir():
                if not p.is_file():
                    continue
                m = pat.match(p.name)
                if m:
                    extras.append((int(m.group(1)), p))
        except OSError:
            pass
        extras.sort(key=lambda t: t[0])
        out.extend(p for _, p in extras)
        return out

    def local_shard_info(self) -> list[dict[str, Any]]:
        info: list[dict[str, Any]] = []
        for i, p in enumerate(self.shard_paths(), start=1):
            try:
                with self.connect(p) as conn:
                    n = int(conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
            except sqlite3.Error:
                n = 0
            info.append(
                {
                    "index": i,
                    "path": str(p.name),
                    "wallets": n,
                    "max": local_db_max(),
                }
            )
        return info

    def _wallet_count_at(self, path: Path) -> int:
        try:
            with self.connect(path) as conn:
                return int(conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0])
        except sqlite3.Error:
            return 0

    def _find_wallet_shard(self, address: str) -> Path | None:
        address = address.strip()
        if not address:
            return None
        for p in self.shard_paths():
            try:
                with self.connect(p) as conn:
                    row = conn.execute(
                        "SELECT 1 FROM wallets WHERE address = ?", (address,)
                    ).fetchone()
                    if row is not None:
                        return p
            except sqlite3.Error:
                continue
        return None

    def _shard_for_new_wallet(self) -> Path:
        """Last shard if under cap; else create next overflow DB."""
        max_n = local_db_max()
        paths = self.shard_paths()
        last = paths[-1]
        if self._wallet_count_at(last) < max_n:
            return last
        # Create next numbered shard
        import re

        stem = self.path.stem
        highest = 1
        for p in paths[1:]:
            m = re.match(rf"^{re.escape(stem)}_(\d{{3}})\.db$", p.name, re.I)
            if m:
                highest = max(highest, int(m.group(1)))
        nxt = self.path.parent / f"{stem}_{highest + 1:03d}.db"
        self._init_schema(nxt, primary=False)
        return nxt

    def _bump_lifetime(self) -> None:
        with self.session(self.path) as conn:
            conn.execute(
                """
                INSERT INTO app_meta(key, value) VALUES ('wallets_logged_lifetime', '1')
                ON CONFLICT(key) DO UPDATE SET
                    value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)
                """
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
        # Never store Pump.fun / known DEX liquidity or program vaults
        try:
            from .lp_filter import is_excluded_lp_wallet

            if is_excluded_lp_wallet(
                {
                    "address": address,
                    "label": label,
                    "notes": notes,
                    "source": source,
                }
            ):
                return
        except Exception:  # noqa: BLE001
            pass
        now = utc_now()
        existing_path = self._find_wallet_shard(address)
        target = existing_path if existing_path is not None else self._shard_for_new_wallet()

        with self.session(target) as conn:
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
            else:
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
                return

        # New wallet: bump lifetime on primary only
        self._bump_lifetime()

    def get_wallet(self, address: str) -> dict[str, Any] | None:
        address = address.strip()
        p = self._find_wallet_shard(address)
        if p is None:
            return None
        with self.session(p) as conn:
            row = conn.execute(
                "SELECT * FROM wallets WHERE address = ?", (address,)
            ).fetchone()
            return dict(row) if row else None

    def delete_wallet(self, address: str) -> dict[str, Any]:
        """
        Remove a wallet from every local shard + mint links / alerts on primary.
        Used when a flagged seller buys back (swing) and must be unflagged.
        """
        address = (address or "").strip()
        out: dict[str, Any] = {
            "address": address,
            "deleted": False,
            "links_removed": 0,
            "alerts_removed": 0,
        }
        if not address:
            return out
        # Wallet row may live on any shard
        for p in self.shard_paths():
            try:
                with self.session(p) as conn:
                    cur = conn.execute(
                        "DELETE FROM wallets WHERE address = ?", (address,)
                    )
                    if cur.rowcount and cur.rowcount > 0:
                        out["deleted"] = True
            except sqlite3.Error:
                continue
        # Links + alerts only on primary
        try:
            with self.session(self.path) as conn:
                cur_l = conn.execute(
                    "DELETE FROM wallet_mint_links WHERE wallet = ?", (address,)
                )
                out["links_removed"] = int(cur_l.rowcount or 0)
                cur_a = conn.execute(
                    "DELETE FROM alerts WHERE wallet = ?", (address,)
                )
                out["alerts_removed"] = int(cur_a.rowcount or 0)
        except sqlite3.Error:
            pass
        return out

    def delete_wallets(self, addresses: list[str]) -> dict[str, Any]:
        """Delete many wallets; returns per-address results + totals."""
        results: list[dict[str, Any]] = []
        deleted_n = 0
        for raw in addresses or []:
            r = self.delete_wallet(str(raw or ""))
            results.append(r)
            if r.get("deleted"):
                deleted_n += 1
        return {
            "ok": True,
            "requested": len(results),
            "deleted": deleted_n,
            "results": results,
        }

    def list_wallets(
        self, *, min_score: int = 0, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Union across all local shards; highest scores first."""
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in self.shard_paths():
            try:
                with self.connect(p) as conn:
                    for r in conn.execute(
                        """
                        SELECT * FROM wallets
                        WHERE risk_score >= ?
                        ORDER BY risk_score DESC, times_seen DESC, last_seen_at DESC
                        """,
                        (min_score,),
                    ).fetchall():
                        d = dict(r)
                        a = d.get("address") or ""
                        if a and a not in seen:
                            seen.add(a)
                            rows.append(d)
            except sqlite3.Error:
                continue
        rows.sort(
            key=lambda w: (
                -int(w.get("risk_score") or 0),
                -int(w.get("times_seen") or 0),
                str(w.get("last_seen_at") or ""),
            )
        )
        return rows[: max(0, int(limit))]

    def known_wallet_set(self, *, min_score: int = 40) -> dict[str, dict[str, Any]]:
        """address -> wallet row for fast launch checks (all local shards)."""
        out: dict[str, dict[str, Any]] = {}
        # High limit: multi-shard can exceed old 50k single-file soft cap
        for w in self.list_wallets(min_score=min_score, limit=5_000_000):
            out[w["address"]] = w
        return out

    def wallet_mint_map(self) -> dict[str, str]:
        """
        wallet address -> most recent linked mint (primary DB links table).
        Used by the Wallets UI to show mint next to each wallet.
        """
        import re

        out: dict[str, str] = {}
        # Links live on primary DB
        try:
            with self.connect(self.path) as conn:
                for r in conn.execute(
                    """
                    SELECT wallet, mint FROM wallet_mint_links
                    ORDER BY id ASC
                    """
                ).fetchall():
                    w = (r[0] or "").strip()
                    m = (r[1] or "").strip()
                    if w and m:
                        out[w] = m  # last row wins (most recent)
        except sqlite3.Error:
            pass
        return out

    @staticmethod
    def mint_from_notes(notes: str | None) -> str | None:
        """Parse 'mint <address>' from Ruggers-style notes if present."""
        if not notes:
            return None
        import re

        m = re.search(
            r"\bmint\s+([1-9A-HJ-NP-Za-km-z]{32,48})\b",
            str(notes),
            flags=re.I,
        )
        return m.group(1) if m else None

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
    ) -> bool:
        """
        Link wallet ↔ mint. Returns True if this is a NEW link
        (counts as a new flag event for that mint + address).
        """
        wallet = wallet.strip()
        mint = mint.strip()
        if not wallet or not mint:
            return False
        now = utc_now()
        is_new = False
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
            prev = conn.execute(
                """
                SELECT 1 FROM wallet_mint_links
                WHERE wallet = ? AND mint = ? AND role = ?
                """,
                (wallet, mint, role),
            ).fetchone()
            is_new = prev is None
            conn.execute(
                """
                INSERT INTO wallet_mint_links(wallet, mint, role, evidence, created_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(wallet, mint, role) DO UPDATE SET
                    evidence = COALESCE(excluded.evidence, wallet_mint_links.evidence)
                """,
                (wallet, mint, role, evidence, now),
            )
        return is_new

    def bump_mint_flag_count(
        self,
        mint: str,
        *,
        symbol: str | None = None,
        by: int = 1,
    ) -> int:
        """Increment how many times this mint has been used as a flag source."""
        mint = (mint or "").strip()
        if not mint or by <= 0:
            return 0
        key = f"mint_flag_count:{mint}"
        with self.session() as conn:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
            try:
                cur = int(row["value"] if row is not None else 0)
            except (TypeError, ValueError, KeyError):
                try:
                    cur = int(row[0]) if row is not None else 0
                except (TypeError, ValueError, IndexError):
                    cur = 0
            nxt = cur + int(by)
            conn.execute(
                """
                INSERT INTO app_meta(key, value) VALUES (?,?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(nxt)),
            )
            if symbol:
                sk = f"mint_symbol:{mint}"
                conn.execute(
                    """
                    INSERT INTO app_meta(key, value) VALUES (?,?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (sk, str(symbol).lstrip("$")[:32]),
                )
            return nxt

    def get_mint_flag_count(self, mint: str) -> int:
        mint = (mint or "").strip()
        if not mint:
            return 0
        key = f"mint_flag_count:{mint}"
        try:
            with self.connect(self.path) as conn:
                row = conn.execute(
                    "SELECT value FROM app_meta WHERE key = ?", (key,)
                ).fetchone()
                if not row:
                    return 0
                try:
                    return int(row["value"] if isinstance(row, sqlite3.Row) else row[0])
                except (TypeError, ValueError, KeyError, IndexError):
                    return 0
        except sqlite3.Error:
            return 0

    def wallet_flag_stats(self, address: str) -> dict[str, Any]:
        """times_flagged (times_seen) + mint links for an address."""
        address = (address or "").strip()
        out: dict[str, Any] = {
            "address": address,
            "times_flagged": 0,
            "mints": [],
        }
        if not address:
            return out
        for p in self.shard_paths():
            try:
                with self.connect(p) as conn:
                    row = conn.execute(
                        "SELECT times_seen FROM wallets WHERE address = ?",
                        (address,),
                    ).fetchone()
                    if row is not None:
                        try:
                            out["times_flagged"] = max(
                                out["times_flagged"],
                                int(
                                    row["times_seen"]
                                    if isinstance(row, sqlite3.Row)
                                    else row[0]
                                    or 0
                                ),
                            )
                        except (TypeError, ValueError, KeyError, IndexError):
                            pass
                    try:
                        for lr in conn.execute(
                            "SELECT mint FROM wallet_mint_links WHERE wallet = ?",
                            (address,),
                        ):
                            m = (
                                lr["mint"]
                                if isinstance(lr, sqlite3.Row)
                                else lr[0]
                            ) or ""
                            m = str(m).strip()
                            if m and m not in out["mints"]:
                                out["mints"].append(m)
                    except sqlite3.Error:
                        pass
            except sqlite3.Error:
                continue
        # Prefer link count if higher than times_seen
        if len(out["mints"]) > int(out["times_flagged"] or 0):
            out["times_flagged"] = len(out["mints"])
        return out

    # ── seen mints ─────────────────────────────────────────────────────

    def is_mint_seen(self, mint: str) -> bool:
        """True if mint is already in seen_mints (any local primary DB)."""
        mint = (mint or "").strip()
        if not mint:
            return False
        try:
            with self.connect(self.path) as conn:
                row = conn.execute(
                    "SELECT 1 FROM seen_mints WHERE mint = ?", (mint,)
                ).fetchone()
                return row is not None
        except sqlite3.Error:
            return False

    def known_mint_set(self) -> set[str]:
        """All mints already recorded in seen_mints."""
        out: set[str] = set()
        try:
            with self.connect(self.path) as conn:
                for row in conn.execute("SELECT mint FROM seen_mints"):
                    m = (row[0] or "").strip()
                    if m:
                        out.add(m)
        except sqlite3.Error:
            pass
        return out

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
        shards = self.local_shard_info()
        wallets_now = sum(int(s.get("wallets") or 0) for s in shards)
        high_risk = 0
        for p in self.shard_paths():
            try:
                with self.connect(p) as conn:
                    high_risk += int(
                        conn.execute(
                            "SELECT COUNT(*) FROM wallets WHERE risk_score >= 70"
                        ).fetchone()[0]
                    )
            except sqlite3.Error:
                pass

        with self.session(self.path) as conn:
            def _c(sql: str) -> int:
                return int(conn.execute(sql).fetchone()[0])

            lifetime = self._meta_int(conn, "wallets_logged_lifetime", wallets_now)
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
                "wallets_logged": wallets_now,
                "wallets_logged_lifetime": lifetime,
                "high_risk_wallets": high_risk,
                "incidents": _c("SELECT COUNT(*) FROM incidents"),
                "links": _c("SELECT COUNT(*) FROM wallet_mint_links"),
                "seen_mints": _c("SELECT COUNT(*) FROM seen_mints"),
                "alerts": _c("SELECT COUNT(*) FROM alerts"),
                "unacked_alerts": _c("SELECT COUNT(*) FROM alerts WHERE acked = 0"),
                "db_path": str(self.path),
                "local_shards": len(shards),
                "local_shard_max": local_db_max(),
                "local_shard_detail": shards,
            }

    def clear_all(self, *, sync_cloud: bool = True) -> dict[str, Any]:
        """Wipe wallets on all shards + research tables on primary."""
        before = self.stats()
        # Primary research + wallets
        with self.session(self.path) as conn:
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM wallet_mint_links")
            conn.execute("DELETE FROM wallets")
            conn.execute("DELETE FROM incidents")
            conn.execute("DELETE FROM seen_mints")
        # Overflow wallet shards
        for p in self.shard_paths()[1:]:
            try:
                with self.session(p) as conn:
                    conn.execute("DELETE FROM wallets")
            except sqlite3.Error:
                continue
        out: dict[str, Any] = {
            "wallets_removed": int(before.get("wallets") or 0),
            "incidents_removed": int(before.get("incidents") or 0),
            "links_removed": int(before.get("links") or 0),
            "alerts_removed": int(before.get("alerts") or 0),
            "seen_mints_removed": int(before.get("seen_mints") or 0),
            "local_shards": int(before.get("local_shards") or 1),
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

    def export_wallets(self, *, min_score: int = 0, limit: int = 5_000_000) -> list[dict[str, Any]]:
        """Portable list for cloud JSON (all local shards)."""
        rows = self.list_wallets(min_score=min_score, limit=limit)
        out: list[dict[str, Any]] = []
        for w in rows:
            addr = w.get("address")
            stats = self.wallet_flag_stats(str(addr or ""))
            mints = list(stats.get("mints") or [])
            initial = mints[0] if mints else None
            out.append(
                {
                    "address": addr,
                    "chain_id": w.get("chain_id") or "solana",
                    "label": w.get("label") or "manual",
                    "risk_score": int(w.get("risk_score") or 0),
                    "notes": w.get("notes") or "",
                    "source": w.get("source") or "manual",
                    "times_flagged": int(
                        stats.get("times_flagged")
                        or w.get("times_seen")
                        or 0
                    ),
                    "times_seen": int(w.get("times_seen") or 0),
                    "flagged_from_mint": initial,
                    "flagged_from_mints": [initial] if initial else [],
                    "mint_flag_count": (
                        self.get_mint_flag_count(initial) if initial else 0
                    ),
                }
            )
        return out

    def wallet_exists(self, address: str) -> bool:
        """True if address is already in any local DB shard."""
        return self._find_wallet_shard((address or "").strip()) is not None

    def known_local_addresses(self) -> set[str]:
        """All wallet addresses currently stored across local shards."""
        out: set[str] = set()
        for p in self.shard_paths():
            try:
                with self.connect(p) as conn:
                    for row in conn.execute("SELECT address FROM wallets"):
                        a = (row[0] or "").strip()
                        if a:
                            out.add(a)
            except sqlite3.Error:
                continue
        return out

    def import_wallets(
        self,
        items: list[dict[str, Any]],
        *,
        source_default: str = "import",
        skip_existing: bool = True,
        also_skip: set[str] | None = None,
    ) -> dict[str, int]:
        """
        Import wallet dicts (manual upload / Ruggers / remote).

        skip_existing=True (default): do not insert or update addresses already
        in the local multi-DB. Prevents duplicate wallets and note spam.

        also_skip: extra addresses to treat as already known (e.g. cloud list)
        so uploads that match cloud-only wallets are ignored too.
        """
        added = 0
        skipped_invalid = 0
        skipped_existing = 0
        skipped_local = 0
        skipped_cloud = 0
        skipped_batch_dup = 0
        skipped_lp = 0
        also = {a.strip() for a in (also_skip or set()) if a and str(a).strip()}
        seen_batch: set[str] = set()
        try:
            from .lp_filter import is_excluded_lp_wallet

            _lp_cache: dict[str, set[str]] = {}
        except Exception:  # noqa: BLE001
            is_excluded_lp_wallet = None  # type: ignore[assignment]
            _lp_cache = {}

        import re as _re

        mint_re = _re.compile(
            r"\bmint\s+([1-9A-HJ-NP-Za-km-z]{32,44})\b", _re.I
        )
        sym_re = _re.compile(r"\$([A-Za-z0-9]{1,20})\b")

        for it in items or []:
            if not isinstance(it, dict):
                skipped_invalid += 1
                continue
            addr = (it.get("address") or it.get("wallet") or "").strip()
            if not addr or len(addr) < 32:
                skipped_invalid += 1
                continue
            if is_excluded_lp_wallet is not None and is_excluded_lp_wallet(
                it, pump_lp_cache=_lp_cache
            ):
                skipped_lp += 1
                continue
            if addr in seen_batch:
                skipped_batch_dup += 1
                continue
            seen_batch.add(addr)

            notes = str(it.get("notes") or "imported")
            mint = (it.get("mint") or it.get("flagged_from_mint") or "").strip()
            if not mint:
                mm = mint_re.search(notes)
                if mm:
                    mint = mm.group(1).strip()
            symbol = (it.get("symbol") or "").strip().lstrip("$")
            if not symbol:
                sm = sym_re.search(notes)
                if sm:
                    symbol = sm.group(1)

            existed = self.wallet_exists(addr)
            if skip_existing:
                # Prefer cloud check first so callers can tell "already on GitHub"
                if addr in also and not mint:
                    skipped_cloud += 1
                    skipped_existing += 1
                    continue
                if existed and not mint:
                    skipped_local += 1
                    skipped_existing += 1
                    continue

            try:
                score = int(
                    it.get("risk_score") if it.get("risk_score") is not None else 70
                )
            except (TypeError, ValueError):
                score = 70

            if not existed:
                self.upsert_wallet(
                    addr,
                    chain_id=str(it.get("chain_id") or "solana"),
                    label=str(it.get("label") or "manual"),
                    risk_score=score,
                    notes=notes,
                    source=str(it.get("source") or source_default),
                    bump_seen=True,
                )
                added += 1
            elif mint:
                # Existing wallet but new mint flag link — still count the flag event
                self.upsert_wallet(
                    addr,
                    chain_id=str(it.get("chain_id") or "solana"),
                    label=str(it.get("label") or "manual"),
                    risk_score=score,
                    notes=notes,
                    source=str(it.get("source") or source_default),
                    bump_seen=True,
                )
            else:
                skipped_local += 1
                skipped_existing += 1
                also.add(addr)
                continue

            # Link mint + bump mint flag count on NEW wallet↔mint links only
            if mint:
                is_new_link = self.link_wallet_mint(
                    addr,
                    mint,
                    role=str(it.get("label") or "ruggers_flag")[:40],
                    evidence=notes[:200] if notes else None,
                )
                if is_new_link:
                    self.bump_mint_flag_count(mint, symbol=symbol or None, by=1)

            # Newly added — treat as known for rest of batch / also_skip
            also.add(addr)

        skipped = (
            skipped_invalid
            + skipped_existing
            + skipped_batch_dup
            + skipped_lp
        )
        return {
            "imported": added,
            "skipped": skipped,
            "skipped_existing": skipped_existing,
            "skipped_local": skipped_local,
            "skipped_cloud": skipped_cloud,
            "skipped_invalid": skipped_invalid,
            "skipped_batch_dup": skipped_batch_dup,
            "skipped_lp": skipped_lp,
        }
