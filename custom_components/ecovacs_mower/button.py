"""Ecovacs button module.

Forkad från Home Assistant core (``homeassistant/components/ecovacs/button.py``).
``relocate`` är borttagen: den är gated på ``caps.map``, som GOAT-klipparen
(2i0fns) saknar. ``STATION_ENTITY_DESCRIPTIONS`` och
``EcovacsStationActionButtonEntity`` beskriver en dammsugarstations tömning
och mopptork — inga knappar en klippare har — och är borttagna tillsammans
med importen av ``SUPPORTED_STATION_ACTIONS``.

Tillagt utöver core: ``play_sound``. Kapabiliteten finns på ``2i0fns`` men
exponeras inte av core-integrationen. Den återanvänder cores befintliga
``EcovacsButtonEntity``/``EcovacsButtonEntityDescription`` — ingen ny
entitetsklass krävs, se ``play_sound: CapabilityExecute[[]]`` i
``deebot_client/capabilities.py``.

Annoteringen på ``EcovacsButtonEntity.entity_description`` är rättad mot core,
som anger ``EcovacsLifespanButtonEntityDescription`` — sannolikt en
copy-paste-miss, eftersom klassen aldrig använder livslängdsbeskrivningen.
Harmlöst vid körning, men en felaktig typ i en fork är svårare att upptäcka
än i uppströms.
"""

from dataclasses import dataclass
from typing import override

from deebot_client.capabilities import CapabilityExecute, CapabilityLifeSpan
from deebot_client.events import LifeSpan

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsMowerConfigEntry
from .const import SUPPORTED_LIFESPANS
from .entity import (
    EcovacsCapabilityEntityDescription,
    EcovacsDescriptionEntity,
    EcovacsEntity,
)
from .util import get_supported_entities


@dataclass(kw_only=True, frozen=True)
class EcovacsButtonEntityDescription(
    ButtonEntityDescription,
    EcovacsCapabilityEntityDescription,
):
    """Ecovacs button entity description."""


@dataclass(kw_only=True, frozen=True)
class EcovacsLifespanButtonEntityDescription(ButtonEntityDescription):
    """Ecovacs lifespan button entity description."""

    component: LifeSpan


ENTITY_DESCRIPTIONS: tuple[EcovacsButtonEntityDescription, ...] = (
    EcovacsButtonEntityDescription(
        capability_fn=lambda caps: caps.play_sound,
        key="play_sound",
        translation_key="play_sound",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


LIFESPAN_ENTITY_DESCRIPTIONS = tuple(
    EcovacsLifespanButtonEntityDescription(
        component=component,
        key=f"reset_lifespan_{component.name.lower()}",
        translation_key=f"reset_lifespan_{component.name.lower()}",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    )
    for component in SUPPORTED_LIFESPANS
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add entities for passed config_entry in HA."""
    controller = config_entry.runtime_data
    entities: list[EcovacsEntity] = get_supported_entities(
        controller, EcovacsButtonEntity, ENTITY_DESCRIPTIONS
    )
    entities.extend(
        EcovacsResetLifespanButtonEntity(
            device, device.capabilities.life_span, description
        )
        for device in controller.devices
        for description in LIFESPAN_ENTITY_DESCRIPTIONS
        if description.component in device.capabilities.life_span.types
    )
    async_add_entities(entities)


class EcovacsButtonEntity(
    EcovacsDescriptionEntity[CapabilityExecute],
    ButtonEntity,
):
    """Ecovacs button entity."""

    entity_description: EcovacsButtonEntityDescription

    @override
    async def async_press(self) -> None:
        """Press the button."""
        await self._device.execute_command(self._capability.execute())


class EcovacsResetLifespanButtonEntity(
    EcovacsDescriptionEntity[CapabilityLifeSpan],
    ButtonEntity,
):
    """Ecovacs reset lifespan button entity."""

    entity_description: EcovacsLifespanButtonEntityDescription

    @override
    async def async_press(self) -> None:
        """Press the button."""
        await self._device.execute_command(
            self._capability.reset(self.entity_description.component)
        )
