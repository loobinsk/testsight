"""Testsight: intelligent impacted-test runner for Python projects."""

from __future__ import annotations

from importlib import metadata

try:  # pragma: no cover - best effort during development
    __version__ = metadata.version("testsight")
except metadata.PackageNotFoundError:  # pragma: no cover - local/dev installs
    __version__ = "0.1.0"

from .runner import TestsightRunner

__all__ = ["TestsightRunner", "__version__"]
