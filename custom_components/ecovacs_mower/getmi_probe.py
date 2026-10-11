"""THROWAWAY EXPERIMENT — not for merging.

Checks whether the Ecovacs app's getMI differs from ours by naming the map.
The app's getMI is followed by onMI every time; ours (``{"type": "0"}``) was
acked without one in three of four tries, and the app already knows the map
id before the mower names it. Once, about 20 s after startup, per patched
mower, it sends ``getMI {"type": "0"}`` and then ``getMI {"mid": "1",
"type": "0"}``, clearing the recorded map id before each and logging 8 s
later whether an onMI taught it again.

    ha core logs | grep "map probe"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from deebot_client.commands.json.common import ExecuteCommand
from deebot_client.device import Device

from .deebot_patch.state_precedence import record_for

_LOGGER = logging.getLogger(__name__)

_START_DELAY = 20  # seconds: let setup finish first
_WAIT = 8  # seconds after each request for a push to arrive
_MAX_LOGGED = 700  # characters of each raw answer


class _Probe(ExecuteCommand):
    """Always sends a body, even an empty one.

    ``JsonCommand._get_payload`` leaves ``body`` out when the args are empty,
    and a header-only ``getMI`` went unanswered in the first probe.
    """

    NAME = "probe"

    def _get_payload(self) -> dict[str, Any]:
        return {**super()._get_payload(), "body": {"data": self._args}}


class _GetMapState(_Probe):
    NAME = "getMapState"


class _GetPos(_Probe):
    NAME = "getPos"


class _GetMI(_Probe):
    NAME = "getMI"


_REQUESTS: tuple[tuple[type[ExecuteCommand], Any], ...] = (
    # Baseline first: if the mower will not resend its map shortly after
    # sending it, a success of the second request cannot be explained away.
    (_GetMI, {"type": "0"}),
    (_GetMI, {"mid": "1", "type": "0"}),
)


async def async_probe(device: Device) -> None:
    """Send each request and report its answer and the map id after it."""
    did = device.device_info["did"]
    await asyncio.sleep(_START_DELAY)
    record = record_for(device.events)
    if record is None:
        _LOGGER.warning("[map probe] %s is not a patched mower, skipped", did)
        return

    _LOGGER.warning(
        "[map probe] start: class=%s fw=%s map_id_before=%r",
        device.device_info["class"],
        device.fw_version,
        record.map_id,
    )
    for command_type, args in _REQUESTS:
        record.map_id = None
        response = await device.execute_command(command_type(args))
        await asyncio.sleep(_WAIT)
        body = (response.get("resp") or {}).get("body") if response else None
        _LOGGER.warning(
            "[map probe] %s %s -> errno=%s map_id_after=%r body=%s",
            command_type.NAME,
            args,
            response.get("errno") if response else "no response",
            record.map_id,
            str(body)[:_MAX_LOGGED],
        )
    _LOGGER.warning("[map probe] done")
