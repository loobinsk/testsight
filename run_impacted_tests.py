#!/usr/bin/env python3
"""Backward-compatible entry point wrapping the Testsight CLI."""

from __future__ import annotations

import sys

from testsight.cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
