"""Ecovacs number module.

Forkad från Home Assistant core (``homeassistant/components/ecovacs/number.py``).
Beskrivningarna för ``clean_count`` och ``water_amount`` är borttagna: de
kräver kapabiliteter (``clean.count`` respektive ``water.amount``) som
GOAT-klipparen (2i0fns) inte deklarerar, så ``get_supported_entities`` hade
filtrerat bort dem ändå — men döda beskrivningar hör inte hemma i en
klipparspecifik fork. ``volume`` och ``cut_direction`` behålls: båda är
klipparens egna inställningar (ljudvolym på notiser respektive linjeorientering
för klippmönstret).

Core's ``EcovacsNumberEntity.__init__`` läser av min/max från kapabiliteten om
den är en ``CapabilityNumber`` (t.ex. ``water_amount``, ``mop_auto_wash_frequency``
— moppfunktioner en gräsklippare saknar). ``volume`` och ``cut_direction`` är
båda vanliga ``CapabilitySet``, inte ``CapabilityNumber``, så den grenen
triggas aldrig här och är borttagen tillsammans med importen.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from deebot_client.capabilities import CapabilitySet
from deebot_client.events import CutDirectionEvent, VolumeEvent
from deebot_client.events.base import Event

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import DEGREE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsMowerConfigEntry
from .entity import (
    EcovacsCapabilityEntityDescription,
    EcovacsDescriptionEntity,
    EcovacsEntity,
)
from .util import get_supported_entities


@dataclass(kw_only=True, frozen=True)
class EcovacsNumberEntityDescription[EventT: Event](
    NumberEntityDescription,
    EcovacsCapabilityEntityDescription,
):
    """Ecovacs number entity description."""

    native_max_value_fn: Callable[[EventT], float | int | None] = lambda _: None
    value_fn: Callable[[EventT], float | None]


ENTITY_DESCRIPTIONS: tuple[EcovacsNumberEntityDescription, ...] = (
    EcovacsNumberEntityDescription[VolumeEvent](
        capability_fn=lambda caps: caps.settings.volume,
        value_fn=lambda e: e.volume,
        native_max_value_fn=lambda e: e.maximum,
        key="volume",
        translation_key="volume",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=10,
        native_step=1.0,
    ),
    EcovacsNumberEntityDescription[CutDirectionEvent](
        capability_fn=lambda caps: caps.settings.cut_direction,
        value_fn=lambda e: e.angle,
        key="cut_direction",
        translation_key="cut_direction",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
        native_min_value=0,
        native_max_value=180,
        native_step=1.0,
        native_unit_of_measurement=DEGREE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add entities for passed config_entry in HA."""
    controller = config_entry.runtime_data
    entities: list[EcovacsEntity] = get_supported_entities(
        controller, EcovacsNumberEntity, ENTITY_DESCRIPTIONS
    )
    if entities:
        async_add_entities(entities)


class EcovacsNumberEntity[EventT: Event](
    EcovacsDescriptionEntity[CapabilitySet[EventT, [int]]],
    NumberEntity,
):
    """Ecovacs number entity."""

    entity_description: EcovacsNumberEntityDescription

    @override
    async def async_added_to_hass(self) -> None:
        """Set up the event listeners now that hass is ready."""
        await super().async_added_to_hass()

        async def on_event(event: EventT) -> None:
            self._attr_native_value = self.entity_description.value_fn(event)
            if maximum := self.entity_description.native_max_value_fn(event):
                self._attr_native_max_value = maximum
            self.async_write_ha_state()

        self._subscribe(self._capability.event, on_event)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        await self._device.execute_command(self._capability.set(int(value)))
