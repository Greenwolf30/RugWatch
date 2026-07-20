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

ATC (Render) should use the **index** URL so it always loads every cloud shard:

```text
RUGWATCH_WALLETS_URL=https://raw.githubusercontent.com/YourUser/RugWatch/main/data/wallets_index.json
```

### GitHub file-size note

Each cloud JSON is still a normal GitHub file (hard max ~100 MB).  
With short notes, **100,000 wallets per shard** fits the design.  
Very long notes may force earlier/smaller practical shards — lower `RUGWATCH_CLOUD_SHARD_MAX` if pushes time out.
