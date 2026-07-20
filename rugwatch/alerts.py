"""Alert helpers — DB + file log + readable formatting with full mint/links."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import alert_log_path
from .db import RugWatchDB


def solscan_token_url(mint: str) -> str:
    m = (mint or "").strip()
    return f"https://solscan.io/token/{m}" if m else ""


def solscan_account_url(wallet: str) -> str:
    w = (wallet or "").strip()
    return f"https://solscan.io/account/{w}" if w else ""


def dexscreener_url(mint: str, *, chain: str = "solana") -> str:
    m = (mint or "").strip()
    c = (chain or "solana").strip().lower() or "solana"
    return f"https://dexscreener.com/{c}/{m}" if m else ""


def emit_alert(
    db: RugWatchDB,
    *,
    wallet: str,
    mint: str,
    message: str,
    role: str | None = None,
    risk_score: int | None = None,
    symbol: str | None = None,
    name: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    alert_id = db.add_alert(
        wallet, mint, message, role=role, risk_score=risk_score
    )
    path = log_path or alert_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"{datetime.now(timezone.utc).isoformat()} | "
        f"wallet={wallet} | mint={mint} | symbol={symbol or ''} | "
        f"role={role} | score={risk_score} | {message}\n"
    )
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass
    return {
        "id": alert_id,
        "wallet": wallet,
        "mint": mint,
        "symbol": symbol,
        "name": name,
        "role": role,
        "risk_score": risk_score,
        "message": message,
    }


def _token_label(a: dict[str, Any]) -> str:
    """Human token label: $SYMBOL or name, never only a short mint."""
    sym = (a.get("symbol") or "").strip()
    name = (a.get("name") or "").strip()
    if sym and name:
        return f"${sym} ({name})"
    if sym:
        return f"${sym}"
    if name:
        return name
    # Try pull symbol from message "on new launch XYZ"
    msg = str(a.get("message") or "")
    if "on new launch " in msg:
        try:
            part = msg.split("on new launch ", 1)[1]
            token = part.split(" — ", 1)[0].split(" - ", 1)[0].strip()
            if token and not token.startswith("http"):
                return token
        except IndexError:
            pass
    return "(unknown symbol)"


def format_alert(a: dict[str, Any]) -> str:
    """
    Multi-line alert for Alerts tab / Log.

    Always includes:
      - token label (symbol/name when known)
      - full mint address
      - full wallet address
      - Solscan + DexScreener links
    """
    wallet = (a.get("wallet") or "").strip()
    mint = (a.get("mint") or "").strip()
    role = a.get("role") or "?"
    score = a.get("risk_score")
    when = a.get("created_at") or ""
    msg = (a.get("message") or "").strip()
    token = _token_label(a)

    lines = [
        f"[{when}]  ALERT  score={score}  role={role}",
        f"  Token:  {token}",
        f"  Mint:   {mint or '(missing)'}",
        f"  Wallet: {wallet or '(missing)'}",
    ]
    if mint:
        lines.append(f"  Solscan token:  {solscan_token_url(mint)}")
        lines.append(f"  DexScreener:    {dexscreener_url(mint)}")
    if wallet:
        lines.append(f"  Solscan wallet: {solscan_account_url(wallet)}")
    if msg:
        lines.append(f"  Detail: {msg}")
    lines.append("")  # blank line between alerts
    return "\n".join(lines)
