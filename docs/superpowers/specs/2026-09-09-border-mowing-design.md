# Border mowing from Home Assistant — design (issue #12)

Status: draft, awaiting the maintainer's review. Written from the evidence on issue #12, issue #51 and PR #83, plus the code as of 0.8.0; nothing here has been tried against hardware yet.

## What is being built

A way to start a **border job** — the GOAT's standalone "mow the perimeter" task — from Home Assistant. Issue #12 set out to find whether the existing `border_switch` entity already covered edge cutting. The captures on the issue answer that with a no: the switch is the `Edge` setting and only decides whether an ordinary job also trims the perimeter, while border mowing is its own task type with its own command, which the integration cannot send today.

The deliverable is a `button` entity on the mower's device page that sends that command.

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

## Scope

In:

- A `MowBorder` command in the patch layer, built on the same family-adaptive machinery as `MowArea`, so `families.py` stays the only place that decides the topic.
- Learning and holding the current map id from the map stream, inside the handlers this integration owns.
- A `button.<mower>_mow_border` entity, limited to the device classes on which the request shape is confirmed.
- Tests, `strings.json`/`translations/en.json`/`icons.json`, README section, `hardware.py` comment block.

Out, deliberately:

- **Ending a task (issue #51).** The stop half of the same command. It is the natural second entry in the button table this design introduces, but it is its own issue with its own hardware question (the non-V2 `stop` shape is unconfirmed on the O800 RTK the reporter has), so it gets its own PR. This design makes that PR a one-entry addition.
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

`MowerStateRecord` in `state_precedence.py` gains a `map_id: str | None` field and a `note_map(mid)` method. `_MapMessage._handle_body_data_dict` in `map_messages.py` calls it with `data.get("mid")` **before** the fragment buffering, so an id is learned from the very first fragment, even of a blob that later turns out undecodable. The method ignores `None`, non-strings, `""` and `"0"`, and is otherwise last-writer-wins: the mower reports one map, and a map switch in the app should be followed.

Why the existing record rather than a new module: `state_precedence.register()` is already the marker that says "this bus belongs to a patched mower", which is what keeps a Deebot vacuum on the same account from being mistaken for one — `MESSAGES` is global and the map handlers are reached for every JSON device. A second registry would duplicate that marker and its lifetime. The module docstring is widened from "the little state needed to prefer docked over paused" to "the per-device facts the handlers learn from the stream", and the rest is unchanged. A `map_id_for(event_bus)` helper alongside `record_for` keeps callers from reaching into the record.

`MowerStateRecord.move()` does **not** clear the map id: leaving the dock does not change the map.

### Gating: which classes get the button

`hardware.py` gains `BORDER_CLASSES = ("77atlz",)`, the same kind of tuple as `ZONE_AREA_CLASSES`: membership means "the request shape is confirmed on this class", not "we patch it". The comment block above it records the capture the entry rests on. Widening it is the way a second class is supported, and the README says so.

Nothing in `Capabilities` has a field for this, so — unlike `MowArea`, which `lawn_mower.py` recognises by `area is MowArea` — the button platform checks `device.device_info["class"] in BORDER_CLASSES`. `verify_capabilities()` is unchanged: the patch does not alter the capabilities object for this feature, so there is nothing new to verify about it.

### Entity: a mower-command button

`button.py` today has three kinds of button: the declarative `ENTITY_DESCRIPTIONS` (a `capability_fn` returning a `CapabilityExecute`), the lifespan resets, and `EcovacsClearFaultButtonEntity`. None fits a command that needs the device's runtime state and may refuse to run. Rather than a fourth one-off class, the design adds one description type that the #51 button can reuse:

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
)
```

`_border_command(device)` reads `map_id_for(device.events)`. If it is `None`, it asks the bus for a refresh of `MowerMapInfoEvent` — the same `getMapInfo_V2` that populates the id at setup — and raises `HomeAssistantError("The mower has not reported its map yet; try again in a moment")`. That turns the one plausible failure into a self-healing one instead of a warning in the log.

`EcovacsMowerCommandButtonEntity(device, controller, description)` is built in `async_setup_entry` for every device whose `device_type is DeviceType.MOWER` and whose class passes `classes`. `async_press` calls `controller.start_polling(device)` when `starts_job` is set — a command sent from HA never produces a `StateEvent` on its own, so the tick has to be nudged, exactly as `async_mow_area` does — and then `await self._execute_command(description.command_fn(self._device))`, so an unconfirmed command is logged under this integration's logger (issue #26).

Follow-up for #51, for the record: one more entry, `command_fn=lambda device: CleanMower(CleanAction.STOP)`, `classes=None`, `starts_job=False`. Not in this PR.

### What happens after the press

Nothing new. The mower answers on the `clean_V2` topic and pushes `onCleanInfo_V2` with `motionState: working`, which `handle_clean_info` maps to `CLEANING`. `OnMowBorderStart` publishes the job edge, the progress sensor computes `cuttedArea / workArea` for the strip, `OnMowBorderStop` ends it, and PR #83 keeps the coverage layer alive throughout. The restarted poll bounds a dropped push.

## Error handling

| Situation | Behaviour |
|---|---|
| Class not in `BORDER_CLASSES` | No entity is created. Nothing to press, nothing to explain. |
| Map id unknown | `HomeAssistantError` with a plain message; a `getMapInfo_V2` refresh is requested so the next press works. |
| Mower does not confirm | `_execute_command` warns under `ecovacs_mower`, names the family attempted, and does not raise (the mower may have started anyway). Unchanged behaviour. |
| Non-V2 mower answers `errno 500` on `clean` | `_AdaptiveFamily` retries on `clean_V2` and commits the family on a positive answer. Unchanged behaviour. |
| Bad `mid` reaches the command | `ValueError` from `MowBorder.__init__`; unreachable through the entity, guards the patch layer's own callers. |

## Testing

Protocol layer (`tests/deebot_patch/`, runnable on Windows with `-p no:homeassistant`):

- `test_border.py`: both delegates produce the captured payload byte for byte on their own topic; `MowBorder` is a `Clean` with `NAME == "clean"`; equality includes the map id; `""` and `"0"` are rejected; executes on non-V2 first, falls back to V2 and commits the family (mirroring `test_zonal.py`, sharing its transport helpers).
- `test_state_precedence.py`: `note_map` ignores `None`, `""`, `"0"` and non-strings; keeps the latest valid id; `move()` leaves it alone.
- `test_map_messages.py`: a single fragment of a multipart blob is enough to record the id; a blob with `mid` `"0"` records nothing; an undecodable blob still records the id.
- `test_zonal.py`: unchanged assertions pass against the shared payload builder — that is the regression check for the refactor.
- `test_contract.py`: the shared builder still bypasses `Clean._execute`'s rewrite.

Platform (`tests/`, CI only):

- `test_button.py`: the border button exists for `77atlz` and for no other class in `SUPPORTED_CLASSES`; a press with a known map id sends `MowBorder("<mid>")` through `_execute_command` and restarts polling; a press with no map id raises `HomeAssistantError`, requests a `MowerMapInfoEvent` refresh and sends nothing; the translation/icon two-way checks cover `MOWER_COMMAND_DESCRIPTIONS`.
- `test_translations.py`: unchanged, guards `strings.json` == `translations/en.json`.
- `test_hardware.py`: `BORDER_CLASSES` is a subset of `SUPPORTED_CLASSES`.

Hardware: the reporter on issue #12 has offered to test a branch on the G1-800. That is the confirmation the `BORDER_CLASSES` entry ultimately rests on, and the PR should not merge without it.

## Documentation

- README: a "Border mowing" section after "Zone-specific mowing", stating what the button does, that it is a separate task from the *Edge cutting* switch, which class it is confirmed on, and how to report another class. The supported-hardware table gets "border mowing confirmed" on the `77atlz` row once it is.
- `hardware.py`: the comment block above `BORDER_CLASSES`.
- The PR description records the decisions below and why, per the maintainer's documentation tiers.

## Decisions taken here that the maintainer should confirm

Each is a recommendation with the alternative named; the design above assumes the recommendation.

1. **Button, not a `lawn_mower` service.** The command takes no input, a button appears on the device page and in dashboards without YAML, and issue #51's users are asking for a button too. Alternative: `ecovacs_mower.mow_border` as an entity service like `mow_area`, which is more natural from automations but invisible on the device page.
2. **Map id from the map stream, held on `MowerStateRecord`.** Alternative: a separate `map_identity.py` record, which keeps `state_precedence.py` narrow at the cost of a second per-bus registry.
3. **Gate by class tuple, `77atlz` only.** Alternative: every supported class with the button disabled by default on the unconfirmed ones — more discoverable, but it puts an unverified request one toggle away on hardware nobody has tested.
4. **A reusable command-button description type**, so #51 becomes one entry. Alternative: a one-off entity class like `EcovacsClearFaultButtonEntity`, less code now and a copy later.
5. **Entity name "Mow border"** (key `mow_border`, icon `mdi:vector-square`), next to the existing switch named "Edge cutting". Alternative: "Edge mowing", which reads closer to the switch and risks being taken for it.
6. **Issue #51 stays a separate PR.**

## One question for the reporter

The captured request carries `mid:2049987783`. The fixtures on PR #83 have their `mid` replaced, so nothing on record confirms that the id in the mower's map messages is the same id the app puts in the request. The design assumes it is — there is only one map — but a one-line confirmation from the raw log would turn the assumption into evidence before the branch is built. Suggested wording for issue #12, English, one paragraph, not hard-wrapped:

> One check before this gets built, if you still have the 30/08 log: does the `mid` in the `onMapInfo_V2` / `onMapTrace_V2` envelopes match the `mid:2049987783` the app sent in the border request? The plan is to take the id from the map messages the integration already receives rather than ask for it separately, and that only works if they agree.

Not posted; the maintainer decides whether and when.
