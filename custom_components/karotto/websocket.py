from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError

from .api import KarottoConnectionError
from .const import ATTR_CONFIG_ENTRY_ID
from .services import coordinator_for_entry

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

ALLOWED: list[tuple[str, re.Pattern[str]]] = [
    ("GET", re.compile(r"/auth/session")),
    ("GET", re.compile(r"/tasks(\?type=completedTodos)?")),
    ("GET", re.compile(r"/tags")),
    ("GET", re.compile(r"/cron/status")),
    ("POST", re.compile(r"/cron")),
    ("POST", re.compile(rf"/tasks/{UUID}/score/(up|down)")),
    ("POST", re.compile(rf"/tasks/{UUID}/checklist/{UUID}/score")),
    ("PATCH", re.compile(rf"/tasks/{UUID}")),
]


def is_allowed(method: str, path: str, body: Any) -> bool:
    """The card's board only reads, scores, rolls over and folds checklists."""
    if not any(method == allowed and pattern.fullmatch(path) for allowed, pattern in ALLOWED):
        return False
    if method == "PATCH":
        return (
            isinstance(body, dict)
            and body.keys() == {"collapseChecklist"}
            and isinstance(body["collapseChecklist"], bool)
        )
    return True


@callback
def async_setup_websocket(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_request)
    websocket_api.async_register_command(hass, ws_events)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "karotto/request",
        vol.Required("method"): vol.In(["GET", "POST", "PATCH"]),
        vol.Required("path"): str,
        vol.Optional("body"): object,
        vol.Optional("client_id"): str,
        vol.Optional(ATTR_CONFIG_ENTRY_ID): str,
    }
)
@websocket_api.async_response
async def ws_request(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        coordinator = coordinator_for_entry(hass, msg.get(ATTR_CONFIG_ENTRY_ID))
    except ServiceValidationError as error:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(error))
        return
    body = msg.get("body")
    if not is_allowed(msg["method"], msg["path"], body):
        connection.send_error(
            msg["id"],
            websocket_api.ERR_UNAUTHORIZED,
            f"{msg['method']} {msg['path']} is not available to the card",
        )
        return
    try:
        status, payload = await coordinator.client.forward(
            msg["method"], msg["path"], body, msg.get("client_id")
        )
    except KarottoConnectionError as error:
        connection.send_error(msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(error))
        return
    connection.send_result(msg["id"], {"status": status, "statusText": "", "body": payload})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "karotto/events",
        vol.Optional(ATTR_CONFIG_ENTRY_ID): str,
    }
)
@callback
def ws_events(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        coordinator = coordinator_for_entry(hass, msg.get(ATTR_CONFIG_ENTRY_ID))
    except ServiceValidationError as error:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, str(error))
        return

    @callback
    def relay(message: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], message))

    connection.subscriptions[msg["id"]] = coordinator.async_add_stream_listener(relay)
    connection.send_result(msg["id"])
