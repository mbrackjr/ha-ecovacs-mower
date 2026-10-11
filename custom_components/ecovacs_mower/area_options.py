"""Zone names in the ``mow_area`` action's area picker.

The action takes area IDs (``deebot_patch.zonal.MowArea``), and the mower
reports a name for each of them (``deebot_patch.areas``). ``services.yaml``
can only describe a fixed field, so the description is republished at runtime
with a ``select`` selector whose options are the reported zones: the name as
the label, the ID as the value. The action's contract does not change, and
``__init__.AREA_IDS_SCHEMA`` already accepts the IDs as strings, which is how a
``select`` selector returns them.

``services.yaml`` stays the one source of the description: it is loaded once
and only the ``area_ids`` selector is swapped. With no zone known, which is the
case until the mower has named the map in use and answered ``getAreaSet``, the
static text field is what is published.

One description serves every mower of every config entry, because Home
Assistant keys descriptions by action, not by target. With more than one mower
reporting zones, each label is prefixed with its mower's name. The value is
still a bare ID, which means something different on each mower.

The frontend fetches descriptions again only when an action is registered or
removed, so a zone added in the app shows up in an open browser after a
reload. Zones change rarely; the action itself is unaffected.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from functools import partial
from pathlib import Path
from typing import Any

from deebot_client.device import Device
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.util.yaml import load_yaml_dict

from . import EcovacsMowerConfigEntry
from .const import DOMAIN
from .deebot_patch.areas import MowerAreaEvent
from .deebot_patch.zonal import MowArea

SERVICE = "mow_area"
FIELD = "area_ids"

# hass.data keys. Domain-wide rather than per config entry: the description
# they produce is domain-wide too.
_BASE = f"{DOMAIN}_mow_area_description"
_ZONES = f"{DOMAIN}_mow_area_zones"
_PUBLISHED = f"{DOMAIN}_mow_area_published"

# A zone is (area ID, name or None), per mower: did -> (mower name, zones).
type MowerZones = tuple[str, Mapping[str, str | None]]


def zone_options(mowers: Mapping[str, MowerZones]) -> list[dict[str, str]]:
    """Return the ``select`` options for every zone of every mower.

    An ID the action would reject (not a whole number from 0 to 999) is left
    out rather than offered and then refused. A zone the mower has not named
    yet is labelled "Area <id>". Two zones with the same label carry their ID,
    so a user can still tell them apart.
    """
    named = [(name, zones) for name, zones in mowers.values() if zones]
    prefix = len(named) > 1

    options: list[dict[str, str]] = []
    for mower_name, zones in sorted(named, key=lambda mower: mower[0]):
        for area_id in sorted(
            (area_id for area_id in zones if _is_valid_id(area_id)), key=int
        ):
            label = zones[area_id] or f"Area {area_id}"
            if prefix:
                label = f"{mower_name} · {label}"
            options.append({"label": label, "value": area_id})

    labels = [option["label"] for option in options]
    for option in options:
        if labels.count(option["label"]) > 1:
            option["label"] = f"{option['label']} ({option['value']})"
    return options


def _is_valid_id(area_id: str) -> bool:
    """Whether ``AREA_IDS_SCHEMA`` would accept *area_id*."""
    return area_id.isdecimal() and 0 <= int(area_id) <= 999


async def async_setup_zone_options(
    hass: HomeAssistant, entry: EcovacsMowerConfigEntry, devices: list[Device]
) -> None:
    """Follow the zones of every zone-capable mower in *entry*.

    Zone-capable is the same test ``EcovacsMower.async_mow_area`` makes: the
    device's area capability is ``MowArea``. Reacting to ``MowerAreaEvent``
    through a subscription is fine here: nothing is derived and held from it
    that a dropped repeat could make wrong, since a repeat changes nothing.
    """
    if _BASE not in hass.data:
        path = Path(__file__).with_name("services.yaml")
        services = await hass.async_add_executor_job(load_yaml_dict, str(path))
        hass.data[_BASE] = services[SERVICE]
    mowers: dict[str, MowerZones] = hass.data.setdefault(_ZONES, {})

    for device in devices:
        if device.capabilities.clean.action.area is not MowArea:
            continue
        did = device.device_info["did"]
        name = device.device_info.get("nick") or device.device_info["class"]
        mowers[did] = (name, {})
        entry.async_on_unload(
            device.events.subscribe(
                MowerAreaEvent, partial(_async_on_areas, hass, did, name)
            )
        )
        entry.async_on_unload(partial(_forget, hass, did))


async def _async_on_areas(
    hass: HomeAssistant, did: str, name: str, event: MowerAreaEvent
) -> None:
    """Record one mower's zones and republish."""
    hass.data[_ZONES][did] = (name, {area.area_id: area.name for area in event.areas})
    _publish(hass)


@callback
def _forget(hass: HomeAssistant, did: str) -> None:
    """Drop an unloaded mower's zones; the static field returns with the last."""
    hass.data[_ZONES].pop(did, None)
    _publish(hass)


@callback
def _publish(hass: HomeAssistant) -> None:
    """Publish the description, unless it is the one already published.

    Every area report lands here, parameter-only pushes included, and those
    leave the zones as they were.
    """
    description: dict[str, Any] = deepcopy(hass.data[_BASE])
    if options := zone_options(hass.data[_ZONES]):
        # custom_value keeps a typed ID working: before the first report, and
        # for a zone the open browser has not been told about yet.
        description["fields"][FIELD]["selector"] = {
            "select": {"multiple": True, "custom_value": True, "options": options}
        }
    if description == hass.data.get(_PUBLISHED):
        return
    hass.data[_PUBLISHED] = description
    async_set_service_schema(hass, DOMAIN, SERVICE, description)
