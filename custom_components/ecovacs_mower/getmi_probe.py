"""THROWAWAY EXPERIMENT — not for merging.

Finds out which ``getMI`` request a GOAT on firmware 1.13 answers with the
``onMI`` push that names the map in use. The Ecovacs app sends ``getMI`` when
its map opens; the mower acks it and then pushes ``onMI`` with ``mid`` and
``using: 1``. The app's request body is not visible on the mower's MQTT
channel, so each candidate body is tried in turn.

For every candidate the probe forgets the map id, sends the request, waits,
and logs whether an ``onMI`` taught the id again. Every line is logged at
WARNING with the prefix ``[getMI probe]``, so no debug logging is needed:

    ha core logs | grep "getMI probe"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from deebot_client.commands.json.common import ExecuteCommand
from deebot_client.device import Device

from .deebot_patch.state_precedence import record_for

_LOGGER = logging.getLogger(__name__)

_START_DELAY = 20  # seconds: let setup, and its getMapInfo_V2 attempt, finish
_WAIT = 5  # seconds after each request for the onMI push to arrive

_CANDIDATES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("no body", {}),
    ('{"type": "0"}', {"type": "0"}),
    ('{"mid": "", "type": "0"}', {"mid": "", "type": "0"}),
)


class _GetMI(ExecuteCommand):
    """``getMI`` with whatever body the probe hands it."""

    NAME = "getMI"


async def async_probe(device: Device) -> None:
    """Try each candidate body and report which one brings the map id back."""
    did = device.device_info["did"]
    await asyncio.sleep(_START_DELAY)
    record = record_for(device.events)
    if record is None:
        _LOGGER.warning("[getMI probe] %s is not a patched mower, skipped", did)
        return

    _LOGGER.warning(
        "[getMI probe] start: did=%s class=%s fw=%s map_id_before=%r",
        did,
        device.device_info["class"],
        device.fw_version,
        record.map_id,
    )
    for label, body in _CANDIDATES:
        record.map_id = None
        response = await device.execute_command(_GetMI(body))
        ack = (response.get("resp") or {}).get("body") if response else None
        await asyncio.sleep(_WAIT)
        _LOGGER.warning(
            "[getMI probe] %-28s ack=%s errno=%s -> map_id=%r (%s)",
            label,
            ack,
            response.get("errno") if response else None,
            record.map_id,
            "onMI ARRIVED" if record.map_id else "no onMI",
        )
    _LOGGER.warning("[getMI probe] done")
