"""What other clients — the Ecovacs app — ask the mower, and what it answers.

Supporting a setting means knowing its commands: what the app sends to change
it, and what it asks to read it back. The MQTT client receives both halves of
every such exchange as p2p messages, but only follows the ones it has a
command for, looked up by name in ``COMMANDS_WITH_MQTT_P2P_HANDLING``; any
other is logged as "does not support p2p handling (yet)" and dropped, and a
known one is turned into the library's own event without keeping the
request. So neither a new setting's commands nor the exact payloads of a
known one are visible.

While ``capture()`` is active, the JSON half of that table answers every
lookup with an observer, which publishes each exchange as a
``MowerAppTrafficEvent`` on the mower's bus once the mower has answered. For a
command the library knows, the observer hands the request and the answer to
the library's own command first, so its handling is unchanged. Outside a
capture the table answers exactly as the library's own: nothing is observed,
and nothing changes. The diagnostic button in ``debug.py`` is the only user.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deebot_client.events import Event
import orjson

if TYPE_CHECKING:
    from deebot_client.event_bus import EventBus


@dataclass(frozen=True)
class MowerAppTrafficEvent(Event):
    """One request another client sent the mower, and the mower's answer.

    ``request`` and ``response`` are the ``body.data`` of each half as JSON,
    in the key order they arrived in; ``response`` is None when the answer
    carried no data, as a set command's does. ``code`` is the answer's
    ``body.code``, 0 for accepted, None when it has none. ``channel`` is the
    request header's, e.g. ``Android``. ``at`` keeps two identical exchanges
    apart, which the bus would otherwise drop as a repeat, and lets a
    subscriber ignore one from before it subscribed.
    """

    command: str
    request: str
    response: str | None
    code: int | None
    channel: str | None
    at: datetime


def _body(payload: str | bytes | bytearray) -> tuple[dict[str, Any], dict[str, Any]]:
    """A message's header and body, either empty when the payload has none."""
    try:
        message = orjson.loads(payload)
    except orjson.JSONDecodeError:
        return {}, {}
    if not isinstance(message, dict):
        return {}, {}
    header, body = message.get("header"), message.get("body")
    return (
        header if isinstance(header, dict) else {},
        body if isinstance(body, dict) else {},
    )


def _json(value: Any) -> str:
    return orjson.dumps(value).decode()


class _ObservedRequest:
    """One request in flight: what was asked, and the library's own command."""

    def __init__(
        self, name: str, payload: str | bytes | bytearray, wrapped: Any
    ) -> None:
        self._name = name
        self._wrapped = wrapped
        header, body = _body(payload)
        self._request = _json(body.get("data", {}))
        channel = header.get("channel")
        self._channel = channel if isinstance(channel, str) else None

    def handle_mqtt_p2p(
        self, event_bus: EventBus, response: str | bytes | bytearray
    ) -> None:
        """Let the library handle the answer as before, then report the exchange."""
        if self._wrapped is not None:
            self._wrapped.handle_mqtt_p2p(event_bus, response)
        _, body = _body(response)
        code = body.get("code")
        event_bus.notify(
            MowerAppTrafficEvent(
                command=self._name,
                request=self._request,
                response=_json(body["data"]) if "data" in body else None,
                code=(
                    code
                    if isinstance(code, int) and not isinstance(code, bool)
                    else None
                ),
                channel=self._channel,
                at=datetime.now(UTC),
            )
        )


@dataclass(frozen=True)
class _Observer:
    """What the table hands the MQTT client in place of a command class.

    The client only ever calls ``create_from_mqtt(payload)`` on it, and
    ``handle_mqtt_p2p(event_bus, payload)`` on what that returns.
    """

    name: str
    wrapped: Any

    def create_from_mqtt(self, payload: str | bytes | bytearray) -> _ObservedRequest:
        # The library's command first, as it would have been: if it cannot
        # parse the request, it raises exactly as without a capture.
        wrapped = self.wrapped.create_from_mqtt(payload) if self.wrapped else None
        return _ObservedRequest(self.name, payload, wrapped)


_captures = 0


class ObservingTable(dict):
    """The library's p2p table for JSON, observing while a capture is active.

    A ``dict`` subclass so everything else that reads the table — iterating
    it, indexing it — sees the library's own entries unchanged. Only ``get``,
    the one call the MQTT client makes, answers differently, and only while
    ``capture()`` is active.
    """

    def get(self, name: str, default: Any = None) -> Any:  # type: ignore[override]
        command = super().get(name, default)
        if _captures == 0:
            return command
        return _Observer(name, command)


def capture() -> Callable[[], None]:
    """Observe app traffic until the returned callable is called.

    Counted, so two mowers' logs can overlap: observing stops when the last
    one ends. The returned callable is safe to call more than once.
    """
    global _captures
    _captures += 1
    stopped = False

    def stop() -> None:
        global _captures
        nonlocal stopped
        if not stopped:
            stopped = True
            _captures -= 1

    return stop


def reset() -> None:
    """Stop every capture. Tests only."""
    global _captures
    _captures = 0


__all__ = ["MowerAppTrafficEvent", "ObservingTable", "capture", "reset"]
