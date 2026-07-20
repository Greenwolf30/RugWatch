"""
RugWatch desktop GUI (Tkinter).

Run:
  python desktop_app.py
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any

from rugwatch import __app_name__, __version__
from rugwatch.alerts import format_alert
from rugwatch.config import load_dotenv
from rugwatch.db import RugWatchDB
from rugwatch.ingest.scan_mint import scan_and_ingest_mint
from rugwatch.monitor.launches import monitor_once


def run_gui() -> None:
    load_dotenv()
    db = RugWatchDB()

    # Cloud-primary: pull Gist into local cache (or create Gist if token set)
    _cloud_boot: dict = {}
    try:
        from rugwatch.cloud_store import ensure_cloud_cache

        _cloud_boot = ensure_cloud_cache(db)
    except Exception as exc:  # noqa: BLE001
        _cloud_boot = {"ok": False, "error": str(exc)}

    BG = "#0b0f14"
    SURFACE = "#12181f"
    FG = "#e8eef6"
    MUTED = "#8b9bb0"
    ACCENT = "#c9a227"
    BORDER = "#2a3544"
    ENTRY_BG = "#0e141c"
    DANGER = "#f07178"
    FONT = "Segoe UI"

    root = tk.Tk()
    root.title(f"{__app_name__} {__version__}")
    root.geometry("980x700")
    root.minsize(860, 560)
    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG, font=(FONT, 10))
    style.configure("TButton", font=(FONT, 10))
    style.configure("Accent.TButton", font=(FONT, 10, "bold"))

    header = tk.Frame(root, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    header.pack(fill="x", padx=16, pady=(14, 8))
    left_h = tk.Frame(header, bg=SURFACE)
    left_h.pack(side="left", fill="x", expand=True)
    tk.Label(
        left_h,
        text=__app_name__,
        bg=SURFACE,
        fg=ACCENT,
        font=(FONT, 16, "bold"),
    ).pack(side="left", padx=14, pady=12)
    tk.Label(
        left_h,
        text="Serial rugger wallet DB · launch watch · manual-only",
        bg=SURFACE,
        fg=MUTED,
        font=(FONT, 9),
    ).pack(side="left", padx=(0, 12))

    # View-count style pills: local now · lifetime logged · cloud now
    pills = tk.Frame(header, bg=SURFACE)
    pills.pack(side="right", padx=12, pady=10)
    wallets_now_var = tk.StringVar(value="wallets —")
    wallets_life_var = tk.StringVar(value="logged —")
    wallets_cloud_var = tk.StringVar(value="cloud —")
    _cloud_count_cache: dict[str, Any] = {"n": None, "err": None}

    def _pill(parent: tk.Misc, textvariable: tk.StringVar, *, fg: str = ACCENT) -> tk.Label:
        lab = tk.Label(
            parent,
            textvariable=textvariable,
            bg=ENTRY_BG,
            fg=fg,
            font=(FONT, 9, "bold"),
            padx=12,
            pady=6,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        lab.pack(side="left", padx=4)
        return lab

    pill_now = _pill(pills, wallets_now_var, fg="#8ee4a8")
    pill_life = _pill(pills, wallets_life_var, fg=ACCENT)
    pill_cloud = _pill(pills, wallets_cloud_var, fg="#7ec8e3")
    pill_now.configure(cursor="hand2")
    pill_life.configure(cursor="hand2")
    pill_cloud.configure(cursor="hand2")

    stats_var = tk.StringVar(value="Loading…")
    tk.Label(root, textvariable=stats_var, bg=BG, fg=MUTED, font=(FONT, 9), anchor="w").pack(
        fill="x", padx=20, pady=(0, 6)
    )

    # ── Scan bar (mint row + button row so Pull cloud stays visible) ──
    bar = tk.Frame(root, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
    bar.pack(fill="x", padx=16, pady=6)
    mint_row = tk.Frame(bar, bg=SURFACE)
    mint_row.pack(fill="x", padx=10, pady=(10, 4))
    btn_row = tk.Frame(bar, bg=SURFACE)
    btn_row.pack(fill="x", padx=10, pady=(0, 10))

    tk.Label(mint_row, text="MINT", bg=SURFACE, fg=MUTED, font=(FONT, 8, "bold")).pack(
        side="left", padx=(0, 8)
    )
    mint_var = tk.StringVar()
    mint_entry = tk.Entry(
        mint_row,
        textvariable=mint_var,
        bg=ENTRY_BG,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        font=(FONT, 11),
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
    )
    mint_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 10))

    deep_var = tk.BooleanVar(value=True)
    tk.Checkbutton(
        mint_row,
        text="Deep (Helius)",
        variable=deep_var,
        bg=SURFACE,
        fg=MUTED,
        selectcolor=ENTRY_BG,
        activebackground=SURFACE,
        activeforeground=FG,
    ).pack(side="left", padx=(0, 8))

    # ── Manual wallet ──────────────────────────────────────────────────
    man = tk.Frame(root, bg=BG)
    man.pack(fill="x", padx=16, pady=(4, 4))
    tk.Label(man, text="Manual wallet", bg=BG, fg=MUTED, font=(FONT, 8, "bold")).pack(
        side="left", padx=(4, 8)
    )
    wallet_var = tk.StringVar()
    tk.Entry(
        man,
        textvariable=wallet_var,
        bg=ENTRY_BG,
        fg=FG,
        insertbackground=FG,
        relief="flat",
        width=42,
        highlightthickness=1,
        highlightbackground=BORDER,
    ).pack(side="left", ipady=5, padx=(0, 8))
    score_var = tk.StringVar(value="75")
    tk.Label(man, text="score", bg=BG, fg=MUTED, font=(FONT, 8)).pack(side="left")
    tk.Entry(
        man,
        textvariable=score_var,
        bg=ENTRY_BG,
        fg=FG,
        width=4,
        relief="flat",
        highlightthickness=1,
        highlightbackground=BORDER,
    ).pack(side="left", padx=4, ipady=4)

    # ── Notebook ───────────────────────────────────────────────────────
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=16, pady=8)

    def make_text(parent: tk.Misc) -> scrolledtext.ScrolledText:
        t = scrolledtext.ScrolledText(
            parent,
            bg=ENTRY_BG,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Cascadia Mono", 9),
            wrap="word",
        )
        t.pack(fill="both", expand=True, padx=2, pady=2)
        return t

    # Tabs: Log · Wallets · Alerts only (no Upload tab between them)
    tab_log = tk.Frame(nb, bg=BG)
    tab_wallets = tk.Frame(nb, bg=BG)
    tab_alerts = tk.Frame(nb, bg=BG)
    nb.add(tab_log, text="  Log  ")
    nb.add(tab_wallets, text="  Wallets  ")
    nb.add(tab_alerts, text="  Alerts  ")

    log_box = make_text(tab_log)
    wallets_box = make_text(tab_wallets)
    # Wallets tab: dimmer yellow scores; dimmer red address/notes
    wallets_box.configure(fg="#c47a7a", insertbackground="#c47a7a")
    wallets_box.tag_configure("w_nums", foreground="#c4a84a")
    wallets_box.tag_configure("w_data", foreground="#c47a7a")
    wallets_box.tag_configure(
        "w_addr",
        foreground="#c98a8a",
        underline=True,
    )

    def _on_wallet_addr_click(event: Any) -> str:
        """Left-click a wallet address in the Wallets tab → copy to clipboard."""
        try:
            idx = wallets_box.index(f"@{event.x},{event.y}")
            ranges = wallets_box.tag_ranges("w_addr")
            # ranges is (start1, end1, start2, end2, ...)
            for i in range(0, len(ranges), 2):
                start, end = ranges[i], ranges[i + 1]
                if wallets_box.compare(start, "<=", idx) and wallets_box.compare(
                    idx, "<", end
                ):
                    addr = wallets_box.get(start, end).strip()
                    if addr:
                        root.clipboard_clear()
                        root.clipboard_append(addr)
                        root.update_idletasks()
                        log(f"Copied address: {addr[:8]}…")
                    break
        except Exception:  # noqa: BLE001
            pass
        return "break"

    wallets_box.tag_bind("w_addr", "<Button-1>", _on_wallet_addr_click)
    wallets_box.tag_bind("w_addr", "<Enter>", lambda _e: wallets_box.config(cursor="hand2"))
    wallets_box.tag_bind("w_addr", "<Leave>", lambda _e: wallets_box.config(cursor=""))
    alerts_box = make_text(tab_alerts)

    q: queue.Queue = queue.Queue()
    busy = {"v": False}

    def log(msg: str) -> None:
        log_box.insert("end", msg + "\n")
        log_box.see("end")

    def refresh_stats() -> None:
        st = db.stats()
        n = int(st.get("wallets_logged") or st.get("wallets") or 0)
        life = int(st.get("wallets_logged_lifetime") or n)
        wallets_now_var.set(f"wallets {n}")
        wallets_life_var.set(f"logged {life}")
        # Cloud pill: last known count (updated async / after push-pull)
        cn = _cloud_count_cache.get("n")
        if cn is None:
            wallets_cloud_var.set("cloud —")
            cloud_bit = "Cloud: —"
        else:
            wallets_cloud_var.set(f"cloud {cn}")
            cloud_bit = f"Cloud now: {cn}"
        stats_var.set(
            f"In DB now: {n}  ·  Lifetime logged: {life}  ·  {cloud_bit}  ·  "
            f"high_risk={st['high_risk_wallets']}  ·  "
            f"incidents={st['incidents']}  ·  alerts={st['unacked_alerts']} unacked"
        )
        try:
            root.title(
                f"{__app_name__} {__version__}  ·  wallets {n}  ·  "
                f"logged {life}  ·  cloud {cn if cn is not None else '—'}"
            )
        except tk.TclError:
            pass

    def refresh_cloud_count(*, force: bool = False) -> None:
        """Background fetch of how many wallets are in the cloud file right now."""

        def work() -> None:
            try:
                from rugwatch.cloud_store import fetch_cloud_wallet_count

                r = fetch_cloud_wallet_count()
                q.put(("cloud_count", r))
            except Exception as exc:  # noqa: BLE001
                q.put(("cloud_count", {"ok": False, "count": None, "error": str(exc)}))

        threading.Thread(target=work, daemon=True).start()

    def refresh_wallets() -> None:
        rows = db.list_wallets(min_score=0, limit=100)
        wallets_box.delete("1.0", "end")
        if not rows:
            wallets_box.insert(
                "end",
                "No wallets yet.\n"
                "Manual-only mode: use Add wallet (or import JSON / pull remote).\n"
                "Scan mint only suggests addresses — it does not auto-flag.\n",
            )
            return
        for w in rows:
            nums = f"{w.get('risk_score'):3}  x{w.get('times_seen')}"
            addr = str(w.get("address") or "").strip()
            rest = (
                f"\n     [{w.get('label') or ''}] {(w.get('notes') or '')[:80]}\n\n"
            )
            wallets_box.insert("end", nums, "w_nums")
            wallets_box.insert("end", "  ", "w_data")
            if addr:
                wallets_box.insert("end", addr, "w_addr")
            wallets_box.insert("end", rest, "w_data")

    def refresh_alerts() -> None:
        rows = db.list_alerts(limit=50)
        alerts_box.delete("1.0", "end")
        if not rows:
            alerts_box.insert(
                "end",
                "No alerts yet. Run Monitor once after building a wallet list.\n\n"
                "When a known wallet hits a new launch, each alert shows:\n"
                "  • Token symbol/name\n"
                "  • Full mint address\n"
                "  • Full wallet address\n"
                "  • Solscan token + wallet links and DexScreener link\n",
            )
            return
        for a in rows:
            alerts_box.insert("end", format_alert(a) + "\n")

    def refresh_all() -> None:
        refresh_stats()
        refresh_wallets()
        refresh_alerts()

    def poll() -> None:
        try:
            while True:
                kind, payload = q.get_nowait()
                busy["v"] = False
                if kind == "err":
                    log(f"ERROR: {payload}")
                    messagebox.showerror(__app_name__, str(payload))
                elif kind == "scan":
                    mode = "AUTO-SAVE" if payload.get("auto_flag") else "MANUAL-ONLY"
                    log(
                        f"Scan OK · {payload.get('symbol')} · type={payload.get('incident_type')} · {mode}"
                    )
                    if payload.get("note"):
                        log(f"  {payload.get('note')}")
                    for f in payload.get("wallets_flagged") or []:
                        tag = "saved" if f.get("saved") else "suggest"
                        log(
                            f"  [{tag}] {f.get('role')}: {f.get('wallet')} "
                            f"(score {f.get('risk_score')})"
                        )
                    if payload.get("errors"):
                        for e in payload["errors"]:
                            log(f"  note: {e}")
                    refresh_all()
                elif kind == "monitor":
                    log(
                        f"Monitor · scanned={payload.get('launches_scanned')} "
                        f"known={payload.get('known_wallets')} "
                        f"alerts={payload.get('alert_count')}"
                    )
                    for a in payload.get("alerts") or []:
                        # Full multi-line alert (token + full mint + links)
                        for line in format_alert(a).splitlines():
                            if line.strip():
                                log(line)
                    if payload.get("alert_count"):
                        nb.select(tab_alerts)
                    refresh_all()
                elif kind == "info":
                    log(str(payload))
                    refresh_all()
                elif kind == "cloud_count":
                    r = payload if isinstance(payload, dict) else {}
                    if r.get("ok") and r.get("count") is not None:
                        _cloud_count_cache["n"] = int(r["count"])
                        _cloud_count_cache["err"] = None
                        wallets_cloud_var.set(f"cloud {int(r['count'])}")
                    else:
                        # Keep last good count if any; show n/a only when never loaded
                        if _cloud_count_cache.get("n") is None:
                            wallets_cloud_var.set("cloud n/a")
                        _cloud_count_cache["err"] = r.get("error")
                    refresh_stats()
        except queue.Empty:
            pass
        root.after(150, poll)

    def do_scan() -> None:
        if busy["v"]:
            return
        mint = mint_var.get().strip()
        if not mint:
            messagebox.showinfo(__app_name__, "Paste a token mint address.")
            return
        busy["v"] = True
        log(f"Scanning {mint}…")

        def work() -> None:
            try:
                r = scan_and_ingest_mint(mint, db=db, deep=deep_var.get())
                q.put(("scan", r))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def do_monitor() -> None:
        if busy["v"]:
            return
        busy["v"] = True
        log("Polling recent pump launches…")

        def work() -> None:
            try:
                r = monitor_once(db, limit=25, min_score=40)
                q.put(("monitor", r))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def do_add() -> None:
        addr = wallet_var.get().strip()
        if not addr:
            messagebox.showinfo(__app_name__, "Enter a wallet address.")
            return
        try:
            score = int(score_var.get().strip() or 70)
        except ValueError:
            score = 70
        db.upsert_wallet(addr, label="manual", risk_score=score, notes="manual GUI", source="manual")
        log(f"Added wallet {addr} score={score}")
        wallet_var.set("")
        try:
            from rugwatch.cloud_store import sync_after_manual_change

            sync = sync_after_manual_change(db)
            if sync:
                if sync.get("ok"):
                    log(
                        f"Cloud push OK · gist={sync.get('gist_id')} · "
                        f"wallets={sync.get('wallet_count')}"
                    )
                    if sync.get("wallet_count") is not None:
                        _cloud_count_cache["n"] = int(sync["wallet_count"])
                else:
                    log(f"Cloud push failed: {sync.get('error')}")
        except Exception as exc:  # noqa: BLE001
            log(f"Cloud sync error: {exc}")
        refresh_all()
        refresh_cloud_count()

    def do_clear_db() -> None:
        if not messagebox.askyesno(
            __app_name__,
            "Delete ALL wallets, incidents, and alerts from the local database?\n"
            "This cannot be undone (export first if you need a backup).",
        ):
            return
        cleared = db.clear_all()
        log(f"Database cleared: {cleared}")
        refresh_all()

    def do_export() -> None:
        from pathlib import Path

        from rugwatch.remote_wallets import export_wallets_to_file

        out = Path.home() / "RugWatch" / "data" / "wallets_export.json"
        r = export_wallets_to_file(out, db)
        log(f"Exported {r.get('count')} wallets → {r.get('path')}")
        messagebox.showinfo(__app_name__, f"Exported to:\n{r.get('path')}")
        refresh_cloud_count()

    def do_upload_file() -> None:
        """Pick Ruggers/JSON/txt file and import into local DB (no Upload tab)."""
        path = filedialog.askopenfilename(
            title="Upload manual wallets (JSON or TXT)",
            filetypes=[
                ("Wallet lists", "*.json;*.txt"),
                ("JSON (Ruggers / RugWatch)", "*.json"),
                ("Text (one address per line)", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        from rugwatch.remote_wallets import import_wallets_from_file

        r = import_wallets_from_file(path, db)
        if not r.get("ok"):
            messagebox.showerror(__app_name__, f"Upload failed:\n{r.get('error')}")
            log(f"Upload file failed: {r.get('error')} path={path}")
            return
        msg = (
            f"Imported {r.get('imported')} wallet(s) from file "
            f"(skipped {r.get('skipped')})."
        )
        log(f"Upload file OK · {msg} · {path}")
        try:
            from rugwatch.cloud_store import sync_after_manual_change

            sync = sync_after_manual_change(db)
            if sync and sync.get("ok"):
                log(f"Cloud push after upload · wallets={sync.get('wallet_count')}")
                if sync.get("wallet_count") is not None:
                    _cloud_count_cache["n"] = int(sync["wallet_count"])
            elif sync and not sync.get("ok"):
                log(f"Cloud push after upload failed: {sync.get('error')}")
        except Exception as exc:  # noqa: BLE001
            log(f"Cloud sync after upload: {exc}")
        refresh_all()
        refresh_cloud_count()
        messagebox.showinfo(__app_name__, msg + f"\n\n{path}")

    def do_pull_remote() -> None:
        from rugwatch.remote_wallets import pull_remote_into_db

        r = pull_remote_into_db(db)
        if not r.get("ok"):
            messagebox.showinfo(
                __app_name__,
                "Set RUGWATCH_WALLETS_URL in RugWatch/.env to a JSON list URL "
                "(GitHub Gist raw, etc.), then try again.\n\n"
                f"Detail: {r.get('error')}",
            )
            log(f"Pull remote failed: {r.get('error')}")
            return
        log(f"Pulled remote: imported={r.get('imported')} total_db={r.get('db_wallets')}")
        refresh_all()

    def do_push_cloud() -> None:
        from rugwatch.cloud_store import push_to_cloud

        try:
            r = push_to_cloud(db)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(__app_name__, str(exc))
            log(f"Push cloud error: {exc}")
            return
        if not r.get("ok"):
            messagebox.showinfo(
                __app_name__,
                "Cloud needs a GitHub token.\n\n"
                "Repo mode (recommended):\n"
                "  RUGWATCH_CLOUD=repo\n"
                "  RUGWATCH_GITHUB_REPO=YourUser/RugWatch\n"
                "  GITHUB_TOKEN=ghp_...\n\n"
                "Or Gist mode:\n"
                "  RUGWATCH_CLOUD=gist\n"
                "  GITHUB_TOKEN=ghp_... (gist scope)\n\n"
                f"Detail: {r.get('error')}",
            )
            log(f"Push cloud failed: {r.get('error')}")
            return
        log(
            f"Cloud {r.get('action')}: gist={r.get('gist_id')} "
            f"url={r.get('html_url')} wallets={r.get('wallet_count')}"
        )
        if r.get("wallet_count") is not None:
            _cloud_count_cache["n"] = int(r["wallet_count"])
        messagebox.showinfo(
            __app_name__,
            f"Saved to cloud (GitHub).\n\n"
            f"URL: {r.get('html_url') or r.get('path') or 'see Log'}\n"
            f"Wallets: {r.get('wallet_count')}\n",
        )
        refresh_all()
        refresh_cloud_count()

    def do_pull_cloud() -> None:
        from rugwatch.cloud_store import pull_from_cloud

        try:
            r = pull_from_cloud(db)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(__app_name__, str(exc))
            log(f"Pull cloud error: {exc}")
            return
        if not r.get("ok"):
            messagebox.showinfo(__app_name__, f"Pull failed:\n{r.get('error')}")
            log(f"Pull cloud failed: {r.get('error')}")
            return
        log(
            f"Pull cloud OK · imported={r.get('imported')} "
            f"db={r.get('db_wallets')} source={r.get('source')}"
        )
        refresh_all()
        refresh_cloud_count()

    ttk.Button(btn_row, text="Scan mint", style="Accent.TButton", command=do_scan).pack(
        side="left", padx=(0, 6)
    )
    ttk.Button(btn_row, text="Monitor once", command=do_monitor).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Refresh", command=refresh_all).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Clear DB", command=do_clear_db).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Export JSON", command=do_export).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Push cloud", command=do_push_cloud).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Pull cloud", command=do_pull_cloud).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Pull URL", command=do_pull_remote).pack(side="left")

    # Manual row: Add wallet + Upload next to it (normal font). No Upload tab.
    ttk.Button(man, text="Add wallet", command=do_add).pack(side="left", padx=(8, 4))
    ttk.Button(
        man,
        text="Upload manual wallets",
        command=do_upload_file,
    ).pack(side="left", padx=(4, 8))

    mint_entry.bind("<Return>", lambda _e: do_scan())
    refresh_all()
    refresh_cloud_count()
    log(
        f"{__app_name__} ready. MANUAL-ONLY. "
        "Tabs: Log · Wallets · Alerts. "
        "Pills: wallets = in DB now · logged = lifetime · cloud = on GitHub now. "
        "Use Add wallet for one address, or Upload manual wallets next to it "
        "(JSON/txt from Ruggers Export). Website: python run_web.py "
        "(API keys stay on the server). See RugCheck Documentation.md."
    )
    # Click cloud pill to refresh cloud count
    pill_cloud.bind("<Button-1>", lambda _e: refresh_cloud_count(force=True))
    try:
        from rugwatch.cloud_store import cloud_status

        st = cloud_status()
        log(
            f"Storage: {st.get('storage')} · enabled={st.get('cloud_enabled')} "
            f"token={st.get('has_token')} gist_id={st.get('gist_id') or 'none'}"
        )
        if _cloud_boot:
            if _cloud_boot.get("ok"):
                log(
                    f"Cloud boot: imported={_cloud_boot.get('imported')} "
                    f"gist={_cloud_boot.get('gist_id') or _cloud_boot.get('action')}"
                )
            elif _cloud_boot.get("skipped"):
                log(f"Cloud boot: {_cloud_boot.get('error')}")
            else:
                log(f"Cloud boot issue: {_cloud_boot.get('error')}")
    except Exception:  # noqa: BLE001
        pass
    root.after(150, poll)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
