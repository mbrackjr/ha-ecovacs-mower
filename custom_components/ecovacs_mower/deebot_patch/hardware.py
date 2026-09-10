"""Seeds deebot-client's device cache with corrected capabilities.

``get_static_device_info()`` reads the ``_DEVICES`` cache before importing the
device module. By letting the library build its own definition, swapping out the
broken parts and putting the result back, we avoid monkeypatching any function —
we use the same mechanism the library itself uses.

This module also owns the supported mower-class profiles. The profile records
only integration capabilities that have been independently validated for a
specific class; raw protocol parsing remains in the patch layer and
human-facing interpretation remains in the HA layer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from types import MappingProxyType

from deebot_client.capabilities import CapabilityEvent
from deebot_client.events import StateEvent, StatsEvent
from deebot_client.hardware import _DEVICES, get_static_device_info

from .areas import MowerAreaEvent
from .area_commands import GetAreaParameter, GetAreaSet
from .commands import (
    CleanMower,
    GetLifeSpanMower,
    GetMapInfoV2,
    GetProtectState,
    GetRainDelay,
    GetStatsMower,
    MowerStateRefresh,
)
from .map_messages import MowerMapInfoEvent
from .messages import (
    MowerBeaconsEvent,
    MowerProtectStateEvent,
    MowerRainDelayEvent,
    MowerStatsEvent,
)
from .zonal import MowArea

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MowerProfile:
    """Validated integration capabilities for one supported mower class."""

    device_class: str
    area_parameters: bool = False


# Device classes this integration patches, and how each one was confirmed:
#   2i0fns — GOAT O1200 LiDAR Pro (owner-verified)
#   9bts2s — GOAT O800 RTK (user-verified, issue #8)
#   2px96q — GOAT O800 RTK (user-verified, issue #24). A second class string
#            for the same hardware: upstream's 2px96q.py is byte-identical to
#            9bts2s.py.
#   77atlz — GOAT G1-800 (issue #30, firmware 1.36.208 — controls
#            user-verified from the lawn_mower entity, issue #74: start,
#            pause/resume and dock all obeyed on 0.7.2). Upstream's 77atlz.py
#            is byte-identical to 9bts2s.py, docstring included, so the O800
#            RTK's patch applies unchanged — but this firmware branch inverts
#            the quirk the patch exists for. Issue #42 has the A/B on one
#            install: patched, getCleanInfo answers errno 500 on every poll
#            and clean is never acknowledged; unpatched, getCleanInfo_V2
#            answers first try and clean_V2 is acked in 526 ms. The class
#            stays here because the family is now chosen at runtime rather
#            than by this tuple — see families.py.
#   e4gqia — GOAT A1600 LiDAR Pro (confirmed, PR #29, firmware 1.11.31).
#            Upstream names this A3000 LiDAR Pro; its module is byte-identical
#            to 9bts2s.py apart from the docstring, so the O800's patch
#            applies unchanged.
#   xmp9ds — GOAT A1600 RTK (reported in issue #43, firmware 1.17.9 — the
#            reporter has not confirmed the patch yet). A different machine
#            from e4gqia above, not a second class string for it: the RTK and
#            LiDAR Pro variants of the A1600 ship separately. Upstream's
#            xmp9ds.py is byte-identical to 9bts2s.py apart from the docstring,
#            which here names the model outright ("DEEBOT GOAT A1600 RTK
#            Capabilities"), so the O800 RTK's patch applies unchanged.
#
# Presence in this mapping means the class is supported by the integration.
# Capability flags are deliberately narrower: they are enabled only where the
# corresponding behavior or raw-value semantics have been independently
# validated on that class. Similar protocol field names on another class are
# not sufficient evidence to enable a capability there.
SUPPORTED_CLASSES: dict[str, MowerProfile] = {
    "2i0fns": MowerProfile("2i0fns"),
    "9bts2s": MowerProfile("9bts2s"),
    "2px96q": MowerProfile("2px96q"),
    "77atlz": MowerProfile("77atlz"),
    "e4gqia": MowerProfile("e4gqia", area_parameters=True),
    "xmp9ds": MowerProfile("xmp9ds"),
}

ZONE_AREA_CLASSES = ("e4gqia",)
BORDER_CLASSES = ("77atlz",)


def profile_for_class(class_: str) -> MowerProfile | None:
    """Return the validated integration profile for a device class."""
    return SUPPORTED_CLASSES.get(class_)


async def patch_device_info(class_: str) -> None:
    """Replace the cached device definition with one where the mower bugs are fixed."""
    if class_ not in SUPPORTED_CLASSES:
        _LOGGER.debug("Device class %s not supported, not patching", class_)
        return

    base = await get_static_device_info(class_)
    if base is None:
        _LOGGER.debug("No device definition for %s, skipping patch", class_)
        return

    capabilities = base.capabilities
    profile = profile_for_class(class_)
    area_parameters = profile is not None and profile.area_parameters
    if capabilities.clean.action.command is CleanMower and not area_parameters:
        return

    patched = replace(
        capabilities,
        clean=replace(
            capabilities.clean,
            action=replace(
                capabilities.clean.action,
                command=CleanMower,
                area=(
                    MowArea
                    if class_ in ZONE_AREA_CLASSES
                    else capabilities.clean.action.area
                ),
            ),
        ),
        state=CapabilityEvent(StateEvent, [MowerStateRefresh()]),
        stats=replace(
            capabilities.stats,
            clean=CapabilityEvent(StatsEvent, [GetStatsMower()]),
        ),
        life_span=replace(
            capabilities.life_span,
            get=[GetLifeSpanMower(capabilities.life_span.types)],
        ),
    )

    events = {
        **patched._events,
        MowerProtectStateEvent: [GetProtectState()],
        MowerRainDelayEvent: [GetRainDelay()],
        MowerStatsEvent: [GetStatsMower()],
        MowerBeaconsEvent: [GetLifeSpanMower(capabilities.life_span.types)],
        MowerMapInfoEvent: [GetMapInfoV2()],
    }
    if area_parameters:
        events[MowerAreaEvent] = [GetAreaParameter(), GetAreaSet()]

    object.__setattr__(patched, "_events", MappingProxyType(events))
    _DEVICES[class_] = replace(base, capabilities=patched)
    _LOGGER.debug("Patched capabilities for %s", class_)
