# Ecovacs Mower for Home Assistant

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Home Assistant custom integration (`custom_components/ecovacs_mower`) for Ecovacs GOAT lawn mowers. It's a **fork of HA core's `ecovacs` integration** with XMPP/legacy support cut out (MQTT-only), plus a patch layer that fixes three bugs in `deebot-client` that make the GOAT uncontrollable. See README.md for the bug descriptions and links to the upstream PRs.

## Commands

```bash
# Full suite — requires Linux/CI
python -m pytest tests/ -v

# Single file / test
python -m pytest tests/test_sensor.py -v
python -m pytest tests/test_sensor.py::test_name -v

# Locally on Windows: only the protocol layer can run
python -m pytest tests/deebot_patch/ -p no:homeassistant -v

pip install -r requirements-test.txt
```

**Home Assistant can't be imported on Windows** (`homeassistant/runner.py` does an unguarded `import fcntl`). Therefore:

- Anything that imports HA lives in a file marked `pytestmark = requires_ha` (from `tests/__init__.py`).
- `-p no:homeassistant` is required locally because `pytest_homeassistant_custom_component` auto-loads as an entry point — the flag does **not** belong in `pytest.ini`, CI needs the plugin.
- The source of truth for test results is CI (`.github/workflows/test.yml`, ubuntu-latest, Python 3.14). Never claim the suite is green based on a Windows run.

CI also runs hassfest and HACS validation (`.github/workflows/hassfest.yml`). The HACS job's `topics` error is expected — it only applies to listing in the default store. The `brands` check is explicitly ignored in the workflow for the same reason.

Releases are cut by `.github/workflows/release.yml`, which runs after the test suite succeeds on `master`: if the version in `manifest.json` has no matching `v<version>` tag, it creates the tag and publishes a release with generated notes. A push whose version is already tagged is a no-op, so the bump commit is what triggers a release — never a hand-made tag.

## Architecture

### The patch layer is the only connection to deebot-client's internals

`deebot_patch/` is the boundary: **no other module may touch private parts of `deebot_client`** (`_DEVICES`, `MESSAGES`, `_AuthClient`). If the library is swapped for a vendored client, only that folder needs rewriting.

Prefer the repository's established `deebot_patch` modules before introducing new architectural structure. Protocol commands belong in `commands.py`, protocol/domain state belongs in the existing feature-specific patch module, and upstream capability corrections belong in `hardware.py`. Add a new patch module or abstraction only when the existing structure cannot accommodate the functionality cleanly, or when the benefit of the separation clearly outweighs the additional conceptual surface. Preserve existing module boundaries unless there is a concrete reason to change them.

- `commands.py` — `CleanMower` and `GetCleanInfoMower`, family-adaptive wrappers that send whichever of the V2/non-V2 command pair the mower actually answers on (issue #42), and `MowerStateRefresh`, which replaces the library's two concurrent state commands with one sequential command so the charge half is recorded before the clean-info half is interpreted (issue #67). New patch protocol commands should normally be added here rather than creating another command module.
- `hardware.py` — `SUPPORTED_CLASSES` is the authoritative supported-device registry. Each entry identifies a supported device class and records additional capabilities that have been independently validated for that class. `patch_device_info()` seeds the `_DEVICES` cache with corrected `Capabilities` (`CleanMower` + `capabilities.state = [MowerStateRefresh()]`). Uses the library's own caching mechanism instead of monkeypatching. Membership means basic integration support; a capability flag means the corresponding behavior has been validated on that specific class.
- `areas.py` — authoritative dynamic mower-area state and the protocol parsing needed to populate it. Area identity/count is learned at runtime, so this is an explicit dynamic feature exception rather than a static capability description.
- `messages.py` — `OnChargeInfo` and `OnScheduleTaskInfo`, the two unsolicited messages the library lacks a handler for.
- `families.py` — which of the V2/non-V2 command pair a given mower answers on, keyed by `did` and learned at runtime rather than from the class string (issue #42).
- `state_precedence.py` — per-device record, keyed by `EventBus`, that prefers "docked" over a paused plan and remembers what a suppressed state was (issue #67).
- `authentication.py` — `AccountAuthenticator`, which renews the session from the `uid`/`accessToken` pair a login or a device verification returns instead of re-posting the password. Backport of the still-open DeebotUniverse/client.py#1743. It wraps two name-mangled privates of `_AuthClient` on the instance; the pair is persisted in `entry.data[CONF_CREDENTIALS]` by the config flow and read back by the controller. Without it, Ecovacs' `1013` answer to the password login sends the entry into an endless reauth loop (issue #21).
- `__init__.py` — `apply()` (registers the messages, idempotent) and `verify_capabilities()`.

### Device identity and model-specific capability resolution

Device identity is established by `deebot-client` on `Device` creation. The patch layer must treat the device class/model as the primary capability discriminator and retain firmware as first-class identity metadata. Do not duplicate that identity as a second authoritative state store when the `Device` already owns it.

`hardware.py` owns the patch-side `SUPPORTED_CLASSES` registry. Its entries may decide whether a protocol capability exists for a verified device class, but they must not contain model- or firmware-specific conversion from raw device values to human-sensible Home Assistant values.

**Raw-value representation boundary:** `deebot_patch` owns the Ecovacs wire format and raw protocol values only. Any model- or firmware-specific interpretation of those raw values — for example, mapping a numeric mow-height level to centimetres, a cut-mode level to metres per second, an obstacle-height code to centimetres, or a wire-space angle to an HA/app-space angle — lives exclusively in the HA layer. Such mappings must be selected there from the actual device identity and must never be generalized from one mower to another without independent validation. Firmware-specific representation is subject to the same rule even when the protocol field names are identical.

**Validated-capability boundary:** A capability whose raw values or human-sensible representation has only been validated on specific mower classes must be explicitly restricted to those classes. Do not advertise, enable, or generalize that capability to other classes merely because their protocol fields look similar. Add another class only after its area data and semantics have been independently validated on that hardware.

Do not scatter model/class/firmware capability conditionals through HA platforms. The HA layer may select its representation mapping from the patch/device identity, but the mapping itself belongs only to HA. The patch must not import HA modules or depend on HA units, entity semantics, or presentation values.

Feature state belongs below HA. For dynamic mower areas, `deebot_patch` owns one authoritative `area_id -> MowerArea` snapshot containing the stable numeric area ID, optional friendly name, and raw protocol parameter values. HA must consume that snapshot and must not maintain a second authoritative copy of area state.

### Mower area capability

The area capability is a dynamic exception analogous to beacon discovery: area IDs/count are learned at runtime rather than declared in the static capability list. The patch exposes one `MowerAreaEvent` containing the complete area snapshot. Its refresh capability owns both active reads (`getAreaParameter` and `getAreaSet`); HA subscribes to that single event and requests that refresh without knowing the Ecovacs wire format.

`getAreaSet` establishes the mower's current area inventory and friendly names. `getAreaParameter` enriches those areas with the four raw parameters. The handlers write the authoritative state before notifying the event because `EventBus.notify` deduplicates equal events before subscriber callbacks and subscriptions are asynchronous.

Area entity identity is based only on numeric `areaID`. Friendly names are mutable metadata and may change without changing HA entity identity. The current implementation has four writable A1600 views: each write must use one cohesive `setAreaParameter` operation that merges the changed field into the authoritative area's complete raw state before sending the mower command. The write path must never maintain a second per-entity copy of the other parameters.

The four current area settings are dynamic `number` entities because their identity/count is learned at runtime. Their HA-unit mappings remain exclusively in the HA layer and are enabled only for mower classes whose raw-value semantics have been independently validated. Do not create four independent protocol commands or four independent protocol state stores.

### The order in `EcovacsController.initialize()` is a hard invariant

```
apply() → patch_device_info(each SUPPORTED_CLASS) → get_devices() → verify_capabilities()
```

`get_devices()` bakes the capabilities into `DeviceInfo.static`, a frozen dataclass. Patching afterwards means the devices already got the unpatched ones. `verify_capabilities()` therefore checks **the object the device actually received**, not the cache — a cache lookup would look correct regardless.

Failing fast is intentional: if `deebot-client` doesn't look like the patch layer expects, it raises `PatchContractError` → `ConfigEntryError`, and the integration refuses to start rather than silently stop reporting the mower's state. `tests/deebot_patch/test_contract.py` catches the same assumptions in CI.

### State derived from the event stream is written by the handlers, never by a subscription

`EventBus.notify` drops an event equal to the previous one of the same type **before** any subscriber runs, and it dispatches subscribers through `create_task`. So a subscription is neither complete nor synchronous: it misses every repeat, and repeats are ordinary — the captured telemetry has two `CLEANING` pushes sixteen seconds apart.

Anything this integration needs to remember about what the mower reported is therefore written inside the handlers it owns, before they notify. `deebot_patch/state_precedence.py` is the worked example (issue #67), and `MowerTriggerEvent._seq` is the same hazard met from the other side — an event deliberately made unequal to its predecessor so the bus cannot swallow it.

Subscribing is still right for *reacting* to a state — `fault.py` and the entity platforms do exactly that. The rule is about deriving and holding state, not about consuming it.

### Entity platforms

`lawn_mower` filters on `device_type is DeviceType.MOWER`. The others (`sensor`, `switch`, `number`, `button`, `event`) are built declaratively: an `ENTITY_DESCRIPTIONS` tuple of `EcovacsCapabilityEntityDescription` subclasses with `capability_fn`, fed through `util.get_supported_entities()`. New entities are added as an entry in that tuple — not as a new class.

Dynamic entities are the explicit exception when entity identity/count cannot be known until runtime, as with beacons and mower areas. Such exceptions should still reuse `EcovacsDescriptionEntity`/standard HA descriptions and remain a thin projection of patch-owned state; they must not introduce a parallel entity architecture or a second authoritative state store.

`entity.py` has the base classes (`EcovacsEntity`, `EcovacsDescriptionEntity`); subscribing to events happens via `_subscribe()` in `async_added_to_hass`. Commands go out through `_execute_command()`, never `self._device.execute_command()` directly — the wrapper is what logs an unconfirmed command under this integration's own logger instead of leaving it to `deebot_client` (issue #26).

## Conventions

- **This is a public repo — all outward-facing text is English**: docstrings, comments, commit messages, PR descriptions, issue/discussion replies. Code identifiers are English too. Forked modules open their docstring with what was removed compared to core.
- **Preserve existing remarks:** do not delete, rewrite, condense, or move existing comments/docstrings/remarks when changing code. Existing remarks carry architectural rationale, hardware evidence, issue references, and operational constraints. The only allowed changes are (a) comments/docstrings we add ourselves, (b) small corrections to an existing remark when the underlying fact is actually corrected, or (c) a narrowly scoped clarification required by a functionality change. Do not treat comment cleanup as part of refactoring.
- Comments explain *why*, especially where the code looks needlessly convoluted (exact type comparison instead of `isinstance`, in-place mutation instead of rebinding). Don't remove them to "clean up".
- `strings.json` and `translations/en.json` must be **identical** — `test_translations.py` guards this, nothing syncs them automatically. Never create an `sv.json`; the HA frontend's language here is English.
- Every translation key and `icons.json` key must belong to a real entity — the platform tests check both directions.
- New hardware is supported by adding the device class to `SUPPORTED_CLASSES`. Unsupported MOWER classes log a warning with the class string; that's the string users are asked to report. Additional capability flags in `SUPPORTED_CLASSES` must only be enabled after independent validation on that class.
- Prefer the existing `deebot_patch` modules and established repository patterns for new protocol work. Introduce a new module or abstraction only when the existing structure cannot accommodate it cleanly or the benefits clearly outweigh the additional surface area.
- Version is bumped in `manifest.json`, and that bump is what publishes a release once it lands on `master` (see above). The bump belongs in its own commit by the maintainer after the work has landed, never in a feature PR: `release.yml` tags whatever version it finds without checking that it is newer than the last tag, so two branches bumping in parallel publish releases out of order. `deebot-client` is pinned there and in `requirements-test.txt` — keep them in sync.
- Conventional commits, no AI attribution.
