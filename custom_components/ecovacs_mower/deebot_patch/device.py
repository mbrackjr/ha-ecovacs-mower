"""Device identity and model capability profiles for the patch layer.

The patch resolves hardware identity before feature code runs. Firmware is kept
with that identity so a future firmware-dependent behavior can be selected in
one place without scattering version checks through the integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable
from weakref import WeakKeyDictionary

if TYPE_CHECKING:
    from deebot_client.device import Device
    from deebot_client.event_bus import EventBus


@dataclass(frozen=True)
class DeviceIdentity:
    """Stable hardware and software identity reported by Ecovacs."""

    device_class: str
    model: str | None
    firmware: str | None


@dataclass(frozen=True)
class AreaParameterMapping:
    """Model-specific conversion between wire values and HA values."""

    mow_height: Callable[[int], float | None]
    cut_speed: Callable[[int], float | None]
    obstacle_height: Callable[[int], int | None]
    cut_angle: Callable[[int], int | None]


@dataclass(frozen=True)
class MowerProfile:
    """Capabilities and compatibility decisions for one mower class."""

    device_class: str
    area_parameters: bool = False
    area_mapping: AreaParameterMapping | None = None


def _a1600_mow_height(level: int) -> float | None:
    """Convert A1600 mow-height level to centimetres."""
    if level not in range(1, 8):
        return None
    return float(10 - level)


def _a1600_cut_speed(level: int) -> float | None:
    """Convert A1600 cut-mode level to metres per second."""
    if level not in range(1, 8):
        return None
    return round(0.40 + 0.05 * (7 - level), 2)


def _a1600_obstacle_height(level: int) -> int | None:
    """Convert A1600 obstacle-height level to centimetres."""
    return {1: 10, 2: 15, 3: 20}.get(level)


def _a1600_cut_angle(wire_angle: int) -> int | None:
    """Convert an A1600 wire-space angle to the app-space angle."""
    if wire_angle not in range(360):
        return None
    return (270 - wire_angle) % 360


A1600_AREA_MAPPING = AreaParameterMapping(
    mow_height=_a1600_mow_height,
    cut_speed=_a1600_cut_speed,
    obstacle_height=_a1600_obstacle_height,
    cut_angle=_a1600_cut_angle,
)


# Class identity is the first capability discriminator. Firmware is deliberately
# not used in profiles until a real firmware-dependent difference is established;
# identity still retains it for that future decision.
MOWER_PROFILES: dict[str, MowerProfile] = {
    "2i0fns": MowerProfile("2i0fns"),
    "9bts2s": MowerProfile("9bts2s"),
    "2px96q": MowerProfile("2px96q"),
    "77atlz": MowerProfile("77atlz"),
    "e4gqia": MowerProfile(
        "e4gqia", area_parameters=True, area_mapping=A1600_AREA_MAPPING
    ),
    "xmp9ds": MowerProfile("xmp9ds"),
}

_IDENTITIES: WeakKeyDictionary[EventBus, DeviceIdentity] = WeakKeyDictionary()


def register_device(device: Device) -> DeviceIdentity:
    """Record device identity before the device starts its MQTT event stream."""
    info = device.device_info
    identity = DeviceIdentity(
        device_class=info["class"],
        model=info.get("deviceName"),
        firmware=device.fw_version,
    )
    _IDENTITIES[device.events] = identity
    return identity


def identity_for(event_bus: EventBus) -> DeviceIdentity | None:
    """Return the identity registered for an event bus."""
    return _IDENTITIES.get(event_bus)


def profile_for_class(device_class: str) -> MowerProfile | None:
    """Return the model profile selected by device class."""
    return MOWER_PROFILES.get(device_class)


def profile_for(event_bus: EventBus) -> MowerProfile | None:
    """Return the model profile selected for a registered device."""
    identity = identity_for(event_bus)
    return profile_for_class(identity.device_class) if identity else None


def reset() -> None:
    """Forget device identity. Tests only."""
    _IDENTITIES.clear()
