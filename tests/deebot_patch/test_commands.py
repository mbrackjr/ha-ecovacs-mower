"""Tester för mower-anpassade kommandon."""

from deebot_client.commands.json.clean import Clean, CleanV2
from deebot_client.models import CleanAction

from custom_components.ecovacs_mower.deebot_patch.commands import CleanMower


def test_publishes_to_clean_topic_not_clean_v2() -> None:
    # Kärnan i buggen: GOAT lyssnar på "clean", inte "clean_V2".
    assert CleanMower.NAME == "clean"
    assert CleanV2.NAME == "clean_V2"


def test_is_a_clean_command() -> None:
    assert issubclass(CleanMower, Clean)


def test_start_uses_v2_content_shape() -> None:
    command = CleanMower(CleanAction.START)
    assert command._args == {"act": "start", "content": {"type": "auto"}}


def test_pause_uses_v2_content_shape() -> None:
    # Till skillnad från CleanV2, som skickar tom typ vid paus, echoar vi
    # "auto" — det är vad appen gör mot en gräsklippare.
    command = CleanMower(CleanAction.PAUSE)
    assert command._args == {"act": "pause", "content": {"type": "auto"}}


def test_resume_uses_v2_content_shape() -> None:
    command = CleanMower(CleanAction.RESUME)
    assert command._args == {"act": "resume", "content": {"type": "auto"}}


def test_stop_uses_v2_content_shape() -> None:
    command = CleanMower(CleanAction.STOP)
    assert command._args == {"act": "stop", "content": {"type": "auto"}}
