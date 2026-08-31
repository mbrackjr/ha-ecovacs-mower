"""Tests for mow_area service input validation."""

import pytest
import voluptuous as vol

from custom_components.ecovacs_mower import AREA_IDS_SCHEMA


@pytest.mark.parametrize("value", [1, 999, [1, 3, 999]])
def test_area_ids_accept_valid_values(value) -> None:
    expected = value if isinstance(value, list) else [value]
    assert AREA_IDS_SCHEMA(value) == expected


@pytest.mark.parametrize("value", [0, -1, 1000, 1.5, "1", None, True])
def test_area_ids_reject_invalid_values(value) -> None:
    with pytest.raises(vol.Invalid):
        AREA_IDS_SCHEMA(value)
