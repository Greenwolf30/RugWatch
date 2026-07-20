"""Rugcheck.xyz report — top holders, risks, insiders."""

from __future__ import annotations

from typing import Any

from ..http_util import get_json

RUGCHECK_REPORT = "https://api.rugcheck.xyz/v1/tokens/{mint}/report"


def fetch_report(mint: str) -> dict[str, Any]:
    url = RUGCHECK_REPORT.format(mint=mint)
    try:
        data = get_json(url, timeout=20.0, retries=1)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "mint": mint}

    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid Rugcheck payload", "mint": mint}

    risks = data.get("risks") or []
    score = data.get("score") or data.get("score_normalised")
    top = data.get("topHolders") or data.get("top_holders") or []
    holders: list[dict[str, Any]] = []
    for i, h in enumerate(top[:40]):
        if not isinstance(h, dict):
            continue
        wallet = (
            h.get("owner")
            or h.get("address")
            or h.get("ownerAddress")
            or ""
        )
        holders.append(
            {
                "rank": i + 1,
                "wallet": wallet,
                "pct": h.get("pct") or h.get("percentage") or h.get("percent"),
                "insider": bool(h.get("insider") or h.get("isInside") or h.get("inside")),
                "label": h.get("label") or h.get("name"),
            }
        )

    creator = (
        data.get("creator")
        or (data.get("token") or {}).get("creator")
        or data.get("mintAuthority")
    )

    risk_names = []
    for r in risks:
        if isinstance(r, dict):
            risk_names.append(str(r.get("name") or r.get("level") or r.get("description") or r))
        else:
            risk_names.append(str(r))

    return {
        "ok": True,
        "mint": mint,
        "score": score,
        "creator": creator,
        "holders": [h for h in holders if h.get("wallet")],
        "risks": risk_names,
        "risks_raw": risks,
        "rugged": bool(data.get("rugged")),
        "tokenMeta": data.get("tokenMeta") or data.get("token") or {},
        "raw_keys": list(data.keys())[:30],
    }
