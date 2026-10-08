"""Render packaging/workpulse.ico from the same artwork the tray uses."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ui.theme import app_icon

target = Path(__file__).with_name("workpulse.ico")
app_icon(size=256).save(target, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"wrote {target}")
