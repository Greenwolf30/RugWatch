"""Solana RPC / Helius helpers."""

from __future__ import annotations

from typing import Any

from ..config import solana_rpc_url
from ..http_util import post_json


def rpc_call(method: str, params: list[Any], *, url: str | None = None) -> Any:
    endpoint = url or solana_rpc_url()
    if not endpoint:
        raise RuntimeError(
            "No Solana RPC configured. Set HELIUS_API_KEY or SOLANA_RPC_URL in .env"
        )
    data = post_json(
        endpoint,
        {"jsonrpc": "2.0", "id": "rugwatch", "method": method, "params": params},
        timeout=25.0,
    )
    if not isinstance(data, dict):
        raise RuntimeError("Invalid RPC response")
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data.get("result")


def get_signatures(address: str, *, limit: int = 20) -> list[dict[str, Any]]:
    result = rpc_call("getSignaturesForAddress", [address, {"limit": limit}])
    return list(result or [])


def get_transaction(signature: str) -> dict[str, Any] | None:
    result = rpc_call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
            },
        ],
    )
    return result if isinstance(result, dict) else None


def largest_token_accounts(mint: str) -> list[dict[str, Any]]:
    """Top token accounts for mint (owner = holder)."""
    result = rpc_call("getTokenLargestAccounts", [mint])
    if not isinstance(result, dict):
        return []
    return list(result.get("value") or [])


def resolve_account_owner(token_account: str) -> str | None:
    result = rpc_call(
        "getAccountInfo",
        [token_account, {"encoding": "jsonParsed"}],
    )
    if not isinstance(result, dict):
        return None
    value = result.get("value") or {}
    data = value.get("data")
    if isinstance(data, dict):
        parsed = data.get("parsed") or {}
        info = parsed.get("info") or {}
        owner = info.get("owner")
        if owner:
            return str(owner)
    return None


def top_holders(mint: str, *, limit: int = 15) -> list[dict[str, Any]]:
    """Return [{wallet, amount, pct?}] for largest holders."""
    accounts = largest_token_accounts(mint)[:limit]
    out: list[dict[str, Any]] = []
    for acc in accounts:
        addr = acc.get("address")
        amount = acc.get("uiAmount")
        if amount is None:
            try:
                amount = float(acc.get("uiAmountString") or 0)
            except (TypeError, ValueError):
                amount = None
        owner = None
        if addr:
            try:
                owner = resolve_account_owner(str(addr))
            except Exception:  # noqa: BLE001
                owner = None
        out.append(
            {
                "token_account": addr,
                "wallet": owner or addr,
                "amount": amount,
            }
        )
    return out


def earliest_signers(mint: str, *, max_sigs: int = 12) -> list[dict[str, Any]]:
    """
    Sample early signatures on the mint address and collect fee-payers / signers.
    Heuristic only — not a full indexer.
    """
    try:
        sigs = get_signatures(mint, limit=max_sigs)
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]

    # signatures come newest-first; reverse for chronological early activity
    ordered = list(reversed(sigs or []))
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ordered[:max_sigs]:
        sig = row.get("signature")
        if not sig:
            continue
        try:
            tx = get_transaction(str(sig))
        except Exception:  # noqa: BLE001
            continue
        if not tx:
            continue
        meta = tx.get("transaction") or {}
        message = meta.get("message") or {}
        account_keys = message.get("accountKeys") or []
        fee_payer = None
        for i, key in enumerate(account_keys):
            if isinstance(key, dict):
                pk = key.get("pubkey")
                signer = key.get("signer")
            else:
                pk = str(key)
                signer = i == 0
            if not pk:
                continue
            if signer and pk not in seen:
                seen.add(pk)
                if fee_payer is None:
                    fee_payer = pk
                found.append(
                    {
                        "wallet": pk,
                        "signature": sig,
                        "slot": row.get("slot"),
                        "role_guess": "early_signer",
                    }
                )
        if fee_payer:
            for f in found:
                if f.get("wallet") == fee_payer:
                    f["role_guess"] = "fee_payer"
    return found
