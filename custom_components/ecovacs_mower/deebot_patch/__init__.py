"""Isolerad koppling mot deebot-clients interna register.

Detta är den enda modulen i integrationen som får röra privata delar av
deebot-client. Byts biblioteket ut mot en vendrad klient är det bara den
här mappen som skrivs om.
"""

from __future__ import annotations

from importlib.metadata import version
import logging
from typing import NoReturn

from deebot_client.capabilities import Capabilities
from deebot_client.commands.json.clean import GetCleanInfo
from deebot_client.events import StateEvent
from deebot_client.hardware import _DEVICES
from deebot_client.messages.json import MESSAGES

from .commands import CleanMower
from .hardware import SUPPORTED_CLASSES, patch_device_info
from .messages import OnChargeInfo, OnScheduleTaskInfo

__all__ = [
    "SUPPORTED_CLASSES",
    "CleanMower",
    "PatchContractError",
    "apply",
    "patch_device_info",
    "verify_capabilities",
]

_LOGGER = logging.getLogger(__name__)


class PatchContractError(Exception):
    """deebot-client ser inte ut som patchlagret förväntar sig."""


def _fail(what: str) -> NoReturn:
    installed = version("deebot-client")
    raise PatchContractError(
        f"deebot-client {installed} does not match what ecovacs_mower expects: "
        f"{what}. The integration refuses to start rather than silently stop "
        f"reporting the mower's state. Report at "
        f"https://github.com/nord-/ha-ecovacs-mower/issues"
    )


def apply() -> None:
    """Registrera våra meddelandehandlare. Idempotent."""
    if not isinstance(_DEVICES, dict):
        _fail("deebot_client.hardware._DEVICES is not a dict")
    if not isinstance(MESSAGES, dict):
        _fail("deebot_client.messages.json.MESSAGES is not a dict")

    # Muteras på plats: messages/__init__.py håller en referens till samma
    # objekt, och en ombindning skulle därför inte synas i get_message().
    for message in (OnChargeInfo, OnScheduleTaskInfo):
        MESSAGES[message.NAME] = message

    if MESSAGES.get("onChargeInfo") is not OnChargeInfo:
        _fail("registration of onChargeInfo did not take")
    if MESSAGES.get("onScheduleTaskInfo") is not OnScheduleTaskInfo:
        _fail("registration of onScheduleTaskInfo did not take")

    _LOGGER.debug("Message handlers registered")


def verify_capabilities(capabilities: Capabilities, class_: str) -> None:
    """Bekräfta att kapabiliteterna en enhet faktiskt fick är de patchade.

    Kontrollen görs mot objektet i ``DeviceInfo.static``, inte mot cachen.
    Det är den enda kontroll som bevisar att patchen hann före
    ``get_devices()`` — en cacheuppslagning skulle se rätt ut även om
    enheten byggts av en opatchad definition.
    """
    if capabilities.clean.action.command is not CleanMower:
        _fail(
            f"device {class_} was built with {capabilities.clean.action.command.__name__} "
            f"instead of CleanMower — the patch ran too late"
        )

    # Exakt typjämförelse, inte isinstance: GetCleanInfoV2 ärver GetCleanInfo,
    # så isinstance() hade godkänt precis den opatchade uppsättning vi vill
    # fånga. Kontrollen hade varit tandlös.
    commands = capabilities.get_refresh_commands(StateEvent)
    if not any(type(c) is GetCleanInfo for c in commands):
        _fail(f"GetCleanInfo is missing from the state commands for {class_}")
