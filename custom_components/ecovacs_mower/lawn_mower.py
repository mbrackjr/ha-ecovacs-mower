"""The lawn_mower entity for Ecovacs GOAT."""

from __future__ import annotations

import logging
from typing import override

from deebot_client.capabilities import Capabilities, DeviceType
from deebot_client.device import Device
from deebot_client.events import StateEvent, StatsEvent
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
from .controller import EcovacsController
from .deebot_patch.job_type import MowerJobTypeEvent
from .deebot_patch.state_precedence import record_for
from .deebot_patch.zonal import ResumeSpotArea
from .entity import EcovacsEntity

_LOGGER = logging.getLogger(__name__)

# IDLE means "standing still", not "standing in the dock" — hence PAUSED.
# Docking is reported separately via onChargeInfo with state "idle", which
# deebot_patch.messages translates to State.DOCKED.
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
    """Add the lawn mowers."""
    controller = config_entry.runtime_data
    mowers = [
        EcovacsMower(device, controller)
        for device in controller.devices
        if device.capabilities.device_type is DeviceType.MOWER
    ]
    _LOGGER.debug("Adding mowers: %s", mowers)
    async_add_entities(mowers)


class EcovacsMower(EcovacsEntity[Capabilities], LawnMowerEntity):
    """An Ecovacs GOAT lawn mower.

    The periodic refresh that keeps the state honest even without a push
    lives in EcovacsController (see POLL_INTERVAL in const.py), not here: a
    disabled lawn_mower entity must not also starve the activity and
    mowing_progress/stats sensors of their five-minute update.
    """

    _attr_supported_features = (
        LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
        | LawnMowerEntityFeature.START_MOWING
    )

    entity_description = LawnMowerEntityEntityDescription(key="mower", name=None)

    def __init__(self, device: Device, controller: EcovacsController) -> None:
        """Initialize the lawn mower."""
        super().__init__(device, device.capabilities)
        self._controller = controller

    @override
    async def async_added_to_hass(self) -> None:
        """Subscribe to state events."""
        await super().async_added_to_hass()

        async def on_status(event: StateEvent) -> None:
            activity = _STATE_TO_MOWER_STATE.get(event.state)
            if activity is None:
                _LOGGER.warning("Unhandled state from device: %s", event.state)
                return
            self._attr_activity = activity
            self.async_write_ha_state()

        async def on_job_type(event: MowerJobTypeEvent) -> None:
            """Remember the active job type reported by the mower itself.

            This is deliberately driven by the mower's wire event rather than
            by ``mow_area``. A spot-area job started in the Ecovacs app therefore
            gets the same pause/resume behavior as one started from HA.
            """
            if (record := record_for(self._capability.state.event)) is None:
                return
            if event.phase == "start":
                record.start_job(event.job_type)
            elif event.phase == "stop":
                record.stop_job()

        # Subscribing is also the startup check: the bus hands over the last
        # event if it has one and otherwise refreshes for the first subscriber.
        self._subscribe(self._capability.state.event, on_status)
        self._subscribe(MowerJobTypeEvent, on_job_type)

    @override
    async def async_update(self) -> None:
        """Ask for everything this mower is asked for.

        The mowing progress wants the same answer as the state, and one
        getStats notifies both StatsEvent and MowerStatsEvent, so refreshing
        StatsEvent here covers both.

        Refreshing StatsEvent rather than MowerStatsEvent is deliberate:
        Device.__init__ always subscribes to StatsEvent itself, so this keeps
        working even if the progress sensor is disabled — MowerStatsEvent's
        only subscriber.

        Also what the update_entity service calls, which stays reachable while
        docked on purpose: asking by hand is how the 2026-08-21 state was
        corrected in the first place (see POLL_INTERVAL in const.py).
        """
        await super().async_update()
        self._device.events.request_refresh(StatsEvent)

    async def _clean_command(self, action: CleanAction) -> None:
        """Send a clean action, using the active job type when resuming."""
        if action is CleanAction.START:
            # A command sent from HA never produces a StateEvent on its own —
            # only a confirmed push does — so the controller's own tick would
            # not restart on a dropped leaving-the-dock push without this
            # nudge.
            self._controller.start_polling(self._device)

        event_bus = self._device.events
        record = record_for(event_bus)
        state = record.suppressed if record is not None else None
        if state is None and (last := event_bus.get_last_event(StateEvent)):
            state = last.state

        if (
            action is CleanAction.START
            and state is State.PAUSED
            and record is not None
            and record.job_type == "spotarea"
        ):
            # The mower retains the selected zones while paused. A plain START
            # would begin a new generic clean; the protocol uses resume with
            # type=spotArea to continue the saved job.
            command = ResumeSpotArea()
        else:
            command = self._capability.clean.action.command(action)

        await self._execute_command(command)

    @override
    async def async_start_mowing(self) -> None:
        """Start or resume mowing."""
        await self._clean_command(CleanAction.START)

    @override
    async def async_pause(self) -> None:
        """Pause mowing."""
        await self._clean_command(CleanAction.PAUSE)

    @override
    async def async_dock(self) -> None:
        """Send the mower back to the dock."""
        await self._execute_command(self._capability.charge.execute())
