"""Start RugWatch website (UI + API). Keys load from .env only."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_server import main

if __name__ == "__main__":
    raise SystemExit(main())
