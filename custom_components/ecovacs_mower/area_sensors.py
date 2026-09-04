"""Mower area parameter sensors.

These entities are dynamic because the mower does not declare its area count in
its device capabilities. ``getAreaParameter`` is the source of truth for which
areas currently have parameters; ``getAreaSet`` supplies the user-editable name
when the mower supports that response.

The parameter values are read-only in this change. The device requires all five
``setAreaParameter`` fields on every write, so adding a write path before the
read/merge state is deliberately left for a separate change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, override

from deebot_client.capabilities import DeviceType
from deebot_client.device import Device

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import DEGREE, EntityCategory, UnitOfLength, UnitOfSpeed
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsMowerConfigEntry
from .deebot_patch.areas import (
    AREA_PARAMETER_CLASSES,
    MowerArea,
    MowerAreaNameEvent,
    MowerAreaParameterEvent,
    decode_cut_angle,
    decode_cut_speed,
    decode_mow_height,
    decode_obstacle_height,
)
from .entity import EcovacsDescriptionEntity


@dataclass(kw_only=True, frozen=True)
class EcovacsAreaSensorEntityDescription(SensorEntityDescription):
    """Mower area sensor entity description."""

    value_fn: Callable[[MowerArea], float | int | str | None]


def _area_name(area: MowerArea) -> str:
    """Return the friendly name or a stable area-ID fallback."""
    return area.name or f"Area {area.area_id}"


def area_sensor_description(
    area_id: str,
    key_suffix: str,
    translation_key: str,
    value_fn: Callable[[MowerArea], float | int | str | None],
    **kwargs: object,
) -> EcovacsAreaSensorEntityDescription:
    """Describe one dynamic sensor for a mower area."""
    return EcovacsAreaSensorEntityDescription(
        key=f"area_{area_id}_{key_suffix}",
        translation_key=translation_key,
        value_fn=value_fn,
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


def area_sensor_descriptions(
    area_id: str = "EXAMPLE",
) -> tuple[EcovacsAreaSensorEntityDescription, ...]:
    """Return the descriptions used by every dynamic area sensor.

    The area ID is part of the unique key, so the entity registry keeps each
    sensor stable even when its user-facing area name changes.
    """
    return (
        area_sensor_description(
            area_id,
            "cutting_height",
            "area_cutting_height",
            lambda area: decode_mow_height(area.mow_height_level)
            if area.mow_height_level is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:grass",
        ),
        area_sensor_description(
            area_id,
            "mowing_speed",
            "area_mowing_speed",
            lambda area: decode_cut_speed(area.cut_mode)
            if area.cut_mode is not None
            else None,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            icon="mdi:speedometer",
        ),
        area_sensor_description(
            area_id,
            "obstacle_height",
            "area_obstacle_height",
            lambda area: decode_obstacle_height(area.obstacle_height)
            if area.obstacle_height is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:format-vertical-align-top",
        ),
        area_sensor_description(
            area_id,
            "cut_direction",
            "area_cut_direction",
            lambda area: decode_cut_angle(area.angle)
            if area.angle is not None
            else None,
            native_unit_of_measurement=DEGREE,
            icon="mdi:angle-acute",
        ),
    )


class EcovacsAreaSensor(EcovacsDescriptionEntity, SensorEntity):
    """Read one interpreted parameter from one mower area."""

    entity_description: EcovacsAreaSensorEntityDescription

    def __init__(
        self,
        device: Device,
        area_id: str,
        description: EcovacsAreaSensorEntityDescription,
        area_name: str | None = None,
    ) -> None:
        """Initialize entity."""
        super().__init__(device, device.capabilities, description)
        self._area_id = area_id
        self._set_area_name(area_name or f"Area {area_id}")
        if description.icon:
            self._attr_icon = description.icon

    @override
    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()
        self._subscribe(MowerAreaParameterEvent, self._on_parameters)
        self._subscribe(MowerAreaNameEvent, self._on_names)

    async def _on_parameters(self, event: MowerAreaParameterEvent) -> None:
        """Update this area's value and friendly name."""
        area = next((area for area in event.areas if area.area_id == self._area_id), None)
        if area is None:
            self._attr_native_value = None
            self.async_write_ha_state()
            return
        self._set_area_name(_area_name(area))
        self._attr_native_value = self.entity_description.value_fn(area)
        self.async_write_ha_state()

    async def _on_names(self, event: MowerAreaNameEvent) -> None:
        """Update this area's friendly name without changing its value."""
        name = next(
            (name for area_id, name in event.names if area_id == self._area_id), None
        )
        if name is None:
            return
        self._set_area_name(name)
        self.async_write_ha_state()

    def _set_area_name(self, name: str) -> None:
        """Set the translated area-name placeholder."""
        self._attr_translation_placeholders = {"area_name": name}


async def async_setup_area_sensors(
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add read-only area sensors for verified mower hardware."""
    controller = config_entry.runtime_data
    for device in controller.devices:
        if device.capabilities.device_type is not DeviceType.MOWER:
            continue
        if device.device_info["class"] not in AREA_PARAMETER_CLASSES:
            continue
        _setup_device_area_sensors(device, config_entry, async_add_entities)


def _setup_device_area_sensors(
    device: Device,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create area entities as soon as the first parameter snapshot arrives."""
    known: set[str] = set()
    names: dict[str, str] = {}
    entities: dict[str, list[EcovacsAreaSensor]] = {}

    def add_area(area_id: str) -> None:
        """Add the fixed set of entities for one area exactly once."""
        if area_id in known:
            return
        known.add(area_id)
        descriptions = area_sensor_descriptions(area_id)
        area_entities = [
            EcovacsAreaSensor(device, area_id, description, names.get(area_id))
            for description in descriptions
        ]
        entities[area_id] = area_entities
        async_add_entities(area_entities)

    async def on_parameters(event: MowerAreaParameterEvent) -> None:
        """Create entities for every area returned by getAreaParameter."""
        for area in event.areas:
            add_area(area.area_id)

    async def on_names(event: MowerAreaNameEvent) -> None:
        """Create entities for areas found by getAreaSet and update existing ones."""
        for area_id, name in event.names:
            names[area_id] = name
            add_area(area_id)
            for entity in entities[area_id]:
                entity._set_area_name(name)
                entity.async_write_ha_state()

    config_entry.async_on_unload(
        device.events.subscribe(MowerAreaNameEvent, on_names)
    )
    config_entry.async_on_unload(
        device.events.subscribe(MowerAreaParameterEvent, on_parameters)
    )
    # Request names first so that, in the normal startup response order, the
    # initial entity name already uses the mower's friendly area name. The
    # parameter response remains the source of truth for which areas exist.
    device.events.request_refresh(MowerAreaNameEvent)
    device.events.request_refresh(MowerAreaParameterEvent)
