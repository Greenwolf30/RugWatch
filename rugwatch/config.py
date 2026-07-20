"""Paths, env, and constants."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def project_root() -> Path:
    """
    Writable project root.
    - Dev: folder that contains desktop_app.py / rugwatch/
    - Frozen .exe: folder that contains RugWatch.exe (not _internal)
    """
    try:
        import sys

        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
    except Exception:  # noqa: BLE001
        pass
    return Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    global _LOADED
    if _LOADED and path is None:
        return
    candidates = []
    if path is not None:
        candidates.append(path)
    else:
        root = project_root()
        candidates.extend(
            [
                root / ".env",
                Path.home() / "RugWatch" / ".env",
                Path.cwd() / ".env",
            ]
        )
        # Dev source tree if running frozen copy but .env only lives in source
        try:
            src = Path(__file__).resolve().parent.parent / ".env"
            if src not in candidates:
                candidates.append(src)
        except Exception:  # noqa: BLE001
            pass
    for p in candidates:
        if not p.is_file():
            continue
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:
            continue
        _LOADED = True
        return
    _LOADED = True


def data_dir() -> Path:
    # Prefer writable dir next to .exe / project; fallback home
    for d in (
        project_root() / "data",
        Path.home() / "RugWatch" / "data",
    ):
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    d = Path.home() / "RugWatch" / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    load_dotenv()
    env = (os.environ.get("RUGWATCH_DB") or "").strip()
    if env:
        return Path(env)
    return data_dir() / "rugwatch.db"


def alert_log_path() -> Path:
    load_dotenv()
    env = (os.environ.get("RUGWATCH_ALERT_LOG") or "").strip()
    if env:
        return Path(env)
    return data_dir() / "alerts.log"


def helius_api_key() -> str | None:
    load_dotenv()
    k = (os.environ.get("HELIUS_API_KEY") or "").strip()
    return k or None


def solana_rpc_url() -> str | None:
    load_dotenv()
    explicit = (os.environ.get("SOLANA_RPC_URL") or "").strip()
    if explicit:
        return explicit
    key = helius_api_key()
    if key:
        return f"https://mainnet.helius-rpc.com/?api-key={key}"
    return None


def poll_seconds() -> int:
    load_dotenv()
    try:
        return max(15, int(os.environ.get("RUGWATCH_POLL_SECONDS") or 45))
    except ValueError:
        return 45


def auto_flag_wallets() -> bool:
    """
    When False (default), Scan mint only *suggests* wallets — nothing is
    written to the DB unless you Add wallet / add-wallet / import manually.
    Set RUGWATCH_AUTO_FLAG=1 to restore old auto-ingest behavior.
    """
    load_dotenv()
    v = (os.environ.get("RUGWATCH_AUTO_FLAG") or "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def wallets_remote_url() -> str | None:
    """
    Optional HTTPS URL to a JSON wallet list (GitHub raw, Gist, your own host).
    Shape: [ {"address":"...","risk_score":70,"label":"manual","notes":"..."}, ... ]
    or { "wallets": [ ... ] }
    Prefer full cloud push/pull via GITHUB_TOKEN + RUGWATCH_GIST_ID (see cloud_store).
    """
    load_dotenv()
    u = (os.environ.get("RUGWATCH_WALLETS_URL") or "").strip()
    return u or None


# Risk score bands (0–100)
SCORE_CREATOR_RUG = 85
SCORE_EARLY_DUMPER = 60
SCORE_FUNDER_OF_RUG = 55
SCORE_INSIDER = 50
SCORE_MANUAL = 70
