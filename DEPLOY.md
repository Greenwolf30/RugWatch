# Deploy RugWatch on Render

## 1. Create the Web Service

1. Open [Render Dashboard](https://dashboard.render.com)
2. **New → Web Service**
3. Connect GitHub repo: **Greenwolf30/RugWatch**
4. Settings:

| Field | Value |
|--------|--------|
| **Name** | `rugwatch` (or any name) |
| **Runtime** | Python 3 |
| **Build command** | `pip install -r requirements.txt` |
| **Start command** | `python run_web.py --host 0.0.0.0` |
| **Instance type** | Free (or paid if you want a disk) |

Or use the repo **Blueprint**: **New → Blueprint** → select this repo (`render.yaml`).

---

## 2. Environment variables (API keys & cloud)

In the service → **Environment** → add these.

### Required for cloud Push / Pull

| Key | Example / notes |
|-----|------------------|
| `RUGWATCH_CLOUD` | `repo` |
| `RUGWATCH_CLOUD_PRIMARY` | `1` |
| `RUGWATCH_GITHUB_REPO` | `Greenwolf30/RugWatch` |
| `RUGWATCH_GITHUB_PATH` | `data/wallets_cloud.json` |
| `RUGWATCH_GITHUB_BRANCH` | `main` |
| `RUGWATCH_CLOUD_INDEX` | `data/wallets_index.json` |
| `GITHUB_TOKEN` | Your GitHub personal access token (`repo` scope) — same idea as local |

### Recommended provider keys (same as local RugWatch)

| Key | Used for |
|-----|----------|
| `HELIUS_API_KEY` | Deep scan / RPC |
| `BIRDEYE_API_KEY` | Optional enrichment |
| `SOLSCAN_API_KEY` | Optional (if you use it) |

### Hosting

| Key | Value |
|-----|--------|
| `WEB_HOST` | `0.0.0.0` |
| `WEB_CORS_ORIGINS` | `*` (so Actual Token Checker can call this API if needed) |
| `PORT` | Set automatically by Render — do not override unless you know why |

### Optional security

| Key | Value |
|-----|--------|
| `WEB_API_TOKEN` | Any long random string — browsers must send it as `X-API-Token` for POST |

**Do not** put keys in `web/config.js` or commit them to GitHub.

Copy values from your PC’s private `RugWatch/.env` (do not share that file).

---

## 3. Deploy

1. Save env vars  
2. **Manual Deploy → Deploy latest commit**  
3. Wait until status is **Live**  
4. Open the URL Render gives you, e.g.  
   `https://rugwatch-xxxx.onrender.com/`

---

## 4. Point Actual Token Checker at live RugWatch (optional)

In ATC `web/config.js` (or your static host):

```js
rugwatchUrl: "https://YOUR-RUGWATCH-ON-RENDER.onrender.com/"
```

Redeploy ATC after changing that.

ATC flags from the **wallet list** still use (on ATC’s Render env):

```text
RUGWATCH_WALLETS_URL=https://raw.githubusercontent.com/Greenwolf30/RugWatch/main/data/wallets_index.json
```

That is separate from the RugWatch website URL.

---

## 5. Free-plan notes

- **Ephemeral disk:** local SQLite on free Render is wiped on redeploy/sleep.  
  Use **Push cloud** so wallets live on GitHub; after restart, **Pull cloud** or rely on cloud-primary boot.  
- **Cold start:** first request after idle can take ~30–60s.  
- Prefer a **persistent disk** on a paid plan if you need a durable local DB on the server.

---

## Checklist

- [ ] Repo **Greenwolf30/RugWatch** connected  
- [ ] Start: `python run_web.py --host 0.0.0.0`  
- [ ] `GITHUB_TOKEN` + `RUGWATCH_GITHUB_REPO` set  
- [ ] `HELIUS_API_KEY` (and optional Birdeye/Solscan) set  
- [ ] Deploy live → open `/` and `/docs.html`  
- [ ] Test **Push cloud** once  
- [ ] Optional: set ATC `rugwatchUrl` to the new Render URL  
