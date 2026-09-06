"""Device identity and model capability profiles for the patch layer.

The upstream Device already owns the authoritative device identity. This module
provides the patch-side profile selected from that identity, so model-specific
capability decisions have one home and firmware is available for future
compatibility rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deebot_client.device import Device


@dataclass(frozen=True)
class DeviceIdentity:
    """Stable hardware and software identity reported by Ecovacs."""

    device_class: str
    model: str | None
    firmware: str | None


@dataclass(frozen=True)
class MowerProfile:
    """Patch-side capability decisions for one mower class."""

    device_class: str
    area_parameters: bool = False


# Class identity is the first capability discriminator. Firmware is deliberately
# not used in profiles until a real firmware-dependent difference is established;
# the Device still retains it as part of DeviceIdentity for that future decision.
MOWER_PROFILES: dict[str, MowerProfile] = {
    "2i0fns": MowerProfile("2i0fns"),
    "9bts2s": MowerProfile("9bts2s"),
    "2px96q": MowerProfile("2px96q"),
    "77atlz": MowerProfile("77atlz"),
    "e4gqia": MowerProfile("e4gqia", area_parameters=True),
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
    """Return the patch profile selected by device class."""
    return MOWER_PROFILES.get(device_class)


def profile_for(device: Device) -> MowerProfile | None:
    """Return the patch profile selected for a device's class."""
    return profile_for_class(device.device_info["class"])
