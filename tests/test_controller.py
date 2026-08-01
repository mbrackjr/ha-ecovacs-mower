"""Controllern får inte släpa med sig dammsugararvet.

Modulerna under test importerar Home Assistant, som inte går att importera på
Windows (``fcntl``). Importerna ligger därför inne i testfunktionerna och hela
filen är märkt ``requires_ha`` — annars kraschar redan insamlingen, innan någon
skip-markör hinner gälla. Sanningskällan är CI på ubuntu-latest.
"""

import ast
import inspect
from pathlib import Path
import textwrap

from . import requires_ha

pytestmark = requires_ha

# Register i deebot-client som bara deebot_patch/ får röra.
FORBIDDEN_MODULES = ("deebot_client.hardware", "deebot_client.messages")


def test_controller_does_not_import_sucks() -> None:
    from custom_components.ecovacs_mower import controller

    source = inspect.getsource(controller)
    assert "sucks" not in source
    assert "VacBot" not in source


def test_entity_module_does_not_import_sucks() -> None:
    from custom_components.ecovacs_mower import entity

    source = inspect.getsource(entity)
    assert "sucks" not in source


def test_controller_has_no_legacy_device_api() -> None:
    from custom_components.ecovacs_mower import controller

    for removed in ("legacy_devices", "add_legacy_entity", "legacy_entity_is_added"):
        assert not hasattr(controller.EcovacsController, removed)


def test_entity_module_has_no_legacy_base_class() -> None:
    from custom_components.ecovacs_mower import entity

    assert not hasattr(entity, "EcovacsLegacyEntity")


def test_controller_exposes_devices() -> None:
    from custom_components.ecovacs_mower import controller

    assert isinstance(
        inspect.getattr_static(controller.EcovacsController, "devices"), property
    )


def _call_order(func: object) -> list[str]:
    """Returnera namnen på anropen i *func*, i källkodsordning.

    AST i stället för strängsökning: kommentarerna i initialize() nämner
    ``get_devices()`` vid namn, och en indexsökning hade träffat kommentaren
    i stället för anropet.
    """
    source = textwrap.dedent(inspect.getsource(func))  # type: ignore[arg-type]
    found: list[tuple[int, int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = (
            target.attr
            if isinstance(target, ast.Attribute)
            else target.id
            if isinstance(target, ast.Name)
            else None
        )
        if name is not None:
            found.append((node.lineno, node.col_offset, name))
    return [name for _, _, name in sorted(found)]


def test_patch_runs_before_get_devices() -> None:
    """Patchen måste sådda cachen innan enheterna byggs.

    ``get_devices()`` anropar ``get_static_device_info()`` och bakar in
    resultatet i ``DeviceInfo.static``, en frozen dataclass. Sker patchen efter
    det anropet har enheterna redan fått de opatchade kapabiliteterna, och en
    cacheuppslagning ser ändå rätt ut. Verifieringen måste i sin tur ske efter
    ``get_devices()``, på det objekt enheten faktiskt fick.

    Notera vad testet bevisar: **källkodsordning, inte exekveringsordning.**
    Det skulle passera för ``if False: patch_device_info(...)`` eller för ett
    anrop som flyttats in i en hjälpfunktion som körs senare. Vad det fångar är
    den realistiska regressionen — att någon flyttar en rad.
    """
    from custom_components.ecovacs_mower import controller

    calls = _call_order(controller.EcovacsController.initialize)

    assert calls.index("patch_device_info") < calls.index("get_devices")
    assert calls.index("get_devices") < calls.index("verify_capabilities")


def test_verification_reads_static_device_info() -> None:
    """Verifieringen får inte slå upp i cachen — då bevisar den ingenting."""
    from custom_components.ecovacs_mower import controller

    source = inspect.getsource(controller.EcovacsController.initialize)
    assert "info.static.capabilities" in source


# En annan GOAT-klass än den enda i SUPPORTED_CLASSES. Samtliga 25
# MOWER-klasser i deebot-client 18.5.1 bär samma CleanV2/GetCleanInfoV2-fel,
# så den här enheten blir en entitet med döda reglage.
_OTHER_MOWER = "cr0e4u"
# T5PRO-dammsugare: giltig klass, DeviceType.VACUUM, blir aldrig en entitet.
_VACUUM = "npwtuz"


async def _initialize_with(hass: object, device_classes: tuple[str, ...]) -> None:
    """Kör ``initialize()`` med enheterna *device_classes* från API:et.

    Allt utanför verifieringsloopen mockas: get_devices, MQTT-klienten och
    Device. Det som testas är vilken gren en klass hamnar i, inte uppkoppling.
    """
    from unittest.mock import AsyncMock, MagicMock, patch

    from deebot_client.api_client import Devices
    from deebot_client.hardware import _DEVICES, get_static_device_info
    from deebot_client.models import DeviceInfo
    from homeassistant.const import (
        CONF_COUNTRY,
        CONF_DEVICE_ID,
        CONF_PASSWORD,
        CONF_USERNAME,
    )

    from custom_components.ecovacs_mower.controller import EcovacsController

    async def fake_get_devices() -> Devices:
        # Byggs vid anropet, inte i förväg: den riktiga get_devices() körs
        # efter patch_device_info() och plockar upp de patchade
        # kapabiliteterna ur cachen. Byggdes DeviceInfo innan initialize()
        # skulle den stödda klassen bära den opatchade definitionen och
        # verifieringen falla — på testets uppställning, inte på koden.
        return Devices(
            mqtt=[
                DeviceInfo(
                    {
                        "class": class_,
                        "company": "eco-ng",
                        "did": f"did-{class_}",
                        "name": f"name-{class_}",
                        "resource": "res",
                    },
                    await get_static_device_info(class_),
                )
                for class_ in device_classes
            ],
            xmpp=[],
            not_supported=[],
        )

    controller = EcovacsController(
        hass,  # type: ignore[arg-type]
        {
            CONF_DEVICE_ID: "STABLE-ID",
            CONF_COUNTRY: "SE",
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "hunter2",
        },
    )
    try:
        with (
            patch(
                "deebot_client.api_client.ApiClient.get_devices",
                AsyncMock(side_effect=fake_get_devices),
            ),
            patch.object(EcovacsController, "_get_mqtt_client", AsyncMock()),
            patch(
                "custom_components.ecovacs_mower.controller.Device",
                MagicMock(return_value=AsyncMock()),
            ),
        ):
            await controller.initialize()
    finally:
        await controller.teardown()
        # initialize() såddar cachen globalt; lämna den som vi fann den.
        for class_ in ("2i0fns", *device_classes):
            _DEVICES.pop(class_, None)


async def test_unsupported_mower_class_warns(hass, caplog) -> None:
    """En gräsklippare utanför SUPPORTED_CLASSES får inte tystna i debug.

    Den användaren får en entitet vars reglage är döda och vars tillstånd
    släpar — exakt produktionssymtomet projektet finns för att eliminera.
    Varningen ska namnge klassen, så att modellen går att rapportera och
    läggas till i SUPPORTED_CLASSES.
    """
    import logging

    from custom_components.ecovacs_mower.const import ISSUE_TRACKER_URL

    caplog.set_level(logging.DEBUG)
    await _initialize_with(hass, (_OTHER_MOWER,))

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert _OTHER_MOWER in message
    assert ISSUE_TRACKER_URL in message


async def test_vacuum_on_the_same_account_stays_quiet(hass, caplog) -> None:
    """Motprovet: en dammsugare är inget falsklarm värt.

    Utan det här testet vore ``elif ... is DeviceType.MOWER`` i controllern
    oprövat i sin negativa riktning, och en förenkling till "varna för allt
    som inte stöds" skulle passera grönt.
    """
    import logging

    caplog.set_level(logging.DEBUG)
    await _initialize_with(hass, (_VACUUM,))

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(_VACUUM in r.getMessage() for r in caplog.records)


async def test_supported_mower_is_verified(hass, caplog) -> None:
    """Den stödda klassen ska gå genom verifieringen, utan varning."""
    import logging

    caplog.set_level(logging.DEBUG)
    await _initialize_with(hass, ("2i0fns",))

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _forbidden_imports(path: Path) -> list[str]:
    """Returnera förbjudna uppströmsmoduler som importeras i *path*.

    Fyra former fångas:

    * ``import deebot_client.hardware``
    * ``from deebot_client.hardware import _DEVICES``
    * ``from deebot_client import hardware`` — innehåller aldrig strängen
      ``deebot_client.hardware``, så en substrängsökning hade missat den
    * ``deebot_client.hardware._DEVICES`` efter ett bart ``import deebot_client``
      — ren attributåtkomst, den mest närliggande läckan av alla eftersom den
      inte kräver något ovanligt av den som skriver koden

    Strängliteraler granskas också, så att
    ``import_module("deebot_client.hardware")`` inte slinker igenom.

    Gränsen går vid statisk analys. Detta fångas **inte**: alias
    (``import deebot_client as dc``), strängkonkatenering
    (``"deebot_client." + "hardware"``) och ``getattr``-indirektion. Den som
    vill runda vakten kan, men ingen gör det av misstag.

    Relativa importer släpps igenom med flit: ``from .deebot_patch.hardware
    import ...`` är nödutgången, och att tvätta uppströmsobjekt genom den är
    hela poängen med modulen.
    """

    def is_forbidden(name: str) -> bool:
        return any(name == m or name.startswith(f"{m}.") for m in FORBIDDEN_MODULES)

    def dotted_name(node: ast.Attribute) -> str | None:
        """Rekonstruera ``a.b.c`` ur en attributkedja rotad i ett namn."""
        parts = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        parts.append(current.id)
        return ".".join(reversed(parts))

    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if is_forbidden(a.name))
        elif isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            if is_forbidden(module):
                found.append(module)
            elif module == "deebot_client":
                found.extend(
                    f"deebot_client.{a.name}"
                    for a in node.names
                    if is_forbidden(f"deebot_client.{a.name}")
                )
        elif isinstance(node, ast.Attribute):
            if (name := dotted_name(node)) and is_forbidden(name):
                found.append(name)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if is_forbidden(node.value):
                found.append(node.value)

    # ast.walk besöker varje led i en attributkedja, så samma läcka kan
    # rapporteras flera gånger. Dedupliceras för läsbar felutskrift.
    return list(dict.fromkeys(found))


def test_only_deebot_patch_touches_upstream_internals() -> None:
    """Upprätthåll isoleringsconstrainten mekaniskt.

    Hela poängen med deebot_patch/ är att en vendrad klient ska kunna ersätta
    den utan att någon entitetsfil ändras. Läcker en import av deebot-clients
    hardware- eller messages-register ut i övriga filer är den garantin borta,
    och ingen märker det förrän uppströms refaktorerar.
    """
    from custom_components.ecovacs_mower import controller

    package = Path(controller.__file__).parent
    offenders = []

    for path in package.rglob("*.py"):
        if "deebot_patch" in path.parts:
            continue
        for name in _forbidden_imports(path):
            offenders.append(f"{path.relative_to(package)}: {name}")

    assert not offenders, (
        "Endast deebot_patch/ får röra deebot-clients interna register. "
        f"Läckor: {offenders}"
    )


def test_constraint_check_catches_a_leak(tmp_path: Path) -> None:
    """Constraintstestet ska faktiskt fånga en läcka, i varje form det påstår."""
    leaks = (
        "from deebot_client.hardware import _DEVICES",
        "from deebot_client import hardware",
        "import deebot_client.messages.json",
        'import_module("deebot_client.hardware")',
        "import deebot_client\n_DEVICES = deebot_client.hardware._DEVICES\n",
    )
    for index, leak in enumerate(leaks):
        path = tmp_path / f"leak{index}.py"
        path.write_text(leak, encoding="utf-8")
        assert _forbidden_imports(path), f"missade läcka: {leak}"

    # Nödutgången måste fortsätta släppas igenom — att nå uppströmsobjekt via
    # deebot_patch är hela poängen med modulen.
    clean = tmp_path / "clean.py"
    clean.write_text(
        "from deebot_client.device import Device\n"
        "from .deebot_patch.hardware import SUPPORTED_CLASSES\n"
        "from . import deebot_patch\n"
        "_DEVICES = deebot_patch.hardware.SUPPORTED_CLASSES\n",
        encoding="utf-8",
    )
    assert not _forbidden_imports(clean)
