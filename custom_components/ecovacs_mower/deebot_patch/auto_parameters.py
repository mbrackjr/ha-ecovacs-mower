"""The mower-wide mowing settings, read as one more area: ``auto``.

Some GOAT models set cutting height, mowing speed, obstacle height and
cutting direction for the whole mower, in the app's Auto mode, besides or
instead of per saved area. Those four are the same four settings the area
layer knows, but each has its own pair of commands rather than one
``getAreaParameter`` for every area:

=================  =====================  ======================  ========
Area wire key      Read                   Write                   Field
=================  =====================  ======================  ========
``mowHeightLevel`` ``getCutHeight``       ``setCutHeight``        level
``cutMode``        ``getCutEfficiency``   ``setCutEfficiency``    level
``obstacleHeight`` ``getObstacleHeight``  ``setObstacleHeight``   level
``angle``          ``getCutDirection``    ``setCutDirection``     angle
=================  =====================  ======================  ========

The write commands are the A1600 RTK app's, captured in issue #23, where the
Auto levels used the same raw scales as that model's per-area values. The
read commands are inferred from the write names and from the library's own
``getCutDirection``; no model has been seen answering the other three yet.

The values are kept raw, keyed by the area wire key, as a ``MowerArea`` with
the id ``auto``, so whatever already reads an area's raw parameters can read
these. They are published as their own ``MowerAutoEvent``, not inside
``MowerAreaEvent``: that event's areas are the mower's saved areas, which zone
mowing and area discovery take as they come, and ``auto`` is not one.

The mower is not known to push changes to these settings. The app's own
write requests are followed instead: the write commands are registered in
the library's p2p table, so the library hands a write another client made,
once the mower has accepted it, to the matching read command, whose handler
records the value. That handler is the one place the snapshot is written,
for an answer and for a followed write alike.
"""

from __future__ import annotations

from abc import ABC
import logging
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from deebot_client.command import InitParam
from deebot_client.commands.json.common import JsonGetCommand, JsonSetCommand
from deebot_client.commands.json.cut_direction import (
    GetCutDirection as _LibraryGetCutDirection,
)
from deebot_client.commands.json.cut_direction import (
    SetCutDirection as _LibrarySetCutDirection,
)
from deebot_client.events.base import Event
from deebot_client.message import HandlingResult, HandlingState

from .areas import MowerArea

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus

_LOGGER = logging.getLogger(__name__)

# The id the mower-wide settings are kept and shown under. Not numeric, so it
# can never be one of the mower's own area ids.
AUTO_AREA_ID = "auto"


@dataclass(frozen=True)
class MowerAutoEvent(Event):
    """The latest raw mower-wide settings known for the mower.

    ``area`` has the id ``AUTO_AREA_ID`` and no name; its ``parameters`` hold
    each setting the mower has reported, keyed by the area wire key.
    """

    area: MowerArea


_AUTO_STATE: WeakKeyDictionary[EventBus, MowerArea] = WeakKeyDictionary()


def auto_for(event_bus: EventBus) -> MowerArea:
    """Return the mower-wide settings known for one mower, possibly none yet."""
    return _AUTO_STATE.get(event_bus, MowerArea(AUTO_AREA_ID))


def _apply(event_bus: EventBus, key: str, value: Any) -> HandlingResult:
    """Record one setting the mower reported, and publish the snapshot.

    Merged per key, like an area's parameters: one setting's answer must not
    drop what the others reported.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        _LOGGER.debug("Unexpected value for %s: %r", key, value)
        return HandlingResult.analyse()
    current = auto_for(event_bus)
    _AUTO_STATE[event_bus] = replace(
        current, parameters={**current.parameters, key: value}
    )
    event_bus.notify(MowerAutoEvent(_AUTO_STATE[event_bus]))
    return HandlingResult.success()


class _GetLevel(JsonGetCommand, ABC):
    """Read one mower-wide level setting, answered as ``{"level": n}``."""

    # The area wire key the level is kept under.
    PARAMETER_KEY: str

    @classmethod
    def _handle_body_data_dict(
        cls, event_bus: EventBus, data: dict[str, Any]
    ) -> HandlingResult:
        return _apply(event_bus, cls.PARAMETER_KEY, data.get("level"))


class GetCutHeight(_GetLevel):
    """Read the mower-wide cutting height level."""

    NAME = "getCutHeight"
    PARAMETER_KEY = "mowHeightLevel"


class GetCutEfficiency(_GetLevel):
    """Read the mower-wide mowing speed level."""

    NAME = "getCutEfficiency"
    PARAMETER_KEY = "cutMode"


class GetObstacleHeight(_GetLevel):
    """Read the mower-wide obstacle height level."""

    NAME = "getObstacleHeight"
    PARAMETER_KEY = "obstacleHeight"


class GetMowerCutDirection(_LibraryGetCutDirection):
    """The library's ``getCutDirection``, also kept as the ``auto`` angle.

    A subclass, so the library's ``CutDirectionEvent``, which the device-wide
    cutting direction number reads, is still published as before.
    """

    @classmethod
    def _handle_body_data_dict(
        cls, event_bus: EventBus, data: dict[str, Any]
    ) -> HandlingResult:
        result = _apply(event_bus, "angle", data.get("angle"))
        if result.state is not HandlingState.SUCCESS:
            return result
        return super()._handle_body_data_dict(event_bus, data)


class _SetLevel(JsonSetCommand, ABC):
    """Write one mower-wide level setting as ``{"level": n}``."""

    _mqtt_params = MappingProxyType({"level": InitParam(int)})

    def __init__(self, level: int) -> None:
        super().__init__({"level": level})


class SetCutHeight(_SetLevel):
    """Write the mower-wide cutting height level."""

    NAME = "setCutHeight"
    get_command = GetCutHeight


class SetCutEfficiency(_SetLevel):
    """Write the mower-wide mowing speed level."""

    NAME = "setCutEfficiency"
    get_command = GetCutEfficiency


class SetObstacleHeight(_SetLevel):
    """Write the mower-wide obstacle height level."""

    NAME = "setObstacleHeight"
    get_command = GetObstacleHeight


class SetMowerCutDirection(_LibrarySetCutDirection):
    """The library's ``setCutDirection``, recorded through ``GetMowerCutDirection``."""

    get_command = GetMowerCutDirection


# Read commands, in AREA_PARAMETER_KEYS order.
AUTO_READ_COMMANDS: tuple[type[JsonGetCommand], ...] = (
    GetCutHeight,
    GetCutEfficiency,
    GetObstacleHeight,
    GetMowerCutDirection,
)

# Write commands another client's requests are followed for, registered in
# the library's p2p table by ``apply()``.
AUTO_WRITE_COMMANDS: tuple[type[JsonSetCommand], ...] = (
    SetCutHeight,
    SetCutEfficiency,
    SetObstacleHeight,
    SetMowerCutDirection,
)


def reset() -> None:
    """Forget all mower-wide settings. Tests only."""
    _AUTO_STATE.clear()


__all__ = [
    "AUTO_AREA_ID",
    "AUTO_READ_COMMANDS",
    "AUTO_WRITE_COMMANDS",
    "GetCutEfficiency",
    "GetCutHeight",
    "GetMowerCutDirection",
    "GetObstacleHeight",
    "MowerAutoEvent",
    "SetCutEfficiency",
    "SetCutHeight",
    "SetMowerCutDirection",
    "SetObstacleHeight",
    "auto_for",
    "reset",
]
