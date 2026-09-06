"""Dynamic Home Assistant entities for mower areas.

Area identity and state are owned by ``deebot_patch``. This module only turns
that state into the four model-specific area parameter views. The entities are
dynamic because the mower reports its area IDs at runtime, just like the
existing beacon sensors.

Model- and firmware-specific conversion from raw device values to
human-sensible Home Assistant values lives exclusively in this HA layer. The
A1600 LiDAR Pro findings that established these mappings are deliberately scoped
to that model: the values have not been verified on the other mower classes
supported by this integration.

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
from .deebot_patch.areas import MowerArea, MowerAreaEvent
from .deebot_patch.device import MowerProfile, profile_for
from .entity import EcovacsDescriptionEntity


@dataclass(frozen=True)
class AreaParameterMapping:
    """HA representation mapping for one verified mower model."""

    mow_height: Callable[[int], float | None]
    cut_speed: Callable[[int], float | None]
    obstacle_height: Callable[[int], int | None]
    cut_angle: Callable[[int], int | None]


def _a1600_mow_height(level: int) -> float | None:
    """Convert A1600 ``mowHeightLevel`` to grass height in centimetres.

    Confirmed on the A1600 LiDAR Pro specifically: levels 1–7 leave 9–3 cm of
    grass respectively. The observed formula is ``cm = 10 - mowHeightLevel``.
    """
    if level not in range(1, 8):
        return None
    return float(10 - level)


def _a1600_cut_speed(level: int) -> float | None:
    """Convert A1600 ``cutMode`` to mowing speed in metres per second.

    Confirmed on the A1600 LiDAR Pro specifically: levels 1–7 mean 0.70–0.40
    m/s respectively. The observed formula is
    ``speed_ms = 0.40 + 0.05 × (7 - cutMode)``.
    """
    if level not in range(1, 8):
        return None
    return round(0.40 + 0.05 * (7 - level), 2)


def _a1600_obstacle_height(level: int) -> int | None:
    """Convert A1600 ``obstacleHeight`` to the obstacle threshold in cm."""
    return {1: 10, 2: 15, 3: 20}.get(level)


def _a1600_cut_angle(wire_angle: int) -> int | None:
    """Convert the A1600 wire-space angle to the app-space angle.

    Confirmed on the A1600 LiDAR Pro specifically. The observed symmetric
    conversion is ``app = (270 - wire) mod 360``; the same formula converts the
    app value back to wire space.
    """
    if wire_angle not in range(360):
        return None
    return (270 - wire_angle) % 360


# These mappings are presentation semantics, not protocol semantics. Keep them
# in the HA layer and add a class only after its raw-value representation has
# been verified independently. Do not infer that another GOAT class shares the
# A1600 representation merely because its protocol fields have the same names.
AREA_PARAMETER_MAPPINGS: dict[str, AreaParameterMapping] = {
    "e4gqia": AreaParameterMapping(
        mow_height=_a1600_mow_height,
        cut_speed=_a1600_cut_speed,
        obstacle_height=_a1600_obstacle_height,
        cut_angle=_a1600_cut_angle,
    ),
}


@dataclass(kw_only=True, frozen=True)
class EcovacsAreaSensorEntityDescription(SensorEntityDescription):
    """Describe one dynamic view of one mower area."""

    value_fn: Callable[[MowerArea], float | int | None]
    parameter_name: str
    suggested_object_id: str | None = None


def area_sensor_description(
    area_id: str,
    key_suffix: str,
    parameter_name: str,
    value_fn: Callable[[MowerArea], float | int | None],
    **kwargs: object,
) -> EcovacsAreaSensorEntityDescription:
    """Describe one dynamic sensor for a mower area."""
    return EcovacsAreaSensorEntityDescription(
        key=f"area_{area_id}_{key_suffix}",
        name=parameter_name,
        value_fn=value_fn,
        parameter_name=parameter_name,
        # Keep the numeric area ID in the suggested object ID so newly created
        # entities use a stable area-ID-based object ID instead of depending on
        # the mower's user-editable friendly name.
        suggested_object_id=f"{area_id}_{key_suffix}",
        entity_category=EntityCategory.DIAGNOSTIC,
        **kwargs,
    )


def area_sensor_descriptions(
    area_id: str,
    *,
    area_mapping: AreaParameterMapping,
) -> tuple[EcovacsAreaSensorEntityDescription, ...]:
    """Return the four model-specific area parameter views."""
    return (
        area_sensor_description(
            area_id,
            "cutting_height",
            "Cutting height",
            lambda area: area_mapping.mow_height(area.mow_height_level)
            if area.mow_height_level is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:grass",
        ),
        area_sensor_description(
            area_id,
            "mowing_speed",
            "Mowing speed",
            lambda area: area_mapping.cut_speed(area.cut_mode)
            if area.cut_mode is not None
            else None,
            native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
            icon="mdi:speedometer",
        ),
        area_sensor_description(
            area_id,
            "obstacle_height",
            "Obstacle height",
            lambda area: area_mapping.obstacle_height(area.obstacle_height)
            if area.obstacle_height is not None
            else None,
            native_unit_of_measurement=UnitOfLength.CENTIMETERS,
            icon="mdi:format-vertical-align-top",
        ),
        area_sensor_description(
            area_id,
            "cut_direction",
            "Cutting direction",
            lambda area: area_mapping.cut_angle(area.angle)
            if area.angle is not None
            else None,
            native_unit_of_measurement=DEGREE,
            icon="mdi:angle-acute",
        ),
    )


class EcovacsAreaSensor(EcovacsDescriptionEntity, SensorEntity):
    """Expose one read-only parameter from one mower area."""

    entity_description: EcovacsAreaSensorEntityDescription

    def __init__(
        self,
        device: Device,
        area_id: str,
        description: EcovacsAreaSensorEntityDescription,
        area_name: str,
    ) -> None:
        """Initialize the dynamic area entity."""
        super().__init__(device, device.capabilities, description)
        self._area_id = area_id
        self._set_area_name(area_name)
        self._attr_icon = description.icon

    def _set_area_name(self, area_name: str) -> None:
        """Set the integration-provided name without changing identity."""
        # The friendly area name is deliberately part of the integration's
        # original name. HA users can override the entity name in the registry.
        self._attr_name = f"{area_name} - {self.entity_description.parameter_name}"

    def set_area_name(self, area_name: str) -> None:
        """Update the integration-provided name after the mower reports it."""
        name = f"{area_name} - {self.entity_description.parameter_name}"
        self._set_area_name(area_name)
        if self.hass is None or self.entity_id is None:
            return
        registry = er.async_get(self.hass)
        if registry.async_get(self.entity_id) is None:
            return
        # Only original_name is changed. A user's entity-name override must
        # survive a rename made in the Ecovacs app.
        registry.async_update_entity(self.entity_id, original_name=name)
        self.async_write_ha_state()

    @property
    @override
    def suggested_object_id(self) -> str | None:
        """Use the numeric area ID, never the mutable friendly name."""
        return self.entity_description.suggested_object_id

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to the authoritative area snapshot."""
        await super().async_added_to_hass()
        self._subscribe(MowerAreaEvent, self._on_area_state)

    async def _on_area_state(self, event: MowerAreaEvent) -> None:
        """Project this area's parameter into the sensor state."""
        area = next(
            (area for area in event.areas if area.area_id == self._area_id), None
        )
        if area is None:
            self._attr_native_value = None
        else:
            self._attr_native_value = self.entity_description.value_fn(area)
            if area.name:
                self.set_area_name(area.name)
        self.async_write_ha_state()


async def async_setup_area_sensors(
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add dynamic area sensors for model profiles that support them."""
    controller = config_entry.runtime_data
    for device in controller.devices:
        if device.capabilities.device_type is not DeviceType.MOWER:
            continue
        profile = profile_for(device)
        if profile is None or not profile.area_parameters:
            continue
        area_mapping = AREA_PARAMETER_MAPPINGS.get(profile.device_class)
        if area_mapping is None:
            continue
        _setup_device_area_sensors(
            device, config_entry, async_add_entities, profile, area_mapping
        )


def _setup_device_area_sensors(
    device: Device,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    profile: MowerProfile,
    area_mapping: AreaParameterMapping,
) -> None:
    """Project the patch-owned area state into dynamic HA entities."""
    del profile
    entities: dict[str, list[EcovacsAreaSensor]] = {}

    def add_area(area: MowerArea) -> None:
        """Create the four entities for a newly discovered area."""
        if area.area_id in entities:
            return
        name = area.name or f"Area {area.area_id}"
        area_entities = [
            EcovacsAreaSensor(device, area.area_id, description, name)
            for description in area_sensor_descriptions(
                area.area_id, area_mapping=area_mapping
            )
        ]
        entities[area.area_id] = area_entities
        async_add_entities(area_entities)
        for entity in area_entities:
            entity._attr_native_value = entity.entity_description.value_fn(area)

    async def on_area_state(event: MowerAreaEvent) -> None:
        """Create missing entities and project the new authoritative state."""
        reported_ids = {area.area_id for area in event.areas}
        for area in event.areas:
            if area.area_id not in entities:
                add_area(area)
            else:
                for entity in entities[area.area_id]:
                    entity._attr_native_value = entity.entity_description.value_fn(area)
                    if area.name:
                        entity.set_area_name(area.name)
                    entity.async_write_ha_state()

        # An area removed from the mower becomes unavailable rather than being
        # silently deleted from HA. Numeric IDs remain stable, and entity
        # removal is intentionally a user-visible lifecycle action.
        for area_id, area_entities in entities.items():
            if area_id not in reported_ids:
                for entity in area_entities:
                    entity._attr_native_value = None
                    entity.async_write_ha_state()

    config_entry.async_on_unload(
        device.events.subscribe(MowerAreaEvent, on_area_state)
    )
    device.events.request_refresh(MowerAreaEvent)
