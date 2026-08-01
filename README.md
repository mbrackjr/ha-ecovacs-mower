# Ecovacs Mower for Home Assistant

A Home Assistant custom integration for Ecovacs GOAT robot mowers, built to
work around three defects in the upstream `ecovacs` integration that leave
GOAT mowers effectively unusable.

If you own a GOAT mower and its state in Home Assistant is stuck, and
start/pause do nothing, this is likely why:
[home-assistant/core#168621](https://github.com/home-assistant/core/issues/168621).

## What's broken, and what this fixes

Home Assistant's built-in `ecovacs` integration talks to Deebot vacuums and
GOAT mowers through the same library, `deebot-client`. For GOAT mowers,
three independent bugs in that path add up to a mower that can't be
controlled and barely reports its own state:

| Defect | Effect |
|---|---|
| Control commands are sent to the MQTT topic `iot/p2p/clean_V2` | GOAT firmware listens on `iot/p2p/clean` and ignores `clean_V2` entirely. `start_mowing` and `pause` do nothing. |
| State refresh uses the command `getCleanInfo_V2` | GOAT mowers never answer it. Polled state refreshes silently fail. |
| The unsolicited messages `onChargeInfo` and `onScheduleTaskInfo` have no handler | They're dropped as unknown messages. In practice this means the mower's state in Home Assistant only updates once a day, when it happens to reconnect and get polled. |

Net effect on the upstream integration: state lags by close to a day, and
the controls that are supposed to fix that don't work either.

This integration patches all three at the protocol layer (correct command,
correct refresh call, handlers for both missing messages) and exposes a
`lawn_mower` entity that reflects real state within seconds and responds to
start / pause / dock.

## Why a separate integration, instead of a fix upstream

The underlying library, `deebot-client`, currently has eight open pull
requests touching GOAT/mower support, the oldest opened in April. None have
merged. In the same period, vacuum and authentication changes to the same
library have merged within days. Two Home Assistant core pull requests
adding mower features were auto-closed as stale by the triage bot while
waiting on those library PRs to land.

This is not a criticism of the maintainers — they're volunteers, and review
bandwidth is finite. It's the reason a fork is the pragmatic way to get a
working mower today rather than waiting on a queue with no visible movement.

Relevant links, so you can check the state of things yourself:

- [DeebotUniverse/client.py#1624](https://github.com/DeebotUniverse/client.py/pull/1624) — fixes the `clean_V2` command (open)
- [DeebotUniverse/client.py#1647](https://github.com/DeebotUniverse/client.py/pull/1647) — adds the two missing message handlers (open, community-approved, no maintainer response)
- [DeebotUniverse/client.py#1650](https://github.com/DeebotUniverse/client.py/issues/1650) — `getCleanInfo_V2` not answered by GOAT hardware
- [DeebotUniverse/client.py#1587](https://github.com/DeebotUniverse/client.py/pull/1587) — RTK support
- [home-assistant/core#168621](https://github.com/home-assistant/core/issues/168621) — the user-facing symptom report this integration exists to fix
- [home-assistant/core#169723](https://github.com/home-assistant/core/issues/169723) — mowers exposed with vacuum terminology

This integration does not depend on any of those merging. If they do,
the corresponding patch in this repo becomes dead code and gets deleted.

## Requirements

- **Home Assistant 2026.7 or later.** This is a hard floor, not a
  suggestion. `deebot-client==18.5.1` (what this integration pins) requires
  `cryptography>=48.0.1` for its device-verification flow. Home Assistant
  2026.4.4 pins `cryptography==46.0.7`. Those two requirements cannot
  coexist, so the integration cannot load at all on HA 2026.4.4 or older —
  it will fail to install, not fail at runtime. If you're on an older
  release, upgrade Home Assistant first.
- HACS, if installing that way (see below). Not required for manual install.

## Hardware support

Verified on one device: **Ecovacs GOAT O1200 LiDAR Pro**, device class
`2i0fns`.

Other GOAT models (O800 RTK, A1600 RTK, and the rest of the GOAT line) share
the same three upstream defects described above, and would very likely work
with the same fix. They are not verified, because I don't own one.

If you install this on an unsupported model, the integration will still
load, but it will not patch that device's commands — meaning you'd be back
to the original symptoms (dead controls, stale state). It logs a warning
naming the device class it saw and didn't recognize, for example:

```
Gräsklipparklass <class> stöds inte av den här integrationen och används
opatchad: styrningen kommer sannolikt inte att fungera och tillståndet att
släpa. Rapportera modellen på <issue tracker> så kan den läggas till
```

("Mower class `<class>` is not supported by this integration and is used
unpatched: controls will likely not work and state will lag. Report the
model at `<issue tracker>` so it can be added.")

That device class string is exactly what to paste into a
[new issue](https://github.com/nord-/ha-ecovacs-mower/issues). Adding a
verified model to `SUPPORTED_CLASSES` is a small, low-risk change — this is
one of the more useful ways to contribute without touching Python.

## Installation

Remove Home Assistant's built-in `ecovacs` integration for this mower
first. Having both installed at once means two integrations racing to
control the same device.

### Via HACS (custom repository)

This integration is not in the HACS default store. Add it as a custom
repository:

1. HACS → the three-dot menu → **Custom repositories**
2. Repository: `nord-/ha-ecovacs-mower`, category: **Integration**
3. Install "Ecovacs Mower" from HACS
4. Restart Home Assistant
5. Settings → Devices & services → **Add integration** → search for
   "Ecovacs Mower"

### Manual

1. Copy `custom_components/ecovacs_mower` from this repository into your
   Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Settings → Devices & services → **Add integration** → search for
   "Ecovacs Mower"

### First-time setup: expect a verification code

Since July 2026, Ecovacs requires device verification for new client IDs
logging into an account. This integration registers as a new client,
separate from the built-in `ecovacs` integration, so the very first setup
will trigger it even if your account was already verified before.

During setup you may see error code `1013` ("Please update to the latest
version to continue") — this is that verification requirement, not a bug.
The config flow will prompt for a code emailed to your Ecovacs account.
Enter it and setup continues.

## What you get

One entity: `lawn_mower.<name>`, with:

- Real state (`mowing`, `paused`, `returning`, `docked`, `error`) that
  updates within seconds of the mower actually changing state, not once a
  day
- Working `start_mowing`, `pause`, and `dock` services

That's it for this release. Not included: sensors (battery, area mowed,
consumable lifespans), switches, buttons, RTK diagnostics, zone control, and
maps. All of those are planned but not built yet — this release is
deliberately scoped to fixing the broken part: state and control.

## Current status

The code is complete for this release and CI is green: hassfest validation,
HACS validation, and the test suite (78 tests) all pass. It has **not yet
been verified against real hardware** — that verification is the next step
before this is considered done, and hasn't happened yet. Install with that
in mind. If you try it and it works (or doesn't), an issue report — with
your device class from the warning above if it's not the O1200 — is useful
either way.

## License and credit

GPL-3.0. This project contains code derived from Home Assistant core's
`ecovacs` integration (Apache-2.0) and depends on `deebot-client`
(GPL-3.0). See [`NOTICE`](NOTICE) for the full attribution.
