"""
Cloud wallet store — one place with the whole RugWatch project on GitHub.

Primary mode (recommended): same GitHub REPO as the code
  RUGWATCH_CLOUD=repo
  RUGWATCH_GITHUB_REPO=YourUser/RugWatch
  GITHUB_TOKEN=ghp_...   (repo scope: contents read/write)
  RUGWATCH_GITHUB_PATH=data/wallets_cloud.json
  RUGWATCH_CLOUD_SHARD_MAX=100000   # new JSON file after this many wallets
  RUGWATCH_CLOUD_INDEX=data/wallets_index.json

When a shard fills, Push cloud creates wallets_cloud_002.json, _003, ...
and updates wallets_index.json. Pull cloud merges every listed shard.

Legacy mode: separate Gist (single file, not multi-sharded)
  RUGWATCH_CLOUD=gist

Local multi-DB: data/rugwatch.db + rugwatch_002.db when RUGWATCH_LOCAL_DB_MAX hit.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from . import config
from .db import RugWatchDB
from .http_util import DEFAULT_HEADERS, _ssl_context
from .remote_wallets import parse_wallet_payload


GIST_API = "https://api.github.com/gists"
REPO_API = "https://api.github.com/repos"
FILE_DEFAULT = "rugwatch_wallets.json"
REPO_WALLETS_PATH = "data/wallets_cloud.json"


def github_token() -> str | None:
    config.load_dotenv()
    k = (
        os.environ.get("RUGWATCH_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()
    return k or None


def cloud_mode() -> str:
    """repo | gist | off"""
    config.load_dotenv()
    mode = (os.environ.get("RUGWATCH_CLOUD") or "repo").strip().lower()
    if mode in {"0", "off", "false", "no", "none", "local"}:
        return "off"
    if mode in {"gist", "gists"}:
        return "gist"
    if mode in {"1", "on", "true", "repo", "github", "repository", ""}:
        return "repo"
    return mode


def github_repo() -> str | None:
    """owner/name"""
    config.load_dotenv()
    r = (
        os.environ.get("RUGWATCH_GITHUB_REPO")
        or os.environ.get("GITHUB_REPO")
        or ""
    ).strip().strip("/")
    return r or None


def github_wallets_path() -> str:
    config.load_dotenv()
    p = (os.environ.get("RUGWATCH_GITHUB_PATH") or REPO_WALLETS_PATH).strip()
    return p.lstrip("/") or REPO_WALLETS_PATH


def github_branch() -> str:
    config.load_dotenv()
    return (os.environ.get("RUGWATCH_GITHUB_BRANCH") or "main").strip() or "main"


def gist_id() -> str | None:
    config.load_dotenv()
    g = (os.environ.get("RUGWATCH_GIST_ID") or "").strip()
    return g or None


def gist_filename() -> str:
    config.load_dotenv()
    return (os.environ.get("RUGWATCH_GIST_FILENAME") or FILE_DEFAULT).strip() or FILE_DEFAULT


def gist_public() -> bool:
    config.load_dotenv()
    v = (os.environ.get("RUGWATCH_GIST_PUBLIC") or "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def cloud_enabled() -> bool:
    mode = cloud_mode()
    if mode == "off":
        return False
    if not github_token():
        return False
    if mode == "repo":
        return bool(github_repo())
    if mode == "gist":
        return True  # can create gist on first push
    return False


def cloud_primary() -> bool:
    if not cloud_enabled():
        return False
    config.load_dotenv()
    v = (os.environ.get("RUGWATCH_CLOUD_PRIMARY") or "1").strip().lower()
    return v not in {"0", "false", "no", "off"}


def _auth_headers() -> dict[str, str]:
    tok = github_token()
    if not tok:
        raise RuntimeError(
            "Set GITHUB_TOKEN in RugWatch/.env "
            "(repo mode needs 'repo' scope; gist mode needs 'gist' scope)."
        )
    return {
        **DEFAULT_HEADERS,
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {tok}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "RugWatch-Cloud/1.1",
    }


def _request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers=_auth_headers(),
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"GitHub API {exc.code}: {body}") from exc


def _payload_shard(wallets: list[dict[str, Any]], *, shard: int, total_shards: int) -> dict[str, Any]:
    return {
        "format": "rugwatch_wallets_v1",
        "wallets": wallets,
        "count": len(wallets),
        "shard": shard,
        "total_shards": total_shards,
        "note": "RugWatch wallet list — cloud shard (same project on GitHub)",
    }


def _shard_file_path(index: int) -> str:
    """1-based shard index → repo path. Shard 1 keeps the classic filename."""
    base = github_wallets_path()
    if index <= 1:
        return base
    # data/wallets_cloud.json → data/wallets_cloud_002.json
    if base.lower().endswith(".json"):
        stem = base[: -len(".json")]
        return f"{stem}_{index:03d}.json"
    return f"{base}_{index:03d}"


def _chunk_wallets(wallets: list[dict[str, Any]], max_n: int) -> list[list[dict[str, Any]]]:
    if max_n < 1:
        max_n = 100_000
    if not wallets:
        return [[]]
    return [wallets[i : i + max_n] for i in range(0, len(wallets), max_n)]


# ── Repo mode (whole project on GitHub) ───────────────────────────────

def _repo_contents_url(path: str | None = None) -> str:
    repo = github_repo()
    if not repo or "/" not in repo:
        raise RuntimeError(
            "Set RUGWATCH_GITHUB_REPO=YourUser/RugWatch (same repo as the whole folder)."
        )
    p = path or github_wallets_path()
    return f"{REPO_API}/{repo}/contents/{p}"


def _put_repo_file(
    path: str,
    content_text: str,
    *,
    message: str,
) -> dict[str, Any]:
    """Create or update a single file in the GitHub repo. Returns API result summary."""
    b64 = base64.b64encode(content_text.encode("utf-8")).decode("ascii")
    url = _repo_contents_url(path)
    branch = github_branch()
    sha = None
    try:
        existing = _request_json("GET", f"{url}?ref={branch}")
        if isinstance(existing, dict):
            sha = existing.get("sha")
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
    payload: dict[str, Any] = {
        "message": message,
        "content": b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    data = _request_json("PUT", url, payload)
    html = (data.get("content") or {}).get("html_url") or data.get("commit", {}).get("html_url")
    return {
        "ok": True,
        "action": "updated" if sha else "created",
        "path": path,
        "html_url": html,
        "sha": (data.get("content") or {}).get("sha"),
    }


def _get_repo_file_json(path: str) -> dict[str, Any] | None:
    """Return parsed JSON for a repo file, or None if 404."""
    url = _repo_contents_url(path)
    branch = github_branch()
    try:
        data = _request_json("GET", f"{url}?ref={branch}")
    except RuntimeError as exc:
        if "404" in str(exc):
            return None
        raise
    content_b64 = data.get("content") or ""
    if not content_b64:
        return None
    raw = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
    return json.loads(raw)


def push_to_repo(db: RugWatchDB | None = None) -> dict[str, Any]:
    """
    Export all local wallets and write one or more cloud JSON shards + index.
    New shard files open automatically when RUGWATCH_CLOUD_SHARD_MAX is reached.
    """
    db = db or RugWatchDB()
    wallets = db.export_wallets(min_score=0)
    # Deduplicate by address (keep highest risk_score) — no duplicate cloud entries
    by_addr: dict[str, dict[str, Any]] = {}
    for w in wallets:
        if not isinstance(w, dict):
            continue
        a = (w.get("address") or "").strip()
        if not a:
            continue
        prev = by_addr.get(a)
        if prev is None or int(w.get("risk_score") or 0) >= int(prev.get("risk_score") or 0):
            by_addr[a] = w
    wallets = list(by_addr.values())
    # Stable order so re-push packs deterministically
    wallets.sort(key=lambda w: str(w.get("address") or ""))
    max_n = config.cloud_shard_max()
    chunks = _chunk_wallets(wallets, max_n)
    total_shards = len(chunks)
    branch = github_branch()
    repo = github_repo()
    shard_meta: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for i, chunk in enumerate(chunks, start=1):
        path = _shard_file_path(i)
        body = _payload_shard(chunk, shard=i, total_shards=total_shards)
        try:
            r = _put_repo_file(
                path,
                json.dumps(body, indent=2),
                message=f"RugWatch: sync wallet shard {i}/{total_shards} ({len(chunk)} addresses)",
            )
            results.append(r)
            shard_meta.append({"path": path, "count": len(chunk), "shard": i})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path}: {exc}")

    index_path = config.cloud_index_path()
    index_body = {
        "format": "rugwatch_wallets_index_v1",
        "shard_max_wallets": max_n,
        "shards": shard_meta,
        "total_count": len(wallets),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Multi-shard wallet index. ATC/readers should load every path in shards[]. "
            "Each file is rugwatch_wallets_v1."
        ),
    }
    try:
        idx_r = _put_repo_file(
            index_path,
            json.dumps(index_body, indent=2),
            message=f"RugWatch: wallet index ({len(wallets)} addresses, {total_shards} shards)",
        )
        results.append(idx_r)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{index_path}: {exc}")

    # Prefer index URL for multi-shard consumers
    index_raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{index_path}"
    primary_raw = f"https://raw.githubusercontent.com/{repo}/{branch}/{_shard_file_path(1)}"
    os.environ["RUGWATCH_WALLETS_URL"] = index_raw

    ok = not errors and bool(shard_meta)
    return {
        "ok": ok or (bool(shard_meta) and not errors),
        "action": "updated",
        "mode": "repo",
        "repo": repo,
        "path": _shard_file_path(1),
        "index_path": index_path,
        "branch": branch,
        "html_url": f"https://github.com/{repo}/blob/{branch}/{index_path}",
        "raw_url": index_raw,
        "primary_raw_url": primary_raw,
        "wallet_count": len(wallets),
        "cloud_shards": total_shards,
        "shard_paths": [s["path"] for s in shard_meta],
        "errors": errors or None,
        "note": (
            f"Wallets stored in {total_shards} shard file(s) under the RugWatch repo "
            f"(max {max_n}/file). Index: {index_path}."
        ),
    }


def pull_from_repo(
    db: RugWatchDB | None = None,
    *,
    max_wallets: int | None = None,
) -> dict[str, Any]:
    """
    Pull cloud shards (via index when present) into the local multi-DB.
    Falls back to a single wallets_cloud.json if no index exists.

    max_wallets: if set, only take the first N wallets from cloud (across shards
    in index order). None / unlimited = pull all.
    """
    db = db or RugWatchDB()
    index_path = config.cloud_index_path()
    paths: list[str] = []
    index = _get_repo_file_json(index_path)
    if isinstance(index, dict) and index.get("format") == "rugwatch_wallets_index_v1":
        for s in index.get("shards") or []:
            if isinstance(s, dict) and s.get("path"):
                paths.append(str(s["path"]))
        if not paths:
            paths = [_shard_file_path(1)]
    else:
        # Backward compatible: only primary file
        paths = [github_wallets_path()]

    total_imported = 0
    total_skipped = 0
    loaded_paths: list[str] = []
    missing: list[str] = []
    considered = 0
    remaining = max_wallets if max_wallets is not None and max_wallets > 0 else None
    limited = remaining is not None

    for path in paths:
        if remaining is not None and remaining <= 0:
            break
        parsed = _get_repo_file_json(path)
        if parsed is None:
            missing.append(path)
            continue
        items = parse_wallet_payload(parsed)
        if remaining is not None:
            items = items[:remaining]
        if not items and remaining is not None:
            loaded_paths.append(path)
            continue
        stats = db.import_wallets(items, source_default="cloud_repo")
        n_items = len(items)
        considered += n_items
        if remaining is not None:
            remaining -= n_items
        total_imported += int(stats.get("imported") or 0)
        total_skipped += int(stats.get("skipped") or 0)
        loaded_paths.append(path)

    if not loaded_paths and missing:
        return {
            "ok": True,
            "mode": "repo",
            "imported": 0,
            "note": (
                f"No cloud wallet files yet ({', '.join(missing[:3])}). "
                "Add wallets and Push cloud."
            ),
            "repo": github_repo(),
            "cloud_shards": 0,
        }

    note_bits = []
    if limited:
        note_bits.append(
            f"Limited pull: considered {considered} cloud wallet(s)"
            + (f" (max {max_wallets})" if max_wallets else "")
        )
    return {
        "ok": True,
        "mode": "repo",
        "source": "github_repo",
        "repo": github_repo(),
        "path": loaded_paths[0] if loaded_paths else github_wallets_path(),
        "paths": loaded_paths,
        "imported": total_imported,
        "skipped": total_skipped,
        "db_wallets": db.stats().get("wallets"),
        "cloud_shards": len(loaded_paths),
        "missing": missing or None,
        "max_wallets": max_wallets if limited else None,
        "considered": considered if limited else None,
        "note": "; ".join(note_bits) if note_bits else None,
        "local_shards": db.stats().get("local_shards"),
    }


# ── Gist mode (legacy separate store) ─────────────────────────────────

def _save_env_key(key: str, value: str) -> None:
    os.environ[key] = value
    env_path = config.project_root() / ".env"
    lines: list[str] = []
    found = False
    if env_path.is_file():
        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
    out: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    try:
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        pass


def push_to_gist(db: RugWatchDB | None = None) -> dict[str, Any]:
    db = db or RugWatchDB()
    body = _payload_from_db(db)
    content = json.dumps(body, indent=2)
    fname = gist_filename()
    gid = gist_id()
    description = "RugWatch wallets (legacy Gist store)"

    if gid:
        data = _request_json(
            "PATCH",
            f"{GIST_API}/{gid}",
            {"description": description, "files": {fname: {"content": content}}},
        )
        action = "updated"
    else:
        data = _request_json(
            "POST",
            GIST_API,
            {
                "description": description,
                "public": gist_public(),
                "files": {fname: {"content": content}},
            },
        )
        action = "created"
        new_id = data.get("id")
        if new_id:
            _save_env_key("RUGWATCH_GIST_ID", str(new_id))
            gid = str(new_id)

    raw_url = None
    files = data.get("files") or {}
    if isinstance(files, dict) and fname in files:
        raw_url = (files[fname] or {}).get("raw_url")
    if raw_url:
        os.environ["RUGWATCH_WALLETS_URL"] = str(raw_url)

    return {
        "ok": True,
        "action": action,
        "mode": "gist",
        "gist_id": gid or data.get("id"),
        "html_url": data.get("html_url"),
        "raw_url": raw_url,
        "wallet_count": body["count"],
        "note": "Legacy separate Gist. Prefer RUGWATCH_CLOUD=repo so wallets live in the same folder/repo.",
    }


def pull_from_gist(
    db: RugWatchDB | None = None,
    *,
    max_wallets: int | None = None,
) -> dict[str, Any]:
    db = db or RugWatchDB()
    gid = gist_id()
    if not gid:
        from .remote_wallets import pull_remote_into_db

        r = pull_remote_into_db(db)
        if r.get("ok"):
            r["mode"] = "gist"
            r["source"] = "wallets_url"
        return r

    data = _request_json("GET", f"{GIST_API}/{gid}")
    files = data.get("files") or {}
    fname = gist_filename()
    file_obj = files.get(fname) if isinstance(files, dict) else None
    if not file_obj and isinstance(files, dict) and files:
        file_obj = next(iter(files.values()))
    content = (file_obj or {}).get("content") if isinstance(file_obj, dict) else None
    if not content and isinstance(file_obj, dict) and file_obj.get("raw_url"):
        from .remote_wallets import fetch_wallets_from_url

        items = fetch_wallets_from_url(str(file_obj["raw_url"]))
    elif content:
        items = parse_wallet_payload(json.loads(content))
    else:
        return {"ok": False, "error": f"Gist {gid} has no wallet content"}

    limited = max_wallets is not None and max_wallets > 0
    if limited:
        items = items[:max_wallets]
    stats = db.import_wallets(items, source_default="cloud_gist")
    out = {
        "ok": True,
        "mode": "gist",
        "source": "gist_api",
        "gist_id": gid,
        "imported": stats["imported"],
        "skipped": stats["skipped"],
        "db_wallets": db.stats().get("wallets"),
    }
    if limited:
        out["max_wallets"] = max_wallets
        out["considered"] = len(items)
        out["note"] = f"Limited pull: considered {len(items)} cloud wallet(s) (max {max_wallets})"
    return out


# ── Unified API ───────────────────────────────────────────────────────

def push_to_cloud(db: RugWatchDB | None = None) -> dict[str, Any]:
    mode = cloud_mode()
    if mode == "off":
        return {"ok": False, "error": "RUGWATCH_CLOUD=off"}
    if not github_token():
        return {
            "ok": False,
            "error": "Set GITHUB_TOKEN in .env (see UPLOAD-RUGWATCH-TO-GITHUB.txt)",
        }
    if mode == "repo":
        if not github_repo():
            return {
                "ok": False,
                "error": "Set RUGWATCH_GITHUB_REPO=YourUser/RugWatch (whole project on GitHub)",
            }
        return push_to_repo(db)
    return push_to_gist(db)


def pull_from_cloud(
    db: RugWatchDB | None = None,
    *,
    max_wallets: int | None = None,
) -> dict[str, Any]:
    """
    Pull cloud wallets into local DB.

    max_wallets: optional cap (first N wallets from cloud). None = all.
    """
    mode = cloud_mode()
    if mode == "off":
        return {"ok": False, "error": "RUGWATCH_CLOUD=off"}
    if mode == "repo":
        if not github_token() or not github_repo():
            return {
                "ok": False,
                "error": "Need GITHUB_TOKEN + RUGWATCH_GITHUB_REPO for repo cloud",
            }
        return pull_from_repo(db, max_wallets=max_wallets)
    if not github_token() and not config.wallets_remote_url():
        return {"ok": False, "error": "Need GITHUB_TOKEN or RUGWATCH_WALLETS_URL"}
    return pull_from_gist(db, max_wallets=max_wallets)


def sync_after_manual_change(db: RugWatchDB | None = None) -> dict[str, Any] | None:
    if not cloud_enabled():
        return None
    try:
        return push_to_cloud(db)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def ensure_cloud_cache(db: RugWatchDB | None = None) -> dict[str, Any]:
    db = db or RugWatchDB()
    mode = cloud_mode()
    if mode == "off" or not github_token():
        return {
            "ok": False,
            "skipped": True,
            "storage": "local_only",
            "local_path": str(db.path),
            "error": (
                "Put the WHOLE RugWatch folder on GitHub, then set in .env:\n"
                "  RUGWATCH_CLOUD=repo\n"
                "  RUGWATCH_GITHUB_REPO=YourUser/RugWatch\n"
                "  GITHUB_TOKEN=ghp_...  (repo contents permission)\n"
                "See UPLOAD-RUGWATCH-TO-GITHUB.txt"
            ),
        }

    if mode == "repo" and not github_repo():
        return {
            "ok": False,
            "skipped": True,
            "error": "Set RUGWATCH_GITHUB_REPO=YourUser/RugWatch after uploading the folder.",
            "storage": "local_only",
        }

    # Prefer pull; if file missing, push creates it in the same repo
    try:
        r = pull_from_cloud(db)
        if r.get("ok") and (r.get("imported") or 0) == 0 and mode == "repo":
            # ensure file exists in repo
            try:
                pr = push_to_cloud(db)
                r["bootstrap_push"] = pr
            except Exception as exc:  # noqa: BLE001
                r["bootstrap_push"] = {"ok": False, "error": str(exc)}
        r["storage"] = "github_repo" if mode == "repo" else "gist"
        r["primary"] = cloud_primary()
        r["local_cache"] = str(db.path)
        return r
    except Exception as exc:  # noqa: BLE001
        # try create
        try:
            pr = push_to_cloud(db)
            pr["storage"] = "github_repo" if mode == "repo" else "gist"
            pr["local_cache"] = str(db.path)
            return pr
        except Exception as exc2:  # noqa: BLE001
            return {"ok": False, "error": f"{exc} | push: {exc2}", "storage": mode}


def cloud_status() -> dict[str, Any]:
    mode = cloud_mode()
    enabled = cloud_enabled()
    if mode == "repo" and enabled:
        storage = f"github_repo:{github_repo()}/{github_wallets_path()}"
    elif mode == "gist" and enabled:
        storage = f"gist:{gist_id() or 'pending'}"
    else:
        storage = "local_sqlite"
    return {
        "cloud_enabled": enabled,
        "cloud_primary": cloud_primary(),
        "mode": mode,
        "has_token": bool(github_token()),
        "repo": github_repo(),
        "repo_path": github_wallets_path() if mode == "repo" else None,
        "branch": github_branch() if mode == "repo" else None,
        "gist_id": gist_id() if mode == "gist" else None,
        "wallets_url": config.wallets_remote_url(),
        "storage": storage,
        "cloud_shard_max": config.cloud_shard_max() if mode == "repo" else None,
        "cloud_index": config.cloud_index_path() if mode == "repo" else None,
        "local_db_max": config.local_db_max(),
        "note": (
            "Whole RugWatch folder on GitHub = one place. "
            "Wallets live in data/wallets_cloud.json (+ _002…) with data/wallets_index.json. "
            f"Auto-shard at {config.cloud_shard_max()} wallets/file; "
            f"local DB auto-shard at {config.local_db_max()} wallets/file."
            if mode == "repo"
            else "Gist is a separate cloud object; use mode=repo to keep everything together."
        ),
    }


def fetch_cloud_address_set() -> set[str]:
    """
    All wallet addresses currently in the cloud store (repo shards or gist).
    Used to ignore upload of wallets that already exist in cloud even if local
    DB was wiped (free Render) or is empty.
    Returns empty set if cloud is off / unreachable (caller still checks local).
    """
    mode = cloud_mode()
    addrs: set[str] = set()
    if mode == "off":
        return addrs

    def _absorb(items: list[dict[str, Any]]) -> None:
        for it in items or []:
            if not isinstance(it, dict):
                continue
            a = (it.get("address") or it.get("wallet") or "").strip()
            if a and len(a) >= 32:
                addrs.add(a)

    try:
        if mode == "repo":
            if not github_token() or not github_repo():
                return addrs
            index_path = config.cloud_index_path()
            index = _get_repo_file_json(index_path)
            paths: list[str] = []
            if isinstance(index, dict) and index.get("format") == "rugwatch_wallets_index_v1":
                for s in index.get("shards") or []:
                    if isinstance(s, dict) and s.get("path"):
                        paths.append(str(s["path"]))
            if not paths:
                paths = [github_wallets_path()]
            for path in paths:
                parsed = _get_repo_file_json(path)
                if parsed is None:
                    continue
                _absorb(parse_wallet_payload(parsed))
            return addrs

        # gist / raw URL fallback
        raw_url = config.wallets_remote_url()
        if mode == "gist" and gist_id() and github_token():
            try:
                data = _request_json("GET", f"{GIST_API}/{gist_id()}")
                files = data.get("files") or {}
                fname = gist_filename()
                content = ""
                if fname in files:
                    content = (files[fname] or {}).get("content") or ""
                else:
                    for meta in files.values():
                        content = (meta or {}).get("content") or ""
                        if content:
                            break
                if content.strip():
                    _absorb(parse_wallet_payload(json.loads(content)))
            except Exception:  # noqa: BLE001
                pass
        elif raw_url:
            try:
                from .remote_wallets import fetch_wallets_from_url

                _absorb(fetch_wallets_from_url(raw_url))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        return addrs
    return addrs


def fetch_cloud_wallet_count() -> dict[str, Any]:
    """
    Count wallets currently stored in the cloud (sum of all shards when indexed).
    Does NOT import into the local DB — read-only count for the UI pill.
    """
    mode = cloud_mode()
    if mode == "off":
        return {"ok": False, "count": None, "error": "cloud off", "storage": "local_only"}
    if not github_token() and mode != "gist":
        # gist can sometimes use public raw URL without token; still try token path first
        if not config.wallets_remote_url():
            return {
                "ok": False,
                "count": None,
                "error": "no GITHUB_TOKEN / cloud not configured",
                "storage": "local_only",
            }

    try:
        if mode == "repo":
            if not github_token() or not github_repo():
                return {
                    "ok": False,
                    "count": None,
                    "error": "need GITHUB_TOKEN + RUGWATCH_GITHUB_REPO",
                    "storage": "local_only",
                }
            index_path = config.cloud_index_path()
            index = _get_repo_file_json(index_path)
            if isinstance(index, dict) and index.get("format") == "rugwatch_wallets_index_v1":
                total = index.get("total_count")
                shards = index.get("shards") or []
                if not isinstance(total, int):
                    total = 0
                    for s in shards:
                        if isinstance(s, dict):
                            total += int(s.get("count") or 0)
                return {
                    "ok": True,
                    "count": int(total),
                    "cloud_shards": len(shards),
                    "storage": f"github_repo:{github_repo()}/{index_path}",
                    "mode": "repo",
                    "index": True,
                }

            path = github_wallets_path()
            parsed = _get_repo_file_json(path)
            if parsed is None:
                return {
                    "ok": True,
                    "count": 0,
                    "cloud_shards": 0,
                    "storage": f"github_repo:{github_repo()}/{path}",
                    "note": "cloud file not created yet",
                }
            items = parse_wallet_payload(parsed)
            n = len(items)
            if isinstance(parsed, dict) and isinstance(parsed.get("count"), int):
                if int(parsed["count"]) >= n:
                    n = int(parsed["count"])
            return {
                "ok": True,
                "count": n,
                "cloud_shards": 1,
                "storage": f"github_repo:{github_repo()}/{path}",
                "mode": "repo",
            }

        # gist / raw URL
        raw_url = config.wallets_remote_url()
        if mode == "gist" and gist_id() and github_token():
            g = _request_json("GET", f"{GIST_API}/{gist_id()}")
            files = g.get("files") or {}
            name = gist_filename()
            fobj = files.get(name) or (next(iter(files.values())) if files else None)
            if not fobj:
                return {"ok": True, "count": 0, "storage": f"gist:{gist_id()}", "mode": "gist"}
            content = fobj.get("content")
            if content is None and fobj.get("raw_url"):
                raw_url = fobj["raw_url"]
            elif content is not None:
                parsed = json.loads(content)
                items = parse_wallet_payload(parsed)
                return {
                    "ok": True,
                    "count": len(items),
                    "storage": f"gist:{gist_id()}",
                    "mode": "gist",
                }
        if raw_url:
            req = urllib.request.Request(
                raw_url, headers={**DEFAULT_HEADERS, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as resp:  # noqa: S310
                raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            items = parse_wallet_payload(parsed)
            return {
                "ok": True,
                "count": len(items),
                "storage": raw_url,
                "mode": mode,
            }
        return {
            "ok": False,
            "count": None,
            "error": "no gist id / raw URL",
            "storage": "local_only",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "count": None, "error": str(exc), "storage": mode}
