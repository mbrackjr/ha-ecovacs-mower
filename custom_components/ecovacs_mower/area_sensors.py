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
from homeassistant.helpers import entity_registry as er
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
    parameter_name: str
    suggested_object_id: str | None = None


def area_sensor_description(
    area_id: str,
    key_suffix: str,
    parameter_name: str,
    value_fn: Callable[[MowerArea], float | int | str | None],
    **kwargs: object,
) -> EcovacsAreaSensorEntityDescription:
    """Describe one dynamic sensor for a mower area."""
    key = f"area_{area_id}_{key_suffix}"
    return EcovacsAreaSensorEntityDescription(
        key=key,
        name=parameter_name,
        value_fn=value_fn,
        parameter_name=parameter_name,
        # Keep the numeric area ID in the suggested object ID so newly created
        # entities use a stable area-ID-based object ID (for example,
        # 2_cutting_height) instead of depending on the mower's user-editable
        # friendly name. The entity key retains the area_ prefix internally.
        suggested_object_id=f"{area_id}_{key_suffix}",
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
            "Cutting height",
            lambda area: decode_mow_height(area.mow_height_level)
            if area.mow_height_level is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:grass",
        ),
        area_sensor_description(
            area_id,
            "mowing_speed",
            "Mowing speed",
            lambda area: decode_cut_speed(area.cut_mode)
            if area.cut_mode is not None
            else None,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            icon="mdi:speedometer",
        ),
        area_sensor_description(
            area_id,
            "obstacle_height",
            "Obstacle height",
            lambda area: decode_obstacle_height(area.obstacle_height)
            if area.obstacle_height is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:format-vertical-align-top",
        ),
        area_sensor_description(
            area_id,
            "cut_direction",
            "Cutting direction",
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
        area_name: str,
    ) -> None:
        """Initialize entity."""
        super().__init__(device, device.capabilities, description)
        self._area_id = area_id
        self._set_area_name(area_name)
        if description.icon:
            self._attr_icon = description.icon

    def _set_area_name(self, area_name: str) -> None:
        """Set the integration-provided name for this area."""
        # The friendly area name is deliberately part of the integration's
        # original name. This is the most useful initial name for mower users,
        # who generally know the area by its app name rather than its numeric ID;
        # HA users can override the entity name in the entity registry.
        self._attr_name = f"{area_name} - {self.entity_description.parameter_name}"

    def set_area_name(self, area_name: str) -> None:
        """Update the integration-provided area name after getAreaSet."""
        name = f"{area_name} - {self.entity_description.parameter_name}"
        self._set_area_name(area_name)

        if self.hass is None or self.entity_id is None:
            return

        registry = er.async_get(self.hass)
        entry = registry.async_get(self.entity_id)
        if entry is None:
            return

        # ``name`` is the user's override. Updating only ``original_name`` means
        # a user-defined name remains untouched while the integration can follow
        # a rename made in the mower app on the next getAreaSet response.
        registry.async_update_entity(self.entity_id, original_name=name)
        self.async_write_ha_state()

    @property
    @override
    def suggested_object_id(self) -> str | None:
        """Return the stable area-ID-based object ID."""
        return self.entity_description.suggested_object_id

    @override
    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()

        # Earlier PR4 revisions accidentally exposed the internal entity key
        # (``area_<id>_<parameter>``) as the suggested object ID, producing
        # entity IDs such as ``..._area_area_4_obstacle_height``. The corrected
        # description above fixes newly created entities; this one-time registry
        # migration fixes entities that already exist, without changing their
        # unique IDs or user-overridden names.
        if self.hass is not None and self.entity_id is not None:
            registry = er.async_get(self.hass)
            legacy_entity_id = self.entity_id
            new_entity_id = legacy_entity_id.replace("_area_area_", "_area_", 1)
            if new_entity_id != legacy_entity_id and registry.async_get(new_entity_id) is None:
                registry.async_update_entity(
                    legacy_entity_id,
                    new_entity_id=new_entity_id,
                )

        self._subscribe(MowerAreaParameterEvent, self._on_parameters)

    async def _on_parameters(self, event: MowerAreaParameterEvent) -> None:
        """Update this area's value."""
        area = next((area for area in event.areas if area.area_id == self._area_id), None)
        if area is None:
            self._attr_native_value = None
        else:
            self._attr_native_value = self.entity_description.value_fn(area)
        self.async_write_ha_state()


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
    """Create area entities and keep their names synchronized with getAreaSet."""
    parameters: dict[str, MowerArea] = {}
    entities: dict[str, list[EcovacsAreaSensor]] = {}

    def add_area(area_id: str, area_name: str) -> None:
        """Add the fixed set of entities for one named area exactly once."""
        if area_id in entities:
            return
        descriptions = area_sensor_descriptions(area_id)
        area_entities = [
            EcovacsAreaSensor(device, area_id, description, area_name)
            for description in descriptions
        ]
        entities[area_id] = area_entities
        async_add_entities(area_entities)

        if area := parameters.get(area_id):
            for entity in area_entities:
                entity._attr_native_value = entity.entity_description.value_fn(area)

    async def on_parameters(event: MowerAreaParameterEvent) -> None:
        """Cache parameter values and update already-created entities."""
        parameters.update({area.area_id: area for area in event.areas})
        for area_id, area in parameters.items():
            for entity in entities.get(area_id, ()):
                entity._attr_native_value = entity.entity_description.value_fn(area)
                entity.async_write_ha_state()

    async def on_names(event: MowerAreaNameEvent) -> None:
        """Create entities and update their integration-provided names."""
        for area_id, name in event.names:
            if area_id not in entities:
                add_area(area_id, name)
            else:
                for entity in entities[area_id]:
                    entity.set_area_name(name)

    config_entry.async_on_unload(
        device.events.subscribe(MowerAreaNameEvent, on_names)
    )
    config_entry.async_on_unload(
        device.events.subscribe(MowerAreaParameterEvent, on_parameters)
    )

    # Both commands are asynchronous MQTT exchanges. Request getAreaSet first
    # so its response normally creates entities with their final friendly names;
    # getAreaParameter remains independently responsible for their values.
    device.events.request_refresh(MowerAreaNameEvent)
    device.events.request_refresh(MowerAreaParameterEvent)
