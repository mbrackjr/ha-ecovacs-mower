"""THROWAWAY EXPERIMENT — not for merging.

Does firmware 1.13 answer getMI with an onMI only after an ``appping``? In
both captures of the iOS app it sent ``appping`` (empty body) over HTTPS
before its getMI, and kept pinging about every two minutes, and its getMI was
answered with an onMI even while the app's own MQTT connection was down. Our
getMI, without a ping, is acked without one. The header alone is ruled out
(A ✘ B ✘ A ✘ on 2026-10-12).

About 20 s after startup, per patched mower, it runs four steps over our
normal route, clearing the recorded map id before each getMI and logging 10 s
later whether an onMI named the map again:

    1  getMI alone                                  baseline
    2  appping (our header), 3 s, getMI
    3  appping (app header), 3 s, getMI
    4  getMI alone                                  does the effect last?

The first ✔ says what it takes: at 2, a ping; at 3, a ping with the app's
header. All ✘ rules the ping out over this route. A ✔ at 1 means the mower was
warm and the run says nothing.

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
_PING_GAP = 3  # seconds between appping and getMI
_PING_TIMEOUT = 15  # seconds to wait for an answer to appping
_WAIT = 10  # seconds after getMI for a push to arrive
_MAX_LOGGED = 300  # characters of each raw answer


class _Ours(ExecuteCommand):
    """Sent exactly as deebot-client sends any JSON command, body included."""

    NAME = "probe"

    def _get_payload(self) -> dict[str, Any]:
        # JsonCommand leaves body out when the args are empty; the app always
        # sends one ({"data": {}} for appping).
        return {**super()._get_payload(), "body": {"data": self._args}}


class _AppHeader(_Ours):
    """The header the iOS app sent in the 2026-10-12 captures."""

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


class _GetMI(_Ours):
    NAME = "getMI"


class _AppPing(_Ours):
    NAME = "appping"


class _AppPingAppHeader(_AppHeader):
    NAME = "appping"


_STEPS: tuple[tuple[str, type[ExecuteCommand] | None], ...] = (
    ("1 getMI alone", None),
    ("2 appping (our header) + getMI", _AppPing),
    ("3 appping (app header) + getMI", _AppPingAppHeader),
    ("4 getMI alone", None),
)


def _summary(response: dict[str, Any] | None) -> str:
    if not response:
        return "no response"
    body = (response.get("resp") or {}).get("body")
    return f"ret={response.get('ret')} errno={response.get('errno')} body={str(body)[:_MAX_LOGGED]}"


async def async_probe(device: Device) -> None:
    """Run each step and report the answers and the map id after it."""
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
    for label, ping_type in _STEPS:
        if ping_type is not None:
            ping = ping_type({})
            _LOGGER.warning("[map probe] %s: ping payload=%s", label, ping._get_payload())
            # The app's appping got no answer in either capture, so do not let
            # a ping that is never answered hold up the getMI behind it.
            try:
                response = await asyncio.wait_for(
                    device.execute_command(ping), _PING_TIMEOUT
                )
                outcome = _summary(response)
            except Exception as ex:  # noqa: BLE001 - throwaway probe
                outcome = f"{type(ex).__name__} {ex}"
            _LOGGER.warning("[map probe] %s: ping -> %s", label, outcome)
            await asyncio.sleep(_PING_GAP)
        record.map_id = None
        response = await device.execute_command(_GetMI({"type": "0"}))
        await asyncio.sleep(_WAIT)
        named = record.map_id is not None
        results.append(f"{label[0]}:{'OK' if named else 'no'}")
        _LOGGER.warning(
            "[map probe] %s: getMI -> %s map_id_after=%r",
            label,
            _summary(response),
            record.map_id,
        )
    _LOGGER.warning("[map probe] done: %s", " ".join(results))
