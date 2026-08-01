"""Diagnostik för Ecovacs Mower."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_DEVICE_ID, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import EcovacsMowerConfigEntry
from .const import CONF_OVERRIDE_MQTT_URL, CONF_OVERRIDE_REST_URL

# CONF_OVERRIDE_MQTT_URL/CONF_OVERRIDE_REST_URL redactas för att
# självhostade installationer inte ska läcka sin interna broker- eller
# REST-adress i en diagnostikrapport som delas i ett GitHub-ärende.
#
# CONF_DEVICE_ID är forkspecifik och finns inte i uppströms REDACT: kärnan
# sparar aldrig klientens enhets-ID utan genererar ett nytt vid varje start
# — vilket är precis 1013-buggen den här integrationen finns för att rätta.
# Vi persisterar det i entry.data (config_flow.py), så det når dumpen där
# kärnans version aldrig kunde nå den. Båda lägena läcker:
#
# * self-hosted: värdet är ``HA-{slugify(location_name)}`` — användarens
#   instans-/hemnamn, direkt PII.
# * moln: värdet är den Ecovacs-verifierade, stabila klientidentiteten.
#   Ihop med ett läckt konto hoppar den över e-postverifieringen helt —
#   exakt det skydd hela fixen bygger på.
#
# "homeId" redactas trots att det inte finns i ApiDeviceInfo-TypedDicten:
# api_client.py matar rå API-JSON rakt in i den, så nycklar utanför
# TypedDict-formen försvinner inte — de följer ändå med i
# device.device_info och hamnar i dumpen. Samma läckmekanism som
# override-URL:erna.
#
# "nick" (användarens eget namn på klipparen) och "resource" (andra halvan
# av MQTT-topicen; "did" är redan maskerad, men utan "resource" går topicen
# ändå att rekonstruera) står däremot i TypedDicten och följer med helt
# oavkortat — device.device_info *är* den råa api-dicten.
REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICE_ID,
    CONF_OVERRIDE_MQTT_URL,
    CONF_OVERRIDE_REST_URL,
    "did",
    "name",
    "nick",
    "resource",
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
