"""Ecovacs sensor platform, including mower area diagnostics.

The existing sensor implementation lives in ``sensor_base.py`` unchanged from
this integration. Keeping the platform entry point here lets the dynamic mower
area entities be added without duplicating or rewriting the existing sensor
implementation.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import sensor_base as _base
from .area_sensors import async_setup_area_sensors
from . import EcovacsMowerConfigEntry

# Preserve the existing sensor module's namespace, including private helpers
# used by this repository's tests. This is deliberately a namespace transfer,
# not a second implementation of the platform.
globals().update(
    {
        name: value
        for name, value in vars(_base).items()
        if name not in {"__name__", "__package__", "__loader__", "__spec__"}
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the existing sensors and verified mower area sensors."""
    await _base.async_setup_entry(hass, config_entry, async_add_entities)
    await async_setup_area_sensors(config_entry, async_add_entities)
