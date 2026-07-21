/* RugWatch website UI — no provider keys in the browser */
(function () {
  const TOKEN_KEY = "rugwatch_site_token";
  const cfg = window.RUGWATCH_CONFIG || {};

  function $(id) {
    return document.getElementById(id);
  }

  function apiBase() {
    return String(cfg.apiBase || "")
      .trim()
      .replace(/\/+$/, "");
  }

  function apiUrl(path) {
    const p = path.startsWith("/") ? path : "/" + path;
    const b = apiBase();
    return b ? b + p : p;
  }

  function siteToken() {
    const el = $("siteToken");
    const typed = el ? String(el.value || "").trim() : "";
    if (typed) {
      try {
        sessionStorage.setItem(TOKEN_KEY, typed);
      } catch (_) {}
      return typed;
    }
    try {
      return sessionStorage.getItem(TOKEN_KEY) || "";
    } catch (_) {
      return "";
    }
  }

  function headers(jsonBody) {
    const h = {};
    if (jsonBody) h["Content-Type"] = "application/json";
    const t = siteToken();
    if (t) h["X-API-Token"] = t;
    return h;
  }

  function log(msg) {
    const box = $("logBox");
    if (!box) return;
    const line = "[" + new Date().toISOString().slice(11, 19) + "] " + msg + "\n";
    box.textContent += line;
    box.scrollTop = box.scrollHeight;
  }

  async function apiGet(path) {
    const r = await fetch(apiUrl(path), { headers: headers(false), cache: "no-store" });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText || "request failed");
    return data;
  }

  async function apiPost(path, body) {
    const r = await fetch(apiUrl(path), {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify(body || {}),
      cache: "no-store",
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error(data.error || r.statusText || "request failed");
      err.status = r.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.toggle("active", p.dataset.panel === name);
    });
  }

  async function refreshStats() {
    try {
      const data = await apiGet("/api/stats");
      const s = data.stats || {};
      const n = s.wallets_logged || s.wallets || 0;
      const life = s.wallets_logged_lifetime || n;
      const cloud =
        s.cloud_wallets != null && s.cloud_wallets !== undefined
          ? s.cloud_wallets
          : null;
      if ($("pillWallets")) $("pillWallets").textContent = "wallets " + n;
      if ($("pillLogged")) $("pillLogged").textContent = "logged " + life;
      if ($("pillCloud")) {
        $("pillCloud").textContent =
          cloud == null ? "cloud n/a" : "cloud " + cloud;
      }
      $("statsBar").textContent =
        "In DB now: " +
        n +
        " · Lifetime logged: " +
        life +
        " · Cloud now: " +
        (cloud == null ? "—" : cloud) +
        " · high_risk=" +
        (s.high_risk_wallets || 0) +
        " · alerts=" +
        (s.unacked_alerts || 0) +
        " unacked";
    } catch (e) {
      $("statsBar").textContent = "Stats: " + e.message;
    }
  }

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function refreshWallets() {
    const box = $("walletsBox");
    if (!box) return;
    try {
      const data = await apiGet("/api/wallets?limit=100");
      const rows = data.wallets || [];
      if (!rows.length) {
        box.textContent =
          "No wallets in local list yet.\n" +
          "If cloud pill shows wallets, click Pull cloud (or wait for auto-pull after deploy).\n" +
          "Or use Add wallet / Upload.\n";
        return;
      }
      // Simple list: yellow scores · red wallet/notes (no copy handlers)
      box.innerHTML = rows
        .map((w) => {
          const score = String(w.risk_score != null ? w.risk_score : 0).padStart(3);
          const times = "x" + (w.times_seen || 0);
          const addr = escHtml(w.address || "");
          const label = escHtml(w.label || "");
          const notes = escHtml(String(w.notes || "").slice(0, 80));
          return (
            '<div class="w-line">' +
            '<span class="w-nums">' +
            escHtml(score) +
            "  " +
            escHtml(times) +
            "</span>" +
            '<span class="w-data">  ' +
            addr +
            "\n     [" +
            label +
            "] " +
            notes +
            "\n</span></div>"
          );
        })
        .join("\n");
    } catch (e) {
      box.textContent = "Error: " + e.message;
    }
  }

  function formatAlertWeb(a) {
    const wallet = (a.wallet || "").trim();
    const mint = (a.mint || "").trim();
    const role = a.role || "?";
    const score = a.risk_score;
    const when = a.created_at || "";
    const msg = (a.message || "").trim();
    let token = "(unknown symbol)";
    if (msg.includes("on new launch ")) {
      try {
        token = msg.split("on new launch ")[1].split(" — ")[0].split(" - ")[0].trim();
      } catch (_) {}
    }
    const lines = [
      "[" + when + "]  ALERT  score=" + score + "  role=" + role,
      "  Token:  " + token,
      "  Mint:   " + (mint || "(missing)"),
      "  Wallet: " + (wallet || "(missing)"),
    ];
    if (mint) {
      lines.push("  Solscan token:  https://solscan.io/token/" + mint);
      lines.push("  DexScreener:    https://dexscreener.com/solana/" + mint);
    }
    if (wallet) {
      lines.push("  Solscan wallet: https://solscan.io/account/" + wallet);
    }
    if (msg) lines.push("  Detail: " + msg);
    lines.push("");
    return lines.join("\n");
  }

  async function refreshAlerts() {
    const box = $("alertsBox");
    try {
      const data = await apiGet("/api/alerts?limit=50");
      const rows = data.alerts || [];
      if (!rows.length) {
        box.textContent =
          "No alerts yet. Run Monitor after building a wallet list.\n\n" +
          "When a known wallet hits a new launch, each alert shows:\n" +
          "  • Token symbol/name\n" +
          "  • Full mint address\n" +
          "  • Full wallet address\n" +
          "  • Solscan token + wallet links and DexScreener link\n";
        return;
      }
      box.textContent = rows.map(formatAlertWeb).join("\n");
    } catch (e) {
      box.textContent = "Error: " + e.message;
    }
  }

  async function refreshAll() {
    await refreshStats();
    await refreshWallets();
    await refreshAlerts();
  }

  async function doScan() {
    const mint = ($("mintInput").value || "").trim();
    if (!mint) {
      alert("Paste a token mint address.");
      return;
    }
    log("Scanning " + mint + "…");
    try {
      const data = await apiPost("/api/scan", {
        mint: mint,
        deep: !!$("deepScan").checked,
      });
      log(
        "Scan OK · " +
          (data.symbol || "") +
          " · type=" +
          (data.incident_type || "") +
          " · flagged=" +
          ((data.wallets_flagged || []).length || 0)
      );
      (data.wallets_flagged || []).forEach((f) => {
        log(
          "  [" +
            (f.saved ? "saved" : "suggest") +
            "] " +
            (f.role || "") +
            ": " +
            (f.wallet || "") +
            " (score " +
            (f.risk_score ?? "") +
            ")"
        );
      });
      if (data.note) log("  " + data.note);
      await refreshAll();
    } catch (e) {
      log("ERROR: " + e.message);
      alert(e.message);
    }
  }

  const MONITOR_COOLDOWN_MS = 5 * 60 * 1000;
  let _monitorCooldownUntil = 0;
  let _monitorCooldownTimer = null;

  function formatCooldown(ms) {
    const s = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + ":" + String(r).padStart(2, "0");
  }

  function updateMonitorButton() {
    const btn = $("btnMonitor");
    if (!btn) return;
    const left = _monitorCooldownUntil - Date.now();
    if (left > 0) {
      btn.disabled = true;
      btn.textContent = "Monitor once (" + formatCooldown(left) + ")";
      btn.title =
        "5 min cooldown — next run checks up to 25 never-seen launches";
    } else {
      btn.disabled = false;
      btn.textContent = "Monitor once";
      btn.title =
        "Scan up to 25 never-seen launches (DexScreener). 5 min cooldown after each run.";
      if (_monitorCooldownTimer) {
        clearInterval(_monitorCooldownTimer);
        _monitorCooldownTimer = null;
      }
    }
  }

  function startMonitorCooldown(ms) {
    const wait = ms != null && Number.isFinite(Number(ms)) ? Number(ms) : MONITOR_COOLDOWN_MS;
    _monitorCooldownUntil = Date.now() + Math.max(1000, wait);
    updateMonitorButton();
    if (_monitorCooldownTimer) clearInterval(_monitorCooldownTimer);
    _monitorCooldownTimer = setInterval(updateMonitorButton, 1000);
  }

  async function doMonitor() {
    if (Date.now() < _monitorCooldownUntil) {
      const left = _monitorCooldownUntil - Date.now();
      alert("Monitor cooldown: wait " + formatCooldown(left) + " before the next run.");
      return;
    }
    const btn = $("btnMonitor");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Monitoring…";
    }
    log("Monitor: fetching up to 25 never-seen launches (newest first)…");
    try {
      const data = await apiPost("/api/monitor", {
        limit: 25,
        only_new: true,
      });
      log(
        "Monitor · new_scanned=" +
          (data.launches_scanned ?? "") +
          "/" +
          (data.launches_target ?? 25) +
          " skipped_seen=" +
          (data.skipped_already_seen ?? "") +
          " pool=" +
          (data.candidates_fetched ?? "") +
          " known_wallets=" +
          (data.known_wallets ?? "") +
          " alerts=" +
          (data.alert_count ?? 0)
      );
      if (data.note) log("  " + data.note);
      (data.alerts || []).forEach((a) => log("  ALERT: " + (a.message || "")));
      if (data.alert_count) switchTab("alerts");
      const cdSec =
        data.retry_after_seconds != null
          ? Number(data.retry_after_seconds)
          : data.cooldown_seconds != null
            ? Number(data.cooldown_seconds)
            : 300;
      startMonitorCooldown(cdSec * 1000);
      await refreshAll();
    } catch (e) {
      const msg = String(e.message || e);
      log("ERROR: " + msg);
      const retry =
        e.data && e.data.retry_after_seconds != null
          ? Number(e.data.retry_after_seconds)
          : null;
      if (retry != null && Number.isFinite(retry)) {
        startMonitorCooldown(retry * 1000);
      } else {
        const m = msg.match(/wait\s+(\d+)\s*s/i);
        if (m) startMonitorCooldown(parseInt(m[1], 10) * 1000);
        else updateMonitorButton();
      }
      alert(msg);
    }
  }

  async function doAdd() {
    const address = ($("walletInput").value || "").trim();
    if (!address) {
      alert("Enter a wallet address.");
      return;
    }
    const score = parseInt($("scoreInput").value || "75", 10) || 75;
    try {
      await apiPost("/api/wallets", {
        address: address,
        score: score,
        label: "manual",
        notes: "web GUI",
      });
      log("Added wallet " + address + " score=" + score);
      $("walletInput").value = "";
      await refreshAll();
      switchTab("wallets");
    } catch (e) {
      log("ERROR: " + e.message);
      alert(e.message);
    }
  }

  async function doPushCloud() {
    log("Push cloud…");
    try {
      const data = await apiPost("/api/push-cloud", {});
      log(
        "Push cloud OK · wallets=" +
          (data.wallet_count ?? "?") +
          (data.cloud_shards != null ? " · cloud_shards=" + data.cloud_shards : "") +
          (data.path ? " · " + data.path : "") +
          (data.index_path ? " · index=" + data.index_path : "") +
          (data.html_url ? " · " + data.html_url : "")
      );
      await refreshAll();
    } catch (e) {
      log("Push cloud failed: " + e.message);
      alert(e.message);
    }
  }

  /**
   * Pull cloud flow (no permanent input bar):
   * 1) Warn about large pulls (>100k / small machines)
   * 2) Ask how many wallets (number or "all")
   * 3) Confirm, then pull
   */
  function promptPullLimit() {
    window.alert(
      "Pull cloud warning\n\n" +
        "Cloud lists can be large. Pulling over ~100,000 wallets can slow or freeze a small machine " +
        "or a nearly full hard drive (RAM during download/import + disk for the local DB).\n\n" +
        "• Prefer a limited number if you are unsure.\n" +
        "• Type all only if you have enough free RAM and disk.\n\n" +
        "Next you will choose how many wallets to pull."
    );

    const raw = window.prompt(
      "How many wallets do you want to pull from the cloud?\n\n" +
        "• Enter a positive number (e.g. 500 or 10000)\n" +
        "• Or type all to pull every shard\n\n" +
        "Cancel aborts the pull.",
      "all"
    );
    if (raw == null) {
      return null; // cancelled
    }
    const s = String(raw).trim();
    if (!s || /^(all|\*|full|everything)$/i.test(s)) {
      return { max_wallets: "all", label: "all" };
    }
    const n = parseInt(s, 10);
    if (!Number.isFinite(n) || n <= 0) {
      window.alert("Invalid amount. Enter a positive number or all.");
      return null;
    }
    if (n > 100000) {
      const okBig = window.confirm(
        "You asked for " +
          n.toLocaleString() +
          " wallets (over 100,000).\n\n" +
          "This can stress a small machine or overloaded hard drive.\n\n" +
          "Continue with this amount?"
      );
      if (!okBig) return null;
    }
    return { max_wallets: n, label: String(n) };
  }

  async function doPullCloud() {
    const choice = promptPullLimit();
    if (!choice) {
      log("Pull cloud cancelled.");
      return;
    }

    const limLabel = choice.label;
    const confirmMsg =
      choice.max_wallets === "all"
        ? "Pull ALL wallets from cloud into the local database?\n\n" +
          "This may take a while if the cloud list is large.\n\nContinue?"
        : "Pull up to " +
          Number(choice.max_wallets).toLocaleString() +
          " wallet(s) from cloud into the local database?\n\nContinue?";
    if (!window.confirm(confirmMsg)) {
      log("Pull cloud cancelled (confirm).");
      return;
    }

    const body =
      choice.max_wallets === "all"
        ? { max_wallets: "all" }
        : { max_wallets: choice.max_wallets };

    log("Pull cloud… (limit=" + limLabel + ")");
    try {
      const data = await apiPost("/api/pull-cloud", body);
      log(
        "Pull cloud OK · imported=" +
          (data.imported ?? 0) +
          " · skipped=" +
          (data.skipped ?? 0) +
          " · db_wallets=" +
          (data.db_wallets ?? "?") +
          (data.considered != null ? " · considered=" + data.considered : "") +
          (data.max_wallets != null ? " · max=" + data.max_wallets : "") +
          (data.cloud_shards != null ? " · cloud_shards=" + data.cloud_shards : "") +
          (data.local_shards != null ? " · local_shards=" + data.local_shards : "") +
          (data.note ? " · " + data.note : "")
      );
      await refreshAll();
      switchTab("wallets");
    } catch (e) {
      log("Pull cloud failed: " + e.message);
      alert(e.message);
    }
  }

  async function doClearDb() {
    if (
      !confirm(
        "Delete ALL wallets, incidents, and alerts from the LOCAL database?\n\n" +
          "Cloud file is NOT cleared until you Push cloud.\n" +
          "Export or Push cloud first if you need a backup."
      )
    ) {
      return;
    }
    log("Clear DB…");
    try {
      const data = await apiPost("/api/clear-db", { confirm: true });
      log("Database cleared · " + (data.note || "local wipe done"));
      await refreshAll();
    } catch (e) {
      log("Clear DB failed: " + e.message);
      alert(e.message);
    }
  }

  async function importText(text, label) {
    const status = $("uploadStatus");
    try {
      const data = await apiPost("/api/upload", { text: text });
      const imp = data.imported ?? 0;
      const skipEx = data.skipped_existing ?? 0;
      const skip = data.skipped ?? 0;
      let msg =
        "Imported " +
        imp +
        " new wallet(s)" +
        (skipEx
          ? " · skipped " + skipEx + " already in DB/cloud"
          : skip
            ? " · skipped " + skip
            : "") +
        " · " +
        label;
      if (imp === 0 && skipEx > 0) {
        msg =
          "No new wallets — all " +
          skipEx +
          " already in local DB and/or cloud (duplicates ignored) · " +
          label;
      }
      if (data.note) msg += " · " + data.note;
      if (status) {
        status.hidden = false;
        status.textContent = msg;
      }
      log(msg);
      await refreshAll();
      switchTab("wallets");
    } catch (e) {
      if (status) {
        status.hidden = false;
        status.textContent = "Upload failed: " + e.message;
      }
      log("Upload failed: " + e.message);
      alert(e.message);
    }
  }

  function wire() {
    document.querySelectorAll(".tab").forEach((t) => {
      t.addEventListener("click", () => switchTab(t.dataset.tab));
    });
    $("btnScan").addEventListener("click", () => doScan());
    $("btnMonitor").addEventListener("click", () => doMonitor());
    updateMonitorButton();
    $("btnRefresh").addEventListener("click", () => {
      refreshAll();
      log("Refreshed.");
    });
    if ($("btnPushCloud")) {
      $("btnPushCloud").addEventListener("click", () => doPushCloud());
    }
    if ($("btnPullCloud")) {
      $("btnPullCloud").addEventListener("click", () => doPullCloud());
    }
    if ($("btnClearDb")) {
      $("btnClearDb").addEventListener("click", () => doClearDb());
    }
    if ($("pillCloud")) {
      $("pillCloud").addEventListener("click", () => {
        log("Refreshing cloud count…");
        refreshStats();
      });
    }
    $("btnAdd").addEventListener("click", () => doAdd());
    // Upload manual wallets is next to Add wallet (no Upload tab)
    if ($("fileInput")) {
      $("fileInput").addEventListener("change", async (ev) => {
        const f = ev.target.files && ev.target.files[0];
        if (!f) return;
        const text = await f.text();
        await importText(text, f.name);
        ev.target.value = "";
      });
    }

    const tok = $("siteToken");
    if (tok) {
      try {
        tok.value = sessionStorage.getItem(TOKEN_KEY) || "";
      } catch (_) {}
    }

    log("RugWatch web ready.");
    log("Tabs: Log · Wallets · Alerts. Upload manual wallets is next to Add wallet.");
    apiGet("/api/health")
      .then((h) => {
        log("Health OK");
        if (h.site_token_required) {
          log("Site passcode required — enter it in the field above.");
        }
      })
      .catch((e) => log("Health error: " + e.message));
    refreshAll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
