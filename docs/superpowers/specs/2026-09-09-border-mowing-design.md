# Border mowing and ending a task from Home Assistant — design (issues #12 and #51)

Status: reviewed by the maintainer on 2026-09-09, who folded issue #51 into the same PR. Written from the evidence on issue #12, issue #51 and PR #83, plus the code as of 0.8.0; nothing here has been tried against hardware yet.

## What is being built

Two buttons on the mower's device page, both sending the `clean` command with a payload the integration cannot produce today.

**Start a border job** (issue #12) — the GOAT's standalone "mow the perimeter" task. Issue #12 set out to find whether the existing `border_switch` entity already covered edge cutting. The captures on the issue answer that with a no: the switch is the `Edge` setting and only decides whether an ordinary job also trims the perimeter, while border mowing is its own task type with its own command.

**End the current task** (issue #51) — the app's *Beenden*. After a return-to-dock the mower keeps the job as resumable, and a later start resumes it instead of beginning a fresh cycle. The `stop` half of the same command ends it for good. The library already builds the exact payload; only the entity side is missing, and HA's `lawn_mower` platform has no stop feature to hang it on, so it is a button too.

The two share one entity class and one description table, which is why they belong in one PR.

## Evidence the design rests on

All of it from a GOAT G1-800 (`77atlz`, firmware 1.36.208), captured by the reporter on issue #12 from the Ecovacs app on the shared MQTT connection.

The request the app sends, and the mower's acknowledgement:

```
q clean_V2  {"act":"start","content":{"type":"border","value":"mid:2049987783"}}
p clean_V2  {"code":0,"msg":"ok"}
```

What the mower reports while it runs (through the handler this integration already owns, so it reads as *mowing*):

```json
{"trigger":"none","state":"clean",
 "cleanState":{"motionState":"working","cid":"122","router":"plan",
               "content":{"type":"border","value":""}}}
```

The job's own boundaries arrive as `onFwBuryPoint-bd_task-mow-border-start` / `-stop`, which `deebot_patch/messages.py` registers since issue #74, with `cuttedArea 1.63` of `workArea 19.24` m² on the stop. The border strip is therefore a job like any other to the progress sensor and the last-job event; nothing downstream needs to learn a new shape.

The one thing the request needs that the integration does not have is the **`mid`** — the id of the map the mower is using. Every map message the mower sends carries it in its envelope (`data["mid"]`), including the `onMapInfo_V2` fragments that answer the `getMapInfo_V2` the integration sends at setup and on every reconnect (issue #81). The library's `OnCachedMapInfo` handler treats `mid` `"0"` as "no map", and the captured `onArI` fixtures show the same `"0"` on idle snapshots, so the id has to be filtered, not just read.

The coverage freeze a border job used to cause (issue #52) is fixed by PR #83, which is on `master`. Nothing gates this work any more.

For ending a task, the same G1-800 owner captured the app's *Beenden* in a comment on issue #51, on a running job (the issue itself was opened by an O800 RTK owner, whose mower answers on the non-V2 family):

```
q clean_V2  {"act":"stop","content":{"type":""},"bdTaskID":"<id>"}
p clean_V2  {"code":0,"msg":"ok"}
```

The job ended and did not come back as resumable. The library's `CleanV2._get_args(STOP)` produces `{"act": "stop", "content": {"type": ""}}`, byte for byte the app's payload minus `bdTaskID`, which the mower has obeyed `charge` without and so looks optional. `CleanMower(CleanAction.STOP)` therefore already routes the right payload to the V2 family, and `_effective_action` leaves `STOP` untouched. What the non-V2 family accepts is unconfirmed — see below.

## Scope

In:

- A `MowBorder` command in the patch layer, built on the same family-adaptive machinery as `MowArea`, so `families.py` stays the only place that decides the topic.
- Learning and holding the current map id from the map stream, inside the handlers this integration owns.
- A `button.<mower>_mow_border` entity, limited to the device classes on which the request shape is confirmed.
- A `button.<mower>_end_task` entity on every supported mower, sending `CleanMower(CleanAction.STOP)`.
- Tests, `strings.json`/`translations/en.json`/`icons.json`, README sections, `hardware.py` comment block.

Out, deliberately:

- **A new `stop` payload for the non-V2 family.** `_CleanNonV2` sends `{"act": "stop", "content": {"type": "auto"}}`, the same shape it sends for `pause`, which non-V2 hardware is confirmed to accept. That is the best-founded guess available; the capture the issue still needs is the app's *Beenden* on an O-series mower, and the reporter there has been asked for it. If it shows another shape, `_CleanNonV2._get_args` grows a `STOP` branch — not this PR's problem to pre-empt.
- **`EdgeMode`.** The settings snapshot shows `EdgeMode: 0` next to `Edge: 1`, with no entity behind it and no idea what it selects. Not touched.
- **A `lawn_mower` entity service.** The command takes no user input, so a button is the better fit — see the decision below. Nothing stops a service being added later if an automation author asks for one.
- **Reading the map id from `getCachedMapInfo`.** The library has the command; whether GOAT answers it is unknown. The map stream already carries the id, so the request is not needed for a first version.
- **Persisting the map id across restarts.** On the one class that gets the button, `getMapInfo_V2` is answered within seconds of setup. Revisit if a report shows the id missing in practice.

## Design

### Patch layer: `MowBorder`

New module `custom_components/ecovacs_mower/deebot_patch/border.py`, mirroring `zonal.py`:

```python
class MowBorder(_AdaptiveFamily, Clean):
    def __init__(self, map_id: str) -> None: ...
```

- Two delegates, `_BorderCleanNonV2(Clean)` and `_BorderCleanV2(CleanV2)`, both sending `{"act": "start", "content": {"type": "border", "value": f"mid:{map_id}"}}` on their own topic. Built in `_execute`, exactly as `MowArea` does.
- `_get_args` returns `{"act": "start", "mid": map_id}` — inert as a payload, there so `Command.__eq__` and `repr()` tell two instances apart (the same equality-only pattern `CleanMower` and `MowArea` document).
- Rejects an empty or `"0"` map id with `ValueError`. The entity never lets that reach the command, but the patch layer should not be able to put `mid:0` on the wire either.
- `_NoActionRewrite` applies, as it does for every delegate the patch layer sends: `Clean._execute`'s start/resume rewrite must not touch a border start.

**Shared payload builder.** `zonal.py`'s `_ZoneClean` and this module's delegates build the same nested shape with a different `type` and `value`. The shared piece — a `_NoActionRewrite` subclass that takes `(type, value)` and produces `{"act", "content": {"type", "value"}}` — moves to `commands.py` next to `_NoActionRewrite`, and `zonal.py` uses it. Small, targeted, and it is exactly the kind of repetition that drifts when a third task type shows up.

**The non-V2 family is a guess, on purpose.** The shape is captured only on `clean_V2`. The non-V2 delegate sends the identical nested payload on `clean`, which is what `_CleanNonV2` and the confirmed `spotArea` command on `e4gqia` both do; there is no better-founded guess. The class gate below keeps it off non-V2 hardware in any case, so a wrong guess costs nothing until someone confirms a non-V2 class and the tuple is widened.

### Learning the map id

The rule in `CLAUDE.md` decides where this lives: state derived from the event stream is written by the handlers, never by a subscription, because `EventBus.notify` drops repeats before subscribers run and dispatches through `create_task`.

`MowerStateRecord` in `state_precedence.py` gains a `map_id: str | None` field and a `note_map(mid, using)` method. `_MapMessage._handle_body_data_dict` in `map_messages.py` calls it with `data.get("mid")` and `data.get("using")` **before** the fragment buffering, so an id is learned from the very first fragment, even of a blob that later turns out undecodable. The method ignores `None`, non-strings, `""` and `"0"`, and is otherwise last-writer-wins: the mower reports one map, and a map switch in the app should be followed.

`using` is the envelope's own word on whether the fragment describes the active map. Every captured `onMI`, `onArI`, `onSpecialContour` and `onMapInfo_V2` envelope carries `using: 1`; `onMapTrack` and `onMapTrace` do not carry the field. A user with several stored maps may get fragments for an inactive one in the answer to `getMapInfo_V2 {"type": "0"}`, and last-writer-wins would then name the wrong map. So an explicit `using` of `0` (or `"0"`) is skipped, and an absent field is taken as "the message does not say" and the id accepted. That is the code-side answer to the open question below: even if the map id in the stream and the one the app sends could differ for an inactive map, the active one is the only one recorded.

Why the existing record rather than a new module: `state_precedence.register()` is already the marker that says "this bus belongs to a patched mower", which is what keeps a Deebot vacuum on the same account from being mistaken for one — `MESSAGES` is global and the map handlers are reached for every JSON device. A second registry would duplicate that marker and its lifetime. The module docstring is widened from "the little state needed to prefer docked over paused" to "the per-device facts the handlers learn from the stream", and the rest is unchanged. A `map_id_for(event_bus)` helper alongside `record_for` keeps callers from reaching into the record.

`MowerStateRecord.move()` does **not** clear the map id: leaving the dock does not change the map.

### Gating: which classes get the button

`hardware.py` gains `BORDER_CLASSES = ("77atlz",)`, the same kind of tuple as `ZONE_AREA_CLASSES`: membership means "the request shape is confirmed on this class", not "we patch it". The comment block above it records the capture the entry rests on. Widening it is the way a second class is supported, and the README says so.

Nothing in `Capabilities` has a field for this, so — unlike `MowArea`, which `lawn_mower.py` recognises by `area is MowArea` — the button platform checks `device.device_info["class"] in BORDER_CLASSES`. `verify_capabilities()` is unchanged: the patch does not alter the capabilities object for this feature, so there is nothing new to verify about it.

### Entity: a mower-command button

`button.py` today has three kinds of button: the declarative `ENTITY_DESCRIPTIONS` (a `capability_fn` returning a `CapabilityExecute`), the lifespan resets, and `EcovacsClearFaultButtonEntity`. None fits a command that needs the device's runtime state and may refuse to run. Rather than a fourth one-off class, the design adds one description type that both new buttons use:

```python
@dataclass(kw_only=True, frozen=True)
class EcovacsMowerCommandButtonEntityDescription(ButtonEntityDescription):
    command_fn: Callable[[Device], Command]   # may raise HomeAssistantError
    classes: tuple[str, ...] | None = None    # None: every MOWER
    starts_job: bool = False                  # restart the controller's poll

MOWER_COMMAND_DESCRIPTIONS = (
    EcovacsMowerCommandButtonEntityDescription(
        key="mow_border",
        translation_key="mow_border",
        command_fn=_border_command,
        classes=BORDER_CLASSES,
        starts_job=True,
        # No entity_category, for the reason play_sound gives: a control,
        # not diagnostics or configuration.
    ),
    EcovacsMowerCommandButtonEntityDescription(
        key="end_task",
        translation_key="end_task",
        command_fn=lambda device: CleanMower(CleanAction.STOP),
        # Every supported mower: the V2 shape is captured, the non-V2 one is
        # the shape pause already uses, and the reporter on #51 has the
        # non-V2 hardware to confirm it on.
        classes=None,
        starts_job=False,
    ),
)
```

`_border_command(device)` reads `map_id_for(device.events)`. If it is `None`, it asks the bus for a refresh of `MowerMapInfoEvent` — the same `getMapInfo_V2` that populates the id at setup — and raises `HomeAssistantError("The mower has not reported its map yet; try again in a moment")`. That turns the one plausible failure into a self-healing one instead of a warning in the log.

`EcovacsMowerCommandButtonEntity(device, controller, description)` is built in `async_setup_entry` for every device whose `device_type is DeviceType.MOWER` and whose class passes `classes`. `async_press` calls `controller.start_polling(device)` when `starts_job` is set — a command sent from HA never produces a `StateEvent` on its own, so the tick has to be nudged, exactly as `async_mow_area` does — and then `await self._execute_command(description.command_fn(self._device))`, so an unconfirmed command is logged under this integration's logger (issue #26).

The end-task button does not restart the poll: ending a job is not a leaving-the-dock command, the same reasoning that keeps `pause` from poking the controller's tick today.

### What happens after the press

Nothing new, for either button. After a border start the mower answers on the `clean_V2` topic and pushes `onCleanInfo_V2` with `motionState: working`, which `handle_clean_info` maps to `CLEANING`. `OnMowBorderStart` publishes the job edge, `OnMowBorderStop` ends it, the progress sensor works from the `getStats` pair as for any job, and PR #83 keeps the coverage layer alive throughout. The restarted poll bounds a dropped push. After an end-task press the mower reports the job over through the same pushes it uses when the app ends one; the `stop` bury point for the job type carries the trigger.

## Error handling

| Situation | Behaviour |
|---|---|
| Class not in `BORDER_CLASSES` | No entity is created. Nothing to press, nothing to explain. |
| Map id unknown | `HomeAssistantError` with a plain message; a `getMapInfo_V2` refresh is requested so the next press works. |
| Mower does not confirm | `_execute_command` warns under `ecovacs_mower`, names the family attempted, and does not raise (the mower may have started anyway). Unchanged behaviour. |
| Non-V2 mower answers `errno 500` on `clean` | `_AdaptiveFamily` retries on `clean_V2` and commits the family on a positive answer. Unchanged behaviour. |
| Bad `mid` reaches the command | `ValueError` from `MowBorder.__init__`; unreachable through the entity, guards the patch layer's own callers. |

## Testing

Protocol layer (`tests/deebot_patch/`, runnable on Windows with `.venv/Scripts/python.exe -m pytest … -p no:homeassistant`):

- `test_border.py`: both delegates produce the captured payload byte for byte on their own topic; `MowBorder` is a `Clean` with `NAME == "clean"`; equality includes the map id; `""` and `"0"` are rejected; executes on non-V2 first, falls back to V2 and commits the family (mirroring `test_zonal.py`, sharing its transport helpers).
- `test_state_precedence.py`: `note_map` ignores `None`, `""`, `"0"` and non-strings; skips `using` `0`/`"0"` and accepts an absent `using`; keeps the latest valid id; `move()` leaves it alone.
- `test_map_messages.py`: a single fragment of a multipart blob is enough to record the id; a blob with `mid` `"0"` records nothing; a fragment with `using: 0` records nothing; an undecodable blob still records the id; an unregistered bus gets no record.
- `test_zonal.py`: unchanged assertions pass against the shared payload builder — that is the regression check for the refactor.
- `test_contract.py`: the shared builder still bypasses `Clean._execute`'s rewrite.

Platform (`tests/`; runnable on Windows through the `unskip_win32` plugin the plan describes, since none of these need the `hass` fixture; CI stays the verdict):

- `test_button.py`: the border button exists for `77atlz` and for no other class in `SUPPORTED_CLASSES`; the end-task button exists for every mower and for no non-mower device; a border press with a known map id sends `MowBorder("<mid>")` through `_execute_command` and restarts polling; a border press with no map id raises `HomeAssistantError`, requests a `MowerMapInfoEvent` refresh and sends nothing; an end-task press sends `CleanMower(CleanAction.STOP)` and does not touch polling; the translation/icon two-way checks cover `MOWER_COMMAND_DESCRIPTIONS`.
- `test_commands.py`: `CleanMower(CleanAction.STOP)` puts `{"act": "stop", "content": {"type": ""}}` on `clean_V2` — the captured payload — and leaves the action alone whatever the last state was.
- `test_translations.py`: unchanged, guards `strings.json` == `translations/en.json`.
- `test_hardware.py`: `BORDER_CLASSES` is a subset of `SUPPORTED_CLASSES`.

Hardware: the reporter on issue #12 has offered to test a branch on the G1-800. That is the confirmation the `BORDER_CLASSES` entry ultimately rests on, and the PR should not merge without it. The end-task button on the V2 family is covered by the same test run; its non-V2 shape is confirmed only when the reporter on issue #51 presses it on the O800 RTK, and the README says so until then.

## Documentation

- README: a "Border mowing" section after "Zone-specific mowing", stating what the button does, that it is a separate task from the *Edge cutting* switch, which class it is confirmed on, and how to report another class. The supported-hardware table gets "border mowing confirmed" on the `77atlz` row once it is. An "Ending a task" section next to it, saying what the button does, why a return-to-dock alone does not end a job, and that the non-V2 shape awaits confirmation. The `button` row in the entity table gains both.
- README: the `button` row of the "Entities disabled by default" table goes from 4 of 6 to 4 of 8, naming the two new buttons as enabled by default.
- `hardware.py`: the comment block above `BORDER_CLASSES`.
- `CLAUDE.md`: the architecture list gains `border.py`, the `hardware.py` bullet gains `BORDER_CLASSES`, and the `state_precedence.py` bullet says it now also holds the map id. Broad strokes belong there per the maintainer's documentation tiers.
- The PR description records the decisions below and why.

## Decisions

Each was a recommendation with the alternative named; the maintainer accepted them on 2026-09-09 and changed the last one.

1. **Buttons, not `lawn_mower` services.** Neither command takes input, a button appears on the device page and in dashboards without YAML, and issue #51 asks for a button outright. Alternative: entity services like `mow_area`, which are more natural from automations but invisible on the device page.
2. **Map id from the map stream, held on `MowerStateRecord`.** Alternative: a separate `map_identity.py` record, which keeps `state_precedence.py` narrow at the cost of a second per-bus registry.
3. **Border gated by class tuple, `77atlz` only.** Alternative: every supported class with the button disabled by default on the unconfirmed ones — more discoverable, but it puts an unverified request one toggle away on hardware nobody has tested.
4. **End task on every supported mower.** The V2 payload is captured; the non-V2 payload is the one `pause` already uses successfully on that hardware, and the reporter on #51 owns the non-V2 mower the confirmation has to come from. Gating it to `77atlz` would keep the button from the one person who asked for it.
5. **A reusable command-button description type**, so the two buttons are two entries. Alternative: two one-off entity classes like `EcovacsClearFaultButtonEntity`.
6. **Entity names "Mow border"** (key `mow_border`, icon `mdi:vector-square`), next to the existing switch named "Edge cutting", and **"End mowing task"** (key `end_task`, icon `mdi:stop-circle-outline`). Alternatives: "Edge mowing", which reads closer to the switch and risks being taken for it; "Stop mowing", which reads like a pause.
7. **Issues #12 and #51 in one PR.** The maintainer's call: they share the entity class, the description table and the test run on the G1-800.

## The question to the reporter

The captured request carries `mid:2049987783`. The fixtures on PR #83 have their `mid` replaced, so nothing on record confirms that the id in the mower's map messages is the same id the app puts in the request. The design assumes it is — there is only one map. Asked on issue #12 on 2026-09-09; if the answer is no, the map id has to come from `getCachedMapInfo` instead and the "Learning the map id" section is the part that changes.
