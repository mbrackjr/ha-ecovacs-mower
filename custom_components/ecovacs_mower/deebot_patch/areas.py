"""Mower area state and protocol parsing missing from deebot-client.

The patch owns the mower-reported area snapshot because the upstream client does
not model these GOAT commands yet. Home Assistant consumes the resulting state
and does not parse the Ecovacs wire format.

The area values remain raw protocol values here. Model- and firmware-specific
conversion to human-sensible Home Assistant values belongs exclusively to the
HA layer and must not be generalized here without validation.

The area name is a separate response from ``getAreaSet``. Its ``ar`` response
contains chunked Base64/LZMA data whose decoded rows start with map ID, area ID
and the user-editable name. The decompressor is supplied by deebot-client; the
patch only adds the missing protocol row interpretation.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
import logging
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

import orjson
from deebot_client.events.base import Event
from deebot_client.message import HandlingResult
from deebot_client.rs.util import decompress_base64_data

from .commands import GetAreaParameter, GetAreaSet, SetAreaParameter
from .hardware import SUPPORTED_CLASSES

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus

_LOGGER = logging.getLogger(__name__)

AREA_PARAMETER_CLASSES = frozenset(
    device_class
    for device_class, profile in SUPPORTED_CLASSES.items()
    if profile.area_parameters
)


@dataclass(frozen=True)
class MowerArea:
    """The raw per-area parameters plus the optional app-defined name."""

    area_id: str
    name: str | None = None
    mow_height_level: int | None = None
    cut_mode: int | None = None
    obstacle_height: int | None = None
    angle: int | None = None


@dataclass(frozen=True)
class MowerAreaEvent(Event):
    """The latest area inventory and parameter snapshot known for the mower."""

    areas: tuple[MowerArea, ...]


_AREA_STATE: WeakKeyDictionary[EventBus, dict[str, MowerArea]] = WeakKeyDictionary()


def _areas_for(event_bus: EventBus) -> dict[str, MowerArea]:
    """Return the authoritative area state for one mower event bus."""
    return _AREA_STATE.setdefault(event_bus, {})


def area_for(event_bus: EventBus, area_id: str) -> MowerArea | None:
    """Return the authoritative raw state for one known area."""
    return _areas_for(event_bus).get(area_id)


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


class _AreaSetFragmentBuffer:
    """Reassemble multipart area-set data using deebot-client's decoder."""

    def __init__(self, max_batches: int = 16) -> None:
        """Create a bounded fragment buffer."""
        self._batches: OrderedDict[str, dict[int, str]] = OrderedDict()
        self._max_batches = max_batches

    def add(
        self, batid: str, index: int, fragment: str, info_size: int
    ) -> bytes | None:
        """Add a fragment and return decoded data when the stream is complete.

        ``infoSize`` in the mower ``ar`` response is not the size of the
        decompressed JSON returned by ``decompress_base64_data``. The A1600,
        for example, reports ``infoSize=498`` while its decoded JSON is 196
        bytes. Completion is therefore determined by successful decompression
        rather than by comparing the decompressed length with ``infoSize``.
        """
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


class GetAreaSetHandler:
    """Handle the mower's multipart area inventory response."""

    def __init__(self) -> None:
        """Create a fresh reassembly buffer for one command instance."""
        self._buffer = _AreaSetFragmentBuffer()

    def handle(
        self, event_bus: EventBus, response: dict[str, Any]
    ) -> HandlingResult:
        """Merge decoded area inventory and names into the snapshot."""
        if response.get("ret") != "ok":
            return HandlingResult.analyse()

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
            if not isinstance(row, list) or len(row) < 2:
                continue
            area_id = str(row[1]).strip()
            if not area_id:
                continue
            reported_ids.add(area_id)
            name = row[2] if len(row) >= 3 else None
            if isinstance(name, str) and name.strip():
                current = areas.get(area_id, MowerArea(area_id))
                areas[area_id] = replace(current, name=name.strip())
            elif area_id not in areas:
                areas[area_id] = MowerArea(area_id)

        # A non-empty decoded response with no valid area IDs is malformed; do
        # not destroy the last known inventory in that case. An empty list is a
        # valid snapshot and intentionally clears the inventory.
        if decoded and not reported_ids:
            _LOGGER.debug("Could not find area IDs in getAreaSet payload")
            return HandlingResult.analyse()

        # A successfully decoded ``ar`` response is the authoritative area
        # inventory, so IDs absent from it no longer exist on the mower.
        for area_id in tuple(areas):
            if area_id not in reported_ids:
                del areas[area_id]

        _notify(event_bus)
        return HandlingResult.success()


class GetAreaParameterHandler:
    """Handle the mower's raw per-area parameter response."""

    def handle(
        self, event_bus: EventBus, response: dict[str, Any]
    ) -> HandlingResult:
        """Merge the parameter response into the area snapshot."""
        if response.get("ret") != "ok":
            return HandlingResult.analyse()

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


# The protocol command classes live in commands.py with the rest of the patch
# commands. These handler helpers are intentionally kept here because they own
# the authoritative area-state interpretation, not the command construction.

def reset() -> None:
    """Forget all per-device area state. Tests only."""
    _AREA_STATE.clear()


__all__ = [
    "AREA_PARAMETER_CLASSES",
    "GetAreaParameterHandler",
    "GetAreaSetHandler",
    "MowerArea",
    "MowerAreaEvent",
    "SetAreaParameter",
    "area_for",
    "reset",
]
