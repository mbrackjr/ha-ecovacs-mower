# Border Mowing and End Task Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two buttons on the mower's device page: one starts a border job (issue #12), one ends the current task (issue #51).

**Architecture:** A `MowBorder` command in the patch layer on the same family-adaptive machinery as `MowArea`, sharing a payload builder with it. The map id the border request needs is learned from the map messages' envelopes inside the handlers this integration owns and held on the per-device `MowerStateRecord`. One new button description type with a `command_fn` carries both buttons; the end-task one sends `CleanMower(CleanAction.STOP)`, which the library already shapes correctly.

**Tech Stack:** Python 3.14, Home Assistant custom integration, `deebot-client` (pinned in `manifest.json`), pytest.

**Spec:** `docs/superpowers/specs/2026-09-09-border-mowing-design.md`

## Global Constraints

- All outward-facing text is English: docstrings, comments, commit messages. Comments explain *why*.
- Conventional commits with the issue number: `feat: … #12`, `test: … #51`. No AI attribution of any kind in commit messages.
- `strings.json` and `translations/en.json` must be byte-identical (`tests/test_translations.py` guards it). Never create `sv.json`.
- Every translation key and `icons.json` key must belong to a real entity; the button tests check both directions.
- `deebot_patch/` is the only package allowed to touch private parts of `deebot_client`.
- **Interpreter.** Always `.venv/Scripts/python.exe` (CPython 3.14.7 with Home Assistant 2026.7.4, deebot-client 18.5.1, pytest 9.1.1). The bare `python` on this machine is 3.12 without `deebot_client`, and every RED step would fail with `ModuleNotFoundError: deebot_client` instead of the failure the step expects.
- **Protocol tests** (`tests/deebot_patch/`): `.venv/Scripts/python.exe -m pytest tests/deebot_patch/ -p no:homeassistant -v`.
- **Platform tests** (`tests/*.py`, marked `requires_ha`) also run locally, through a five-line plugin that defeats the blanket win32 skip before `tests/__init__.py` is imported. It lives at `C:/Users/RICKAR~1/AppData/Local/Temp/claude/D--private-projects-ha-ecovacs-mower/a85fa24e-d58f-4ed5-ab9b-7ba696ce0340/scratchpad/unskip_win32.py`; if that file is missing, create it with exactly this content:

  ```python
  """Defeat the blanket win32 skipif in tests/__init__.py before it is imported."""
  import pytest


  def pytest_configure(config):
      import tests
      tests.requires_ha = pytest.mark.skipif(False, reason="")
  ```

  Then run, from the repo root in the Bash tool:

  ```bash
  PYTHONPATH="C:/Users/RICKAR~1/AppData/Local/Temp/claude/D--private-projects-ha-ecovacs-mower/a85fa24e-d58f-4ed5-ab9b-7ba696ce0340/scratchpad" .venv/Scripts/python.exe -m pytest tests/test_button.py -p no:homeassistant -p unskip_win32 -v
  ```

  Only the thirteen tests that need the `hass` fixture stay CI's job; none of the tests in this plan do. Never install `pytest-homeassistant-custom-component` into the venv — it auto-loads and crashes collection. CI (`.github/workflows/test.yml`) remains the source of truth for the whole suite; a local green is evidence, not the verdict.
- Line endings: `.gitattributes` normalises to CRLF; write files normally.
- Work on branch `feat/12-border-mowing` (already exists, holds the spec).

---

### Task 1: Shared task-start payload builder

`zonal.py`'s `_ZoneClean` builds `{"act": "start", "content": {"type": "spotArea", "value": …}}`. The border command needs the same shape with `type: border`. Extract the builder to `commands.py` so the second task type does not copy the first.

**Files:**
- Modify: `custom_components/ecovacs_mower/deebot_patch/commands.py` (add `_TaskClean` directly below `_NoActionRewrite`)
- Modify: `custom_components/ecovacs_mower/deebot_patch/zonal.py:32-44`
- Test: `tests/deebot_patch/test_zonal.py`

**Interfaces:**
- Produces: `class _TaskClean(_NoActionRewrite)` with `__init__(self, task: str, value: str)`; `_get_args(action)` returns `{"act": action.value, "content": {"type": task, "value": value}}`. Subclasses mix in `Clean` or `CleanV2` to pick the topic.

- [ ] **Step 1: Write the failing test**

Append to `tests/deebot_patch/test_zonal.py`:

```python
def test_zone_delegates_are_built_on_the_shared_task_builder() -> None:
    # The border command (issue #12) sends the same nested shape with another
    # type string; one builder keeps the two from drifting apart.
    from custom_components.ecovacs_mower.deebot_patch.commands import (
        _NoActionRewrite,
        _TaskClean,
    )

    assert issubclass(_ZoneCleanNonV2, _TaskClean)
    assert issubclass(_ZoneCleanV2, _TaskClean)
    # The builder must still bypass Clean._execute's start/resume rewrite: the
    # bypass only works when _NoActionRewrite comes before Clean in the MRO.
    for delegate, topic_base in ((_ZoneCleanNonV2, Clean), (_ZoneCleanV2, CleanV2)):
        mro = delegate.__mro__
        assert mro.index(_NoActionRewrite) < mro.index(topic_base)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_zonal.py -p no:homeassistant -v`
Expected: `ImportError: cannot import name '_TaskClean'`

- [ ] **Step 3: Add the builder to `commands.py`**

Directly after the `_NoActionRewrite` class (before `_CleanNonV2`):

```python
class _TaskClean(_NoActionRewrite):
    """A ``start`` for one named task type, on whichever topic the subclass adds.

    ``spotArea`` (issue #11) and ``border`` (issue #12) share the shape
    ``{"act": "start", "content": {"type": <task>, "value": <argument>}}``
    and differ only in the two strings. One builder keeps them identical the
    day the firmware wants a third field, and keeps the action-rewrite bypass
    in one place. Not sendable on its own: a concrete subclass mixes in
    ``Clean`` or ``CleanV2`` to supply ``NAME`` and the topic.
    """

    def __init__(self, task: str, value: str) -> None:
        self._task = task
        self._value = value
        super().__init__(CleanAction.START)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        return {
            "act": action.value,
            "content": {"type": self._task, "value": self._value},
        }
```

- [ ] **Step 4: Make `zonal.py` use it**

Replace the `_ZoneClean` class (lines 32-44) with:

```python
class _ZoneClean(_TaskClean):
    """The spot-area payload, before a topic is chosen."""

    def __init__(self, area: list[int | float]) -> None:
        super().__init__(_TYPE_SPOT_AREA, ",".join(str(value) for value in area))
```

and change the import line `from .commands import _AdaptiveFamily, _NoActionRewrite` to `from .commands import _AdaptiveFamily, _TaskClean`. `_ZoneCleanNonV2` and `_ZoneCleanV2` are unchanged.

- [ ] **Step 5: Run the protocol tests**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/ -p no:homeassistant -v`
Expected: all pass, including the existing `test_spot_area_payload_uses_saved_area_ids` and `test_v2_spot_area_payload_has_the_same_nested_shape` (the payload is unchanged) and the new MRO assertion (the rewrite bypass survived the move). `test_contract.py`'s `test_clean_still_rewrites_the_action_and_our_delegates_still_skip_it` pins the other half — that `Clean` still has a rewrite to bypass — and is unaffected.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ecovacs_mower/deebot_patch/commands.py custom_components/ecovacs_mower/deebot_patch/zonal.py tests/deebot_patch/test_zonal.py
git commit -m "refactor: share the task-start payload builder between task types #12"
```

---

### Task 2: Hold the map id on the per-device record

**Files:**
- Modify: `custom_components/ecovacs_mower/deebot_patch/state_precedence.py`
- Test: `tests/deebot_patch/test_state_precedence.py`

**Interfaces:**
- Produces: `MowerStateRecord.map_id: str | None` (default `None`); `MowerStateRecord.note_map(mid: object, using: object = None) -> None`; module function `map_id_for(event_bus: EventBus) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/deebot_patch/test_state_precedence.py`:

```python
def test_a_new_record_knows_no_map() -> None:
    assert MowerStateRecord().map_id is None


def test_note_map_keeps_a_real_map_id_and_follows_a_change() -> None:
    record = MowerStateRecord()
    record.note_map("2049987783")
    assert record.map_id == "2049987783"
    # Last writer wins: a map switched in the app is the map the next border
    # job should run on.
    record.note_map("1")
    assert record.map_id == "1"


def test_note_map_ignores_everything_that_is_not_a_map() -> None:
    # "0" is the library's own "no map" marker (OnCachedMapInfo) and what the
    # onMapTrack envelopes of an idle mower carry; an empty string and a
    # missing field say nothing either.
    record = MowerStateRecord()
    record.note_map("7")
    for junk in (None, "", "0", 0, 12, ["1"]):
        record.note_map(junk)
    assert record.map_id == "7"


def test_note_map_skips_a_map_the_mower_is_not_using() -> None:
    # A getMapInfo_V2 answer can carry fragments for a stored map that is not
    # the active one; last-writer-wins would then name the wrong map. The
    # envelope says which is which with "using", so an explicit 0 is skipped.
    record = MowerStateRecord()
    record.note_map("7", using=1)
    record.note_map("8", using=0)
    assert record.map_id == "7"
    record.note_map("9", using="0")
    assert record.map_id == "7"


def test_note_map_accepts_an_envelope_without_using() -> None:
    # onMapTrack and onMapTrace never carry the field; absence is not "not
    # using", it is "the message does not say", and the id is still good.
    record = MowerStateRecord()
    record.note_map("7", using=None)
    assert record.map_id == "7"
    record.note_map("8")
    assert record.map_id == "8"


def test_moving_does_not_forget_the_map() -> None:
    # Leaving the dock does not change the map, unlike the suppressed state.
    record = MowerStateRecord()
    record.note_map("7")
    record.dock()
    record.move()
    assert record.map_id == "7"


def test_map_id_for_reads_the_record_and_is_none_for_strangers() -> None:
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
    )

    bus = _bus()
    assert map_id_for(bus) is None  # unregistered: an ordinary vacuum
    register(bus)
    assert map_id_for(bus) is None  # registered, nothing reported yet
    record_for(bus).note_map("7")
    assert map_id_for(bus) == "7"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_state_precedence.py -p no:homeassistant -v`
Expected: `AttributeError: 'MowerStateRecord' object has no attribute 'map_id'` and `ImportError` for `map_id_for`.

- [ ] **Step 3: Implement**

In `state_precedence.py`, change the module docstring's first paragraph to:

```python
"""Per-device facts the handlers learn from the stream.

Two of them. The mower reports charging and a paused plan as two orthogonal
facts, and ``capabilities.state`` collapses them into a single ``StateEvent``;
this module holds the little state needed to prefer the first over the second
(issue #67). It also remembers the id of the map the mower is using, read from
the envelope of every map message, because a border job has to name it
(issue #12). Plus the registry that says which event buses belong to a patched
mower at all.
```

(keep the two existing paragraphs about keying by `EventBus` and the no-back-reference rule as they are.)

In `MowerStateRecord`, add the field and method:

```python
    docked: bool = False
    suppressed: State | None = None
    map_id: str | None = None

    def note_map(self, mid: object, using: object = None) -> None:
        """Remember the map the mower reports, from any map message's envelope.

        ``"0"`` is not a map: it is what the library's own ``OnCachedMapInfo``
        skips as "no map", and what an idle mower's ``onMapTrack`` envelopes
        carry. Anything that is not a non-empty string is ignored too, so a
        malformed envelope cannot erase an id a good one taught.

        ``using`` is the envelope's own word on whether this is the active
        map. ``onMI``, ``onArI``, ``onSpecialContour`` and ``onMapInfo_V2``
        carry it; ``onMapTrack`` and ``onMapTrace`` do not. An explicit ``0``
        (or ``"0"``) is a stored map the mower is not on, and a border job
        must not name it — the answer to ``getMapInfo_V2`` may carry such a
        map alongside the active one. An absent field says nothing and the
        id is taken as is.
        """
        if not isinstance(mid, str) or mid in ("", "0"):
            return
        if using in (0, "0"):
            return
        self.map_id = mid
```

`move()` is untouched: it must not clear `map_id`.

After `record_for`, add:

```python
def map_id_for(event_bus: EventBus) -> str | None:
    """The id of the map *event_bus*'s mower reports, or ``None`` if unknown.

    ``None`` both for an unregistered bus and for a registered one whose mower
    has not sent a map message yet; the caller cannot tell them apart and does
    not need to — neither can run a border job.
    """
    record = record_for(event_bus)
    return None if record is None else record.map_id
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_state_precedence.py -p no:homeassistant -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ecovacs_mower/deebot_patch/state_precedence.py tests/deebot_patch/test_state_precedence.py
git commit -m "feat: remember the map id the mower reports #12"
```

---

### Task 3: Record the map id from every map message

**Files:**
- Modify: `custom_components/ecovacs_mower/deebot_patch/map_messages.py:107-137` (`_MapMessage._handle_body_data_dict`) and its imports
- Test: `tests/deebot_patch/test_map_messages.py`

**Interfaces:**
- Consumes: `record_for`, `MowerStateRecord.note_map` from Task 2.

- [ ] **Step 1: Write the failing tests**

Append to `tests/deebot_patch/test_map_messages.py`:

```python
def test_the_first_fragment_of_a_map_message_teaches_the_map_id() -> None:
    # Written by the handler, not learned from an event: the bus drops repeated
    # events before subscribers run, and the id has to be known before the
    # blob is even complete — a border job cannot wait for a full outline.
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
        register,
    )

    event_bus = Mock()
    register(event_bus)
    fragments = sorted(
        FIXTURES["on_map_info_v2_g1800"],
        key=lambda i: int(i["payload"]["body"]["data"]["index"]),
    )
    OnMapInfo.handle(event_bus, deepcopy(fragments[0]["payload"]))

    assert map_id_for(event_bus) == "123456789"


def test_a_map_id_of_zero_teaches_nothing() -> None:
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
        register,
    )

    event_bus = Mock()
    register(event_bus)
    for item in FIXTURES["on_map_track_multipart"]:
        OnMapTrack.handle(event_bus, deepcopy(item["payload"]))

    assert map_id_for(event_bus) is None


def test_a_fragment_for_a_map_not_in_use_teaches_nothing() -> None:
    # The envelope's own "using" flag, passed through to the record: a stored
    # but inactive map in a getMapInfo_V2 answer must not become the border
    # job's target. Constructed, not captured — no fixture has using 0.
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
        register,
    )

    event_bus = Mock()
    register(event_bus)
    fragment = deepcopy(FIXTURES["on_map_info_v2_g1800"][0]["payload"])
    fragment["body"]["data"]["mid"] = "987654321"
    fragment["body"]["data"]["using"] = 0
    OnMapInfo.handle(event_bus, fragment)

    assert map_id_for(event_bus) is None


def test_an_undecodable_blob_still_teaches_the_map_id() -> None:
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
        register,
    )

    event_bus = Mock()
    register(event_bus)
    payload = deepcopy(FIXTURES["on_mi_full"][0]["payload"])
    payload["body"]["data"]["info"] = "not base64 at all!!"
    OnMI.handle(event_bus, payload)  # must not raise

    assert map_id_for(event_bus) == "1"


def test_an_unregistered_bus_records_no_map_id() -> None:
    # A Deebot vacuum on the same account reaches these handlers too; it must
    # not get a record made for it as a side effect.
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import (
        map_id_for,
        record_for,
    )

    event_bus = Mock()
    OnMI.handle(event_bus, deepcopy(FIXTURES["on_mi_full"][0]["payload"]))

    assert record_for(event_bus) is None
    assert map_id_for(event_bus) is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_map_messages.py -p no:homeassistant -v -k map_id`
Expected: `test_the_first_fragment_of_a_map_message_teaches_the_map_id` and `test_an_undecodable_blob_still_teaches_the_map_id` fail with `assert None == "123456789"` / `assert None == "1"`; the other three already pass (nothing is recorded yet) — that is fine, they pin the behaviour that must survive Step 3.

- [ ] **Step 3: Implement**

In `map_messages.py`, add to the imports (after `from .geometry import (...)`):

```python
from .state_precedence import record_for
```

In `_MapMessage._handle_body_data_dict`, insert before `info = data.get("info")`:

```python
        # Every map message names the map in its envelope, and a border job
        # has to name it back (issue #12). Recorded here, ahead of the fragment
        # buffering, so the first fragment teaches it and a blob that never
        # completes or never decodes still does. "using" goes along so a
        # stored-but-inactive map is not mistaken for the current one. Only
        # for a registered bus: an ordinary vacuum on the same account reaches
        # this handler too.
        if (record := record_for(event_bus)) is not None:
            record.note_map(data.get("mid"), data.get("using"))
```

- [ ] **Step 4: Run the protocol tests**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/ -p no:homeassistant -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ecovacs_mower/deebot_patch/map_messages.py tests/deebot_patch/test_map_messages.py
git commit -m "feat: learn the map id from the map messages' envelopes #12"
```

---

### Task 4: The `MowBorder` command

**Files:**
- Create: `custom_components/ecovacs_mower/deebot_patch/border.py`
- Test: `tests/deebot_patch/test_border.py`

**Interfaces:**
- Consumes: `_AdaptiveFamily`, `_TaskClean` from `commands.py`; `Family` from `families.py`.
- Produces: `class MowBorder(_AdaptiveFamily, Clean)` with `__init__(self, map_id: str)`; raises `ValueError` for `""` or `"0"`. Private delegates `_BorderCleanNonV2`, `_BorderCleanV2`.

- [ ] **Step 1: Write the failing tests**

Create `tests/deebot_patch/test_border.py`:

```python
"""Tests for the GOAT border-mowing command (issue #12)."""

from unittest.mock import AsyncMock, patch

import pytest
from deebot_client.command import Command
from deebot_client.commands.json.clean import Clean, CleanV2

from custom_components.ecovacs_mower.deebot_patch.border import (
    MowBorder,
    _BorderCleanNonV2,
    _BorderCleanV2,
)
from custom_components.ecovacs_mower.deebot_patch.families import Family, selected

from .test_commands import _DEVICE_INFO, _NO_ANSWER, _OK, _transport

# The request the Ecovacs app sent on a GOAT G1-800 (77atlz, fw 1.36.208),
# captured on issue #12. The map id is the one from that capture.
_CAPTURED_MAP_ID = "2049987783"
_CAPTURED_ARGS = {
    "act": "start",
    "content": {"type": "border", "value": "mid:2049987783"},
}


def test_border_delegates_are_clean_commands() -> None:
    assert issubclass(_BorderCleanNonV2, Clean)
    assert issubclass(_BorderCleanV2, CleanV2)


def test_v2_border_payload_is_the_captured_request() -> None:
    command = _BorderCleanV2(_CAPTURED_MAP_ID)
    assert command.NAME == "clean_V2"
    assert command._args == _CAPTURED_ARGS


def test_non_v2_border_payload_has_the_same_nested_shape() -> None:
    # Unconfirmed on the wire: no non-V2 mower has been captured sending a
    # border job. This is the shape spotArea uses on the non-V2 family, and
    # the class gate keeps it off that hardware until someone confirms it.
    command = _BorderCleanNonV2(_CAPTURED_MAP_ID)
    assert command.NAME == "clean"
    assert command._args == _CAPTURED_ARGS


def test_border_delegates_bypass_the_action_rewrite() -> None:
    # Clean._execute would turn this start into a resume while the mower reads
    # paused; the bypass only holds with _NoActionRewrite ahead of Clean.
    from custom_components.ecovacs_mower.deebot_patch.commands import _NoActionRewrite

    for delegate, topic_base in ((_BorderCleanNonV2, Clean), (_BorderCleanV2, CleanV2)):
        mro = delegate.__mro__
        assert mro.index(_NoActionRewrite) < mro.index(topic_base)


@pytest.mark.parametrize("map_id", ["", "0"])
def test_mow_border_refuses_a_map_id_that_is_not_a_map(map_id: str) -> None:
    with pytest.raises(ValueError, match="map"):
        MowBorder(map_id)


def test_mow_border_equality_includes_the_map_id() -> None:
    assert MowBorder("1") == MowBorder("1")
    assert MowBorder("1") != MowBorder("2")


def test_mow_border_keeps_clean_contract() -> None:
    assert issubclass(MowBorder, Clean)
    assert MowBorder.NAME == "clean"


async def test_mow_border_executes_first_on_non_v2() -> None:
    fake, sent = _transport(_OK)
    command = MowBorder(_CAPTURED_MAP_ID)

    with patch.object(Command, "_execute", fake):
        await command._execute(AsyncMock(), _DEVICE_INFO, AsyncMock())

    assert sent == ["clean"]
    assert command._delegate(Family.NON_V2)._args == _CAPTURED_ARGS
    assert selected(_DEVICE_INFO["did"]) is Family.NON_V2


async def test_mow_border_falls_back_to_v2_and_commits_family() -> None:
    fake, sent = _transport(_NO_ANSWER, _OK)
    command = MowBorder(_CAPTURED_MAP_ID)

    with patch.object(Command, "_execute", fake):
        await command._execute(AsyncMock(), _DEVICE_INFO, AsyncMock())

    assert sent == ["clean", "clean_V2"]
    assert command._delegate(Family.V2)._args == _CAPTURED_ARGS
    assert selected(_DEVICE_INFO["did"]) is Family.V2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_border.py -p no:homeassistant -v`
Expected: `ModuleNotFoundError: No module named 'custom_components.ecovacs_mower.deebot_patch.border'`

- [ ] **Step 3: Create `border.py`**

```python
"""Border mowing for GOAT mowers (issue #12).

Border mowing is a task type of its own, not the ``Edge`` setting the
``border_switch`` entity toggles: that setting decides whether an ordinary job
also trims the perimeter, while this command starts a job that does nothing
else. The request shape was captured from the Ecovacs app on a GOAT G1-800
(``77atlz``, firmware 1.36.208)::

    clean_V2  {"act": "start", "content": {"type": "border", "value": "mid:<mid>"}}

``mid`` is the id of the map in use, which every map message names in its
envelope — see ``state_precedence.note_map``. The mower stores everything
else about the job, so the command carries nothing but that id.

Only the ``clean_V2`` shape is confirmed. The non-V2 delegate sends the same
nested payload on ``clean``, which is what the confirmed ``spotArea`` command
does on that family; ``hardware.BORDER_CLASSES`` keeps the button off the
non-V2 hardware until someone confirms it there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deebot_client.command import Command
from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.message import HandlingResult
from deebot_client.models import CleanAction

from .commands import _AdaptiveFamily, _TaskClean
from .families import Family

if TYPE_CHECKING:
    from deebot_client.authentication import Authenticator
    from deebot_client.event_bus import EventBus
    from deebot_client.models import ApiDeviceInfo


_TYPE_BORDER = "border"


class _BorderClean(_TaskClean):
    """The border payload, before a topic is chosen."""

    def __init__(self, map_id: str) -> None:
        super().__init__(_TYPE_BORDER, f"mid:{map_id}")


class _BorderCleanNonV2(_BorderClean, Clean):
    """Send the border payload on the ``clean`` topic."""


class _BorderCleanV2(_BorderClean, CleanV2):
    """Send the border payload on the ``clean_V2`` topic."""


class MowBorder(_AdaptiveFamily, Clean):
    """Start a border job, on whichever clean command the mower answers.

    Still a ``Clean`` subclass for the reasons ``CleanMower`` gives:
    ``ExecuteCommand`` supplies the concrete ``_handle_body``, and the patch
    layer promises that its mow commands are ``Clean`` commands.
    """

    def __init__(self, map_id: str) -> None:
        """Build a border start for the map *map_id*."""
        if not map_id or map_id == "0":
            # The entity never lets this through; this keeps the patch layer
            # itself from putting "mid:0" on the wire.
            raise ValueError("A border job needs the id of the map in use")
        self._map_id = map_id
        self._delegates: dict[Family, Command] = {}
        super().__init__(CleanAction.START)

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        # Inert as a wire payload: the delegates build their own, and _execute
        # is fully overridden. Keyed on the map id so Command.__eq__ and repr()
        # tell two instances apart — see CleanMower._get_args for the pattern.
        return {"act": action.value, "mid": self._map_id}

    def _delegate(self, family: Family) -> Command:
        """Return the command for the selected wire family."""
        return self._delegates[family]

    async def _execute(
        self,
        authenticator: Authenticator,
        device_info: ApiDeviceInfo,
        event_bus: EventBus,
    ) -> tuple[HandlingResult, dict[str, Any]]:
        """Build the two wire variants and let the adaptive family choose."""
        self._delegates = {
            Family.NON_V2: _BorderCleanNonV2(self._map_id),
            Family.V2: _BorderCleanV2(self._map_id),
        }
        return await super()._execute(authenticator, device_info, event_bus)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_border.py -p no:homeassistant -v`
Expected: PASS, all nine.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ecovacs_mower/deebot_patch/border.py tests/deebot_patch/test_border.py
git commit -m "feat: add the border-mowing command #12"
```

---

### Task 5: `BORDER_CLASSES` — which classes get the button

**Files:**
- Modify: `custom_components/ecovacs_mower/deebot_patch/hardware.py:66-68` (after `ZONE_AREA_CLASSES`)
- Test: `tests/deebot_patch/test_hardware.py`

**Interfaces:**
- Produces: `BORDER_CLASSES: tuple[str, ...] = ("77atlz",)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/deebot_patch/test_hardware.py`:

```python
def test_border_classes_are_the_ones_with_a_captured_request() -> None:
    # Membership means "the border request shape is confirmed on this class",
    # not "we patch it" — the opposite sense from SUPPORTED_CLASSES, the same
    # sense as ZONE_AREA_CLASSES. Only the G1-800 has a capture (issue #12).
    from custom_components.ecovacs_mower.deebot_patch.hardware import BORDER_CLASSES

    assert set(BORDER_CLASSES) == {G1_800}
    assert set(BORDER_CLASSES) <= set(SUPPORTED_CLASSES)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_hardware.py -p no:homeassistant -v -k border_classes`
Expected: `ImportError: cannot import name 'BORDER_CLASSES'`

- [ ] **Step 3: Add the tuple**

In `hardware.py`, after `ZONE_AREA_CLASSES = ("e4gqia",)`:

```python
# Classes on which the border-job request shape has been captured from the
# app (issue #12). Like ZONE_AREA_CLASSES, membership means "confirmed", not
# "patched": the button is only built for these, because the non-V2 shape is
# a guess nobody has tested — see border.py. Widening this tuple is how a
# second class gains the button.
#   77atlz — GOAT G1-800, firmware 1.36.208: clean_V2 with
#            {"type": "border", "value": "mid:<mid>"}, acknowledged code 0.
BORDER_CLASSES = ("77atlz",)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_hardware.py -p no:homeassistant -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ecovacs_mower/deebot_patch/hardware.py tests/deebot_patch/test_hardware.py
git commit -m "feat: name the classes with a confirmed border request #12"
```

---

### Task 6: The two buttons

**Files:**
- Modify: `custom_components/ecovacs_mower/button.py`
- Modify: `custom_components/ecovacs_mower/strings.json:70-77` (`entity.button`)
- Modify: `custom_components/ecovacs_mower/translations/en.json` (same block, must stay identical to `strings.json`)
- Modify: `custom_components/ecovacs_mower/icons.json:29-48` (`entity.button`)
- Test: `tests/test_button.py`, `tests/deebot_patch/test_commands.py`

**Interfaces:**
- Consumes: `MowBorder` (Task 4), `BORDER_CLASSES` (Task 5), `map_id_for` (Task 2), `MowerMapInfoEvent` from `map_messages.py`, `CleanMower` from `commands.py`, `EcovacsController.start_polling(device)`.
- Produces: `EcovacsMowerCommandButtonEntityDescription`, `MOWER_COMMAND_DESCRIPTIONS`, `EcovacsMowerCommandButtonEntity(device, controller, description)`, module function `_border_command(device) -> Command`.

- [ ] **Step 1: Pin the end-task payload in the protocol tests**

Append to `tests/deebot_patch/test_commands.py`:

```python
async def test_stop_goes_out_untouched_whatever_the_last_state_was() -> None:
    # Issue #51. The app's Beenden is {"act": "stop", "content": {"type": ""}}
    # on clean_V2, which is CleanV2's own shape; the wrapper's START/RESUME
    # decision must leave STOP alone even while the mower reads paused.
    bus = _bus()
    bus.notify(StateEvent(State.PAUSED))
    fake, sent = _transport(_NO_ANSWER, _OK)
    command = CleanMower(CleanAction.STOP)

    with patch.object(Command, "_execute", fake):
        await command._execute(AsyncMock(), _DEVICE_INFO, bus)

    assert sent == ["clean", "clean_V2"]
    assert command._delegate(Family.V2)._args == {"act": "stop", "content": {"type": ""}}
```

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/test_commands.py -p no:homeassistant -v -k stop_goes_out`
Expected: PASS already — this is the evidence the button rests on, not new behaviour. If it fails, stop and report: the library's shape has changed.

- [ ] **Step 2: Write the failing platform tests**

Append to `tests/test_button.py`:

```python
def test_the_mower_command_buttons_are_border_and_end_task() -> None:
    from custom_components.ecovacs_mower.button import MOWER_COMMAND_DESCRIPTIONS

    assert {d.key for d in MOWER_COMMAND_DESCRIPTIONS} == {"mow_border", "end_task"}


def test_the_border_button_is_limited_to_the_classes_with_a_capture() -> None:
    from custom_components.ecovacs_mower.button import MOWER_COMMAND_DESCRIPTIONS
    from custom_components.ecovacs_mower.deebot_patch.hardware import BORDER_CLASSES

    by_key = {d.key: d for d in MOWER_COMMAND_DESCRIPTIONS}
    assert by_key["mow_border"].classes == BORDER_CLASSES
    assert by_key["mow_border"].starts_job is True
    # Every supported mower: the V2 stop is captured, the non-V2 one is the
    # shape pause already uses, and the #51 reporter has non-V2 hardware.
    assert by_key["end_task"].classes is None
    assert by_key["end_task"].starts_job is False


def test_mower_command_buttons_have_translations_and_icons() -> None:
    import json
    from pathlib import Path

    from custom_components.ecovacs_mower.button import MOWER_COMMAND_DESCRIPTIONS

    root = Path(__file__).parent.parent / "custom_components" / "ecovacs_mower"
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    icons = json.loads((root / "icons.json").read_text(encoding="utf-8"))

    for description in MOWER_COMMAND_DESCRIPTIONS:
        assert description.translation_key in strings["entity"]["button"]
        assert description.translation_key in icons["entity"]["button"]


async def test_the_border_button_sends_the_recorded_map_id_and_restarts_polling() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from custom_components.ecovacs_mower.button import (
        MOWER_COMMAND_DESCRIPTIONS,
        EcovacsMowerCommandButtonEntity,
    )
    from custom_components.ecovacs_mower.deebot_patch.border import MowBorder
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import register

    description = next(d for d in MOWER_COMMAND_DESCRIPTIONS if d.key == "mow_border")
    device = MagicMock()
    device.device_info = {"did": "test-did", "class": "77atlz"}
    register(device.events).note_map("2049987783")
    controller = MagicMock()
    entity = EcovacsMowerCommandButtonEntity(device, controller, description)
    entity._execute_command = AsyncMock()

    await entity.async_press()

    controller.start_polling.assert_called_once_with(device)
    entity._execute_command.assert_awaited_once_with(MowBorder("2049987783"))


async def test_the_border_button_asks_for_the_map_when_it_has_none() -> None:
    from unittest.mock import AsyncMock, MagicMock

    import pytest
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.ecovacs_mower.button import (
        MOWER_COMMAND_DESCRIPTIONS,
        EcovacsMowerCommandButtonEntity,
    )
    from custom_components.ecovacs_mower.deebot_patch.map_messages import (
        MowerMapInfoEvent,
    )
    from custom_components.ecovacs_mower.deebot_patch.state_precedence import register

    description = next(d for d in MOWER_COMMAND_DESCRIPTIONS if d.key == "mow_border")
    device = MagicMock()
    device.device_info = {"did": "test-did", "class": "77atlz"}
    register(device.events)  # registered, but no map message has arrived
    controller = MagicMock()
    entity = EcovacsMowerCommandButtonEntity(device, controller, description)
    entity._execute_command = AsyncMock()

    with pytest.raises(HomeAssistantError, match="has not reported its map"):
        await entity.async_press()

    # Self-healing: the refresh is the getMapInfo_V2 that teaches the id.
    device.events.request_refresh.assert_called_once_with(MowerMapInfoEvent)
    entity._execute_command.assert_not_awaited()
    controller.start_polling.assert_not_called()


async def test_the_end_task_button_sends_stop_and_leaves_polling_alone() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from deebot_client.models import CleanAction

    from custom_components.ecovacs_mower.button import (
        MOWER_COMMAND_DESCRIPTIONS,
        EcovacsMowerCommandButtonEntity,
    )
    from custom_components.ecovacs_mower.deebot_patch.commands import CleanMower

    description = next(d for d in MOWER_COMMAND_DESCRIPTIONS if d.key == "end_task")
    device = MagicMock()
    device.device_info = {"did": "test-did", "class": "2px96q"}
    controller = MagicMock()
    entity = EcovacsMowerCommandButtonEntity(device, controller, description)
    entity._execute_command = AsyncMock()

    await entity.async_press()

    entity._execute_command.assert_awaited_once_with(CleanMower(CleanAction.STOP))
    # Ending a job is not a leaving-the-dock command, same as pause.
    controller.start_polling.assert_not_called()


def test_mower_command_buttons_are_built_per_class() -> None:
    from unittest.mock import MagicMock

    from deebot_client.capabilities import DeviceType

    from custom_components.ecovacs_mower.button import _mower_command_entities

    def mower(class_: str) -> MagicMock:
        device = MagicMock()
        device.device_info = {"did": f"did-{class_}", "class": class_}
        device.capabilities.device_type = DeviceType.MOWER
        return device

    vacuum = MagicMock()
    vacuum.device_info = {"did": "did-vac", "class": "yna5xi"}
    vacuum.capabilities.device_type = DeviceType.VACUUM

    controller = MagicMock()
    controller.devices = [mower("77atlz"), mower("2px96q"), vacuum]

    built = {
        (e._device.device_info["class"], e.entity_description.key)
        for e in _mower_command_entities(controller)
    }
    assert built == {
        ("77atlz", "mow_border"),
        ("77atlz", "end_task"),
        ("2px96q", "end_task"),
    }
```

Also update the existing `test_no_stale_button_translations_or_icons` so the reverse check knows the new keys: change its `keys` expression to

```python
    keys = {
        d.translation_key
        for d in (
            *ENTITY_DESCRIPTIONS,
            *LIFESPAN_ENTITY_DESCRIPTIONS,
            *MOWER_COMMAND_DESCRIPTIONS,
        )
    } | {EcovacsClearFaultButtonEntity.entity_description.translation_key}
```

and add `MOWER_COMMAND_DESCRIPTIONS` to that test's import from `custom_components.ecovacs_mower.button`.

Run them RED, with the unskip plugin from Global Constraints:

```bash
PYTHONPATH="C:/Users/RICKAR~1/AppData/Local/Temp/claude/D--private-projects-ha-ecovacs-mower/a85fa24e-d58f-4ed5-ab9b-7ba696ce0340/scratchpad" .venv/Scripts/python.exe -m pytest tests/test_button.py -p no:homeassistant -p unskip_win32 -v
```

Expected: the seven new tests and the edited `test_no_stale_button_translations_or_icons` fail with `ImportError: cannot import name 'MOWER_COMMAND_DESCRIPTIONS'`; the other eight still pass.

- [ ] **Step 3: Implement the button platform**

In `button.py`, extend the imports:

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from deebot_client.capabilities import (
    Capabilities,
    CapabilityExecute,
    CapabilityLifeSpan,
    DeviceType,
)
from deebot_client.command import Command
from deebot_client.device import Device
from deebot_client.events import LifeSpan
from deebot_client.models import CleanAction

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import EcovacsMowerConfigEntry
from .const import SUPPORTED_LIFESPANS
from .controller import EcovacsController
from .deebot_patch.border import MowBorder
from .deebot_patch.commands import CleanMower
from .deebot_patch.hardware import BORDER_CLASSES
from .deebot_patch.map_messages import MowerMapInfoEvent
from .deebot_patch.state_precedence import map_id_for
from .entity import (
    EcovacsCapabilityEntityDescription,
    EcovacsDescriptionEntity,
    EcovacsEntity,
)
from .fault import FaultLatch
from .util import get_supported_entities
```

Add to the module docstring, after the `play_sound` paragraph:

```
Added beyond core as well: the mower-command buttons, ``mow_border`` (issue
#12) and ``end_task`` (issue #51). Neither is a library capability — one needs
the device's recorded map id, the other sends a ``CleanAction`` HA's
``lawn_mower`` platform has no feature for — so they are described by
``EcovacsMowerCommandButtonEntityDescription``, whose ``command_fn`` builds
the command from the device at press time. A third such button is one more
entry in ``MOWER_COMMAND_DESCRIPTIONS``.
```

After `LIFESPAN_ENTITY_DESCRIPTIONS`, add:

```python
def _border_command(device: Device) -> Command:
    """The border start for *device*'s current map, or a clear refusal.

    The id is learned from the map messages' envelopes (state_precedence), and
    on the one class that has this button the mower answers getMapInfo_V2
    within seconds of setup, so an unknown id is the rare case. Asking for
    that refresh here makes the failure heal itself: the next press works.
    """
    map_id = map_id_for(device.events)
    if map_id is None:
        device.events.request_refresh(MowerMapInfoEvent)
        raise HomeAssistantError(
            "The mower has not reported its map yet; try again in a moment"
        )
    return MowBorder(map_id)


@dataclass(kw_only=True, frozen=True)
class EcovacsMowerCommandButtonEntityDescription(ButtonEntityDescription):
    """A button that sends one command built from the device at press time."""

    command_fn: Callable[[Device], Command]
    # None means every mower. A tuple limits the button to classes on which
    # the command's request shape is confirmed.
    classes: tuple[str, ...] | None = None
    # A command that takes the mower off its dock never produces a StateEvent
    # on its own, so the controller's poll has to be nudged — the same nudge
    # lawn_mower.py gives start_mowing and mow_area.
    starts_job: bool = False


MOWER_COMMAND_DESCRIPTIONS: tuple[EcovacsMowerCommandButtonEntityDescription, ...] = (
    EcovacsMowerCommandButtonEntityDescription(
        key="mow_border",
        translation_key="mow_border",
        command_fn=_border_command,
        classes=BORDER_CLASSES,
        starts_job=True,
        # No entity_category, for the reason play_sound gives above: a
        # control, not diagnostics or configuration.
    ),
    EcovacsMowerCommandButtonEntityDescription(
        key="end_task",
        translation_key="end_task",
        command_fn=lambda device: CleanMower(CleanAction.STOP),
        # Every supported mower. The V2 payload is the app's own, captured on
        # issue #51; the non-V2 payload is the shape pause already uses on
        # that hardware, and the reporter there owns the mower that has to
        # confirm it.
        classes=None,
        starts_job=False,
    ),
)


def _mower_command_entities(
    controller: EcovacsController,
) -> list[EcovacsMowerCommandButtonEntity]:
    """One command button per mower per description whose class gate passes."""
    return [
        EcovacsMowerCommandButtonEntity(device, controller, description)
        for device in controller.devices
        if device.capabilities.device_type is DeviceType.MOWER
        for description in MOWER_COMMAND_DESCRIPTIONS
        if description.classes is None
        or device.device_info["class"] in description.classes
    ]
```

In `async_setup_entry`, after the `EcovacsClearFaultButtonEntity` extension and before `async_add_entities(entities)`:

```python
    entities.extend(_mower_command_entities(controller))
```

At the end of the module, add the entity class:

```python
class EcovacsMowerCommandButtonEntity(
    EcovacsEntity[Capabilities],
    ButtonEntity,
):
    """A button whose command is built from the device when pressed.

    Issues #12 and #51. ``entity_description`` is assigned before the base
    ``__init__`` runs because ``EcovacsEntity.__init__`` reads its ``key`` for
    the unique id — the same order ``EcovacsDescriptionEntity`` uses.
    """

    entity_description: EcovacsMowerCommandButtonEntityDescription

    def __init__(
        self,
        device: Device,
        controller: EcovacsController,
        description: EcovacsMowerCommandButtonEntityDescription,
    ) -> None:
        """Initialize entity."""
        self.entity_description = description
        super().__init__(device, device.capabilities)
        self._controller = controller

    @override
    async def async_press(self) -> None:
        """Press the button."""
        # Built first: a refusal (no map id yet) must not restart the poll
        # for a job that is not going to start.
        command = self.entity_description.command_fn(self._device)
        if self.entity_description.starts_job:
            self._controller.start_polling(self._device)
        await self._execute_command(command)
```

`_mower_command_entities` is defined above the entity class it names in its return annotation. `button.py` has no `from __future__ import annotations` today, so that annotation would be evaluated at definition time and raise `NameError`. Add `from __future__ import annotations` as the first import of the module (below the docstring); it is what every module in `deebot_patch/` already does, and it changes nothing else in the file.

- [ ] **Step 4: Add the strings, translations and icons**

In `strings.json`, `entity.button` becomes (alphabetical, matching the file's habit):

```json
    "button": {
      "clear_fault": { "name": "Clear fault" },
      "end_task": { "name": "End mowing task" },
      "mow_border": { "name": "Mow border" },
      "play_sound": { "name": "Locate mower" },
      "reset_lifespan_blade": { "name": "Reset blades" },
      "reset_lifespan_lens_brush": { "name": "Reset lens brush" },
      "reset_lifespan_trimmer_brush": { "name": "Reset trimmer brush" },
      "reset_lifespan_weed_rope": { "name": "Reset weed rope" }
    },
```

Make the identical edit in `translations/en.json`. Then verify:

```bash
cmp custom_components/ecovacs_mower/strings.json custom_components/ecovacs_mower/translations/en.json && echo IDENTICAL
```

Expected: `IDENTICAL`. (`test_translations.py` compares the raw text, so formatting must match too: copy the block verbatim.)

In `icons.json`, `entity.button` gains two entries:

```json
      "end_task": {
        "default": "mdi:stop-circle-outline"
      },
      "mow_border": {
        "default": "mdi:vector-square"
      },
```

placed after `clear_fault` and before `play_sound`.

- [ ] **Step 5: Run GREEN, locally**

Run: `.venv/Scripts/python.exe -m pytest tests/deebot_patch/ -p no:homeassistant -v`
Expected: all pass.

Run:

```bash
PYTHONPATH="C:/Users/RICKAR~1/AppData/Local/Temp/claude/D--private-projects-ha-ecovacs-mower/a85fa24e-d58f-4ed5-ab9b-7ba696ce0340/scratchpad" .venv/Scripts/python.exe -m pytest tests/test_button.py tests/test_translations.py -p no:homeassistant -p unskip_win32 -v
```

Expected: every test in both files passes — the seven new button tests, the reverse translation/icon check with the new keys, and the byte-identity of `strings.json` and `translations/en.json`.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ecovacs_mower/button.py custom_components/ecovacs_mower/strings.json custom_components/ecovacs_mower/translations/en.json custom_components/ecovacs_mower/icons.json tests/test_button.py tests/deebot_patch/test_commands.py
git commit -m "feat: buttons to start a border job and to end the current task #12 #51"
```

---

### Task 7: README and CLAUDE.md

**Files:**
- Modify: `README.md` — three table rows and two new sections. Anchor every edit on the row's or paragraph's text, never on a line number; the numbers below are for orientation only and are one off in places.
- Modify: `CLAUDE.md` — the architecture list under "The patch layer is the only connection to deebot-client's internals".

- [ ] **Step 1: Update the `button` row of the "What you get" entity table**

Find the row that begins `| \`button\` | 6 |` (under `## What you get`, near line 177) and replace the whole row with:

```markdown
| `button` | 8 | Reset each of the four consumable lifespans, "Locate mower" (plays a sound on the device), "Clear fault" (releases the latched fault; see below), "End mowing task" (ends the current job for good; see below) and, on the G1-800, "Mow border" (starts a border job; see below) |
```

- [ ] **Step 1b: Update the `button` row of the "Entities disabled by default" table**

Find the row that begins `| \`button\` | 4 of 6 |` (under `### Entities disabled by default`, near line 513) and replace the whole row with:

```markdown
| `button` | 4 of 8 | the four consumable-lifespan resets (blade, lens brush, trimmer brush, weed rope) — "Locate mower", "Clear fault", "End mowing task" and "Mow border" are enabled by default |
```

- [ ] **Step 2: Update the `77atlz` row of the hardware table**

Find the row that begins `| **Ecovacs GOAT G1-800** | \`77atlz\` |` (under `## Hardware support`, near line 84 — the row *above* the A1600 LiDAR Pro) and append to the end of its "Confirmed by" cell, before the closing `|`:

```
; border mowing is built for this class from the request captured in [#12](https://github.com/nord-/ha-ecovacs-mower/issues/12) and awaits confirmation on hardware
```

Once the reporter confirms the branch on the G1-800, the executor of the release changes "awaits confirmation on hardware" to "confirmed" — not part of this plan.

- [ ] **Step 3: Add the two sections**

Insert after the paragraph ending "range does not imply that the mower has a zone with that ID." (the last paragraph of `### Zone-specific mowing`) and before the heading `### When a run stops because of rain`:

```markdown
### Border mowing

The *Edge cutting* switch is a setting: it decides whether an ordinary job also trims the perimeter. Border mowing is a separate task the mower runs on its own, and the **Mow border** button starts one — the same job the Ecovacs app starts from its border-mowing action. While it runs the mower reports `mowing`, the progress sensor tracks the strip along the boundary rather than the lawn, and the map keeps updating.

The button exists only on classes where the request the app sends has been captured, which today is the GOAT G1-800 (`77atlz`). If you have another mower and would like the button, open an issue with a debug log of the app starting a border job; the request shape and the device class are what it needs.

The command names the mower's current map, which the integration learns from the map messages the mower sends. Right after a restart that can take a few seconds; pressing the button before then answers "The mower has not reported its map yet; try again in a moment" and asks the mower for its map, so the next press works.

### Ending a task

Sending the mower back to its dock does not end the job. The mower keeps it as resumable — the app shows the unfinished progress with *End* and *Continue* — and a later *Start* resumes it instead of beginning a fresh cycle. The **End mowing task** button is the app's *End*: it ends the current job for good, so the next start is a new one. Useful in automations that interrupt a job during the day and want tomorrow's run to start from scratch.

The payload is confirmed on the G1-800 (`77atlz`), where the app's own request was captured ([#51](https://github.com/nord-/ha-ecovacs-mower/issues/51)). On the O-series and A-series mowers it sends the same shape those mowers already accept for *Pause*; if it does nothing on yours, a debug log of the app's *End* on that mower is what settles it.
```

Wrap the new paragraphs the way the surrounding README prose is wrapped (the file is hard-wrapped at about 80 columns; match it). Table rows stay on one line each, as the existing rows do.

- [ ] **Step 4: Check the tables are still one row per line**

Run: `grep -c "^| \`button\` | " README.md; grep -c "^### " README.md`
Expected: `2` (one row per table, each on one line) and `14` (two more `###` headings than the 12 before the edit).

- [ ] **Step 5: Record the architecture in CLAUDE.md**

In the bullet list under "The patch layer is the only connection to deebot-client's internals":

Append to the `hardware.py` bullet, after the sentence ending "(`e4gqia` so far).":

```
`BORDER_CLASSES` is the same kind as `ZONE_AREA_CLASSES`: membership means the border-job request shape is captured on that class, and only those get the `mow_border` button (`77atlz` so far). It gates a button rather than a capability, because `Capabilities` has no field for it — `button.py` checks the class string directly.
```

Insert a new bullet directly after the `zonal.py` bullet:

```
- `border.py` — `MowBorder`, the `border` task-start command (issue #12), built on the same `_AdaptiveFamily` machinery as `MowArea` and sharing `_TaskClean`, the `{"type", "value"}` payload builder in `commands.py`, with it. Needs the id of the map in use, which it does not fetch: it is handed one by `button.py`, which reads it from `state_precedence.map_id_for()`. Exposed as the `mow_border` button, alongside `end_task`, which is `CleanMower(CleanAction.STOP)` and needs nothing from this module (issue #51).
```

Replace the `state_precedence.py` bullet with:

```
- `state_precedence.py` — per-device record, keyed by `EventBus`, of the facts the handlers learn from the stream: that the mower is docked, which beats a paused plan, and what the suppressed state was (issue #67); and the id of the map the mower is using, written by `map_messages._MapMessage` from every map message's envelope and read by the border button (issue #12). `register()` is also the marker that says a bus belongs to a patched mower rather than a vacuum on the same account.
```

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: describe the border-mowing and end-task buttons #12 #51"
```

---

## Self-review

**Spec coverage.** `MowBorder` with delegates, `ValueError` and the rewrite bypass pinned — Task 4. Shared payload builder with its bypass pinned — Task 1. Map id on `MowerStateRecord`, `note_map(mid, using)`, `map_id_for`, `move()` leaving it — Task 2. Handler writes id and `using` before buffering, registered buses only — Task 3. `BORDER_CLASSES` and comment — Task 5. Description type, both entries, class gate, `starts_job`, refresh-then-raise, `_execute_command`, no poll on end task — Task 6. Strings/translations/icons — Task 6. `CleanMower(STOP)` V2 shape pinned — Task 6 Step 1. README sections, three table rows, CLAUDE.md architecture — Task 7. Hardware confirmation on the G1-800 is a merge gate, not a task.

**Placeholders.** None: every step has its code or its exact command, and every command names the venv interpreter.

**Type consistency.** `_TaskClean(task: str, value: str)` in Task 1 is what Task 4's `_BorderClean` calls. `note_map(mid, using=None)` in Task 2 is what Task 3's handler calls with two positional arguments. `map_id_for(event_bus) -> str | None` in Task 2 is what Task 3 asserts on and Task 6's `_border_command` reads. `MowBorder(map_id: str)` in Task 4 is what Task 6's tests compare against. `BORDER_CLASSES` in Task 5 is the `classes` value in Task 6. `EcovacsMowerCommandButtonEntity(device, controller, description)` matches its tests and `_mower_command_entities`.

**Review 2026-09-09.** The maintainer's review found the bare `python` (3.12, no `deebot_client`), two README line numbers one row off, the untouched "Entities disabled by default" table, the missing `using` gate, the local platform-test recipe, the missing CLAUDE.md update and the contract gap on the shared builder. All seven are folded in above.
