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
**Push cloud** **merges** local wallets **into** cloud (union by address).  
**Cloud wallets are never erased** by Push or Pull — empty local cannot wipe GitHub.  
**Pull cloud** merges every listed cloud file into the local database only (does not write cloud).

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

| Wallets | Shards (at 100k each) | Rough cloud JSON size (order of magnitude) |
|---------|----------------------|--------------------------------------------|
| 10,000 | 1 | ~2–5 MB |
| 100,000 | 1 | ~20–50 MB |
| **200,000** | **2** | **~40–100 MB** |
| 500,000 | 5 | ~100–250 MB |
| 1,000,000 | 10 | ~200–500 MB |
| 10,000,000 | many | multi‑GB |

Local SQLite (after a full Pull) is usually the **same order of magnitude** as the cloud total for that wallet count.

**Example — 200,000 wallets maxed on RugWatch**

| Piece | Where it lives | Rough size |
|-------|----------------|------------|
| Cloud JSON (2 shards + index) | GitHub `data/wallets_cloud*.json` | **~40–100 MB** |
| Local DB (if fully pulled) | `data/rugwatch.db` (+ `_002` if needed) | **~40–100 MB** again on that machine |
| RugWatch **application code** | repo / deploy | **~few MB** (tiny next to wallets) |
| **Whole stack if cloud + one full local copy** | — | **~100–200 MB** wallet data + small code |

Disk rarely “runs out” first on a home PC. **RAM during import** and **trying to list everything in the browser** usually hurt first.

---

### 2b) Is ~200 MB a lot for a laptop?

**No. ~200 MB is tiny for a normal laptop.**

| Size | Feels like |
|------|------------|
| **200 MB** | A few phone photos, or part of one music album |
| 1 GB | About 5× that |
| 256–512 GB+ | Typical whole laptop drive |

- **200 MB** is under **0.1%** of a **256 GB** drive — you will not notice it for storage.
- Loading **~200 MB into RAM once** is fine on a typical laptop (**8 GB+ RAM**).
- Pressure at high wallet counts is usually **slow Push/Pull**, **free-host RAM**, or **UI listing**, not “disk full.”

**Rule of thumb:** wallet data in the **tens–low hundreds of MB** is normal laptop territory; multi‑GB only appears if you go toward **millions** of wallets with long notes.

---

### 2c) What is *not* part of RugWatch cloud size (ATC website Logs)

**Actual Token Checker (website) Logs** are **not** stored on RugWatch, GitHub cloud, or the Render server.

| Data | Where it lives | Grows RugWatch cloud? |
|------|----------------|------------------------|
| RugWatch wallet list (Push cloud) | GitHub + optional local DB | **Yes** |
| ATC website **Logs** (History tab, max **200** searches) | **Browser localStorage only** (`adtc_history_log`) | **No** |
| ATC **Ruggers** track (browser) | Browser storage | **No** |
| ATC application code | ATC deploy / repo (~**1 MB**) | **No** |

Maxed ATC website Logs (~**200** full Analyze snapshots) is roughly **~3–5 MB in that user’s browser** — separate from every other user, and **0 MB** on the RugWatch server.

So when estimating “how big can things get”:

1. **RugWatch cloud / local wallets** → server + GitHub (see tables above).  
2. **ATC Logs** → each user’s browser only (cap **200** entries; oldest deleted on later lookups).  
3. **App code** → stays small; **wallets** dominate disk size.

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
| ~200k wallets on disk? | About **~40–100 MB** cloud (2 shards); **~100–200 MB** if you also keep a full local pull |
| Is ~200 MB a lot for a laptop? | **No** — tiny vs a normal drive (see §2b) |
| Do ATC website Logs count toward cloud? | **No** — browser only, max 200 searches (~few MB) |
| Safe on a normal home PC? | **Hundreds of thousands easily**; **millions** if sharded and RAM allows |
| Free hosting OK? | **Yes for light personal use** + cloud; not for heavy multi-user load |
| Still call other APIs on free? | **Yes**, subject to provider free quotas |
| What breaks first? | **RAM on pull**, **UI listing**, or **API 429s** — not usually disk alone |

---

## Pull cloud: does it only load 100,000 wallets?

**No.** **100,000 is per cloud *file* (shard), not the maximum a Pull loads in total.**

### What one Pull does

1. Reads **`data/wallets_index.json`**
2. Loads **every** shard listed there (`wallets_cloud.json`, `wallets_cloud_002.json`, …)
3. Merges each into the **local multi-DB** (`rugwatch.db`, then `rugwatch_002.db` when full, etc.)

So if cloud has **3 shards × ~100k**, one Pull tries to load **~300,000 wallets**, not only 100k.

| Cloud layout | What Pull loads |
|--------------|-----------------|
| 1 file, e.g. 46 wallets | **All of them** |
| 1 full shard | Up to **~100,000** |
| 5 full shards | Up to **~500,000** (all of them) |
| N shards in the index | **All N files** |

### What 100k *does* mean

| Cap | Meaning |
|-----|--------|
| **Cloud shard** | One JSON file tops out near **100k**; the **next** wallet goes in the **next** shard file on **Push cloud** |
| **Local DB** | One SQLite file tops out near **100k**; the next wallet goes in **`rugwatch_002.db`**, etc. |
| **Pull cloud** | Loads **all** cloud shards (total can be **greater than 100k**) |

### What happens if you keep pulling

| Situation | Result |
|-----------|--------|
| Same wallets already in local DB | **Skipped** — no duplicates (`skip_existing` on import) |
| New wallets only in cloud | **Imported** |
| Local DB hits ~100k | New local file: `rugwatch_002.db`, … |
| Pull again with nothing new | **Imported ≈ 0**, high skipped — safe, list size does not grow from copies |

**Pull is a merge**, not “download only 100k then stop forever.”  
Repeating Pull is mostly **idempotent**: addresses already local are not stored twice.

### ATC / other readers vs RugWatch Pull

| Consumer | Behavior |
|----------|----------|
| **RugWatch website / desktop Pull cloud** | Uses the **index** → loads **every** shard |
| **ATC** with `.../data/wallets_index.json` | Should load **every** shard listed in the index |
| **ATC** (or anything) pointed only at a **single** `wallets_cloud.json` | May only see **one** shard (~100k max for that file) |

**Always prefer the index URL** for flags:

```text
RUGWATCH_WALLETS_URL=https://raw.githubusercontent.com/YourUser/RugWatch/main/data/wallets_index.json
```

### Practical takeaway

- **One Pull ≠ only 100k max.** It is “**all shards in the index**.”  
- **Keep pulling** → only **new** cloud wallets are added; existing ones are **skipped**.  
- Risk at huge scale is **RAM/time** if the cloud has many full shards — not “the app only allows one 100k pull.”
