"""Debug logs a user can start from a button, for reporting what a mower sends.

Supporting another model's area parameters needs a table of what each raw
value means: set a value in the Ecovacs app, see which raw number the mower
reports for it. Every model has its own ranges, so there is no fixed list of
steps to ask for, only a record of what changed while the owner tries.

``AreaParameterLog`` keeps that record. Started from the mower's "Log area
parameters" button, it reads the areas once, then follows every change for
``LOG_WINDOW``. Read-only on every class: nothing here writes to the mower, so
it is safe on a model whose values nobody has mapped yet. Changes made in the
app arrive in two ways. The mower pushes ``onAreaParameter`` to every client,
and that push is handled for every patched mower, flag or no flag; but it has
only been seen on the A1600 LiDAR Pro, and this is for models nobody has
looked at. So the areas are also asked for again every ``POLL_INTERVAL`` while
the window is open. On a mower that pushes, a poll answer that repeats the
last report is dropped by the bus and costs nothing more than the request.

Some models also have mowing settings for the whole mower — the app's Auto
mode speed, height and obstacle height, the cutting direction, the edge mode
— which no area table shows. Mapping those needs two things: the payload the
app writes, which a future ``Set…`` command must send, and the raw values it
writes and reads while the owner steps through them. So while the window is
open, the app's requests for the commands in ``MOWER_SETTINGS`` and the
mower's answers are followed too, from the ``MowerAppTrafficEvent`` the patch
layer publishes during a ``capture()``. Only requests that carry a channel
(``Android``, ``iOS``) count: those are the app's, not this integration's
own. Nothing is asked for: the read commands of these settings are not known
on every model, and the app reads them itself when its screens open.

The record is a persistent notification, one per mower, rewritten on every
change: the current raw values as tables, per area and for the whole mower,
and every change with its time.
Not log lines, because HA's log viewer groups warnings by the line of code
that logged them, so a run of snapshot and change lines collapsed into one
entry showing only the last. Each change is still logged at DEBUG, and the
start and the end at WARNING, all under ``[area parameters]``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from deebot_client.command import Command
from deebot_client.device import Device
from homeassistant.components import persistent_notification
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .deebot_patch.app_traffic import MowerAppTrafficEvent, capture
from .deebot_patch.areas import AREA_PARAMETER_KEYS, MowerArea, MowerAreaEvent
from .deebot_patch.commands import GetAreaParameter, GetAreaSet
from .deebot_patch.state_precedence import map_id_for

_LOGGER = logging.getLogger(__name__)

LOG_WINDOW = timedelta(minutes=15)
POLL_INTERVAL = timedelta(seconds=15)

# Enough for stepping every setting through its range; past it the oldest
# changes give way so the notification stays readable.
MAX_CHANGES = 50

# The mowing settings for the whole mower, by the name their get and set
# commands share (getCutHeight, setCutHeight), with the label shown. Explicit,
# like AREA_PARAMETER_KEYS: a command not listed is not shown. Each is either
# a raw value a model maps in its own way, or a toggle needed to read those:
# CustomCutMode is whether the Auto or the per-area values apply.
MOWER_SETTINGS = {
    "CutEfficiency": "Auto speed",
    "CutHeight": "Auto height",
    "ObstacleHeight": "Auto obstacle height",
    "CutDirection": "Cutting direction",
    "AutoCutDirection": "Weekly direction change",
    "BorderSwitch": "Edge mode",
    "CustomCutMode": "Auto or Area mode",
}

# Per-area values come from the area table; only the app's write is kept, as
# the payload a write from Home Assistant must match.
_PER_AREA = "AreaParameter"

_TAG = "[area parameters]"

type Execute = Callable[[Command], Awaitable[bool]]


class DebugLog(Protocol):
    """What a debug button needs from the log it starts."""

    async def async_start(self) -> None:
        """Start, or restart, logging."""

    @callback
    def async_shutdown(self) -> None:
        """Stop logging for good. Called when the button is removed."""


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
        self._settings: dict[str, _Setting] = {}
        self._started: datetime | None = None
        self._until: datetime | None = None
        self._unsub_event: CALLBACK_TYPE | None = None
        self._unsub_traffic: CALLBACK_TYPE | None = None
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_poll: CALLBACK_TYPE | None = None
        self._stop_capture: Callable[[], None] | None = None

    async def async_start(self) -> None:
        """Show the current values now, then every change until the window closes.

        A second press starts over: a fresh table and an empty change list. The
        subscription is renewed because the bus hands a new subscriber its last
        event, which is the current table when nothing has changed since.
        """
        self._async_stop()
        self._areas = None
        self._changes = []
        self._notes = []
        self._settings = {}
        self._started = dt_util.utcnow()
        self._until = dt_util.now() + LOG_WINDOW
        self._unsub_timer = async_call_later(self._hass, LOG_WINDOW, self._on_window_end)
        _LOGGER.warning(
            "%s %s: started; see the notification for the values", _TAG, self._label
        )
        self._publish()
        # Subscribed before asking, so the answer cannot arrive unheard.
        self._unsub_event = self._device.events.subscribe(MowerAreaEvent, self._on_areas)
        self._unsub_traffic = self._device.events.subscribe(
            MowerAppTrafficEvent, self._on_traffic
        )
        self._stop_capture = capture()
        self._unsub_poll = async_track_time_interval(
            self._hass, self._poll, POLL_INTERVAL
        )

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
    def async_shutdown(self) -> None:
        """Stop for good, and say so if a window was open.

        Called when the button is removed: an integration reload, HA stopping,
        the entity disabled. Without the rewrite the notification would keep
        saying it is following changes.
        """
        if self._until is not None:
            self._end("stopped early")

    @callback
    def _async_stop(self) -> None:
        """Stop following changes, silently; the notification stays."""
        for unsub in (
            self._unsub_event,
            self._unsub_traffic,
            self._unsub_timer,
            self._unsub_poll,
            self._stop_capture,
        ):
            if unsub is not None:
                unsub()
        self._unsub_event = self._unsub_traffic = None
        self._unsub_timer = self._unsub_poll = self._stop_capture = None

    @callback
    def _on_window_end(self, _now: datetime) -> None:
        # async_call_later has fired and removed itself; the rest is left.
        self._unsub_timer = None
        self._end("stopped")

    @callback
    def _end(self, how: str) -> None:
        self._async_stop()
        self._until = None
        self._publish()
        _LOGGER.warning("%s %s: %s", _TAG, self._label, how)

    async def _poll(self, _now: datetime) -> None:
        """Ask again, for a mower that does not push its changes."""
        # A failure here is not noted: the first answer already said whether
        # the mower answers at all, and one lost poll is made up by the next.
        await self._execute(GetAreaParameter())

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
                    for key in AREA_PARAMETER_KEYS:
                        old, new = before.parameters.get(key), after.parameters.get(key)
                        if old != new:
                            self._change(
                                f"{time} {_name(after)}: {key} {_raw(old)} → {_raw(new)}"
                            )
        self._publish()

    async def _on_traffic(self, event: MowerAppTrafficEvent) -> None:
        """Follow the app's reads and writes of the settings for the whole mower."""
        # The bus hands a new subscriber its last event, which can be an
        # exchange from before this press. No channel: not the app's.
        if self._started is None or event.at < self._started or not event.channel:
            return
        time = dt_util.as_local(event.at).strftime("%H:%M:%S")
        changed = False
        for command, request, data, code in _parts(event):
            verb, name = command[:3], command[3:]
            if name != _PER_AREA and name not in MOWER_SETTINGS:
                continue
            setting = self._settings.setdefault(name, _Setting())
            label = f"{MOWER_SETTINGS.get(name, 'Per area')} ({name})"
            if verb == "set":
                if code not in (None, 0):
                    self._change(
                        f"{time} {label}: `{command} {request}` refused (code {code})"
                    )
                    changed = True
                    continue
                setting.last_write = f"{command} {request}"
                written = _object(request)
                if name != _PER_AREA and written is not None:
                    self._follow(setting, written, f"{time} {label}", wrote=True)
                changed = True
            elif verb == "get" and name != _PER_AREA and code in (None, 0):
                if isinstance(data, dict):
                    setting.read_with = command
                    self._follow(setting, data, f"{time} {label}", wrote=False)
                    changed = True
        if changed:
            self._publish()

    def _follow(
        self, setting: _Setting, value: dict[str, Any], prefix: str, *, wrote: bool
    ) -> None:
        """Take a setting's new raw value; list what changed against the last.

        The first read only fills the table: there is nothing to compare it
        with. A first write is a change from unknown, since the app made it.
        """
        before = setting.value
        setting.value = {**(before or {}), **value}
        if before is None and not wrote:
            return
        for key, new in value.items():
            old = (before or {}).get(key)
            if old != new or before is None:
                self._change(f"{prefix}: {key} {_shown(old)} → {_shown(new)}")

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
            # Every known key, also one this model may not have: a column of
            # "?" is itself what an owner of an unmapped model can report.
            lines.append("| Area | " + " | ".join(AREA_PARAMETER_KEYS) + " |")
            lines.append("|---" * (len(AREA_PARAMETER_KEYS) + 1) + "|")
            for area_id in sorted(self._areas, key=_area_order):
                area = self._areas[area_id]
                cells = (_raw(area.parameters.get(key)) for key in AREA_PARAMETER_KEYS)
                lines.append(f"| {_name(area)} | " + " | ".join(cells) + " |")
        if self._settings:
            lines += [
                "",
                "**Whole-mower settings** (as the app read or wrote them)",
                "",
                "| Setting | Current value | Read with | Last write |",
                "|---|---|---|---|",
            ]
            for name in [*MOWER_SETTINGS, _PER_AREA]:
                if (setting := self._settings.get(name)) is None:
                    continue
                label = f"{MOWER_SETTINGS.get(name, 'Per area')} ({name})"
                value = (
                    "see the table above"
                    if name == _PER_AREA
                    else _code(_json(setting.value) if setting.value else None)
                )
                lines.append(
                    f"| {label} | {value} | {_code(setting.read_with)} "
                    f"| {_code(setting.last_write)} |"
                )
        if self._changes:
            lines += ["", "**Changes**", *(f"- {line}" for line in self._changes)]
        if self._notes:
            lines += ["", *(f"_{note}_" for note in self._notes)]
        lines += [
            "",
            "Copy this into an issue, together with the values you set in the app.",
        ]
        return "\n".join(lines)


@dataclass
class _Setting:
    """What the app showed of one setting for the whole mower."""

    value: dict[str, Any] | None = None
    read_with: str | None = None
    last_write: str | None = None


def _parts(
    event: MowerAppTrafficEvent,
) -> list[tuple[str, str, Any, int | None]]:
    """An exchange as (command, request, answer data, code) per command in it.

    ``getInfo`` asks for several settings at once: its request is the list of
    commands, its answer one ``{data, code}`` per command.
    """
    if event.command != "getInfo":
        return [(event.command, event.request, _parsed(event.response), event.code)]
    names, answers = _parsed(event.request), _parsed(event.response)
    if not isinstance(names, list) or not isinstance(answers, dict):
        return []
    parts = []
    for name in names:
        answer = answers.get(name)
        if isinstance(name, str) and isinstance(answer, dict):
            code = answer.get("code")
            code = code if isinstance(code, int) else None
            parts.append((name, "{}", answer.get("data"), code))
    return parts


def _parsed(text: str | None) -> Any:
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _object(text: str) -> dict[str, Any] | None:
    value = _parsed(text)
    return value if isinstance(value, dict) else None


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _shown(value: Any) -> str:
    # None is a value nobody has seen yet, not a value of null.
    return "?" if value is None else _json(value)


def _code(text: str | None) -> str:
    return f"`{text}`" if text else "—"


def _area_order(area_id: str) -> tuple[int, str]:
    """Numeric ids in numeric order, anything else after them."""
    return (0, f"{int(area_id):09d}") if area_id.isdecimal() else (1, area_id)


def _name(area: MowerArea) -> str:
    return f"Area {area.area_id}" + (f" ({area.name})" if area.name else "")


def _values(area: MowerArea) -> str:
    return ", ".join(
        f"{key}={_raw(area.parameters.get(key))}" for key in AREA_PARAMETER_KEYS
    )


def _raw(value: int | None) -> str:
    # None is a key the mower has not reported, not a value of zero.
    return "?" if value is None else str(value)
