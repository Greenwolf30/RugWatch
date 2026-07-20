# One cloud home: whole RugWatch on GitHub

Do **not** split “code in one place, wallets in another Gist” if you want one folder.

## Layout on GitHub

```text
YourUser/RugWatch/                 ← whole project
  rugwatch/
  desktop_app.py
  data/
    wallets_cloud.json             ← ALL logged wallets (source of truth)
  ...
```

Local PC:

```text
data/rugwatch.db                   ← cache only (not uploaded)
.env                               ← secrets only on your PC
```

## Setup

See **UPLOAD-RUGWATCH-TO-GITHUB.txt**

```text
RUGWATCH_CLOUD=repo
RUGWATCH_GITHUB_REPO=YourUser/RugWatch
GITHUB_TOKEN=ghp_...
```

Then:

```powershell
python -m rugwatch cloud-init
python -m rugwatch push-cloud
python -m rugwatch pull-cloud
```

Working store is local `data/rugwatch.db`.  
**Push cloud** uploads wallets to your repo `data/wallets_cloud.json` (or Gist).  
**Pull cloud** imports that file back into the local DB.

---

## Cloud capacity (how many wallets)

RugWatch does **not** hard-cap the number of wallets in the cloud.  
Capacity is limited by **one GitHub JSON file** (`data/wallets_cloud.json`) and what stays practical for the website + ATC.

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
