"""Area-parameter protocol commands missing from deebot-client.

Raw Ecovacs values stay here; Home Assistant conversion belongs in
``area_sensors.py``. Keeping these commands separate avoids coupling the area
protocol work to the larger mower command module.
"""

from __future__ import annotations

import logging
from typing import Any

from deebot_client.commands.json.custom import CustomCommand
from deebot_client.message import HandlingResult
from deebot_client.rs.util import decompress_base64_data

from .areas import MowerArea, _AreaSetFragmentBuffer, _areas_for, _as_int, _notify

_LOGGER = logging.getLogger(__name__)


class GetAreaParameter(CustomCommand):
    """Read all raw per-area mowing parameters from the mower."""

    NAME = "getAreaParameter"

    def __init__(self) -> None:
        super().__init__(self.NAME, {})

    def _handle_response(
        self, event_bus: Any, response: dict[str, Any]
    ) -> HandlingResult:
        if response.get("ret") != "ok":
            return super()._handle_response(event_bus, response)
        try:
            parameters = response["resp"]["body"]["data"]["areaParameters"]
        except (KeyError, TypeError):
            _LOGGER.debug("Unexpected getAreaParameter response: %r", response)
            return HandlingResult.analyse()
        if not isinstance(parameters, list):
            return HandlingResult.analyse()

        areas = _areas_for(event_bus)
        for parameter in parameters:
            if not isinstance(parameter, dict) or parameter.get("areaID") is None:
                continue
            area_id = str(parameter["areaID"])
            current = areas.get(area_id, MowerArea(area_id))
            areas[area_id] = MowerArea(
                area_id=current.area_id,
                name=current.name,
                mow_height_level=_as_int(parameter.get("mowHeightLevel")),
                cut_mode=_as_int(parameter.get("cutMode")),
                obstacle_height=_as_int(parameter.get("obstacleHeight")),
                angle=_as_int(parameter.get("angle")),
            )
        _notify(event_bus)
        return HandlingResult.success()


class GetAreaSet(CustomCommand):
    """Read the mower's area inventory and friendly names."""

    NAME = "getAreaSet"

    def __init__(self) -> None:
        super().__init__(self.NAME, {"mid": "1", "aid": "0", "type": "ar"})
        self._buffer = _AreaSetFragmentBuffer()

    def _handle_response(
        self, event_bus: Any, response: dict[str, Any]
    ) -> HandlingResult:
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
            import orjson

            decoded = orjson.loads(blob)
        except (orjson.JSONDecodeError, TypeError):
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
            current = areas.get(area_id, MowerArea(area_id))
            areas[area_id] = MowerArea(
                area_id=current.area_id,
                name=name.strip() if isinstance(name, str) and name.strip() else current.name,
                mow_height_level=current.mow_height_level,
                cut_mode=current.cut_mode,
                obstacle_height=current.obstacle_height,
                angle=current.angle,
            )

        if decoded and not reported_ids:
            _LOGGER.debug("Could not find area IDs in getAreaSet payload")
            return HandlingResult.analyse()
        for area_id in tuple(areas):
            if area_id not in reported_ids:
                del areas[area_id]
        _notify(event_bus)
        return HandlingResult.success()


class SetAreaParameter(CustomCommand):
    """Set the complete raw parameter set for one mower area."""

    NAME = "setAreaParameter"

    def __init__(
        self,
        *,
        area_id: str,
        mow_height_level: int,
        cut_mode: int,
        obstacle_height: int,
        angle: int,
    ) -> None:
        super().__init__(
            self.NAME,
            {
                "areaID": area_id,
                "mowHeightLevel": mow_height_level,
                "cutMode": cut_mode,
                "obstacleHeight": obstacle_height,
                "angle": angle,
            },
        )


__all__ = ["GetAreaParameter", "GetAreaSet", "SetAreaParameter"]
