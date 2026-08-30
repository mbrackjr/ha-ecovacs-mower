"""Zone-specific mowing commands for GOAT mowers.

The ``spotArea`` payload shape was reverse-engineered by
PhilippF1992/ecovacs_goat_zonal_additions (MIT licensed) and confirmed by the
integration author on an A1600 LiDAR Pro (``e4gqia``), firmware 1.11.31.

The command is deliberately stateless: the mower already stores the zone and
its mowing parameters. This PR only sends the saved area IDs; reading or
changing those parameters is a separate feature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deebot_client.command import Command
from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.message import HandlingResult
from deebot_client.models import CleanAction

from .commands import _AdaptiveFamily
from .families import Family

if TYPE_CHECKING:
    from deebot_client.authentication import Authenticator
    from deebot_client.event_bus import EventBus
    from deebot_client.models import ApiDeviceInfo


_TYPE_SPOT_AREA = "spotArea"


class _ZoneCleanNonV2(Clean):
    """Send the spot-area payload on the ``clean`` topic."""

    def __init__(self, area: list[int | float]) -> None:
        self._value = ",".join(str(value) for value in area)
        super().__init__(CleanAction.START)

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Execute without Clean rewriting the requested action."""
        return await Command._execute(self, authenticator, device_info, event_bus)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        return {
            "act": action.value,
            "content": {"type": _TYPE_SPOT_AREA, "value": self._value},
        }


class _ZoneCleanV2(CleanV2):
    """Send the spot-area payload on the ``clean_V2`` topic."""

    def __init__(self, area: list[int | float]) -> None:
        self._value = ",".join(str(value) for value in area)
        super().__init__(CleanAction.START)

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Execute without Clean rewriting the requested action."""
        return await Command._execute(self, authenticator, device_info, event_bus)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        return {
            "act": action.value,
            "content": {"type": _TYPE_SPOT_AREA, "value": self._value},
        }


class _ResumeSpotAreaNonV2(Clean):
    """Resume the mower's saved spot-area job on the ``clean`` topic."""

    def __init__(self) -> None:
        super().__init__(CleanAction.RESUME)

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Execute without Clean rewriting the resume action."""
        return await Command._execute(self, authenticator, device_info, event_bus)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        # The mower retains the selected zones and their parameters. Resume
        # identifies that stored job by type; sending the area IDs again is
        # neither necessary nor equivalent to resume.
        return {"act": action.value, "content": {"type": _TYPE_SPOT_AREA}}


class _ResumeSpotAreaV2(CleanV2):
    """Resume the mower's saved spot-area job on the ``clean_V2`` topic."""

    def __init__(self) -> None:
        super().__init__(CleanAction.RESUME)

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Execute without Clean rewriting the resume action."""
        return await Command._execute(self, authenticator, device_info, event_bus)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        return {"act": action.value, "content": {"type": _TYPE_SPOT_AREA}}


class MowArea(_AdaptiveFamily, Clean):
    """Mow saved area IDs using the GOAT ``spotArea`` command.

    The command family is selected at runtime because GOAT firmware versions
    exist that answer only one of ``clean`` and ``clean_V2``.
    """

    def __init__(
        self,
        mode: Any,
        area: list[int | float],
        cleanings: int = 1,
    ) -> None:
        """Initialize an area-clean command."""
        if getattr(mode, "value", mode) != _TYPE_SPOT_AREA:
            raise ValueError(f"Unsupported mower area mode: {mode}")
        if not area:
            raise ValueError("At least one area ID is required")
        if cleanings < 1:
            raise ValueError("cleanings must be at least 1")
        self._area = list(area)
        self._delegates: dict[Family, Command] = {}
        super().__init__(CleanAction.START)

    def _delegate(self, family: Family) -> Command:
        """Return the command for the selected wire family."""
        return self._delegates[family]

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Build the two wire variants and let the adaptive family choose."""
        self._delegates = {
            Family.NON_V2: _ZoneCleanNonV2(self._area),
            Family.V2: _ZoneCleanV2(self._area),
        }
        return await super()._execute(authenticator, device_info, event_bus)


class ResumeSpotArea(_AdaptiveFamily, Clean):
    """Resume an already active ``spotArea`` job.

    The mower keeps the selected zones and their mowing parameters while a
    job is paused. Unlike ``MowArea``, this command therefore carries no area
    IDs: the wire protocol uses ``resume`` with ``type=spotArea`` to identify
    the saved job.
    """

    def __init__(self) -> None:
        """Initialize a spot-area resume command."""
        self._delegates: dict[Family, Command] = {}
        super().__init__(CleanAction.RESUME)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        # Keep command equality/repr meaningful without treating this wrapper's
        # inert args as a wire payload; the delegates below build that payload.
        return {"act": action.value, "content": {"type": _TYPE_SPOT_AREA}}

    def _delegate(self, family: Family) -> Command:
        """Return the command for the selected wire family."""
        return self._delegates[family]

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Build both resume variants and let the adaptive family choose."""
        self._delegates = {
            Family.NON_V2: _ResumeSpotAreaNonV2(),
            Family.V2: _ResumeSpotAreaV2(),
        }
        return await super()._execute(authenticator, device_info, event_bus)
