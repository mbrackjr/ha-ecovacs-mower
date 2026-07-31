"""Antaganden om deebot-clients interna struktur.

Går något av dessa sönder har uppströms ändrat något vi hakat i. Bättre att
CI blir röd än att gräsklipparen tyst slutar rapportera.
"""

from dataclasses import fields

from deebot_client.capabilities import Capabilities
from deebot_client.hardware import _DEVICES
from deebot_client.messages.json import MESSAGES


def test_devices_cache_is_a_mutable_dict() -> None:
    assert isinstance(_DEVICES, dict)


def test_messages_registry_is_a_mutable_dict() -> None:
    assert isinstance(MESSAGES, dict)


def test_messages_registry_is_shared_by_reference() -> None:
    # messages/__init__.py håller en referens till samma objekt. Muterar vi
    # det på plats syns ändringen i get_message().
    from deebot_client.const import DataType
    from deebot_client.messages import MESSAGES as ALL_MESSAGES

    assert ALL_MESSAGES[DataType.JSON] is MESSAGES


def test_capabilities_has_the_fields_we_patch() -> None:
    names = {f.name for f in fields(Capabilities)}
    assert {"clean", "state", "device_type"} <= names


def test_capabilities_is_frozen() -> None:
    # Patchningen använder dataclasses.replace() just för att den är frozen.
    assert Capabilities.__dataclass_params__.frozen


def test_clean_info_v2_subclasses_clean_info() -> None:
    # Därför jämför verify_capabilities med exakt typ i stället för isinstance:
    # en GetCleanInfoV2-instans är en GetCleanInfo, så isinstance() hade
    # godkänt den opatchade uppsättningen och gjort kontrollen tandlös.
    # Slutar det här gälla kan kontrollen förenklas — men den är korrekt ändå.
    from deebot_client.commands.json.clean import GetCleanInfo, GetCleanInfoV2

    assert issubclass(GetCleanInfoV2, GetCleanInfo)
