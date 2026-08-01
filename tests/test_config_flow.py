"""Config flow, med tonvikt på enhetsverifieringen som löser felkod 1013.

Home Assistant kan inte importeras på Windows (``fcntl``), se
``tests/conftest.py``. Importerna ligger därför inne i testfunktionerna och
hela filen är märkt ``requires_ha`` — annars kraschar redan insamlingen.
Sanningskällan är CI på ubuntu-latest.
"""

from unittest.mock import patch

from custom_components.ecovacs_mower.const import CONF_VERIFICATION_CODE, DOMAIN

from . import requires_ha

pytestmark = requires_ha

_AUTHENTICATOR = "custom_components.ecovacs_mower.config_flow.Authenticator"
_VALIDATE_MQTT = "custom_components.ecovacs_mower.config_flow._validate_mqtt"

AUTH = {
    "username": "someone@example.com",
    "password": "hunter2",
    "country": "SE",
}


async def _start(hass):
    from homeassistant.config_entries import SOURCE_USER

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"mode": "cloud"}
    )


async def test_happy_path_creates_entry(hass) -> None:
    from homeassistant.const import CONF_DEVICE_ID, CONF_USERNAME
    from homeassistant.data_entry_flow import FlowResultType

    with (
        patch(_AUTHENTICATOR, autospec=True),
        patch(_VALIDATE_MQTT, return_value={}),
    ):
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], AUTH
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == AUTH[CONF_USERNAME]
    assert result["data"][CONF_DEVICE_ID]


async def test_verification_required_shows_code_step(hass) -> None:
    from deebot_client.exceptions import DeviceVerificationRequiredError
    from homeassistant.data_entry_flow import FlowResultType

    with patch(_AUTHENTICATOR, autospec=True) as authenticator:
        authenticator.return_value.authenticate.side_effect = (
            DeviceVerificationRequiredError
        )
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], AUTH
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device_verification"


async def test_bad_verification_code_reports_error(hass) -> None:
    from deebot_client.exceptions import (
        DeviceVerificationRequiredError,
        InvalidVerificationCodeError,
    )
    from homeassistant.data_entry_flow import FlowResultType

    with patch(_AUTHENTICATOR, autospec=True) as authenticator:
        authenticator.return_value.authenticate.side_effect = (
            DeviceVerificationRequiredError
        )
        authenticator.return_value.verify_device.side_effect = (
            InvalidVerificationCodeError
        )
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], AUTH
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VERIFICATION_CODE: "000000"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_verification_code"}


async def test_device_id_is_persisted_after_verification(hass) -> None:
    # Kärnan i 1013-fixen: samma klient-ID måste återanvändas vid varje
    # inloggning, annars kräver Ecovacs ny verifiering.
    from deebot_client.exceptions import DeviceVerificationRequiredError
    from homeassistant.const import CONF_DEVICE_ID
    from homeassistant.data_entry_flow import FlowResultType

    with (
        patch(_AUTHENTICATOR, autospec=True) as authenticator,
        patch(_VALIDATE_MQTT, return_value={}),
    ):
        authenticator.return_value.authenticate.side_effect = (
            DeviceVerificationRequiredError
        )
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], AUTH
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_VERIFICATION_CODE: "123456"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_ID]
