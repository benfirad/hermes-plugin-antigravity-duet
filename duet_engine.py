#!/usr/bin/env python3
"""
Backwards-compatibility shim for daak_duffy.
Delegates all engine and store operations to daak_duffy.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure local package path resolution
_dir = Path(__file__).parent.resolve()
if str(_dir) not in sys.path:
    sys.path.insert(0, str(_dir))

from daak_duffy import *  # noqa: F401, F403
from daak_duffy import main

if __name__ == "__main__":
    main()
