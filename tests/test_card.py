from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import (
    ClientSessionGenerator,
    WebSocketGenerator,
)

from custom_components.karotto.websocket import is_allowed

from .conftest import (
    API,
    CARROTS,
    SHOWER,
    URL,
    EventStream,
    active_tasks,
    daily,
    setup_entry,
)

ITEM = "88888888-8888-4888-8888-888888888888"
CARD_JS = "customElements.define('karotto-card')"


async def request(ws: Any, **message: Any) -> dict[str, Any]:
    await ws.send_json_auto_id({"type": "karotto/request", **message})
    return await ws.receive_json()


def test_allowlist_covers_the_board_and_nothing_else() -> None:
    assert is_allowed("GET", "/tasks", None)
    assert is_allowed("GET", "/tasks?type=completedTodos", None)
    assert is_allowed("POST", f"/tasks/{SHOWER}/score/up", None)
    assert is_allowed("POST", f"/tasks/{SHOWER}/checklist/{ITEM}/score", None)
    assert is_allowed("POST", "/cron", {"scores": []})
    assert is_allowed("PATCH", f"/tasks/{SHOWER}", {"collapseChecklist": True})

    assert not is_allowed("PATCH", f"/tasks/{SHOWER}", {"text": "renamed"})
    assert not is_allowed("PATCH", f"/tasks/{SHOWER}", {"collapseChecklist": True, "text": "x"})
    assert not is_allowed("POST", "/user/tokens", {"name": "mine now"})
    assert not is_allowed("GET", "/user/tokens", None)
    assert not is_allowed("POST", "/tasks", [{"type": "todo", "text": "x"}])
    assert not is_allowed("POST", f"/tasks/{SHOWER}/score/sideways", None)
    assert not is_allowed("POST", "/tasks/../user/tokens/score/up", None)
    assert not is_allowed("GET", "/tasks?type=all", None)


async def test_request_forwards_with_the_card_client_id(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    ws = await hass_ws_client(hass)

    reply = await request(ws, method="GET", path="/tasks", client_id="card-1")

    assert reply["success"]
    assert reply["result"]["status"] == 200
    assert [task["id"] for task in reply["result"]["body"]] == [
        task["id"] for task in active_tasks()
    ]
    _method, url, _data, headers = mock_api.mock_calls[-1]
    assert str(url) == f"{API}/tasks"
    assert headers["x-client-id"] == "card-1"
    assert headers["authorization"] == "Bearer krt_test"


async def test_request_passes_karotto_errors_through(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    error = {"error": {"code": "not_found", "message": "Task not found"}}
    mock_api.post(f"{API}/tasks/{CARROTS}/score/up", status=404, json=error)
    ws = await hass_ws_client(hass)

    reply = await request(ws, method="POST", path=f"/tasks/{CARROTS}/score/up")

    assert reply["result"] == {"status": 404, "statusText": "", "body": error}


async def test_request_refuses_anything_off_the_list(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    calls = len(mock_api.mock_calls)
    ws = await hass_ws_client(hass)

    reply = await request(ws, method="POST", path="/user/tokens", body={"name": "x"})

    assert not reply["success"]
    assert reply["error"]["code"] == "unauthorized"
    assert len(mock_api.mock_calls) == calls


async def test_request_for_an_unknown_account_fails(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    ws = await hass_ws_client(hass)

    reply = await request(ws, method="GET", path="/tags", config_entry_id="nope")

    assert reply["error"]["code"] == "not_found"


async def test_events_relay_the_stream_and_resync_after_reconnect(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id({"type": "karotto/events"})
    assert (await ws.receive_json())["success"]

    task = daily(SHOWER, "Shower", 0, completed=True)
    await stream.emit("task.upserted", {"task": task})
    message = await ws.receive_json()
    assert message["type"] == "event"
    assert message["event"] == {
        "kind": "event",
        "type": "task.upserted",
        "event": {"task": task, "type": "task.upserted", "origin": None},
    }

    config_entry.runtime_data._on_stream_connect()
    assert (await ws.receive_json())["event"] == {"kind": "resync"}


async def test_card_is_served_from_the_karotto_server(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.get(f"{URL}/karotto-card.js", text=CARD_JS, headers={"etag": '"v1"'})
    client = await hass_client_no_auth()

    response = await client.get("/karotto/karotto-card.js")

    assert response.status == 200
    assert response.content_type == "text/javascript"
    assert response.headers["ETag"] == '"v1"'
    assert await response.text() == CARD_JS


async def test_card_reports_an_unreachable_server(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.get(f"{URL}/karotto-card.js", status=404)
    client = await hass_client_no_auth()

    response = await client.get("/karotto/karotto-card.js")

    assert response.status == 502
