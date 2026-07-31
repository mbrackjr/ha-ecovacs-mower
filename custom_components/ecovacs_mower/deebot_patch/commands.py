"""Kommandon anpassade för GOAT-gräsklippare.

Biblioteket kopplar alla GOAT-klasser till ``CleanV2``, som publicerar på
``iot/p2p/clean_V2``. Klipparens firmware lyssnar på ``iot/p2p/clean`` och
ignorerar clean_V2 helt, vilket ger "No response received for command
clean_V2" och gör start och paus verkningslösa.

``CleanMower`` ärver ``Clean`` (topic ``clean``) men skickar V2-formaterad
nyttolast, vilket är vad Ecovacs egen app gör.

Motsvarar DeebotUniverse/client.py PR #1624, utan dess cachning av aktiv
klipptyp — den behövs bara för customArea, som ligger utanför scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deebot_client.commands.json.clean import Clean
from deebot_client.models import CleanMode

if TYPE_CHECKING:
    from deebot_client.models import CleanAction


class CleanMower(Clean):
    """Klippkommando: topicen ``clean`` med V2-nyttolast."""

    def _get_args(self, action: CleanAction) -> dict[str, Any]:
        return {"act": action.value, "content": {"type": CleanMode.AUTO.value}}
