"""get_supported_entities kräver HA-importer och körs därför i CI."""

from tests import requires_ha

pytestmark = requires_ha


def test_only_devices_with_the_capability_get_an_entity() -> None:
    """Beskrivningar vars capability_fn ger None ska inte bli entiteter.

    Det är den här filtreringen som gör att en gräsklippare slipper
    dammsugarentiteter utan att vi behöver räkna upp dem.
    """
    from dataclasses import dataclass
    from unittest.mock import Mock

    from custom_components.ecovacs_mower.entity import (
        EcovacsCapabilityEntityDescription,
    )
    from custom_components.ecovacs_mower.util import get_supported_entities

    @dataclass(kw_only=True, frozen=True)
    class _Description(EcovacsCapabilityEntityDescription):
        pass

    has_it = _Description(key="has_it", capability_fn=lambda caps: caps.battery)
    lacks_it = _Description(key="lacks_it", capability_fn=lambda caps: caps.water)

    device = Mock()
    device.capabilities.battery = object()
    device.capabilities.water = None
    controller = Mock()
    controller.devices = [device]

    created = get_supported_entities(controller, Mock, (has_it, lacks_it))

    assert len(created) == 1
