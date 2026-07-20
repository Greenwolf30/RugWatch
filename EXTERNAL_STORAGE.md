# One cloud home: whole RugWatch on GitHub

Do **not** split “code in one place, wallets in another Gist” if you want one folder.

## Layout on GitHub

```text
YourUser/RugWatch/                 ← whole project
  rugwatch/
  desktop_app.py
  data/
    wallets_index.json             ← lists every cloud wallet shard
    wallets_cloud.json             ← shard 1 (up to RUGWATCH_CLOUD_SHARD_MAX)
    wallets_cloud_002.json         ← auto-created when shard 1 is full
    wallets_cloud_003.json         ← …
  ...
```

Local PC:

```text
data/rugwatch.db                   ← primary local database
data/rugwatch_002.db               ← created automatically when the primary fills
```

## Setup

See **UPLOAD-RUGWATCH-TO-GITHUB.txt** for connecting the project folder and cloud list to GitHub.

Cloud capacity settings (defaults):

```text
RUGWATCH_CLOUD=repo
RUGWATCH_GITHUB_REPO=YourUser/RugWatch
RUGWATCH_CLOUD_SHARD_MAX=100000
RUGWATCH_LOCAL_DB_MAX=100000
```

Then on the website use **Push cloud** / **Pull cloud**, or from a terminal:

```powershell
python -m rugwatch cloud-init
python -m rugwatch push-cloud
python -m rugwatch pull-cloud
```

Working store is the local multi-file database (`rugwatch.db` and overflow files).  
**Push cloud** packs all local wallets into cloud files + `wallets_index.json`.  
**Pull cloud** merges every listed cloud file into the local database.

---

## Wallet capacity scheme (current)

RugWatch **auto-shards**. There is **no fixed total wallet cap**.  
When one file fills, the next file is created automatically.

### Per-file limits (defaults)

| Store | Env var | Wallets per file | Next file when full |
|--------|---------|------------------|---------------------|
| **Local SQLite** | `RUGWATCH_LOCAL_DB_MAX` | **100,000** | `rugwatch_002.db`, `rugwatch_003.db`, … |
| **Cloud JSON** | `RUGWATCH_CLOUD_SHARD_MAX` | **100,000** | `wallets_cloud_002.json`, `_003`, … |

Primary files stay: `data/rugwatch.db` and `data/wallets_cloud.json`.  
Cloud also keeps **`data/wallets_index.json`** listing every shard and `total_count`.

### How totals grow

| Shards | Approx. total capacity (at 100k each) |
|--------|----------------------------------------|
| 1 | 100,000 |
| 2 | 200,000 |
| 5 | 500,000 |
| 10 | 1,000,000 |

Website **Push cloud** writes **all** shards + index.  
Website **Pull cloud** merges **every** listed cloud shard into local DBs.  
Pills show **combined totals** across all local / cloud shards.

### Effective use (speed, not hard caps)

| Total wallets | Guidance |
|---------------|----------|
| **Hundreds – few thousand** | Ideal day-to-day |
| **~10,000 – 100,000** | Strong; one local DB + one cloud file |
| **~100,000 – few hundred thousand** | Multi-shard; Push/ATC slower but OK |
| **~1M+** | Possible; expect heavy Push and ATC loads |

Actual Token Checker should use the **index** URL so it always loads every cloud file:

```text
RUGWATCH_WALLETS_URL=https://raw.githubusercontent.com/YourUser/RugWatch/main/data/wallets_index.json
```

### Cloud file size

Each cloud JSON is a normal repository file. About **100,000 wallets per file** is the designed size. Very long notes can make each file larger, so keep notes short when possible.

---

## Capacity limits (full guide)

This section covers **auto-shard caps**, **how many wallets a PC can pull from cloud**, **free hosting limits**, and **external API** limits. Not financial advice — operational guidance only.

### 1) Designed shard caps (app defaults)

RugWatch **auto-shards**. There is **no hard total wallet ceiling** in the app.

| Store | Env var | Default wallets per file | Next file when full |
|--------|---------|--------------------------|---------------------|
| **Local SQLite** | `RUGWATCH_LOCAL_DB_MAX` | **100,000** | `rugwatch_002.db`, `_003`, … |
| **Cloud JSON** | `RUGWATCH_CLOUD_SHARD_MAX` | **100,000** | `wallets_cloud_002.json`, `_003`, … |
| **Cloud index** | `RUGWATCH_CLOUD_INDEX` | `data/wallets_index.json` | Lists every shard + `total_count` |

| Cloud / local shards | Approx. total wallets (at 100k each) |
|----------------------|--------------------------------------|
| 1 | 100,000 |
| 2 | 200,000 |
| 5 | 500,000 |
| 10 | 1,000,000 |
| 50 | 5,000,000 |

**Push cloud** writes all shards + index. **Pull cloud** merges every listed shard into local DBs. UI pills show **combined** totals.

---

### 2) Rough cloud file size (disk)

Each wallet row is roughly **200–500+ bytes** (address, score, notes, labels). Long notes inflate size.

| Wallets | Rough cloud JSON size (order of magnitude) |
|---------|--------------------------------------------|
| 10,000 | ~2–5 MB |
| 100,000 (1 shard) | ~20–50 MB |
| 1,000,000 (10 shards) | ~200–500 MB |
| 10,000,000 | multi‑GB (many shards) |

Disk rarely “runs out” first on a home PC. **RAM during import** and **trying to list everything in the browser** usually hurt first.

---

### 3) How many wallets can one hard drive / PC pull without crashing?

There is **no single crash number**. Limits are **RAM**, **disk**, and **whether the UI tries to render every row**.

Pull downloads JSON → parses in Python → writes SQLite. Peak RAM is often **a few × file size** during import.

| Machine | Comfortable pull | Stretching it | Risky / may freeze |
|---------|------------------|---------------|---------------------|
| Average laptop (**8 GB RAM**) | **100k–300k** | **~500k–1M** | **Several million** at once |
| Strong desktop (**16–32 GB**) | **1M+** | **a few million** | Tens of millions without care |
| Free Render web service | **Tens of thousands – low hundreds of k** | Can OOM / restart | Large multi‑shard pull on free tier |

| Action | What limits it |
|--------|----------------|
| **Pull cloud → local DB** | RAM + disk (SQLite handles large DBs better than one giant list in the UI) |
| **Show all wallets in the website list** | Browser/UI — tens/hundreds of thousands of DOM rows can freeze even if DB is fine |
| **ATC flags from cloud** | Free server RAM + loading shards for matching |

**Rule of thumb (home PC, auto-shard):**

| Target | Guidance |
|--------|----------|
| **Hundreds – few thousand** | Ideal day-to-day |
| **~10k – 100k** | Strong; often one local DB + one cloud file |
| **~100k – few hundred thousand** | Multi-shard; Push/ATC slower but OK |
| **~1M+** | Possible with shards + enough RAM; heavy Push/Pull |
| **UI list** | Keep list views **capped** — don’t dump the full cloud into the browser |

---

### 4) Free hosting (e.g. Render free) — can the server still pull other APIs?

**Yes** — free web services can still call Helius, Birdeye, GitHub, DexScreener, Pump.fun, etc. They are **not blocked** from outbound HTTPS. Limits are **sleep, CPU, concurrent load**, and **provider rate limits**.

| Free web behavior | What it means for RugWatch / ATC |
|-------------------|----------------------------------|
| **Sleep after idle** (~15 min no traffic) | First request after sleep: **~30–90s** cold start |
| **One small instance** | Fine for light personal use; many simultaneous Analyzes/Uploads can time out |
| **CPU / RAM** | Full Analyze (holders + bundles + cloud) is heavy — about **1–2 long jobs** at a time is realistic |
| **Ephemeral disk** | Local SQLite **wiped** on restart — use **Push/Pull cloud** (GitHub) for durable wallets |
| **Outbound APIs** | Still work; provider free tiers may 429 or cap monthly usage |

There is usually **no fixed public “X requests/day”** for free web hosting itself. Real caps:

1. Host sleep / timeouts  
2. **API key free tiers** (Helius, Birdeye, …)  
3. **GitHub** API limits if using a PAT heavily  

| Use case | Free account |
|----------|----------------|
| You + a few friends, occasional use | **Yes** — expect cold starts |
| Pull cloud + flags | **Yes** if `GITHUB_TOKEN` / cloud env set |
| Many users clicking Analyze at once | **Poor** — timeouts, 429s |
| Always-fast, no sleep | **No** — need paid always-on |

**Two free services (RugWatch + Actual Token Checker)** can sleep **separately**. Upload from ATC → RugWatch may wait for RugWatch to wake.

---

### 5) External API limits (often the real bottleneck)

| Source | Typical free / light-use reality |
|--------|----------------------------------|
| **Helius** | Free tier has **monthly request caps** and RPC rate limits; deep scan uses these heavily |
| **Birdeye** | Free/dev keys are **rate-limited** |
| **GitHub** (cloud wallets / Push) | ~**5,000 authenticated req/hour** with a PAT; raw.githubusercontent is usually fine for light reads |
| **DexScreener / Pump.fun / public RPC** | Public endpoints: **rate limits / 429** under load |

Your server **can pull** them; **they** may refuse or slow you when free quotas are hit.

---

### 6) Recommended operating ranges (summary chart)

| Total wallets (cloud + local) | Desktop PC | Free Render website | ATC flags |
|-------------------------------|------------|---------------------|-----------|
| &lt; 10,000 | Excellent | Excellent | Excellent |
| 10,000 – 100,000 | Excellent | OK (cold start OK) | OK |
| 100,000 – 500,000 | Good (multi-shard) | Heavy / may OOM | Slower |
| 1,000,000+ | Possible with care | Not recommended free | Risky free |

---

### 7) Env knobs

```text
RUGWATCH_CLOUD=repo
RUGWATCH_GITHUB_REPO=YourUser/RugWatch
RUGWATCH_CLOUD_SHARD_MAX=100000      # wallets per cloud JSON
RUGWATCH_LOCAL_DB_MAX=100000         # wallets per local SQLite file
RUGWATCH_CLOUD_INDEX=data/wallets_index.json
GITHUB_TOKEN=ghp_...                 # repo contents read/write for Push/Pull
```

ATC (flags / cloud list):

```text
RUGWATCH_WALLETS_URL=https://raw.githubusercontent.com/YourUser/RugWatch/main/data/wallets_index.json
```

Prefer the **index** URL so every shard is loaded.

---

### 8) Bottom line

| Question | Answer |
|----------|--------|
| Hard total wallet cap? | **No** — auto-shard at **100k per file** |
| Safe on a normal home PC? | **Hundreds of thousands easily**; **millions** if sharded and RAM allows |
| Free hosting OK? | **Yes for light personal use** + cloud; not for heavy multi-user load |
| Still call other APIs on free? | **Yes**, subject to provider free quotas |
| What breaks first? | **RAM on pull**, **UI listing**, or **API 429s** — not usually disk alone |
