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
    if (!r.ok) throw new Error(data.error || r.statusText || "request failed");
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
          "No wallets yet.\nUse Add wallet, or Upload manual wallets (next to Add wallet).\n";
        return;
      }
      // Same layout as before; yellow scores, red wallet lines
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

  async function doMonitor() {
    log("Polling recent launches…");
    try {
      const data = await apiPost("/api/monitor", {});
      log(
        "Monitor · scanned=" +
          (data.launches_scanned ?? "") +
          " known=" +
          (data.known_wallets ?? "") +
          " alerts=" +
          (data.alert_count ?? 0)
      );
      (data.alerts || []).forEach((a) => log("  ALERT: " + (a.message || "")));
      if (data.alert_count) switchTab("alerts");
      await refreshAll();
    } catch (e) {
      log("ERROR: " + e.message);
      alert(e.message);
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

  async function doPullCloud() {
    log("Pull cloud…");
    try {
      const data = await apiPost("/api/pull-cloud", {});
      log(
        "Pull cloud OK · imported=" +
          (data.imported ?? 0) +
          " · db_wallets=" +
          (data.db_wallets ?? "?") +
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
      const msg =
        "Imported " +
        (data.imported ?? 0) +
        " wallet(s)" +
        (data.skipped != null ? " (skipped " + data.skipped + ")" : "") +
        " · " +
        label;
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
    // Mint field: left-click copies the address when present
    if ($("mintInput")) {
      const mintEl = $("mintInput");
      mintEl.setAttribute("title", "Left-click to copy mint address");
      mintEl.addEventListener("click", () => {
        const v = String(mintEl.value || "").trim();
        if (!v) return;
        mintEl.select();
        const done = () => log("Copied mint: " + v.slice(0, 8) + "…");
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(v).then(done).catch(() => {
            try {
              document.execCommand("copy");
              done();
            } catch (_) {
              alert("Copy failed:\n" + v);
            }
          });
        } else {
          try {
            document.execCommand("copy");
            done();
          } catch (_) {
            alert("Copy failed:\n" + v);
          }
        }
      });
    }
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
