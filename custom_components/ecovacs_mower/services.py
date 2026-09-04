"""Home Assistant actions for Ecovacs GOAT area parameters."""

from __future__ import annotations

import asyncio

from deebot_client.device import Device

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_extract_device_ids

from .const import DOMAIN
from .deebot_patch.areas import (
    AREA_PARAMETER_CLASSES,
    AREA_PARAMETER_PROFILES,
    GetAreaParameter,
    get_area,
)

SERVICE_SET_AREA_PARAMETERS = "set_area_parameters"
AREA_PARAMETER_REFRESH_DELAY = 3.0


def _find_device(hass: HomeAssistant, device_id: str) -> Device:
    """Resolve a Home Assistant device ID to the loaded deebot device."""
    registry = dr.async_get(hass)
    device_entry = registry.async_get(device_id)
    if device_entry is None:
        raise ServiceValidationError("The selected mower device was not found")

    device_dids = {
        identifier[1]
        for identifier in device_entry.identifiers
        if identifier[0] == DOMAIN
    }
    for config_entry_id in device_entry.config_entries:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
            continue
        for device in entry.runtime_data.devices:
            if device.device_info["did"] in device_dids:
                return device

    raise ServiceValidationError("The selected mower is not loaded")


async def _refresh_current_area(device: Device, area_id: str):
    """Ask the mower for the current complete area parameter set."""
    response = await device.execute_command(GetAreaParameter())
    if not response or response.get("ret") != "ok":
        raise ServiceValidationError("The mower did not return area parameters")
    current = get_area(device.events, area_id)
    if current is None:
        raise ServiceValidationError(f"Area {area_id} was not returned by the mower")
    return current


async def _refresh_after_set(device: Device) -> None:
    """Wait for the mower/cloud round trip, then refresh the sensor state."""
    # The API acknowledgement only establishes that the request reached the
    # service endpoint. The mower still needs time to receive and apply it.
    await asyncio.sleep(AREA_PARAMETER_REFRESH_DELAY)
    await device.execute_command(GetAreaParameter())


async def async_set_area_parameters(hass: HomeAssistant, call: ServiceCall) -> None:
    """Set one area's mowing parameters, preserving fields not supplied."""
    device_ids = async_extract_device_ids(hass, call)
    if len(device_ids) != 1:
        raise ServiceValidationError("Select exactly one mower device")

    device = _find_device(hass, next(iter(device_ids)))
    class_ = device.device_info["class"]
    if class_ not in AREA_PARAMETER_CLASSES or class_ not in AREA_PARAMETER_PROFILES:
        raise ServiceValidationError(
            f"Area parameter control is not validated for mower class {class_}"
        )
    profile = AREA_PARAMETER_PROFILES[class_]

    area_id = str(int(call.data["area_id"]))
    current = await _refresh_current_area(device, area_id)

    if None in (
        current.mow_height_level,
        current.cut_mode,
        current.obstacle_height,
        current.angle,
    ):
        raise ServiceValidationError(
            f"Area {area_id} does not have a complete parameter set"
        )

    payload = {
        "areaID": area_id,
        "mowHeightLevel": int(current.mow_height_level),
        "cutMode": int(current.cut_mode),
        "obstacleHeight": int(current.obstacle_height),
        "angle": int(current.angle),
    }

    try:
        if "mow_height_cm" in call.data:
            payload["mowHeightLevel"] = profile.mow_height_to_wire(
                float(call.data["mow_height_cm"])
            )
        if "speed_mps" in call.data:
            payload["cutMode"] = profile.speed_to_wire(float(call.data["speed_mps"]))
        if "obstacle_max_cm" in call.data:
            payload["obstacleHeight"] = profile.obstacle_height_to_wire(
                int(call.data["obstacle_max_cm"])
            )
        if "cutting_angle" in call.data:
            payload["angle"] = profile.angle_to_wire(float(call.data["cutting_angle"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ServiceValidationError("One or more area parameter values are invalid") from exc

    from deebot_client.commands.json.custom import CustomCommand

    response = await device.execute_command(CustomCommand("setAreaParameter", payload))
    if not response or response.get("ret") != "ok":
        raise ServiceValidationError("The mower did not acknowledge setAreaParameter")

    body = response.get("resp", {}).get("body", {})
    if body.get("code") not in (None, 0, 200):
        raise ServiceValidationError(
            f"The mower rejected setAreaParameter (code {body.get('code')})"
        )

    await _refresh_after_set(device)


def async_register(hass: HomeAssistant) -> None:
    """Register integration service actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AREA_PARAMETERS,
        lambda call: async_set_area_parameters(hass, call),
    )
