"""Frozen-executable entry point (PyInstaller cannot use `-m app.main`)."""

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
