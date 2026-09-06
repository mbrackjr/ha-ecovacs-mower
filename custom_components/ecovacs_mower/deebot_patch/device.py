"""Device identity and model capability profiles for the patch layer.

The upstream Device already owns the authoritative device identity. This module
provides the patch-side profile selected from that identity, so model-specific
behaviour has one home and firmware is available for future compatibility rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from deebot_client.device import Device


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
# the Device still retains it as part of DeviceIdentity for that future decision.
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


def identity_for(device: Device) -> DeviceIdentity:
    """Return the device identity already established by deebot-client."""
    info = device.device_info
    return DeviceIdentity(
        device_class=info["class"],
        model=info.get("deviceName"),
        firmware=device.fw_version,
    )


def profile_for_class(device_class: str) -> MowerProfile | None:
    """Return the model profile selected by device class."""
    return MOWER_PROFILES.get(device_class)


def profile_for(device: Device) -> MowerProfile | None:
    """Return the model profile selected for a device's class."""
    return profile_for_class(device.device_info["class"])
