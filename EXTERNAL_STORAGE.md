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
