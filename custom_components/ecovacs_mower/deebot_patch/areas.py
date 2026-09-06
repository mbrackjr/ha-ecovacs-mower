"""Mower area state and commands missing from deebot-client.

The patch owns the mower-reported area snapshot because the upstream client does
not model these GOAT commands yet. Home Assistant consumes the resulting state
and does not parse the Ecovacs wire format.

The A1600 LiDAR Pro parameter mappings are selected through the model profile
rather than treated as generic GOAT behaviour.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
import logging
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

import orjson
from deebot_client.commands.json.custom import CustomCommand
from deebot_client.events.base import Event
from deebot_client.message import HandlingResult
from deebot_client.rs.util import decompress_base64_data

from .device import A1600_AREA_MAPPING, MOWER_PROFILES

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus

_LOGGER = logging.getLogger(__name__)

AREA_PARAMETER_CLASSES = frozenset(
    device_class
    for device_class, profile in MOWER_PROFILES.items()
    if profile.area_parameters
)

decode_mow_height = A1600_AREA_MAPPING.mow_height
decode_cut_speed = A1600_AREA_MAPPING.cut_speed
decode_obstacle_height = A1600_AREA_MAPPING.obstacle_height
decode_cut_angle = A1600_AREA_MAPPING.cut_angle


@dataclass(frozen=True)
class MowerArea:
    """Authoritative mower-reported state for one area."""

    area_id: str
    name: str | None = None
    mow_height_level: int | None = None
    cut_mode: int | None = None
    obstacle_height: int | None = None
    angle: int | None = None


@dataclass(frozen=True)
class MowerAreaEvent(Event):
    """The latest area inventory and parameter snapshot known for one mower."""

    areas: tuple[MowerArea, ...]


_AREA_STATE: WeakKeyDictionary[EventBus, dict[str, MowerArea]] = WeakKeyDictionary()


def _areas_for(event_bus: EventBus) -> dict[str, MowerArea]:
    """Return the authoritative area state for one mower event bus."""
    return _AREA_STATE.setdefault(event_bus, {})


def _notify(event_bus: EventBus) -> None:
    """Publish the state after the owning handler has updated it."""
    event_bus.notify(MowerAreaEvent(tuple(_areas_for(event_bus).values())))


def _as_int(value: Any) -> int | None:
    """Return an integer payload value, or None when it is absent/invalid."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GetAreaParameter(CustomCommand):
    """Read all per-area mowing parameters from the mower."""

    NAME = "getAreaParameter"

    def __init__(self) -> None:
        """Build the empty getAreaParameter request."""
        super().__init__(self.NAME, {})

    def _handle_response(
        self, event_bus: EventBus, response: dict[str, Any]
    ) -> HandlingResult:
        """Merge the parameter response into the area snapshot."""
        if response.get("ret") != "ok":
            return super()._handle_response(event_bus, response)

        try:
            parameters = response["resp"]["body"]["data"]["areaParameters"]
        except (KeyError, TypeError):
            _LOGGER.debug("Unexpected getAreaParameter response: %r", response)
            return HandlingResult.analyse()

        if not isinstance(parameters, list):
            _LOGGER.debug("Unexpected areaParameters value: %r", parameters)
            return HandlingResult.analyse()

        areas = _areas_for(event_bus)
        for parameter in parameters:
            if not isinstance(parameter, dict) or parameter.get("areaID") is None:
                continue
            area_id = str(parameter["areaID"])
            current = areas.get(area_id, MowerArea(area_id))
            areas[area_id] = replace(
                current,
                mow_height_level=_as_int(parameter.get("mowHeightLevel")),
                cut_mode=_as_int(parameter.get("cutMode")),
                obstacle_height=_as_int(parameter.get("obstacleHeight")),
                angle=_as_int(parameter.get("angle")),
            )

        # getAreaSet owns inventory membership. Parameters only enrich existing
        # areas (or provide a fallback area if parameters arrive first).
        _notify(event_bus)
        return HandlingResult.success()


class _AreaSetFragmentBuffer:
    """Reassemble multipart area-set data using deebot-client's decoder."""

    def __init__(self, max_batches: int = 16) -> None:
        """Create a bounded fragment buffer."""
        self._batches: OrderedDict[str, dict[int, str]] = OrderedDict()
        self._max_batches = max_batches

    def add(
        self, batid: str, index: int, fragment: str, info_size: int
    ) -> bytes | None:
        """Add a fragment and return decoded data when complete."""
        del info_size
        parts = self._batches.setdefault(batid, {})
        self._batches.move_to_end(batid)
        parts[index] = fragment
        while len(self._batches) > self._max_batches:
            self._batches.popitem(last=False)

        joined = "".join(parts[i] for i in sorted(parts))
        try:
            blob = decompress_base64_data(joined)
        except (ValueError, RuntimeError):
            return None
        del self._batches[batid]
        return blob


class GetAreaSet(CustomCommand):
    """Read the mower's current area inventory and friendly names."""

    NAME = "getAreaSet"

    def __init__(self) -> None:
        """Build a request for mowing areas (``ar``)."""
        # The A1600 rejects type=ar without mid/aid. These values mirror the
        # request emitted by the Ecovacs app.
        super().__init__(self.NAME, {"mid": "1", "aid": "0", "type": "ar"})
        self._buffer = _AreaSetFragmentBuffer()

    def _handle_response(
        self, event_bus: EventBus, response: dict[str, Any]
    ) -> HandlingResult:
        """Merge decoded area names into the authoritative snapshot."""
        if response.get("ret") != "ok":
            return super()._handle_response(event_bus, response)

        try:
            data = response["resp"]["body"]["data"]
            info = data["subsets"]
        except (KeyError, TypeError):
            _LOGGER.debug("Unexpected getAreaSet response: %r", response)
            return HandlingResult.analyse()

        if not isinstance(info, str):
            return HandlingResult.analyse()

        try:
            index = int(data.get("index", 0))
            info_size = int(data.get("infoSize", -1))
        except (TypeError, ValueError):
            return HandlingResult.analyse()

        blob = self._buffer.add(str(data.get("batid", "")), index, info, info_size)
        if blob is None:
            return HandlingResult.success()

        try:
            decoded = orjson.loads(blob)
        except orjson.JSONDecodeError:
            _LOGGER.debug("Could not decode getAreaSet payload")
            return HandlingResult.analyse()

        if not isinstance(decoded, list):
            return HandlingResult.analyse()

        areas = _areas_for(event_bus)
        reported_ids: set[str] = set()
        for row in decoded:
            if not isinstance(row, list) or len(row) < 3:
                continue
            area_id = str(row[1])
            name = row[2]
            if not isinstance(name, str) or not name.strip():
                continue
            reported_ids.add(area_id)
            current = areas.get(area_id, MowerArea(area_id))
            areas[area_id] = replace(current, name=name.strip())

        # A successfully decoded ``ar`` response is the authoritative area
        # inventory, so IDs absent from it no longer exist on the mower.
        for area_id in tuple(areas):
            if area_id not in reported_ids:
                del areas[area_id]

        _notify(event_bus)
        return HandlingResult.success()


def reset() -> None:
    """Forget all per-device area state. Tests only."""
    _AREA_STATE.clear()


__all__ = [
    "AREA_PARAMETER_CLASSES",
    "GetAreaParameter",
    "GetAreaSet",
    "MowerArea",
    "MowerAreaEvent",
    "decode_cut_angle",
    "decode_cut_speed",
    "decode_mow_height",
    "decode_obstacle_height",
    "reset",
]
