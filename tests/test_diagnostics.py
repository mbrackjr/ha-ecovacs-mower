"""REDACT must mask everything upstream core masks.

The module under test imports Home Assistant (via ``diagnostics.py``, which in
turn imports the package's ``__init__``), which cannot be imported on Windows
(``fcntl``). The imports therefore live inside the test functions and the whole
file is marked ``requires_ha`` — otherwise collection itself crashes before any
skip marker gets a chance to apply. The source of truth is CI on ubuntu-latest.
"""

from . import requires_ha

pytestmark = requires_ha


def test_redact_covers_everything_core_redacts() -> None:
    """The contract, not a one-off observation.

    homeassistant/components/ecovacs/diagnostics.py masks CONF_USERNAME,
    CONF_PASSWORD, "title", CONF_OVERRIDE_MQTT_URL, CONF_OVERRIDE_REST_URL
    (config) plus "did", CONF_NAME, "homeId" (device). "title" is not needed here
    — we dump entry.data, not entry.as_dict() — but the rest must be present,
    otherwise a diagnostics report leaks data a user shares publicly.
    """
    from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME

    from custom_components.ecovacs_mower.const import (
        CONF_OVERRIDE_MQTT_URL,
        CONF_OVERRIDE_REST_URL,
    )
    from custom_components.ecovacs_mower.diagnostics import REDACT

    must_redact = {
        CONF_USERNAME,
        CONF_PASSWORD,
        CONF_OVERRIDE_MQTT_URL,
        CONF_OVERRIDE_REST_URL,
        "did",
        CONF_NAME,
        "homeId",
    }
    assert must_redact <= REDACT


def test_redact_covers_the_fork_specific_leaks() -> None:
    """Three keys upstream never had to mask.

    * ``CONF_DEVICE_ID``: core never persists the client's device ID — it
      generates a new one on every start, which *is* the 1013 bug. We store it in
      ``entry.data``, so it reaches the dump. Self-hosted, the value is
      ``HA-{slugify(location_name)}`` (the home name, PII); in cloud mode it is
      the verified client identity, which combined with a leaked account skips
      email verification.
    * ``nick``/``resource``: present in ``ApiDeviceInfo`` and carried straight
      into the dump, since ``device.device_info`` *is* the raw api dict.
      ``resource`` is the other half of the MQTT topic.
    """
    from homeassistant.const import CONF_DEVICE_ID

    from custom_components.ecovacs_mower.diagnostics import REDACT

    from custom_components.ecovacs_mower.const import CONF_CREDENTIALS

    # CONF_CREDENTIALS is the account access token, which mints portal
    # credentials on its own: leaking it is leaking the account.
    assert {CONF_DEVICE_ID, CONF_CREDENTIALS, "nick", "resource"} <= REDACT


def test_device_info_keys_are_covered_or_deliberately_public() -> None:
    """Every key in ApiDeviceInfo must be a deliberate decision.

    ``device.device_info`` returns the api dict unabridged. If upstream adds a
    key, this line must go red, so that somebody actually takes a position
    instead of letting it leak out in a diagnostics report pasted into a GitHub
    issue.
    """
    from deebot_client.models import ApiDeviceInfo

    from custom_components.ecovacs_mower.diagnostics import REDACT

    # Deliberately unmasked: the model class and manufacturer are not identifying
    # and are exactly what you need to debug an issue.
    public = {"class", "company", "deviceName"}

    assert set(ApiDeviceInfo.__annotations__) <= REDACT | public


def test_keys_observed_on_real_hardware_are_covered_or_deliberately_public() -> None:
    """The TypedDict is not the payload.

    ``ApiDeviceInfo`` declares a subset. ``api_client.py`` feeds raw API JSON
    straight into it, so a real mower's ``device.device_info`` carries keys the
    annotations never mention — and the test above, which walks
    ``__annotations__``, is structurally blind to every one of them. ``homeId``
    was already masked for exactly this reason; it was added by hand, because
    nothing could have failed to point at it.

    This is the key set one GOAT G1-800 (``77atlz``, firmware 1.36.208) put
    in its payload, which is the shape that actually reaches a diagnostics
    report. It is what caught ``btMac``: a Bluetooth MAC shipping in the
    clear past a REDACT that listed ``mac`` and therefore looked like it
    covered the case. Another class or firmware may carry keys this one does
    not; a second observed set belongs here as a union, not a replacement.

    Keys only, never values — the point of the file this guards is that real
    values do not get published, and a fixture is not an exception to that.
    """
    from custom_components.ecovacs_mower.diagnostics import REDACT

    observed = {
        "did",
        "name",
        "class",
        "resource",
        "company",
        "bindTs",
        "service",
        "deviceName",
        "icon",
        "ota",
        "UILogicId",
        "materialNo",
        "pid",
        "product_category",
        "model",
        "updateInfo",
        "nick",
        "homeId",
        "homeSort",
        "status",
        "btName",
        "btMac",
        "otaUpgrade",
        "networkMode",
    }

    # Deliberately unmasked, in three groups.
    #
    # Model identity ("class", "deviceName", "model", "pid", "materialNo",
    # "product_category", "UILogicId", "icon", "company") describes which machine
    # this is, not whose: it is shared by every unit of the same product, and it
    # is the first thing anyone triaging an issue needs.
    #
    # Firmware and connectivity posture ("ota", "otaUpgrade", "updateInfo",
    # "networkMode", "status") is state, not identity, and a report without it
    # cannot distinguish a stale firmware from a broken patch layer.
    #
    # "service" is the regional endpoint pair (which Ecovacs datacenter answers
    # this account) and "bindTs" is when the mower was bound. Regional and
    # coarse rather than personal, and both change the interpretation of an
    # authentication failure — the class of bug this fork exists for.
    # "homeSort" is this device's ordinal within a household whose "homeId" is
    # already masked, so on its own it names nothing.
    public = {
        "class",
        "company",
        "deviceName",
        "model",
        "pid",
        "materialNo",
        "product_category",
        "UILogicId",
        "icon",
        "ota",
        "otaUpgrade",
        "updateInfo",
        "networkMode",
        "status",
        "service",
        "bindTs",
        "homeSort",
    }

    assert observed <= REDACT | public


async def test_the_dump_itself_redacts_and_not_only_the_set() -> None:
    """The set is not the behaviour.

    Every other test in this file asserts something about REDACT's *contents*.
    None of them calls the function, so dropping ``async_redact_data`` from
    either branch of the dump — or reaching for ``device.device_info`` a second
    time somewhere below — would leave all of them green while the report goes
    out in full. This one reads the output.

    ``async_get_config_entry_diagnostics`` never touches ``hass``, so the entry
    and its controller are plain stubs rather than a set-up config entry: the
    contract under test is what comes back, not how the entry was loaded.

    Placeholder values throughout, and deliberately so — a test that pins
    redaction is the last place a real identifier should appear.
    """
    from unittest.mock import MagicMock

    from homeassistant.components.diagnostics import REDACTED

    from custom_components.ecovacs_mower.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    device = MagicMock()
    device.device_info = {
        "did": "test-did",
        "resource": "test-resource",
        "btMac": "00:00:00:00:00:XX",
        "btName": "GOAT-0000",
        "class": "77atlz",
        # Nested, because the raw api dict nests and the mower's real payload
        # repeats identifiers below the top level. Redaction has to recurse.
        "service": {"jmq": "jmq.example.net", "did": "test-did"},
    }

    entry = MagicMock()
    entry.data = {
        "username": "user@example.com",
        "password": "password",
        "country": "IT",
    }
    entry.runtime_data.devices = [device]

    dump = await async_get_config_entry_diagnostics(None, entry)
    config = dump["config"]
    (reported,) = dump["devices"]

    assert config["username"] == REDACTED
    assert config["password"] == REDACTED
    assert reported["did"] == REDACTED
    assert reported["resource"] == REDACTED
    assert reported["btMac"] == REDACTED
    assert reported["btName"] == REDACTED
    assert reported["service"]["did"] == REDACTED

    # The other half of the contract: a redacted report has to stay useful.
    # Country and device class are what someone triaging reads first.
    assert config["country"] == "IT"
    assert reported["class"] == "77atlz"


async def _dump_with_a_latched_fault() -> dict:
    """A two-mower dump: one holding fault 406, one with no latch at all.

    The faulted mower's latch is a real ``FaultLatch`` on a real bus, driven the
    way the controller drives it, so the dump reads what the latch actually
    holds rather than what a stub says it holds. The other mower has no entry in
    ``fault_latches`` — the shape for a device the controller never latched.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, Mock

    from deebot_client.event_bus import EventBus
    from deebot_client.events import ErrorEvent

    from custom_components.ecovacs_mower.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    from custom_components.ecovacs_mower.fault import FaultLatch

    faulted = MagicMock()
    faulted.device_info = {"did": "faulted-did", "class": "77atlz"}
    faulted.events = EventBus(
        AsyncMock(), Mock(get_refresh_commands=lambda _event: [])
    )
    latch = FaultLatch(faulted)
    latch.subscribe()
    faulted.events.notify(
        ErrorEvent(406, "Blade-disc blocked! Blade-disc cannot rotate.")
    )
    for _ in range(4):
        await asyncio.sleep(0)

    healthy = MagicMock()
    healthy.device_info = {"did": "healthy-did", "class": "77atlz"}

    entry = MagicMock()
    entry.data = {"country": "IT"}
    entry.runtime_data.devices = [faulted, healthy]
    entry.runtime_data.fault_latches = {"faulted-did": latch}

    return await async_get_config_entry_diagnostics(None, entry)


async def test_the_dump_carries_the_latched_fault_with_its_device() -> None:
    """Issue #65: the latch is per-device state the dump could not show.

    The code and its description ride along in the device's own entry. Both
    are safe to publish as they are — the code is a number from the device and
    the text is a fixed English string from ``errors.py`` or deebot-client.
    """
    faulted, healthy = (await _dump_with_a_latched_fault())["devices"]

    assert faulted["fault_code"] == 406
    assert (
        faulted["fault_description"]
        == "Blade-disc blocked! Blade-disc cannot rotate."
    )
    assert healthy["fault_code"] is None
    assert healthy["fault_description"] is None


async def test_no_did_reaches_the_dump_in_key_position() -> None:
    """The trap issue #65 names, pinned for every future section.

    ``controller.fault_latches`` is keyed by ``did``, and so are ``maps`` and
    the map stores. ``async_redact_data`` replaces the *value* under a redacted
    key and never looks at keys themselves, so publishing any of those dicts
    as-is would put the identifier exactly where redaction does not reach.
    Serialising the whole dump and searching it covers keys, values and every
    level of nesting in one assertion.
    """
    import json

    dump = await _dump_with_a_latched_fault()

    assert "faulted-did" not in json.dumps(dump)
    assert "healthy-did" not in json.dumps(dump)
