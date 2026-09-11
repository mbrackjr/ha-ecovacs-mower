"""Raw area-parameter refresh button."""

from tests import requires_ha

pytestmark = requires_ha


def test_raw_area_parameter_refresh_button_is_diagnostic_and_disabled_by_default() -> None:
    from homeassistant.const import EntityCategory

    from custom_components.ecovacs_mower.button import (
        AREA_PARAMETER_REFRESH_DESCRIPTION,
    )

    assert AREA_PARAMETER_REFRESH_DESCRIPTION.key == "refresh_raw_area_parameters"
    assert (
        AREA_PARAMETER_REFRESH_DESCRIPTION.entity_category
        is EntityCategory.DIAGNOSTIC
    )
    assert (
        AREA_PARAMETER_REFRESH_DESCRIPTION.entity_registry_enabled_default is False
    )


def test_raw_area_parameter_refresh_button_is_only_built_for_unmapped_area_models() -> None:
    from unittest.mock import MagicMock, patch

    from deebot_client.capabilities import DeviceType

    from custom_components.ecovacs_mower.button import (
        _area_parameter_refresh_entities,
    )

    device = MagicMock()
    device.device_info = {"did": "test-did", "class": "e4gqia"}
    device.capabilities.device_type = DeviceType.MOWER
    controller = MagicMock()
    controller.devices = [device]

    assert _area_parameter_refresh_entities(controller) == []

    with patch.dict(
        "custom_components.ecovacs_mower.button.AREA_PARAMETER_MAPPINGS",
        {},
        clear=True,
    ):
        entities = _area_parameter_refresh_entities(controller)

    assert len(entities) == 1
    assert entities[0].entity_description.key == "refresh_raw_area_parameters"
    assert entities[0]._device is device


async def test_raw_area_parameter_refresh_button_requests_area_refresh() -> None:
    from unittest.mock import MagicMock

    from custom_components.ecovacs_mower.button import (
        EcovacsAreaParameterRefreshButtonEntity,
    )
    from custom_components.ecovacs_mower.deebot_patch.areas import MowerAreaEvent

    device = MagicMock()
    device.device_info = {"did": "test-did", "class": "e4gqia"}
    entity = EcovacsAreaParameterRefreshButtonEntity(device, device.capabilities)

    await entity.async_press()

    device.events.request_refresh.assert_called_once_with(MowerAreaEvent)
