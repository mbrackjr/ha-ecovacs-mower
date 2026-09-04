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
from typing import TYPE_CHECKING, Any, Callable
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
class AreaParameterProfile:
    """Human/wire conversion rules for one mower class or firmware family."""

    mow_height_to_wire: Callable[[float], int]
    mow_height_from_wire: Callable[[int], float | None]
    speed_to_wire: Callable[[float], int]
    speed_from_wire: Callable[[int], float | None]
    obstacle_height_to_wire: Callable[[int], int]
    obstacle_height_from_wire: Callable[[int], int | None]
    angle_to_wire: Callable[[float], int]
    angle_from_wire: Callable[[int], int | None]
    mow_height_values: tuple[float, ...]
    speed_values: tuple[float, ...]
    obstacle_height_values: tuple[int, ...]


def _a1600_mow_height_to_wire(cm: float) -> int:
    """Convert A1600 grass height in cm to its wire level."""
    value = float(cm)
    if value not in A1600_PROFILE.mow_height_values:
        raise ValueError(f"Unsupported mowing height: {cm}")
    return int(10 - value)


def _a1600_mow_height_from_wire(level: int) -> float | None:
    """Convert an A1600 wire level to grass height in cm."""
    if level not in range(1, 8):
        return None
    return float(10 - level)


def _a1600_speed_to_wire(speed: float) -> int:
    """Convert A1600 mowing speed in m/s to cutMode."""
    value = round(float(speed), 2)
    if value not in A1600_PROFILE.speed_values:
        raise ValueError(f"Unsupported mowing speed: {speed}")
    return int(round(7 - ((value - 0.40) / 0.05)))


def _a1600_speed_from_wire(level: int) -> float | None:
    """Convert A1600 cutMode to mowing speed in m/s."""
    if level not in range(1, 8):
        return None
    return round(0.40 + 0.05 * (7 - level), 2)


def _a1600_obstacle_height_to_wire(cm: int) -> int:
    """Convert A1600 obstacle threshold in cm to obstacleHeight."""
    value = int(cm)
    return {10: 1, 15: 2, 20: 3}[value]


def _a1600_obstacle_height_from_wire(level: int) -> int | None:
    """Convert A1600 obstacleHeight to the obstacle threshold in cm."""
    return {1: 10, 2: 15, 3: 20}.get(level)


def _a1600_angle_to_wire(degrees: float) -> int:
    """Convert A1600 app-space cutting angle to wire-space angle."""
    value = float(degrees)
    if value < 0 or value >= 360:
        raise ValueError(f"Unsupported cutting angle: {degrees}")
    return int(round(270 - value)) % 360


def _a1600_angle_from_wire(wire_angle: int) -> int | None:
    """Convert A1600 wire-space angle to app-space cutting angle."""
    if wire_angle not in range(360):
        return None
    return (270 - wire_angle) % 360


A1600_PROFILE = AreaParameterProfile(
    mow_height_to_wire=_a1600_mow_height_to_wire,
    mow_height_from_wire=_a1600_mow_height_from_wire,
    speed_to_wire=_a1600_speed_to_wire,
    speed_from_wire=_a1600_speed_from_wire,
    obstacle_height_to_wire=_a1600_obstacle_height_to_wire,
    obstacle_height_from_wire=_a1600_obstacle_height_from_wire,
    angle_to_wire=_a1600_angle_to_wire,
    angle_from_wire=_a1600_angle_from_wire,
    # A1600 LiDAR Pro confirmed values. New mower/firmware families should add
    # a profile rather than changing these conversion functions.
    mow_height_values=tuple(float(value) for value in range(3, 10)),
    speed_values=tuple(round(0.40 + 0.05 * i, 2) for i in range(7)),
    obstacle_height_values=(10, 15, 20),
)

AREA_PARAMETER_PROFILES = {"e4gqia": A1600_PROFILE}


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


def get_area(event_bus: EventBus, area_id: str) -> MowerArea | None:
    """Return the most recently received parameters for an area."""
    return _areas_for(event_bus).get(str(area_id))


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
        super().__init__(
            self.NAME,
            {"mid": "1", "aid": "0", "type": "ar"},
        )
        self._buffer = _AreaSetFragmentBuffer()

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
    """Convert A1600 ``mowHeightLevel`` to the grass height in centimetres."""
    return A1600_PROFILE.mow_height_from_wire(level)


def decode_cut_speed(level: int) -> float | None:
    """Convert A1600 ``cutMode`` to mowing speed in metres per second."""
    return A1600_PROFILE.speed_from_wire(level)


def decode_obstacle_height(level: int) -> int | None:
    """Convert A1600 ``obstacleHeight`` to the obstacle threshold in cm."""
    return A1600_PROFILE.obstacle_height_from_wire(level)


def decode_cut_angle(wire_angle: int) -> int | None:
    """Convert A1600 wire-space angle to the app-space angle."""
    return A1600_PROFILE.angle_from_wire(wire_angle)
