"""Såddningen av enhetsregistret."""

import pytest
from deebot_client.commands.json.charge_state import GetChargeState
from deebot_client.commands.json.clean import CleanV2, GetCleanInfo, GetCleanInfoV2
from deebot_client.events import StateEvent
from deebot_client.hardware import _DEVICES, get_static_device_info

from custom_components.ecovacs_mower.deebot_patch.commands import CleanMower
from custom_components.ecovacs_mower.deebot_patch.hardware import (
    SUPPORTED_CLASSES,
    patch_device_info,
)

O1200 = "2i0fns"


def test_o1200_is_supported() -> None:
    assert O1200 in SUPPORTED_CLASSES


@pytest.fixture(autouse=True)
def _clear_cache():
    """Töm bibliotekets cache mellan testerna."""
    _DEVICES.pop(O1200, None)
    yield
    _DEVICES.pop(O1200, None)


async def test_unpatched_library_uses_the_broken_command() -> None:
    # Dokumenterar buggen vi rättar: uppströms kopplar O1200 till CleanV2.
    info = await get_static_device_info(O1200)
    assert info.capabilities.clean.action.command is CleanV2


async def test_unpatched_library_refreshes_state_with_clean_info_v2() -> None:
    # Dokumenterar den andra buggen: GOAT besvarar inte getCleanInfo_V2.
    info = await get_static_device_info(O1200)
    commands = info.capabilities.get_refresh_commands(StateEvent)
    assert any(type(c) is GetCleanInfoV2 for c in commands)
    assert not any(type(c) is GetCleanInfo for c in commands)

    # Längden är ingen godtycklig siffra — ta inte bort den.
    #
    # patch_device_info() bygger ett helt nytt CapabilityEvent med exakt två
    # kommandon i stället för att byta ut det enda trasiga. Det är korrekt så
    # länge uppströms lista också är just [GetChargeState, GetCleanInfoV2],
    # men lägger uppströms till ett tredje state-kommando skulle vår patch
    # tappa det spårlöst — och övriga assertions här skulle inte märka något,
    # eftersom de bara kontrollerar närvaro och frånvaro av två typer.
    #
    # Blir raden röd: avgör om det nya kommandot ska följa med i patchen
    # (troligen ja) och uppdatera hardware.py, inte bara siffran.
    assert [type(c).__name__ for c in commands] == ["GetChargeState", "GetCleanInfoV2"]


async def test_patch_swaps_in_clean_mower() -> None:
    await patch_device_info(O1200)
    info = await get_static_device_info(O1200)
    assert info.capabilities.clean.action.command is CleanMower


async def test_patch_swaps_clean_info_v2_for_clean_info() -> None:
    await patch_device_info(O1200)
    info = await get_static_device_info(O1200)
    commands = info.capabilities.get_refresh_commands(StateEvent)
    # Exakt typ, inte isinstance: GetCleanInfoV2 ärver GetCleanInfo, så
    # isinstance() hade passerat även utan patch och testet varit meningslöst.
    assert any(type(c) is GetCleanInfo for c in commands)
    assert not any(type(c) is GetCleanInfoV2 for c in commands)
    assert any(type(c) is GetChargeState for c in commands)


async def test_patch_preserves_untouched_capabilities() -> None:
    before = await get_static_device_info(O1200)
    battery_before = before.capabilities.battery
    lifespans_before = before.capabilities.life_span.types
    _DEVICES.pop(O1200, None)

    await patch_device_info(O1200)
    after = await get_static_device_info(O1200)

    assert after.capabilities.battery == battery_before
    assert after.capabilities.life_span.types == lifespans_before


async def test_patch_is_idempotent() -> None:
    await patch_device_info(O1200)
    await patch_device_info(O1200)
    info = await get_static_device_info(O1200)
    assert info.capabilities.clean.action.command is CleanMower


async def test_unknown_device_class_is_left_alone() -> None:
    # Okänd klass ska inte krascha. Verifierat i 18.5.1: get_static_device_info
    # returnerar None vid ModuleNotFoundError, det finns ingen fallbackdefinition.
    await patch_device_info("nonexistent_class")
    assert "nonexistent_class" not in _DEVICES


async def test_unsupported_class_is_not_patched() -> None:
    # T5PRO-dammsugare (npwtuz) är en giltig klass i biblioteket men ligger
    # utanför SUPPORTED_CLASSES. Den ska inte röras.
    from deebot_client.hardware import _DEVICES as cache

    cache.pop("npwtuz", None)
    await patch_device_info("npwtuz")
    assert "npwtuz" not in cache


async def test_apply_registers_both_handlers() -> None:
    from deebot_client.messages.json import MESSAGES

    from custom_components.ecovacs_mower.deebot_patch import apply
    from custom_components.ecovacs_mower.deebot_patch.messages import (
        OnChargeInfo,
        OnScheduleTaskInfo,
    )

    apply()
    assert MESSAGES["onChargeInfo"] is OnChargeInfo
    assert MESSAGES["onScheduleTaskInfo"] is OnScheduleTaskInfo


async def test_apply_is_idempotent() -> None:
    from deebot_client.messages.json import MESSAGES

    from custom_components.ecovacs_mower.deebot_patch import apply
    from custom_components.ecovacs_mower.deebot_patch.messages import (
        OnChargeInfo,
        OnScheduleTaskInfo,
    )

    apply()
    apply()

    # Utan de här hävdandena består testet enbart på att apply():s egen
    # efterkontroll skulle ha kastat — det står då inte på egna ben.
    assert MESSAGES["onChargeInfo"] is OnChargeInfo
    assert MESSAGES["onScheduleTaskInfo"] is OnScheduleTaskInfo


async def test_get_message_finds_the_registered_handlers() -> None:
    # Det är den här vägen biblioteket faktiskt slår upp meddelanden.
    from deebot_client.messages import get_message

    from custom_components.ecovacs_mower.deebot_patch import apply
    from custom_components.ecovacs_mower.deebot_patch.messages import OnChargeInfo

    apply()
    info = await get_static_device_info(O1200)
    assert get_message("onChargeInfo", info) is OnChargeInfo


async def test_verify_capabilities_passes_after_patching() -> None:
    from custom_components.ecovacs_mower.deebot_patch import verify_capabilities

    await patch_device_info(O1200)
    info = await get_static_device_info(O1200)
    verify_capabilities(info.capabilities, O1200)


async def test_verify_capabilities_raises_on_unpatched_object() -> None:
    from custom_components.ecovacs_mower.deebot_patch import (
        PatchContractError,
        verify_capabilities,
    )

    info = await get_static_device_info(O1200)
    with pytest.raises(PatchContractError, match="too late"):
        verify_capabilities(info.capabilities, O1200)


async def test_get_devices_path_produces_patched_capabilities() -> None:
    """Positivprovet: enheten som byggs av get_devices() bär CleanMower.

    Det här är testet som hade fångat ordningsfelet. Cachen kan se korrekt ut
    samtidigt som DeviceInfo.static bär de opatchade kapabiliteterna, så det
    räcker inte att kontrollera _DEVICES. Testet går dessutom via bibliotekets
    riktiga kodväg: slutar get_devices() någon gång läsa cachen blir det rött.
    """
    from unittest.mock import AsyncMock

    from deebot_client.api_client import ApiClient

    authenticator = AsyncMock()
    authenticator.post_authenticated.return_value = {
        "devices": [{"did": "abc123", "class": O1200, "company": "eco-ng"}]
    }

    await patch_device_info(O1200)  # före get_devices, precis som i controllern
    devices = await ApiClient(authenticator).get_devices()

    assert len(devices.mqtt) == 1
    assert devices.mqtt[0].static.capabilities.clean.action.command is CleanMower


async def test_get_devices_without_patch_is_broken() -> None:
    """Motprovet: utan patch bygger get_devices() enheten med CleanV2.

    Börjar det här testet fela har uppströms rättat buggen och vår patch kan
    tas bort.
    """
    from unittest.mock import AsyncMock

    from deebot_client.api_client import ApiClient

    authenticator = AsyncMock()
    authenticator.post_authenticated.return_value = {
        "devices": [{"did": "abc123", "class": O1200, "company": "eco-ng"}]
    }

    devices = await ApiClient(authenticator).get_devices()

    assert devices.mqtt[0].static.capabilities.clean.action.command is CleanV2


async def test_patch_must_run_before_get_devices() -> None:
    """Regressionsskydd för ordningsfelet.

    ApiClient.get_devices() bakar in kapabiliteterna i DeviceInfo.static, som
    är en frozen dataclass. Patchas cachen efteråt får enheten ändå de gamla.
    """
    from deebot_client.models import DeviceInfo

    from custom_components.ecovacs_mower.deebot_patch import (
        PatchContractError,
        verify_capabilities,
    )

    # Så här ser det ut när patchen kom för sent:
    stale = await get_static_device_info(O1200)
    device_info = DeviceInfo({"class": O1200, "did": "x"}, stale)
    await patch_device_info(O1200)  # för sent för device_info

    with pytest.raises(PatchContractError):
        verify_capabilities(device_info.static.capabilities, O1200)
