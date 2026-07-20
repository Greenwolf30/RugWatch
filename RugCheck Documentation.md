# RugWatch — How to Use the App

Complete user guide for the **RugWatch** desktop app **and** the optional **website** version: every button, tab, and workflow.

**Not financial advice.** Risk scores and “serial” labels are **your** research heuristics. False positives happen. Nothing here is a legal judgment.

---

## How RugWatch works (big picture)

RugWatch is a **private serial-wallet watchlist** for Solana research. You build the list; the app helps you spot those wallets again on new launches and surfaces them inside Actual Token Checker (ATC).

```text
  ┌─────────────────┐     you choose who to save      ┌──────────────────────┐
  │  Scan mint      │  ──suggest only──►  Add / Upload │  Local DB            │
  │  (research)     │                     wallets     │  data/rugwatch.db    │
  └─────────────────┘                                 └──────────┬───────────┘
                                                                  │
                         Push cloud (optional)                    │
                                  │                               │
                                  ▼                               │
                         ┌─────────────────┐                      │
                         │ Your GitHub     │ ◄── Pull cloud ──────┤
                         │ wallets JSON    │                      │
                         └────────┬────────┘                      │
                                  │                               │
                                  └──────────┬────────────────────┘
                                             │
                         Monitor once        │        Actual Token Checker
                         (recent launches)   │        reads local + cloud
                                  │          │               │
                                  ▼          │               ▼
                         ┌─────────────┐     │     Holders: FLAGGED WALLETS
                         │ Alerts tab  │     │     tags [local] [cloud] [both]
                         │ full mint + │     │
                         │ explorer URL│     │
                         └─────────────┘     │
```

| Step | Tool | What it does |
|------|------|----------------|
| 1. Research | **Scan mint** | Looks up one token; **suggests** wallets (does not auto-save by default). |
| 2. Save | **Add wallet** / **Upload manual wallets** | Writes addresses into **your** local DB (and can push cloud). |
| 3. Watch | **Monitor once** | Checks ~25 **current** recent launches against wallets with score ≥ 40. |
| 4. Investigate | **Alerts** | On a hit: full **mint**, **wallet**, symbol, Solscan + DexScreener links. |
| 5. ATC | Separate app | Flags those wallets on Holders when they appear on a mint you analyze. |

**Manual-only by default:** Scan is research. **You** decide what enters the serial list. That keeps noise down and keeps responsibility with you.

Everything is **local by default** (`data/rugwatch.db`). Cloud only talks to **your** GitHub when configured.

---

## What RugWatch does

1. **Research a token mint** — scan for creator, insider, and large-holder wallet *candidates*.  
2. **Build a private “bad wallet” list** — Add / Upload; you choose the score.  
3. **Watch new launches** — alert when a saved wallet shows up again as creator (serial-style reuse).  
4. **Back up / restore** — Export JSON, Push/Pull cloud, Pull URL.  
5. **Feed Actual Token Checker** — ATC reads **local DB + cloud list** and tags flagged holders.  
6. **Optional website** — same workflows in a browser (`python run_web.py`).

---

## Open the app

| Method | How |
|---|---|
| **Built app** | Double-click `C:\Users\levyr\RugWatch\dist\RugWatch\RugWatch.exe` |
| **From source** | In the RugWatch folder: `python desktop_app.py` |
| **Website** | In the RugWatch folder: `python run_web.py` → http://127.0.0.1:8787/ |

On first open you should see:

- Title bar: **RugWatch · wallets N · logged N · cloud N**
- Header pills (top right): green **wallets**, gold **logged**, blue **cloud**
- Status line: In DB now · Lifetime logged · Cloud now · high_risk · incidents · alerts
- Mint field, action buttons, manual wallet row
- Three tabs: **Log**, **Wallets**, **Alerts** (no separate Upload tab — use **Upload manual wallets** next to **Add wallet**)
- Manual row: **Add wallet** + **Upload manual wallets** (file picker for Ruggers JSON / address lists)

The **Log** tab prints a ready message and storage / cloud status.

The website shows the same three pills (**wallets · logged · cloud**), tabs **Log · Wallets · Alerts** only, multi-line alerts with full mint + links, and **Upload manual wallets** next to **Add wallet**.

---

## Header pills: wallets · logged · cloud

These three numbers are **database / cloud inventory**, not Monitor results.

| Pill | Label | What it counts |
|------|--------|----------------|
| **wallets N** | “wallets” / “In DB now” | How many wallets are in the **local SQLite DB right now**. This is your current list (what the Wallets tab shows). |
| **logged N** | “logged” / “Lifetime logged” | How many wallets have **ever been added** over this DB’s life. A running total that **survives Clear DB** (like a view counter). After Clear DB you may see wallets **0** but logged still **high**. |
| **cloud N** | “cloud” / “Cloud now” | How many wallets are in the **cloud file right now** (your GitHub wallet list when cloud is set up). This is read from the cloud (not a copy of the local count unless you just pushed). |

### How they relate

```text
  You Add / Upload wallet  →  local DB (wallets ↑, logged ↑ if new)
           │
           │ Push cloud (or auto-sync after add if cloud enabled)
           ▼
  GitHub cloud file        →  cloud pill updates to that file’s count
           │
           │ Pull cloud
           ▼
  Local DB merges          →  wallets may rise; logged rises for new addresses
```

| Situation | wallets | logged | cloud |
|-----------|---------|--------|-------|
| Fresh install, no cloud | 0 | 0 | — or n/a |
| Added 10 wallets, not pushed | 10 | 10 | 0 or old / n/a until refresh |
| Pushed those 10 | 10 | 10 | **10** |
| Clear DB only | **0** | **10** | **10** (cloud still has them) |
| Pull cloud after clear | **10** | ≥10 | **10** |

### Notes

- **cloud —** or **cloud n/a**: cloud not configured or fetch failed. Click the **cloud** pill to retry a count refresh.  
- **cloud 0**: cloud is configured but the wallet file is empty or not created yet — Add wallets then **Push cloud**.  
- Local and cloud can **differ** until you push or pull.  
- Monitor’s `known=37` is **not** the same as these pills (that is “wallets with score ≥ 40 used for launch watch”).

---

## Screen map

```text
┌──────────────────────────────────────────────────────────────────┐
│  RugWatch     Serial rugger wallet DB · launch watch · manual-only│
│                          [wallets N]  [logged N]  [cloud N]      │
│  In DB now · Lifetime · Cloud now · high_risk · incidents · alerts│
├──────────────────────────────────────────────────────────────────┤
│  MINT  [ paste token mint address ________ ]  ☑ Deep             │
│  [Scan mint] [Monitor once] [Refresh] [Clear DB]                 │
│  [Export JSON] [Push cloud] [Pull cloud] [Pull URL]              │
├──────────────────────────────────────────────────────────────────┤
│  Manual wallet [ address ] score [75] [Add wallet]               │
│                               [Upload manual wallets]            │
├──────────────────────────────────────────────────────────────────┤
│  [ Log ]   [ Wallets ]   [ Alerts ]     ← no Upload tab          │
│  (results, list, and alerts appear here)                         │
└──────────────────────────────────────────────────────────────────┘
```

---

## Header & status (read-only)

| UI element | Meaning |
|---|---|
| **wallets N** (green pill) | How many wallets are in the local DB **right now** |
| **logged N** (gold pill) | Lifetime count of wallets ever added (survives Clear DB) |
| **cloud N** (blue pill) | How many wallets are in the cloud file **right now** (GitHub); click pill to re-fetch |
| Status line | `In DB now` · `Lifetime logged` · `Cloud now` · `high_risk` · `incidents` · `alerts` |
| Window title | Same counts for a quick glance on the taskbar |

These update after Scan, Add wallet, Monitor, **Refresh**, Clear, Upload, and cloud push/pull.  
See also [Header pills: wallets · logged · cloud](#header-pills-wallets--logged--cloud).

---

## Mint row

### MINT field

- Paste a **Solana token mint address** (the token’s mint, not a pair address and not a random wallet).
- Press **Enter** or click **Scan mint** to start a scan.

### Deep

| State | Behavior |
|---|---|
| **Checked** (default) | Scan also fans out early signers via RPC-style providers — more complete graph |
| **Unchecked** | Faster / lighter scan; still uses public Rugcheck + Pump.fun-style sources when available |

Deep mode may need optional provider setup on the machine/server. Without it, deep features are limited.

---

## Action buttons (what every control does)

### Scan mint

**Purpose:** Research **one** token mint and get **candidate** wallets (creator, insiders, large holders, etc.). By default nothing is saved until **you** choose.

**When to use:** You have a mint from a rug, a sketchy launch, or ATC research and want wallet candidates to review.

**What happens step by step:**

1. You paste a **mint** (token address) and click **Scan mint** (or press Enter).  
2. App queries best-effort public/optional sources (Rugcheck, Pump.fun creator, optional deeper RPC/holder sources).  
3. **Log** shows `Scan OK · SYMBOL · type=… · MANUAL-ONLY` (or auto-save mode if enabled in setup).  
4. Each candidate line looks like:
   - `[suggest] creator: <wallet> (score 85)` — **not** in your DB yet  
   - `[saved] …` — only if auto-flag is on  
5. **Wallets** / stats refresh only if something was actually written.

**Important:**

- Scanning alone does **not** put a wallet on the Monitor list or in ATC flags.  
- To flag: **Manual wallet** → score → **Add wallet**, or **Upload manual wallets** (bulk).  
- Scan is **not** the same as Monitor (Scan = one mint you pick; Monitor = recent launches vs your saved list).

**Sources used during scan (best-effort):**

| Source | What you get |
|---|---|
| Rugcheck | Risks, holders, insiders, creator hints |
| Pump.fun-style APIs | Creator (when available) |
| Optional deep RPC | Early signers / deeper graph (**Deep** checked) |
| Optional holder APIs | Extra holders |
| DexScreener-style search | Used mainly by **Monitor** for recent pairs |

**Deep** checkbox sits on the mint row — see [Mint row](#mint-row).

---

### Monitor once

**Purpose:** One pass over **recent pump-style launches**, then stop. Checks whether any wallet **already in your DB** (score ≥ **40** by default) reappears as **creator** / light insider.

**When to use:** After you have saved wallets; click regularly (or use continuous CLI monitor). Empty Alerts until you both have a list **and** a hit.

**What happens step by step:**

1. Loads **known** wallets from local DB with score ≥ 40 → that number is `known=…`.  
2. Fetches up to **~25 current recent** launches (DexScreener-style pump search) → `scanned=…`.  
   - This is **not** “25 more never-seen launches.” Next click checks the **latest** 25 again (overlap is normal).  
3. For each launch, resolves **creator** (and light rugcheck on mints not seen before).  
4. If creator/insider is in your known set → **Alert** with full mint, wallet, symbol, explorer links → `alerts=…`.  
5. If `alerts > 0`, app switches to the **Alerts** tab.  
6. Stops (GUI does not loop; CLI `monitor` can run continuously).

**Log line example:**

```text
Monitor · scanned=25 known=37 alerts=0
```

| Field | Meaning |
|-------|---------|
| **scanned** | Launches checked this run (~25 current recent). |
| **known** | Your watchlist size for this run (score ≥ 40). |
| **alerts** | Hits this run. **0** = none of your known wallets matched those launches. |

**What Monitor does *not* do:**

- Does not deep-scan every holder on every launch  
- Does not auto-add new wallets to the DB (only alerts + activity on **already-known** wallets)  
- Does not mean “found 25 ruggers” when `scanned=25`  

Full detail also under [Monitor once — what the summary means](#monitor-once--what-the-summary-means) and [Alerts](#alerts).

---

### Refresh

**Purpose:** Reload what the screen shows from storage. It does **not** research the chain again.

**What Refresh does (desktop app):**

1. Updates the **header pills** and status line — **wallets**, **logged**, high_risk, incidents, unacked alerts  
2. Reloads the **Wallets** tab from local `rugwatch.db`  
3. Reloads the **Alerts** tab from the local alerts table  
4. On the desktop build with cloud support, a separate background refresh may also update the **cloud** pill (click the cloud pill to force a cloud count refresh)

**What Refresh does (website `python run_web.py`):**

1. Calls the server for **stats** (including **cloud** count when configured)  
2. Reloads **Wallets** and **Alerts** lists  
3. Prints `Refreshed.` in the Log  

**What Refresh does *not* do:**

| Not done by Refresh | Use this instead |
|---------------------|------------------|
| Scan a token mint | **Scan mint** |
| Check new pump launches | **Monitor once** |
| Pull wallets from GitHub | **Pull cloud** |
| Push wallets to GitHub | **Push cloud** |
| Clear the database | **Clear DB** |
| Add or upload wallets | **Add wallet** / **Upload manual wallets** |

**When to use Refresh:**

- UI looks out of date after CLI changes, another RugWatch window, or cloud pull  
- You just imported/cleared data and the lists look empty or wrong  
- You want a clean re-read of the DB without starting a scan or monitor  

**Short version:** Refresh = “show me the latest from the DB (and stats) again,” not “search Solana again.”

Local list refresh does not require scanning the chain. The **cloud** pill may use the network when it re-fetches the GitHub count.

---

### Clear DB

**Deletes all** wallets, incidents, links, alerts, and seen mints from the **local** database after a yes/no confirm.

#### Local only — not the cloud

| Cleared by Clear DB | **Not** cleared |
|---------------------|-----------------|
| Local `data/rugwatch.db` research data (wallets, incidents, links, alerts, seen mints) | **Cloud** (GitHub `wallets_cloud.json` / Gist) |
| Current **wallets** pill → usually **0** | **logged** (lifetime) often still shows past total |
| | Export files already saved on disk |
| | Other apps’ copies of the list |

To empty the cloud list too: Clear DB, then **Push cloud** (overwrites the cloud file with the empty/local list), or edit/delete the cloud file on GitHub yourself.

#### Does Clear DB free local storage?

**Yes — local disk data for that research is removed.**

- **Local storage (disk):** Wallet/alert data is deleted from SQLite. Free space is reused; the file may not shrink fully on disk until a vacuum, but the list is gone.
- **RAM:** Slightly less when the UI reloads (small for normal list sizes).
- **Cloud:** Unchanged until you push.

**Always Export JSON or Push cloud first** if you might need the list again.

---

### Export JSON

Writes a portable backup of flagged wallets to:

```text
C:\Users\<you>\RugWatch\data\wallets_export.json
```

- Local file only — **does not** upload  
- Safe “before Clear DB” backup  
- Can be re-imported later via CLI `import-wallets`

---

### Push cloud

**Direction:** local DB → **your** GitHub (repo file or Gist).

| Cloud mode | Where wallets go |
|---|---|
| `RUGWATCH_CLOUD=repo` (recommended) | `data/wallets_cloud.json` in **your** RugWatch GitHub repo |
| `RUGWATCH_CLOUD=gist` | A Gist under your account |
| `RUGWATCH_CLOUD=off` | Disabled |

Cloud must be set up for your account first. Failures appear in a dialog and the **Log**.

Use for: backup, second PC, or keeping one shared list you control.

**Capacity / auto-shard:** default **100,000 wallets per cloud file** and **per local DB**. When full, RugWatch creates the next file automatically (`wallets_cloud_002.json`, `rugwatch_002.db`, …). Push/Pull uses **all** shards via `data/wallets_index.json`. See [How many wallets is “too many”?](#how-many-wallets-is-too-many) and **EXTERNAL_STORAGE.md**.

---

### Pull cloud

**Direction:** your configured cloud (GitHub repo or Gist) → local DB.

- **Merges** remote wallets into `rugwatch.db`  
- Does **not** delete wallets that only exist locally  
- Use after reinstall, new machine, or to load a list you already keep in the cloud  

If cloud is not set up, the app explains what is missing.

---

### Pull URL

**Direction:** any HTTPS JSON wallet list → local DB.

Uses a wallet-list URL from local setup (when configured). Useful for a raw public JSON file or your own host **without** full cloud push mode. Merges into local DB (same idea as Pull cloud).

---

## Manual wallet row (how wallets enter the DB)

This is the **primary** way addresses become “flagged” for Monitor and ATC.

| Control | What it does |
|---|---|
| **Manual wallet** | Paste a Solana **wallet** address (not a mint) |
| **score** | Risk score **0–100** (default often **75**). Higher = more serious for you and for monitor min-score filters |
| **Add wallet** | Saves one address + score + label `manual` into `data/rugwatch.db` |
| **Upload manual wallets** | Opens a file picker for **bulk** import (next to Add wallet — **not** a tab). Accepts RugWatch JSON or Ruggers Export JSON / one address per line `.txt` |

There is **no** “Upload” tab between Wallets and Alerts. Bulk import is only via **Upload manual wallets** beside **Add wallet** (desktop + website).

### After a successful **Add wallet**

1. **Log:** `Added wallet … score=…`  
2. **Wallets** tab shows the address  
3. **Monitor once** can alert if that wallet appears on a new launch (if score ≥ 40)  
4. **Actual Token Checker** can flag it on Holders (local and/or cloud after push)  
5. If cloud is enabled, app may auto **Push** after add (Log shows OK or failure)

### After **Upload manual wallets**

1. You pick a `.json` or `.txt` file  
2. App imports addresses into the **local DB first** (always)  
3. Log shows how many imported / skipped  
4. **Wallets** / **wallets** pill update from local  
5. **Cloud:** if cloud is **not** configured → stays local until you set up cloud and click **Push cloud**. If cloud **is** configured → the app may **auto-push** after upload (Log: `Cloud push OK`). If auto-push fails, data remains local until you **Push cloud**.  
6. Same Monitor + ATC behavior as manually added wallets  

**Upload always hits local DB first.** Cloud is optional and may be automatic when enabled — not only when you press Push cloud.

**Score guidance (suggested, not rules):**

| Score | Typical use |
|---|---|
| 40–59 | Soft watch / weak confidence |
| 60–79 | Default “flag this” research |
| 80–100 | High confidence serial / insider abuse |

**Monitor defaults ignore wallets below score 40.** They still appear on the Wallets tab and in ATC if score filters allow.

---

## Tabs

### Log

Live activity stream:

- Startup ready + storage / cloud boot status  
- Scan progress and **suggest** vs **saved** lines  
- Monitor summary (`scanned` / `known` / `alerts`) and ALERT lines  
- Add wallet, export, push/pull, clear messages  
- Errors (also pop-up dialogs when severe)

Scroll stays pinned to the bottom as new lines arrive.

### Wallets

List of wallets currently in the DB (up to 100), each as:

```text
 75  x2  <address>
     [manual] manual GUI
```

Columns meaning:

| Piece | Meaning |
|---|---|
| First number | Risk score |
| `xN` | Times seen / activity count |
| Address | Wallet pubkey |
| `[label]` | e.g. `manual` |
| Notes | Short note (truncated) |

Empty state reminds you: Scan only **suggests**; use **Add wallet** (or import / pull) to save.

### Alerts

Serial-watch hits: a **known** wallet (already in your DB, score ≥ 40 by default)
appeared as **creator** / light **insider** (or related role) on a launch Monitor
checked.

- Empty until you both have wallets in the DB **and** run **Monitor once**  
- When `alert_count > 0`, the app switches to this tab automatically  
- Each alert is **multi-line** and always identifies the **token**

#### What each alert shows (token identity)

| Line | What it is |
|------|------------|
| **Token** | Symbol and/or name when known (e.g. `$PEPE` or `$PEPE (Pepe Coin)`). If symbol missing, best label from the launch. |
| **Mint** | **Full** token contract address (not truncated). |
| **Wallet** | **Full** flagged wallet address (the known serial/suspect). |
| **Solscan token** | Clickable-style URL: `https://solscan.io/token/<full mint>` |
| **DexScreener** | `https://dexscreener.com/solana/<full mint>` |
| **Solscan wallet** | `https://solscan.io/account/<full wallet>` |
| **Detail** | Full message (role, score, label, times_seen, mint + links again) |

Example shape:

```text
[2026-07-20T12:00:00+00:00]  ALERT  score=80  role=creator
  Token:  $EXAMPLE
  Mint:   SoMeFuLlMiNtAddressHere1111111111111111111
  Wallet: SoMeFuLlWaLlEtAddressHere22222222222222222
  Solscan token:  https://solscan.io/token/SoMeFuLlMiNt...
  DexScreener:    https://dexscreener.com/solana/SoMeFuLlMiNt...
  Solscan wallet: https://solscan.io/account/SoMeFuLlWaLlEt...
  Detail: SERIAL WATCH HIT: known wallet (creator) on new launch $EXAMPLE — …
```

Copy the **Mint** line into Actual Token Checker, DexScreener, or Solscan for full research.

The same multi-line block is also printed on the **Log** tab when Monitor fires hits.

---

## Monitor once — summary line (detail)

When you click **Monitor once**, the Log prints something like:

```text
Monitor · scanned=25 known=37 alerts=0
```

This is the same Monitor behavior described under [Monitor once](#monitor-once). Quick reference:

| Field | Meaning |
|-------|---------|
| **scanned** | ~**25 current** recent pump-style launches (re-fetched each click; not “25 more new ones”). |
| **known** | Your watchlist size for this run (**score ≥ 40**). |
| **alerts** | Hits this run. **0** is normal if none of your wallets launched in that batch. |

---

## Website version

Browser UI for the same workflows as the desktop app.

### Start the site

```text
cd C:\Users\levyr\RugWatch
python run_web.py
```

Open **http://127.0.0.1:8787/**

### Website controls (same meaning as desktop)

| Control | What it does |
|---------|----------------|
| Scan mint | Research one mint |
| Monitor once | Check ~25 recent launches vs local DB |
| Refresh | Reload stats / wallets / alerts |
| **Push cloud** | Local DB → your cloud wallet list |
| **Pull cloud** | Cloud → merge into local DB |
| **Clear DB** | Wipe **local** DB only (cloud unchanged until Push) |
| Add wallet | One address → local DB |
| Upload manual wallets | File picker next to Add wallet (no Upload tab) |
| Tabs | **Log · Wallets · Alerts** only |
| Pills | wallets · logged · cloud |

### Website workflow → Actual Token Checker flags

```text
1. python run_web.py  →  http://127.0.0.1:8787/
2. Add / Upload wallets  →  local DB
3. Push cloud            →  cloud wallet list updated
4. Point ATC at that cloud list (when using ATC website/server)
5. Analyze a mint on ATC →  Holders flags [cloud] / [local] / [both]
```

Website and desktop share the **same** `data/rugwatch.db` when run from the same project folder.

---

## End-to-end workflows

### A. Research a rug and flag the bad actors

1. Hear about a rug → copy the **token mint**.  
2. Paste into **MINT** → leave **Deep** on for a fuller scan when available.  
3. Click **Scan mint**.  
4. Read **Log** suggestions (`creator`, `insider`, large holders, etc.).  
5. For each wallet you believe is high risk: paste into **Manual wallet**, set **score**, click **Add wallet**.  
   Or use **Upload manual wallets** next to Add wallet (JSON/txt from ATC Ruggers Export).  
6. Confirm under **Wallets**.  
7. Optional: **Push cloud** or **Export JSON** for backup.

### B. Watch for serial reuse on new launches

1. Build a wallet list (workflow A).  
2. Click **Monitor once** regularly (or run continuous CLI monitor).  
3. Read Log summary: `scanned=… known=… alerts=…` (see above).  
4. If `alerts > 0` → **Alerts** tab (auto-selected) shows **token + full mint + wallet + links**.  
5. Copy **Mint** into Actual Token Checker / open DexScreener or Solscan from the printed URLs.

### C. Day-to-day research with Actual Token Checker (local + cloud)

ATC **reads** RugWatch — it does **not** write into RugWatch.

ATC merges **two** sources when building the Holders “FLAGGED WALLETS (RugWatch)” list:

1. **Local** — `rugwatch.db` on this PC  
2. **Cloud** — your pushed wallet JSON on GitHub (if configured)

```text
  RugWatch local DB  ──┐
                       ├── merge (unique addresses) ──► ATC Holders flags
  RugWatch cloud JSON ─┘     tags: [local] [cloud] [both]
```

**Where ATC looks for the local DB (first match wins):**

1. Env `RUGWATCH_DB` (full path to `rugwatch.db`)  
2. Sibling folder `../RugWatch/data/rugwatch.db`  
3. `~/RugWatch/data/rugwatch.db`

**Where ATC loads the cloud list:** from ATC’s own server/app configuration (wallet list URL or linked cloud location). After you **Push cloud** in RugWatch, ATC can flag wallets that exist **only on cloud**, **only local**, or **both** (shown as tags on each flagged line).

**A flag only appears in ATC if:**

| Requirement | Why |
|---|---|
| Wallet is in **local DB and/or cloud list** | Scan suggestions alone are not saved |
| Address shows up in ATC’s holder / creator view | Must appear in the data ATC is building |
| Score meets any min filter ATC applies | Very low scores may be ignored |

What this does **not** do: auto-add from ATC into RugWatch; share one multi-user police DB for everyone (cloud is **your** list).

### D. New PC or reinstall

1. Install / copy RugWatch.  
2. Set up cloud if you use it.  
3. **Pull cloud** (or import a JSON backup).  
4. Confirm **Wallets** tab.  
5. Continue scanning and monitoring.

---

## Local database

| Item | Path / role |
|---|---|
| SQLite file | `data/rugwatch.db` (next to project or next to `.exe` / web server) |
| Cloud JSON (optional) | Your cloud wallet list (after Push cloud) |
| Export file | e.g. `~/RugWatch/data/wallets_export.json` |
| Tables | `wallets`, `incidents`, `wallet_mint_links`, `seen_mints`, `alerts` |

**Privacy**

- Default: data stays on **your PC / your server**.  
- Push/Pull only uses **your** cloud when configured.  
- Does **not** upload to Rugcheck.xyz or a shared global “main” database.

---

## Feature map (at a glance)

| Feature | Where | Writes local DB? | Network? |
|---|---|---|---|
| Scan mint | Button | No by default (suggest only) | Yes |
| Deep | Checkbox | No | Yes (if deep) |
| Monitor once | Button | Alerts + activity on hits | Yes |
| Refresh | Button | No (re-reads UI) | Cloud pill may re-fetch count |
| Clear DB | Button | Yes (deletes all local research) | No |
| Export JSON | Button | No (reads → file) | No |
| Push cloud | Button | No (reads → GitHub) | Yes |
| Pull cloud | Button | Yes (merge) | Yes |
| Pull URL | Button | Yes (merge) | Yes |
| Add wallet | Manual row | Yes | Optional auto cloud sync |
| Upload manual wallets | Manual row (file) | Yes (bulk) | Optional auto cloud sync |
| Continuous monitor | CLI only | Alerts on hits | Yes |
| Website UI | `python run_web.py` | Same DB on server | Yes for scan/monitor/cloud |

---

## CLI (optional power user)

Same engine as the GUI. From the RugWatch folder after `pip install -r requirements.txt`:

```text
python -m rugwatch init-db
python -m rugwatch scan <MINT>
python -m rugwatch add-wallet <WALLET> --score 80 --notes "serial"
python -m rugwatch list-wallets
python -m rugwatch monitor --once
python -m rugwatch monitor
python -m rugwatch alerts
python -m rugwatch stats
python -m rugwatch export-wallets -o wallets_export.json
python -m rugwatch import-wallets wallets_export.json
python -m rugwatch push-cloud
python -m rugwatch pull-cloud
python -m rugwatch pull-remote
python -m rugwatch cloud-status
python -m rugwatch cloud-init
python -m rugwatch clear-db --yes
```

Continuous monitor: `python -m rugwatch monitor` or `python run_monitor.py` (Ctrl+C to stop).

Desktop: `python desktop_app.py` or `dist\RugWatch\RugWatch.exe`.

---

## Limits & gotchas

- Not a full chain indexer — **sampling + heuristics**.  
- Public RPC/rate limits can slow Deep scans.  
- Pump.fun / third-party APIs change; creator resolve is best-effort.  
- “Scam” / “serial” are **your** scores, not legal judgments.  
- Actual Token Checker flags wallets from **local DB and/or cloud list** when ATC is pointed at them.  
- Cloud needs correct setup; failures show in **Log**.  
- Only **one** busy network job at a time in the GUI (Scan or Monitor); wait for Log to finish before starting another.  
- If the window “doesn’t open,” check Task Manager for `RugWatch.exe` — it may already be running behind other windows.  
- **Clear DB** = local only (see [Clear DB](#clear-db)); free local research data, not cloud by itself.  

---

## How many wallets is “too many”?

For **disk alone**, a normal PC almost never fails from wallet count. Each row is a small SQLite record.

| Scale | Rough feel |
|-------|------------|
| **Hundreds** | Ideal for a personal serial list |
| **Thousands** | Fine |
| **~10k–50k** | Usually OK; Monitor / export / cloud push can feel slower |
| **100k+** | Possible; app becomes heavy (lists, export, Monitor load) |
| **Millions** | Not what this app is designed for |

**What gets heavy first (not disk):**

1. **Monitor once** — loads known wallets (score ≥ 40) into memory (up to ~50k in code) and checks ~25 launches.  
2. **Wallets tab** — only shows **100** on screen; the rest stay in the DB.  
3. **Export / Push cloud** — large JSON files take longer.  
4. **Actual Token Checker** — merges local + cloud on Analyze; huge lists = more matching work.

**Practical advice:** Prefer a **curated** list (hundreds to a few thousand) over dumping everything. Quality of flags matters more than raw count. **Clear DB** frees **local** list space when you want a clean slate (export/push first if you still need the data).

### Cloud capacity + auto-sharding

RugWatch does **not** hard-cap the **total** wallets you can store. When one file fills up, it **opens another**:

| | Default max per file | Next file name |
|--|----------------------|----------------|
| Cloud | `RUGWATCH_CLOUD_SHARD_MAX=100000` | `wallets_cloud_002.json`, `_003`, … + `wallets_index.json` |
| Local | `RUGWATCH_LOCAL_DB_MAX=100000` | `rugwatch_002.db`, `_003`, … |

**Push cloud** packs every local wallet into shards and updates the index.  
**Pull cloud** merges **every** cloud shard into local DBs.  
Pills show **combined totals** across all shards.

Per-file practical size (GitHub / ATC speed) still applies to each shard:

#### Hard limits (GitHub)

| Limit | Meaning |
|--------|---------|
| **~100 MB** | Hard max for a normal file in a GitHub repo |
| **~1 MB** | Best zone for the Contents API used by Push/Pull cloud |
| **No fixed wallet count** | Code does not stop at 1,000 / 10,000 / etc. |

#### Rough size (with labels/notes like Ruggers exports)

About **350–400 bytes per wallet** when notes are included.

| File size | Approx. wallets |
|-----------|------------------|
| **1 MB** | ~2,500–3,000 |
| **5 MB** | ~12,000–15,000 |
| **10 MB** | ~25,000–30,000 |
| **50 MB** | ~100,000+ (gets heavy) |
| **100 MB** | theoretical max — not recommended |

Address-only rows (short notes) fit **several times more**.

#### Practical recommendation for cloud + ATC

| Range | Guidance |
|--------|----------|
| **Thousands → ~10k–30k** | Comfortable: fast Push/Pull, fine for website + ATC on Render |
| **~50k–100k+** | Still works, but slower loads and larger downloads |
| **Huge multi‑MB list every push** | Risk of timeouts, slow ATC scans, API friction |

**Effective target for RugWatch + ATC flags:** about **10,000–30,000 wallets** in the cloud file.  
Hundreds of thousands are possible on GitHub but not ideal for speed.

Local SQLite can hold more than you push; only what you **Push cloud** is what ATC reads via `RUGWATCH_WALLETS_URL`.

More detail: **EXTERNAL_STORAGE.md** → *Cloud capacity (how many wallets)*.

---

## Project layout (RugWatch only)

```text
RugWatch/
  desktop_app.py              ← desktop GUI
  run_web.py / web_server.py  ← website
  web/                        ← website UI
  run_monitor.py              ← continuous monitor helper
  build_exe.py
  RugCheck Documentation.md   ← this guide
  EXTERNAL_STORAGE.md         ← cloud / storage notes
  rugwatch/                   ← package (db, scan, monitor, sources, cloud)
  data/
    rugwatch.db               ← local wallet warehouse
  dist/RugWatch/RugWatch.exe  ← built app
```

RugWatch does **not** import Actual Token Checker. ATC **reads** local SQLite and optional cloud wallet list.

---

## Quick reference card

| I want to… | Do this |
|---|---|
| Understand the whole loop | [How RugWatch works](#how-rugwatch-works-big-picture) |
| Research a token | Paste mint → **Scan mint** → read **Log** (suggest only) |
| Save one bad wallet | **Manual wallet** + score → **Add wallet** |
| Save many wallets | **Upload manual wallets** (JSON/txt next to Add wallet) |
| See my list | **Wallets** tab (or **Refresh**) |
| Check new launches | **Monitor once** → read `scanned/known/alerts` → **Alerts** |
| See which token alerted | **Alerts**: Token, full **Mint**, full **Wallet**, explorer links |
| Reload UI only | **Refresh** (not a scan) |
| Back up locally | **Export JSON** |
| Back up to cloud | **Push cloud** (after cloud is set up) |
| Restore from cloud | **Pull cloud** |
| Restore from a JSON link | **Pull URL** (when a wallet-list URL is configured) |
| Start over (local only) | **Export** / **Push cloud** first → **Clear DB** (cloud stays until you push empty; **logged** may stay) |
| Free local list space | **Clear DB** (local data gone; cloud unchanged) |
| How big can the list get? | [How many wallets is “too many?”](#how-many-wallets-is-too-many) — prefer curated thousands, not millions |
| Use flags in ATC | Local DB and/or cloud list available to ATC → Analyze mint in ATC |
| Open website UI | `python run_web.py` → http://127.0.0.1:8787/ |
| Always-on watch | CLI: `python -m rugwatch monitor` |
