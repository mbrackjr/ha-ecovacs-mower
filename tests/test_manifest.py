"""Manifest må uppfylla integrationens hårda krav."""

import json
from pathlib import Path

MANIFEST = (
    Path(__file__).parent.parent
    / "custom_components"
    / "ecovacs_mower"
    / "manifest.json"
)


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_domain_is_ecovacs_mower() -> None:
    assert _manifest()["domain"] == "ecovacs_mower"


def test_version_present() -> None:
    # Custom components måste ha version; core-integrationer får inte ha det.
    assert _manifest()["version"]


def test_deebot_client_pinned_exactly() -> None:
    assert _manifest()["requirements"] == ["deebot-client==18.5.1"]


def test_no_sucks_dependency() -> None:
    joined = " ".join(_manifest()["requirements"])
    assert "sucks" not in joined
