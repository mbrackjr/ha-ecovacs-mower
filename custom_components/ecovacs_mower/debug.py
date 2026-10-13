"""Debug logs a user can start from a button, for reporting what a mower sends.

Supporting another model's area parameters needs a table of what each raw
value means: set a value in the Ecovacs app, see which raw number the mower
reports for it. Every model has its own ranges, so there is no fixed list of
steps to ask for, only a record of what changed while the owner tries.

``AreaParameterLog`` keeps that record. Started from the mower's "Log area
parameters" button, it reads the areas once, then follows every change for
``LOG_WINDOW``. Read-only on every class: nothing here writes to the mower, so
it is safe on a model whose values nobody has mapped yet. Changes made in the
app arrive without a request, because the mower pushes ``onAreaParameter`` to
every client and that push is handled for every patched mower, flag or no flag.

The record is a persistent notification, one per mower, rewritten on every
change: the current raw values as a table and every change with its time.
Not log lines, because HA's log viewer groups warnings by the line of code
that logged them, so a run of snapshot and change lines collapsed into one
entry showing only the last. Each change is still logged at DEBUG, and the
start and the end at WARNING, all under ``[area parameters]``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Protocol

from deebot_client.command import Command
from deebot_client.device import Device
from homeassistant.components import persistent_notification
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .deebot_patch.areas import MowerArea, MowerAreaEvent
from .deebot_patch.commands import GetAreaParameter, GetAreaSet
from .deebot_patch.state_precedence import map_id_for

_LOGGER = logging.getLogger(__name__)

LOG_WINDOW = timedelta(minutes=15)

# Enough for stepping four settings through their ranges; past it the oldest
# changes give way so the notification stays readable.
MAX_CHANGES = 50

_TAG = "[area parameters]"

# The raw fields, in the order they are shown.
_FIELDS = ("mow_height_level", "cut_mode", "obstacle_height", "angle")

type Execute = Callable[[Command], Awaitable[bool]]


class DebugLog(Protocol):
    """What a debug button needs from the log it starts."""

    async def async_start(self) -> None:
        """Start, or restart, logging."""

    @callback
    def async_stop(self) -> None:
        """Stop logging, silently. Called when the button is removed."""


class AreaParameterLog:
    """Record one mower's raw area parameters, and every change, for a while."""

    def __init__(self, hass: HomeAssistant, device: Device, execute: Execute) -> None:
        """Keep what a press needs; nothing is subscribed until then."""
        self._hass = hass
        self._device = device
        self._execute = execute
        info = device.device_info
        self._label = f"{info.get('nick') or info['class']} ({info['class']})"
        self._notification_id = f"{DOMAIN}_area_parameters_{info['did']}"
        self._areas: dict[str, MowerArea] | None = None
        self._changes: list[str] = []
        self._notes: list[str] = []
        self._until: datetime | None = None
        self._unsub_event: CALLBACK_TYPE | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        """Show the current values now, then every change until the window closes.

        A second press starts over: a fresh table and an empty change list. The
        subscription is renewed because the bus hands a new subscriber its last
        event, which is the current table when nothing has changed since.
        """
        self.async_stop()
        self._areas = None
        self._changes = []
        self._notes = []
        self._until = dt_util.now() + LOG_WINDOW
        self._unsub_timer = async_call_later(self._hass, LOG_WINDOW, self._on_window_end)
        _LOGGER.warning(
            "%s %s: started; see the notification for the values", _TAG, self._label
        )
        self._publish()
        # Subscribed before asking, so the answer cannot arrive unheard.
        self._unsub_event = self._device.events.subscribe(MowerAreaEvent, self._on_areas)

        if not await self._execute(GetAreaParameter()):
            self._note(
                "The mower did not answer getAreaParameter. This model may not "
                "support area parameters."
            )
        # Asked explicitly rather than left to GetAreaSet, which sends nothing
        # without a map id, so the notification can say why names are missing.
        if (map_id := map_id_for(self._device.events)) is None:
            self._note(
                "Area names are unknown until the mower names its map; the areas "
                "are shown by id."
            )
        else:
            await self._execute(GetAreaSet(map_id))

    @callback
    def async_stop(self) -> None:
        """Stop following changes, silently; the notification stays."""
        for unsub in (self._unsub_event, self._unsub_timer):
            if unsub is not None:
                unsub()
        self._unsub_event = self._unsub_timer = None

    @callback
    def _on_window_end(self, _now: datetime) -> None:
        # async_call_later has fired and removed itself; only the event is left.
        self._unsub_timer = None
        self.async_stop()
        self._until = None
        self._publish()
        _LOGGER.warning("%s %s: stopped", _TAG, self._label)

    async def _on_areas(self, event: MowerAreaEvent) -> None:
        """Take the first report as the table, record what changes after it."""
        areas = {area.area_id: area for area in event.areas}
        previous, self._areas = self._areas, areas
        if previous is not None:
            time = dt_util.now().strftime("%H:%M:%S")
            for area_id in sorted(areas.keys() | previous.keys(), key=_area_order):
                before, after = previous.get(area_id), areas.get(area_id)
                if after is None:
                    self._change(f"{time} {_name(before)}: no longer reported")
                elif before is None:
                    self._change(f"{time} {_name(after)}: new, {_values(after)}")
                else:
                    for field in _FIELDS:
                        old, new = getattr(before, field), getattr(after, field)
                        if old != new:
                            self._change(
                                f"{time} {_name(after)}: {field} {_raw(old)} → {_raw(new)}"
                            )
        self._publish()

    def _change(self, line: str) -> None:
        _LOGGER.debug("%s %s: %s", _TAG, self._label, line)
        self._changes.append(line)
        del self._changes[:-MAX_CHANGES]

    def _note(self, line: str) -> None:
        _LOGGER.debug("%s %s: %s", _TAG, self._label, line)
        self._notes.append(line)
        self._publish()

    @callback
    def _publish(self) -> None:
        """Rewrite the notification from the current state."""
        persistent_notification.async_create(
            self._hass,
            self._message(),
            title=f"Area parameters: {self._label}",
            notification_id=self._notification_id,
        )

    def _message(self) -> str:
        lines = [
            f"Following changes until {self._until:%H:%M}. Change the settings "
            "in the Ecovacs app; this updates as the mower reports each one."
            if self._until is not None
            else "Stopped. Press **Log area parameters** again to start over.",
            "",
        ]
        if self._areas is None:
            lines.append("Waiting for the mower to report its areas.")
        elif not self._areas:
            lines.append("The mower reported no areas.")
        else:
            lines.append("| Area | " + " | ".join(_FIELDS) + " |")
            lines.append("|---" * (len(_FIELDS) + 1) + "|")
            for area_id in sorted(self._areas, key=_area_order):
                area = self._areas[area_id]
                cells = (_raw(getattr(area, field)) for field in _FIELDS)
                lines.append(f"| {_name(area)} | " + " | ".join(cells) + " |")
        if self._changes:
            lines += ["", "**Changes**", *(f"- {line}" for line in self._changes)]
        if self._notes:
            lines += ["", *(f"_{note}_" for note in self._notes)]
        lines += [
            "",
            "Copy this into an issue, together with the values you set in the app.",
        ]
        return "\n".join(lines)


def _area_order(area_id: str) -> tuple[int, str]:
    """Numeric ids in numeric order, anything else after them."""
    return (0, f"{int(area_id):09d}") if area_id.isdecimal() else (1, area_id)


def _name(area: MowerArea) -> str:
    return f"Area {area.area_id}" + (f" ({area.name})" if area.name else "")


def _values(area: MowerArea) -> str:
    return ", ".join(f"{field}={_raw(getattr(area, field))}" for field in _FIELDS)


def _raw(value: int | None) -> str:
    # None is a field the mower has not reported yet, not a value of zero.
    return "?" if value is None else str(value)
