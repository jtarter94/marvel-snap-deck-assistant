"""macOS notifications (no-op elsewhere)."""
from __future__ import annotations

import subprocess
import sys


def notify(title: str, message: str) -> bool:
    if sys.platform != "darwin":
        return False
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=10, capture_output=True)
        return True
    except Exception:
        return False
