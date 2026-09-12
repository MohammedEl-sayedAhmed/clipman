#!/usr/bin/env python3
"""Checkout and staged-tree launcher; pip installs use clipman.cli."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clipman.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
