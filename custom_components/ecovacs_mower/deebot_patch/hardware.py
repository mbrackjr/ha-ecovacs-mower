"""Såddar deebot-clients enhetscache med rättade kapabiliteter.

``get_static_device_info()`` läser cachen ``_DEVICES`` innan den importerar
enhetsmodulen. Genom att låta biblioteket bygga sin definition, byta ut de
trasiga delarna och lägga tillbaka resultatet slipper vi monkeypatcha någon
funktion — vi använder samma mekanism som biblioteket självt.
"""

from __future__ import annotations

from dataclasses import replace
import logging

from deebot_client.capabilities import CapabilityEvent
from deebot_client.commands.json.charge_state import GetChargeState
from deebot_client.commands.json.clean import GetCleanInfo
from deebot_client.events import StateEvent
from deebot_client.hardware import _DEVICES, get_static_device_info

from .commands import CleanMower

_LOGGER = logging.getLogger(__name__)

# Enhetsklasser fas 1 stöder. Verifierad hårdvara: O1200 LiDAR Pro.
SUPPORTED_CLASSES = ("2i0fns",)


async def patch_device_info(class_: str) -> None:
    """Ersätt cachad enhetsdefinition med en där klippfelen är rättade.

    Två rättelser:

    * ``clean.action.command``: ``CleanV2`` publicerar på ``clean_V2``, som
      GOAT-firmware ignorerar. Byts mot ``CleanMower`` på ``clean``.
    * ``state``: ``GetCleanInfoV2`` besvaras inte av GOAT. Byts mot
      ``GetCleanInfo``.

    Anropet är idempotent och gör ingenting för klasser utanför
    ``SUPPORTED_CLASSES``.

    **Måste anropas före ``ApiClient.get_devices()``.** Den metoden anropar
    ``get_static_device_info()`` och bakar in resultatet i ``DeviceInfo.static``,
    som är en frozen dataclass. Patchar man cachen efteråt har enheterna redan
    fått de opatchade kapabiliteterna.
    """
    if class_ not in SUPPORTED_CLASSES:
        _LOGGER.debug("Device class %s not supported by phase 1, not patching", class_)
        return

    base = await get_static_device_info(class_)
    if base is None:
        # Uppströms returnerar None för okända klasser; ingen fallbackdefinition
        # finns, så här är det inget att patcha.
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
        state=CapabilityEvent(StateEvent, [GetChargeState(), GetCleanInfo()]),
    )
    _DEVICES[class_] = replace(base, capabilities=patched)
    _LOGGER.debug("Patched capabilities for %s", class_)
