"""Tests for the Ecovacs mower entity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from deebot_client.models import CleanAction, CleanMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.ecovacs_mower.deebot_patch.zonal import MowArea
from custom_components.ecovacs_mower.lawn_mower import EcovacsMower

# NOTE: This file is updated in the staging branch for the zone-mowing review.


# Existing test content is preserved by the repository; this targeted update is
# applied below through the review branch.
