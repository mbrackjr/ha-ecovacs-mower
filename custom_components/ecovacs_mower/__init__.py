"""Ecovacs Mower — Home Assistant integration for GOAT lawn mowers."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr, service
from homeassistant.helpers.typing import ConfigType

from .const import CONF_CREDENTIALS, DOMAIN
from .controller import EcovacsController, async_remove_map_store

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.LAWN_MOWER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

type EcovacsMowerConfigEntry = ConfigEntry[EcovacsController]


def _valid_area_id(value: object) -> int:
    """Validate an area ID without coercing its type."""
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 999:
        raise vol.Invalid("area ID must be an integer between 1 and 999")
    return value


AREA_IDS_SCHEMA = vol.All(
    cv.ensure_list,
    vol.Length(min=1),
    [_valid_area_id],
)


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration domain."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        "mow_area",
        entity_domain="lawn_mower",
        schema={vol.Required("area_ids"): AREA_IDS_SCHEMA},
        func="async_mow_area",
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: EcovacsMowerConfigEntry
) -> bool:
    """Set up the integration from a config entry."""
