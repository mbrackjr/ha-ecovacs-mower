"""Diagnostik för Ecovacs Mower."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import EcovacsMowerConfigEntry
from .const import CONF_OVERRIDE_MQTT_URL, CONF_OVERRIDE_REST_URL

# CONF_OVERRIDE_MQTT_URL/CONF_OVERRIDE_REST_URL redactas för att
# självhostade installationer inte ska läcka sin interna broker- eller
# REST-adress i en diagnostikrapport som delas i ett GitHub-ärende.
#
# "homeId" redactas trots att det inte finns i ApiDeviceInfo-TypedDicten:
# api_client.py matar rå API-JSON rakt in i den, så nycklar utanför
# TypedDict-formen försvinner inte — de följer ändå med i
# device.device_info och hamnar i dumpen. Samma läckmekanism som
# override-URL:erna.
REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_OVERRIDE_MQTT_URL,
    CONF_OVERRIDE_REST_URL,
    "did",
    "name",
    "homeId",
    "mac",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EcovacsMowerConfigEntry
) -> dict[str, Any]:
    """Diagnostik för en config entry."""
    controller = entry.runtime_data
    return {
        "config": async_redact_data(dict(entry.data), REDACT),
        "devices": [
            async_redact_data(dict(device.device_info), REDACT)
            for device in controller.devices
        ],
    }
