"""Entry script for the packaged app (PyInstaller needs a plain script)."""

import sys

from transcribe_anywhere.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
