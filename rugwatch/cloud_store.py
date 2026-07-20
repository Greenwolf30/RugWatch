"""
Cloud wallet store — one place with the whole RugWatch project on GitHub.

Primary mode (recommended): same GitHub REPO as the code
  RUGWATCH_CLOUD=repo
  RUGWATCH_GITHUB_REPO=YourUser/RugWatch
  GITHUB_TOKEN=ghp_...   (repo scope: contents read/write)
  RUGWATCH_GITHUB_PATH=data/wallets_cloud.json

Legacy mode: separate Gist
  RUGWATCH_CLOUD=gist
  GITHUB_TOKEN=... (gist scope)
  RUGWATCH_GIST_ID=...

Local data/rugwatch.db is only a cache so the desktop app runs offline-ish.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
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


def _payload_from_db(db: RugWatchDB) -> dict[str, Any]:
    wallets = db.export_wallets(min_score=0)
    return {
        "format": "rugwatch_wallets_v1",
        "wallets": wallets,
        "count": len(wallets),
        "note": "RugWatch wallet list — primary cloud store (same project on GitHub)",
    }


# ── Repo mode (whole project on GitHub) ───────────────────────────────

def _repo_contents_url(path: str | None = None) -> str:
    repo = github_repo()
    if not repo or "/" not in repo:
        raise RuntimeError(
            "Set RUGWATCH_GITHUB_REPO=YourUser/RugWatch (same repo as the whole folder)."
        )
    p = path or github_wallets_path()
    return f"{REPO_API}/{repo}/contents/{p}"


def push_to_repo(db: RugWatchDB | None = None) -> dict[str, Any]:
    db = db or RugWatchDB()
    body = _payload_from_db(db)
    content = json.dumps(body, indent=2)
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    path = github_wallets_path()
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
        "message": f"RugWatch: sync wallets ({body['count']} addresses)",
        "content": b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    data = _request_json("PUT", url, payload)
    html = (data.get("content") or {}).get("html_url") or data.get("commit", {}).get("html_url")
    raw = (
        f"https://raw.githubusercontent.com/{github_repo()}/{branch}/{path}"
    )
    os.environ["RUGWATCH_WALLETS_URL"] = raw

    return {
        "ok": True,
        "action": "updated" if sha else "created",
        "mode": "repo",
        "repo": github_repo(),
        "path": path,
        "branch": branch,
        "html_url": html,
        "raw_url": raw,
        "wallet_count": body["count"],
        "note": "Wallets stored IN the same GitHub repo as RugWatch (not a separate Gist).",
    }


def pull_from_repo(db: RugWatchDB | None = None) -> dict[str, Any]:
    db = db or RugWatchDB()
    path = github_wallets_path()
    url = _repo_contents_url(path)
    branch = github_branch()
    try:
        data = _request_json("GET", f"{url}?ref={branch}")
    except RuntimeError as exc:
        if "404" in str(exc):
            return {
                "ok": True,
                "mode": "repo",
                "imported": 0,
                "note": f"No {path} in repo yet — add a wallet and push, or run push-cloud.",
                "repo": github_repo(),
            }
        raise

    content_b64 = data.get("content") or ""
    if not content_b64:
        return {"ok": False, "error": "Empty file content from GitHub"}
    # GitHub may wrap base64 with newlines
    raw = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
    parsed = json.loads(raw)
    items = parse_wallet_payload(parsed)
    stats = db.import_wallets(items, source_default="cloud_repo")
    return {
        "ok": True,
        "mode": "repo",
        "source": "github_repo",
        "repo": github_repo(),
        "path": path,
        "imported": stats["imported"],
        "skipped": stats["skipped"],
        "db_wallets": db.stats().get("wallets"),
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


def pull_from_gist(db: RugWatchDB | None = None) -> dict[str, Any]:
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

    stats = db.import_wallets(items, source_default="cloud_gist")
    return {
        "ok": True,
        "mode": "gist",
        "source": "gist_api",
        "gist_id": gid,
        "imported": stats["imported"],
        "skipped": stats["skipped"],
        "db_wallets": db.stats().get("wallets"),
    }


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


def pull_from_cloud(db: RugWatchDB | None = None) -> dict[str, Any]:
    mode = cloud_mode()
    if mode == "off":
        return {"ok": False, "error": "RUGWATCH_CLOUD=off"}
    if mode == "repo":
        if not github_token() or not github_repo():
            return {
                "ok": False,
                "error": "Need GITHUB_TOKEN + RUGWATCH_GITHUB_REPO for repo cloud",
            }
        return pull_from_repo(db)
    if not github_token() and not config.wallets_remote_url():
        return {"ok": False, "error": "Need GITHUB_TOKEN or RUGWATCH_WALLETS_URL"}
    return pull_from_gist(db)


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
        "note": (
            "Whole RugWatch folder on GitHub = one place. "
            "Wallets file lives inside that repo at data/wallets_cloud.json"
            if mode == "repo"
            else "Gist is a separate cloud object; use mode=repo to keep everything together."
        ),
    }


def fetch_cloud_wallet_count() -> dict[str, Any]:
    """
    Count wallets currently stored in the cloud file (repo or gist).
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
            path = github_wallets_path()
            url = _repo_contents_url(path)
            branch = github_branch()
            try:
                data = _request_json("GET", f"{url}?ref={branch}")
            except RuntimeError as exc:
                if "404" in str(exc):
                    return {
                        "ok": True,
                        "count": 0,
                        "storage": f"github_repo:{github_repo()}/{path}",
                        "note": "cloud file not created yet",
                    }
                raise
            content_b64 = data.get("content") or ""
            if not content_b64:
                return {"ok": True, "count": 0, "storage": f"github_repo:{github_repo()}/{path}"}
            raw = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8")
            parsed = json.loads(raw)
            items = parse_wallet_payload(parsed)
            # Prefer explicit count field when present and matches list shape
            if isinstance(parsed, dict) and isinstance(parsed.get("count"), int):
                n = int(parsed["count"])
                if n >= len(items):
                    return {
                        "ok": True,
                        "count": n,
                        "storage": f"github_repo:{github_repo()}/{path}",
                        "mode": "repo",
                    }
            return {
                "ok": True,
                "count": len(items),
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
