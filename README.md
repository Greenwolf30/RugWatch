# RugWatch

Standalone project for tracking wallets involved in Solana rugs/scams, storing them in a local database, and watching new launches for those wallets.

Not financial advice. Heuristics only — false positives happen.

---

## What it does

1. **Scan a mint** (token address) and review suggested wallets.  
2. **Store** wallets, incidents, links, and alerts in a local database.  
3. **Monitor** new launches against your wallet list.  
4. **Push cloud** to keep an online list for Actual Token Checker.

---

## Setup

```text
cd C:\Users\levyr\RugWatch
pip install -r requirements.txt
python -m rugwatch init-db
python run_web.py --port 8790
```

Open http://127.0.0.1:8790/ — on-site docs: `/docs.html`.

**Capacity:** about **100,000** wallets per local DB file and per cloud file, then a new file is created automatically (no fixed total cap).  
**Pull cloud** loads **all** shards from the index (not “only 100k total”); re-pull skips wallets already local.  
Full limits + Pull FAQ: **EXTERNAL_STORAGE.md** → *Capacity limits* and *Pull cloud: does it only load 100,000 wallets?*

**Actual Token Checker:** Ruggers **Upload** can send sellers here; Analyze flags read local and/or cloud lists. Full guide: **RugCheck Documentation.md**.

---

## CLI

```text
# Create DB
python -m rugwatch init-db

# Scan a mint (seed the DB from a known rug / risky token)
# Scan a mint (manual-only by default: suggests wallets, does NOT auto-save)
python -m rugwatch scan <MINT_ADDRESS>

# Manually add a wallet (only way wallets enter DB unless you import)
python -m rugwatch add-wallet <WALLET> --score 80 --notes "serial"

# Clear all local data
python -m rugwatch clear-db --yes

# Export / import / cloud JSON — see EXTERNAL_STORAGE.md (includes cloud capacity)
# and RugCheck Documentation.md
python -m rugwatch export-wallets -o wallets_export.json
python -m rugwatch pull-remote
python -m rugwatch push-cloud
python -m rugwatch pull-cloud

# List flagged wallets
python -m rugwatch list-wallets --min-score 40

# Manually add a wallet
python -m rugwatch add-wallet <WALLET> --score 80 --label serial --notes "from telegram"

# One-shot launch check
python -m rugwatch monitor --once

# Continuous monitor (Ctrl+C to stop)
python -m rugwatch monitor
python run_monitor.py

# Recent alerts
python -m rugwatch alerts
python -m rugwatch stats
```

---

## Desktop GUI

```text
python desktop_app.py
```

- Paste a **mint** → **Scan mint**  
- **Monitor once** → check latest launches  
- **Add wallet** manually  
- Tabs: Log · Wallets · Alerts  

---

## Suggested workflow

1. When you see a rug, **scan its mint** → review **suggested** wallets (not auto-saved).  
2. **Add wallet** only for ones you choose (or import/pull remote JSON).  
3. Optional: set `RUGWATCH_AUTO_FLAG=1` only if you want old auto-flag behavior.  

3. Leave **monitor** running (or click Monitor once often).  
4. If a known wallet shows up as creator/insider on a new launch → **alert**.

---

## Data model (SQLite)

| Table | Purpose |
|---|---|
| `wallets` | Address, risk_score 0–100, labels, times_seen |
| `incidents` | Per-mint risk events |
| `wallet_mint_links` | creator / insider / early_signer / … |
| `seen_mints` | Launches already processed |
| `alerts` | Serial hits on new launches |

---

## Sources

| Source | Needs key? | Use |
|---|---|---|
| Rugcheck | No | Risks, holders, insiders |
| DexScreener | No | Recent pump pairs |
| Pump.fun front API | No | Creator (best-effort) |
| Helius / RPC | Recommended | Early signers / holders |
| Solscan Pro | Optional | Extra holders |

---

## Limits

- Not a full chain indexer — **sampling + heuristics**.  
- Free RPCs will rate-limit; **Helius** is strongly recommended for deep scans.  
- Launch data sources change over time; creator resolve is best-effort.  
- Risk labels are heuristics, not legal judgments.

---

## Project layout

```text
RugWatch/
  desktop_app.py
  run_web.py
  web/
  rugwatch/
  data/          (created when you run the app)
  README.md
  EXTERNAL_STORAGE.md
  RugCheck Documentation.md
```
