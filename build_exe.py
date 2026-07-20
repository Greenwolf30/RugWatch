"""
Build RugWatch desktop .exe with PyInstaller (onedir).

Usage:
  python build_exe.py

Output:
  dist/RugWatch/RugWatch.exe
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "desktop_app.py"
DIST = ROOT / "dist"
NAME = "RugWatch"
PKG = ROOT / "rugwatch"


def main() -> int:
    if not ENTRY.exists():
        print(f"Missing {ENTRY}")
        return 1
    if not PKG.exists():
        print(f"Missing package {PKG}")
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    sep = ";" if sys.platform.startswith("win") else ":"
    datas = [f"{PKG}{sep}rugwatch"]
    # Include empty cloud wallets template if present
    wallets = ROOT / "data" / "wallets_cloud.json"
    if wallets.is_file():
        datas.append(f"{wallets.parent}{sep}data")
    # Ship user docs next to the app package
    docs = ROOT / "RugCheck Documentation.md"
    if docs.is_file():
        datas.append(f"{docs}{sep}.")

    hidden = [
        "rugwatch",
        "rugwatch.db",
        "rugwatch.config",
        "rugwatch.cli",
        "rugwatch.cloud_store",
        "rugwatch.remote_wallets",
        "rugwatch.http_util",
        "rugwatch.alerts",
        "rugwatch.ingest",
        "rugwatch.ingest.scan_mint",
        "rugwatch.monitor",
        "rugwatch.monitor.launches",
        "rugwatch.sources",
        "rugwatch.sources.rugcheck",
        "rugwatch.sources.pumpfun",
        "rugwatch.sources.rpc",
        "rugwatch.sources.solscan",
        "certifi",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--onedir",
        f"--name={NAME}",
        f"--distpath={DIST}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT}",
    ]
    for d in datas:
        cmd.append(f"--add-data={d}")
    for h in hidden:
        cmd.append(f"--hidden-import={h}")
    cmd.append(str(ENTRY))

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))
    exe = DIST / NAME / f"{NAME}.exe"
    print("\nSUCCESS" if exe.is_file() else "\nBuild finished (check dist/)")
    print(f"Run: {exe}")
    print("Keep .env next to the .exe folder or in C:\\Users\\levyr\\RugWatch\\.env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
