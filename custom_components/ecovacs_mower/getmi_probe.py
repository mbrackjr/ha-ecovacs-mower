"""THROWAWAY EXPERIMENT — not for merging.

Does firmware 1.13 answer getMI with an onMI only when the request carries
the Ecovacs app's header? The app's getMI (sent over the v2 endpoint) is
followed by an onMI within seconds; ours, over iot/devmanager.do with
deebot-client's header, is acked without one once the app has been closed
for a while. The body is identical (``{"type": "0"}``), so this probe changes
the header only and keeps our route.

About 20 s after startup, per patched mower, it sends three getMI requests,
clearing the recorded map id before each and logging 10 s later whether an
onMI named the map again:

    A  app header           {"channel": "iOS", "ver": "1.0.0", "tzm": 120, "pri": 1, ...}
    B  deebot-client header {"pri": "1", "ver": "0.0.50", "tzm": 480, ...}
    A  app header again

A ✔ B ✘ A ✔ means the header decides it. All ✘ rules the header out. All ✔
means the mower was warm (the app was open recently) and the run says nothing.

    ha core logs | grep "map probe"
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
import time
from typing import Any

from deebot_client.commands.json.common import ExecuteCommand
from deebot_client.device import Device

from .deebot_patch.state_precedence import record_for

_LOGGER = logging.getLogger(__name__)

_START_DELAY = 20  # seconds: let setup finish first
_WAIT = 10  # seconds after each request for a push to arrive
_MAX_LOGGED = 400  # characters of each raw answer
_BODY = {"type": "0"}


class _GetMIOurs(ExecuteCommand):
    """getMI exactly as deebot-client sends any JSON command."""

    NAME = "getMI"

    def __init__(self) -> None:
        super().__init__(_BODY)


class _GetMIApp(_GetMIOurs):
    """getMI with the header the iOS app sent in the 2026-10-12 capture."""

    def _get_payload(self) -> dict[str, Any]:
        return {
            "body": {"data": self._args},
            "header": {
                "channel": "iOS",
                "reqid": "".join(random.choices(string.ascii_letters, k=6)),
                "ts": str(int(time.time() * 1000)),
                "ver": "1.0.0",
                "m": "request",
                "pri": 1,
                "tzm": 120,
                "tzc": "Europe/Amsterdam",
            },
        }


_REQUESTS: tuple[tuple[str, type[ExecuteCommand]], ...] = (
    ("A app header", _GetMIApp),
    ("B our header", _GetMIOurs),
    ("A app header again", _GetMIApp),
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
    results = []
    for label, command_type in _REQUESTS:
        record.map_id = None
        command = command_type()
        _LOGGER.warning("[map probe] %s payload=%s", label, command._get_payload())
        response = await device.execute_command(command)
        await asyncio.sleep(_WAIT)
        body = (response.get("resp") or {}).get("body") if response else None
        named = record.map_id is not None
        results.append(f"{label[0]}{'✔' if named else '✘'}")
        _LOGGER.warning(
            "[map probe] %s -> errno=%s map_id_after=%r body=%s",
            label,
            response.get("errno") if response else "no response",
            record.map_id,
            str(body)[:_MAX_LOGGED],
        )
    _LOGGER.warning("[map probe] done: %s", " ".join(results))
