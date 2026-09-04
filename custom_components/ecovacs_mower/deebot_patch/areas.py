"""Area parameter commands and events missing from deebot-client.

GOAT exposes per-area mowing settings through ``getAreaParameter``. The
library does not model this command, so the patch layer keeps the wire format
here and publishes a mower-specific event for the sensor platform.

The A1600 LiDAR Pro findings that established the mappings live in issue #11.
They are deliberately scoped to that model here: the values have not been
verified on the other mower classes supported by this integration.

The area name is a separate response from ``getAreaSet``. Its ``ar`` response
contains chunked Base64/LZMA data whose decoded rows start with map ID, area ID
and the user-editable name. The decompressor is supplied by deebot-client; the
patch only adds the missing command and mower-specific row interpretation.
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

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus

_LOGGER = logging.getLogger(__name__)

AREA_PARAMETER_CLASSES = frozenset({"e4gqia"})


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
class MowerAreaParameterEvent(Event):
    """The latest per-area parameter snapshot known for the mower."""

    areas: tuple[MowerArea, ...]


@dataclass(frozen=True)
class MowerAreaNameEvent(Event):
    """The latest user-defined names known for mower areas."""

    names: tuple[tuple[str, str], ...]


_AREA_STATE: WeakKeyDictionary[EventBus, dict[str, MowerArea]] = WeakKeyDictionary()


def _areas_for(event_bus: EventBus) -> dict[str, MowerArea]:
    """Return the per-device area state."""
    return _AREA_STATE.setdefault(event_bus, {})


def _notify_parameters(event_bus: EventBus) -> None:
    """Publish the current per-area parameter snapshot."""
    event_bus.notify(MowerAreaParameterEvent(tuple(_areas_for(event_bus).values())))


def _notify_names(event_bus: EventBus) -> None:
    """Publish the current area names."""
    names = tuple(
        (area_id, area.name)
        for area_id, area in _areas_for(event_bus).items()
        if area.name is not None
    )
    if names:
        event_bus.notify(MowerAreaNameEvent(names))


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
        """Parse the complete area parameter response."""
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

        areas: dict[str, MowerArea] = {}
        previous = _areas_for(event_bus)
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            area_id = parameter.get("areaID")
            if area_id is None:
                continue
            area_id = str(area_id)
            areas[area_id] = MowerArea(
                area_id=area_id,
                name=previous.get(area_id, MowerArea(area_id)).name,
                mow_height_level=_as_int(parameter.get("mowHeightLevel")),
                cut_mode=_as_int(parameter.get("cutMode")),
                obstacle_height=_as_int(parameter.get("obstacleHeight")),
                angle=_as_int(parameter.get("angle")),
            )

        _AREA_STATE[event_bus] = areas
        _notify_parameters(event_bus)
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


class GetAreaSet(CustomCommand):
    """Read user-defined mower area names from the ``ar`` area set.

    ``getAreaSet`` is not modelled by deebot-client. The response uses the
    chunked Base64/LZMA decoder already provided by the pinned deebot-client
    18.5.1 release. For ``ar`` the decoded rows are documented upstream as
    ``mapID | areaID | name | neighbourIDs | 2 reference coordinates | flags``.
    """

    NAME = "getAreaSet"

    def __init__(self) -> None:
        """Build a request for mowing areas (``ar``)."""
        # The GOAT expects mid/aid as well as type in the body data. A request
        # containing only ``type=ar`` is rejected by the A1600 with
        # ``code=20011, msg=get aid error``. This mirrors the payload emitted
        # by the Ecovacs app and is required even though the response itself
        # carries the area records.
        super().__init__(
            self.NAME,
            {"mid": "1", "aid": "0", "type": "ar"},
        )

    def _handle_response(
        self, event_bus: EventBus, response: dict[str, Any]
    ) -> HandlingResult:
        """Parse names from a successful ``getAreaSet`` response."""
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
        names_found = False
        for subset in decoded:
            if not isinstance(subset, list) or len(subset) < 3:
                continue
            area_id = str(subset[1])
            name = subset[2]
            if not isinstance(name, str) or not name.strip():
                continue
            current = areas.get(area_id, MowerArea(area_id))
            areas[area_id] = replace(current, name=name.strip())
            names_found = True

        if names_found:
            _notify_names(event_bus)
        return HandlingResult.success()


def reset() -> None:
    """Forget all per-device area state. Tests only."""
    _AREA_STATE.clear()


def decode_mow_height(level: int) -> float | None:
    """Convert A1600 ``mowHeightLevel`` to the grass height in centimetres.

    Confirmed on the A1600 LiDAR Pro specifically: levels 1–7 leave 9–3 cm of
    grass respectively. The observed formula is ``cm = 10 - mowHeightLevel``.
    """
    if level not in range(1, 8):
        return None
    return float(10 - level)


def decode_cut_speed(level: int) -> float | None:
    """Convert A1600 ``cutMode`` to mowing speed in metres per second.

    Confirmed on the A1600 LiDAR Pro specifically: levels 1–7 mean 0.70–0.40
    m/s respectively. The observed formula is
    ``speed_ms = 0.40 + 0.05 × (7 - cutMode)``.
    """
    if level not in range(1, 8):
        return None
    return round(0.40 + 0.05 * (7 - level), 2)


def decode_obstacle_height(level: int) -> int | None:
    """Convert A1600 ``obstacleHeight`` to the obstacle threshold in cm."""
    return {1: 10, 2: 15, 3: 20}.get(level)


def decode_cut_angle(wire_angle: int) -> int | None:
    """Convert the A1600 wire-space angle to the app-space angle.

    Confirmed on the A1600 LiDAR Pro specifically. The observed symmetric
    conversion is ``app = (270 - wire) mod 360``; the same formula converts the
    app value back to wire space.
    """
    if wire_angle not in range(360):
        return None
    return (270 - wire_angle) % 360
