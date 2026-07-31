"""Testpaket."""

import sys

import pytest

requires_ha = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Home Assistant kan inte importeras på Windows (fcntl). Körs i CI.",
)
