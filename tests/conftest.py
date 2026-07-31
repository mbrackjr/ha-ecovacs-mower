"""Delad testuppsättning.

Home Assistant kan inte importeras på Windows: ``homeassistant/runner.py``
gör ett oskyddat ``import fcntl``, som är POSIX-only. Sanningskällan för
testresultat är därför CI på ubuntu-latest, där hela sviten körs.

Vakten nedan gör att protokoll-lagrets tester — ``tests/deebot_patch/``, som
bara rör ``deebot_client`` — ändå går att köra lokalt på Windows. Utan den
kraschar insamlingen av *alla* tester på plugin-importen.
"""

import sys

import pytest

# Vakten hindrar bara den explicita laddningen. Pluginet registrerar sig även
# som pytest11-entry point och autoladdas av pytest oberoende av den här filen.
# Lokalt på Windows krävs därför också flaggan:
#
#     python -m pytest tests/deebot_patch/ -p no:homeassistant -v
#
# Flaggan hör inte hemma i pytest.ini — CI behöver pluginet laddat.
_HA_AVAILABLE = sys.platform != "win32"

if _HA_AVAILABLE:
    pytest_plugins = "pytest_homeassistant_custom_component"

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        """Låt HA ladda custom_components under test."""
        return
