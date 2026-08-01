"""lawn_mower-entiteten för Ecovacs GOAT."""

from __future__ import annotations

import logging
from typing import override

from deebot_client.capabilities import Capabilities, DeviceType
from deebot_client.device import Device
from deebot_client.events import StateEvent
from deebot_client.models import CleanAction, State
from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityEntityDescription,
    LawnMowerEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsMowerConfigEntry
from .entity import EcovacsEntity

_LOGGER = logging.getLogger(__name__)

# IDLE betyder "står stilla", inte "står i dockan" — därför PAUSED.
# Dockning rapporteras separat via onChargeInfo med state "idle", som
# deebot_patch.messages översätter till State.DOCKED.
_STATE_TO_MOWER_STATE = {
    State.IDLE: LawnMowerActivity.PAUSED,
    State.CLEANING: LawnMowerActivity.MOWING,
    State.RETURNING: LawnMowerActivity.RETURNING,
    State.DOCKED: LawnMowerActivity.DOCKED,
    State.ERROR: LawnMowerActivity.ERROR,
    State.PAUSED: LawnMowerActivity.PAUSED,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EcovacsMowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Lägg till gräsklipparna."""
    controller = config_entry.runtime_data
    mowers = [
        EcovacsMower(device)
        for device in controller.devices
        if device.capabilities.device_type is DeviceType.MOWER
    ]
    _LOGGER.debug("Lägger till gräsklippare: %s", mowers)
    async_add_entities(mowers)


class EcovacsMower(EcovacsEntity[Capabilities], LawnMowerEntity):
    """En Ecovacs GOAT-gräsklippare."""

    _attr_supported_features = (
        LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
    )

    entity_description = LawnMowerEntityEntityDescription(key="mower", name=None)

    def __init__(self, device: Device) -> None:
        """Initiera gräsklipparen."""
        super().__init__(device, device.capabilities)

    @override
    async def async_added_to_hass(self) -> None:
        """Prenumerera på tillståndshändelser."""
        await super().async_added_to_hass()

        async def on_status(event: StateEvent) -> None:
            activity = _STATE_TO_MOWER_STATE.get(event.state)
            if activity is None:
                _LOGGER.warning("Ohanterat tillstånd från enheten: %s", event.state)
                return
            self._attr_activity = activity
            self.async_write_ha_state()

        self._subscribe(self._capability.state.event, on_status)

    async def _clean_command(self, action: CleanAction) -> None:
        await self._device.execute_command(
            self._capability.clean.action.command(action)
        )

    @override
    async def async_start_mowing(self) -> None:
        """Starta eller återuppta klippning."""
        await self._clean_command(CleanAction.START)

    @override
    async def async_pause(self) -> None:
        """Pausa klippningen."""
        await self._clean_command(CleanAction.PAUSE)

    @override
    async def async_dock(self) -> None:
        """Skicka klipparen till dockan."""
        await self._device.execute_command(self._capability.charge.execute())
