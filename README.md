# RugWatch

**Standalone project** — not part of Leonidas / GrokScreener.  
Own folder, own code, own database, own `.env`. No shared imports.

Local tool that **tracks wallets involved in Solana rugs/scams**, stores them in a **SQLite database**, and **watches new pump.fun-style launches** for those wallets (serial rugger watch).

Not financial advice. Heuristics only — false positives happen.

---

## What it does

1. **Scan a mint** (token address)  
   Pulls Rugcheck + optional Pump.fun creator + Helius early signers + optional Solscan holders.  
   Flags creators, insiders, large holders on risky mints → **wallet DB**.

2. **Store evidence**  
   `data/rugwatch.db` — wallets, incidents, wallet↔mint links, seen mints, alerts.

3. **Monitor launches**  
   Polls recent pump-related pairs (DexScreener), resolves creators when possible,  
   compares against your bad-wallet list → **alerts** (`data/alerts.log` + DB).

---

## Setup

```text
cd C:\Users\levyr\RugWatch
copy .env.example .env
```

Edit `.env`:

```env
HELIUS_API_KEY=your_key_here
```

Optional: `SOLSCAN_API_KEY`, `BIRDEYE_API_KEY`, `RUGWATCH_POLL_SECONDS=45`

```text
pip install -r requirements.txt
python -m rugwatch init-db
```

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
- Pump.fun API paths change; creator resolve is best-effort.  
- “Scam” labels are **risk scores**, not legal judgments.  
- API quotas apply (Helius / optional paid APIs).

---

## Separation from other projects

| | RugWatch | Leonidas (other project) |
|---|---|---|
| Path | `C:\Users\levyr\RugWatch` | `C:\Users\levyr\GrokScreener` |
| Purpose | Serial wallet DB + launch watch | Token research UI |
| Database | `data/rugwatch.db` | `data/market.db` |
| Config | `RugWatch\.env` | `GrokScreener\.env` |
| Code | `rugwatch/` package only | `token_tracker/`, `desktop_app.py`, … |

No Python imports cross the two trees. Keys may be *copied by you* into each `.env` if you want both apps to use Helius — still two separate files.

---

## Privacy

- All data stays **on your PC** (`data/rugwatch.db`).  
- Do not share your `.env`.  
- Share only code, never your DB if it has research notes you care about.

---

## Project layout

```text
C:\Users\levyr\RugWatch\     ← this project only
  desktop_app.py
  run_monitor.py
  rugwatch/
    cli.py
    db.py
    config.py
    alerts.py
    ingest/scan_mint.py
    monitor/launches.py
    sources/   # pumpfun, rugcheck, rpc, solscan
  data/        # created at runtime
  .env.example
  README.md
```

---

## Later ideas

- Continuous Windows service / tray icon  
- Telegram alert bot  
- Funding-graph clustering  
- Optional export of alerts to a file for other tools (still no hard dependency)
