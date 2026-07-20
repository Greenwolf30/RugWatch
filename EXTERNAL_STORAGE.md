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
data/rugwatch.db                   ← primary local DB (not uploaded)
data/rugwatch_002.db               ← auto-created when primary hits local max
.env                               ← secrets only on your PC
```

## Setup

See **UPLOAD-RUGWATCH-TO-GITHUB.txt**

```text
RUGWATCH_CLOUD=repo
RUGWATCH_GITHUB_REPO=YourUser/RugWatch
GITHUB_TOKEN=ghp_...
RUGWATCH_CLOUD_SHARD_MAX=100000
RUGWATCH_LOCAL_DB_MAX=100000
```

Then (website: **Push cloud** / **Pull cloud**, or CLI):

```powershell
python -m rugwatch cloud-init
python -m rugwatch push-cloud
python -m rugwatch pull-cloud
```

Working store is local multi-DB (`rugwatch.db` + overflow).  
**Push cloud** packs all local wallets into shard files + `wallets_index.json`.  
**Pull cloud** merges **every** listed cloud shard into local shards.

---

## Auto-sharding (new DBs / cloud files when full)

| Store | Cap per file (default) | What happens when full |
|--------|-------------------------|-------------------------|
| **Cloud JSON** | `RUGWATCH_CLOUD_SHARD_MAX` = **100000** | Creates `wallets_cloud_002.json`, then `_003`, … and updates `wallets_index.json` |
| **Local SQLite** | `RUGWATCH_LOCAL_DB_MAX` = **100000** | Creates `rugwatch_002.db`, then `_003`, … New wallets go into the newest file under the cap |

- Website **Push cloud** writes **all** needed shards + index.  
- Website **Pull cloud** reads **all** shards in the index.  
- Counts (`wallets` pill / `cloud` pill) are **totals across all shards**.  
- For ATC multi-shard, point `RUGWATCH_WALLETS_URL` at the **index** raw URL when the bridge supports it:  
  `https://raw.githubusercontent.com/YourUser/RugWatch/main/data/wallets_index.json`

## Cloud capacity (how many wallets)

RugWatch does **not** hard-cap the **total** number of wallets.  
Each **shard file** still has practical size limits; auto-sharding opens the next file at the configured max.

### Hard limits (GitHub)

| Limit | Meaning |
|--------|---------|
| **~100 MB** | Hard max for a normal file in a GitHub repo |
| **~1 MB** | Best zone for the Contents API used by Push/Pull cloud |
| **No fixed wallet count** | Code does not stop at 1,000 / 10,000 / etc. |

### Rough size (with labels/notes like Ruggers exports)

About **350–400 bytes per wallet** when notes are included.

| File size | Approx. wallets |
|-----------|------------------|
| **1 MB** | ~2,500–3,000 |
| **5 MB** | ~12,000–15,000 |
| **10 MB** | ~25,000–30,000 |
| **50 MB** | ~100,000+ (gets heavy) |
| **100 MB** | theoretical max — not recommended |

Address-only rows (short notes) fit **several times more**.

### Practical recommendation

| Range | Guidance |
|--------|----------|
| **Thousands → ~10k–30k** | Comfortable: fast Push/Pull, fine for website + ATC on Render |
| **~50k–100k+** | Still works, but slower loads and larger downloads |
| **Huge multi‑MB list every push** | Risk of timeouts, slow ATC scans, API friction |

**Effective target for RugWatch + ATC flags:** about **10,000–30,000 wallets**.  
Hundreds of thousands are possible on GitHub but not ideal for speed.

Local SQLite (`data/rugwatch.db`) can hold more than you push; only what you **Push cloud** is what ATC reads via `RUGWATCH_WALLETS_URL`.
