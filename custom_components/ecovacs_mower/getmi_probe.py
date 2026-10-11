"""THROWAWAY EXPERIMENT — not for merging.

Finds out which request makes a GOAT on firmware 1.13 name the map in use,
which ``GetAreaSet`` needs before it can fetch the area names. Once, about
20 s after startup, per patched mower, it sends in turn:

1. ``getMapState {}``: does the answer carry ``mid``? (Janverhu/ecovacs-goat-g1
   reads it from there for the O-series.)
2. ``getPos ["chargePos", "deebotPos"]``: does the answer carry ``mid``, and is
   it a real one or ``"0"``?
3. ``getMI {"type": "0"}``: is it followed by ``onMI`` on the first request
   after a fresh start?

Before each request the recorded map id is cleared; 5 s after it the raw
answer and the map id are logged. Everything is logged at WARNING with the
prefix ``[map probe]``, so no debug logging is needed:

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
_WAIT = 5  # seconds after each request for a push to arrive
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
    (_GetMapState, {}),
    (_GetPos, ["chargePos", "deebotPos"]),
    (_GetMI, {"type": "0"}),
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
