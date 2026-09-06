"""Seeds deebot-client's device cache with corrected capabilities.

``get_static_device_info()`` reads the ``_DEVICES`` cache before importing the
device module. By letting the library build its own definition, swapping out the
broken parts and putting the result back, we avoid monkeypatching any function —
we use the same mechanism the library itself uses.

The patch's device profiles are kept separately in ``device.py``. This module
only applies the protocol corrections and wires the corresponding refresh
commands into the library's capability graph.
"""

from __future__ import annotations

from dataclasses import replace
import logging
from types import MappingProxyType

from deebot_client.capabilities import CapabilityEvent
from deebot_client.events import StateEvent, StatsEvent
from deebot_client.hardware import _DEVICES, get_static_device_info

from .areas import GetAreaParameter, GetAreaSet, MowerAreaEvent
from .commands import (
    CleanMower,
    GetLifeSpanMower,
    GetProtectState,
    GetRainDelay,
    GetStatsMower,
    MowerStateRefresh,
)
from .device import MOWER_PROFILES, profile_for_class
from .messages import (
    MowerBeaconsEvent,
    MowerProtectStateEvent,
    MowerRainDelayEvent,
    MowerStatsEvent,
)

_LOGGER = logging.getLogger(__name__)

# Device classes this integration patches, and how each one was confirmed:
#   2i0fns — GOAT O1200 LiDAR Pro (owner-verified)
#   9bts2s — GOAT O800 RTK (user-verified, issue #8)
#   2px96q — GOAT O800 RTK (user-verified, issue #24). A second class string
#            for the same hardware: upstream's 2px96q.py is byte-identical to
#            9bts2s.py.
#   77atlz — GOAT G1-800 (issue #30, firmware 1.36.208 — controls not
#            confirmed). Upstream's 77atlz.py is byte-identical to 9bts2s.py,
#            docstring included, so the O800's patch applies unchanged —
#            but this firmware branch inverts the quirk the patch exists for.
#            Issue #42 has the A/B on one install: patched, getCleanInfo
#            answers errno 500 on every poll and clean is never acknowledged;
#            unpatched, getCleanInfo_V2 answers first try and clean_V2 is
#            acked in 526 ms. The class stays here because the family is now
#            chosen at runtime rather than by this tuple — see families.py.
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
SUPPORTED_CLASSES = tuple(MOWER_PROFILES)


async def patch_device_info(class_: str) -> None:
    """Replace the cached device definition with one where the mow bugs are fixed.

    Five corrections:

    * ``clean.action.command``: ``CleanV2`` publishes on ``clean_V2``, which
      GOAT firmware ignores. Swapped for ``CleanMower`` on ``clean``.
    * ``state``: the clean-info answer is a constant ``idle`` regardless of
      what the mower is actually doing (issue #48), and the library ran the
      charge and clean-info answers concurrently in one ``TaskGroup`` — a race
      that let a mower parked on its charger read as docked or as paused
      depending on which answer landed last (issue #67). Swapped for
      ``MowerStateRefresh``, one sequential command that awaits the charge half
      before asking for clean info, so the record is written before the clean-
      info answer is interpreted; the clean-info half picks its own command name,
      ``getCleanInfo`` or ``getCleanInfo_V2``, from whichever the mower answers at
      runtime — see ``families.py``.
    * ``stats.clean``: ``GetStats`` drops ``mowedArea``, the one number that
      moves while a job runs. Swapped for ``GetStatsMower``.
    * ``life_span.get``: ``GetLifeSpan`` raises on the ``uwbCell`` entries a
      beacon-guided mower reports, which loses the beacons and every component
      listed after them. Swapped for ``GetLifeSpanMower``.
    * ``MowerProtectStateEvent``, ``MowerRainDelayEvent``, ``MowerStatsEvent``
      and ``MowerBeaconsEvent``: given the refresh commands they had none of.

    The call is idempotent and does nothing for classes outside
    ``SUPPORTED_CLASSES``.

    **Must be called before ``ApiClient.get_devices()``.** That method calls
    ``get_static_device_info()`` and bakes the result into ``DeviceInfo.static``,
    which is a frozen dataclass. Patching the cache afterwards means the devices
    already got the unpatched capabilities.
    """
    if class_ not in SUPPORTED_CLASSES:
        _LOGGER.debug("Device class %s not supported, not patching", class_)
        return

    base = await get_static_device_info(class_)
    if base is None:
        _LOGGER.debug("No device definition for %s, skipping patch", class_)
        return

    capabilities = base.capabilities
    if capabilities.clean.action.command is CleanMower:
        return

    patched = replace(
        capabilities,
        clean=replace(
            capabilities.clean,
            action=replace(capabilities.clean.action, command=CleanMower),
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
    }
    profile = profile_for_class(class_)
    if profile is not None and profile.area_parameters:
        # One area event represents the whole area capability. The two protocol
        # reads populate one authoritative snapshot before notifying that event.
        events[MowerAreaEvent] = [GetAreaParameter(), GetAreaSet()]

    object.__setattr__(patched, "_events", MappingProxyType(events))
    _DEVICES[class_] = replace(base, capabilities=patched)
    _LOGGER.debug("Patched capabilities for %s", class_)
