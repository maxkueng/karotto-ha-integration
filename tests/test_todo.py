from __future__ import annotations

from datetime import date

import pytest
from homeassistant.components.todo import (
    ATTR_DESCRIPTION,
    ATTR_DUE_DATE,
    ATTR_ITEM,
    ATTR_RENAME,
    ATTR_STATUS,
    TodoServices,
)
from homeassistant.components.todo import (
    DOMAIN as TODO_DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from .conftest import (
    API,
    CARROTS,
    SHOWER,
    STRETCH,
    TAXES,
    USER,
    EventStream,
    daily,
    request_at,
    setup_entry,
    todo,
)

TODOS = "todo.karotto_max_to_dos"
DAILIES = "todo.karotto_max_dailies"


async def get_items(hass: HomeAssistant, entity_id: str) -> list[dict]:
    result = await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.GET_ITEMS,
        {},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["items"]


async def test_lists_expose_tasks(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    todos = await get_items(hass, TODOS)
    assert [item["summary"] for item in todos] == ["Buy carrots", "Taxes", "Already done"]
    assert todos[0]["due"] == "2020-01-01"
    assert todos[0]["description"] == "orange ones"
    assert todos[2]["status"] == "completed"

    dailies = await get_items(hass, DAILIES)
    assert [(item["summary"], item["status"]) for item in dailies] == [
        ("Shower", "needs_action"),
        ("Stretch", "completed"),
    ]


async def test_completing_a_daily_runs_rollover_then_scores(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(f"{API}/cron", json={"ran": False, "daysMissed": 0, "user": USER})
    scored = daily(SHOWER, "Shower", 0, alias="shower", completed=True, streak=4)
    mock_api.post(f"{API}/tasks/{SHOWER}/score/up", json={"task": scored, "delta": 1})

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ITEM: SHOWER, ATTR_STATUS: "completed"},
        target={"entity_id": DAILIES},
        blocking=True,
    )
    assert request_at(mock_api, -2)[:2] == ("POST", f"{API}/cron")
    assert request_at(mock_api, -1)[:2] == ("POST", f"{API}/tasks/{SHOWER}/score/up")
    assert hass.states.get(DAILIES).state == "0"
    assert hass.states.get("sensor.karotto_max_dailies_completed").state == "2"


async def test_completing_a_todo_skips_rollover(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    scored = todo(CARROTS, "Buy carrots", 0, completed=True, dueDate="2020-01-01")
    mock_api.post(f"{API}/tasks/{CARROTS}/score/up", json={"task": scored, "delta": 1})

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ITEM: "Buy carrots", ATTR_STATUS: "completed"},
        target={"entity_id": TODOS},
        blocking=True,
    )
    assert request_at(mock_api, -1)[:2] == ("POST", f"{API}/tasks/{CARROTS}/score/up")
    assert all(str(call[1]) != f"{API}/cron" for call in mock_api.mock_calls)
    assert hass.states.get(TODOS).state == "1"


async def test_editing_a_todo_patches_changed_fields(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    patched = todo(TAXES, "Taxes 2026", 1, dueDate="2027-03-31", notes="ugh")
    mock_api.patch(f"{API}/tasks/{TAXES}", json=patched)

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {
            ATTR_ITEM: TAXES,
            ATTR_RENAME: "Taxes 2026",
            ATTR_DESCRIPTION: "ugh",
            ATTR_DUE_DATE: date(2027, 3, 31),
        },
        target={"entity_id": TODOS},
        blocking=True,
    )
    method, url, body = request_at(mock_api, -1)
    assert (method, url) == ("PATCH", f"{API}/tasks/{TAXES}")
    assert body == {"text": "Taxes 2026", "notes": "ugh", "dueDate": "2027-03-31"}
    items = await get_items(hass, TODOS)
    assert items[1]["summary"] == "Taxes 2026"


async def test_add_and_delete_todo(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    new_id = "88888888-8888-4888-8888-888888888888"
    mock_api.post(
        f"{API}/tasks", json=todo(new_id, "Call mum", 0, dueDate="2026-10-01"), status=201
    )
    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.ADD_ITEM,
        {ATTR_ITEM: "Call mum", ATTR_DUE_DATE: date(2026, 10, 1)},
        target={"entity_id": TODOS},
        blocking=True,
    )
    method, url, body = request_at(mock_api, -1)
    assert (method, url) == ("POST", f"{API}/tasks")
    assert body == {"type": "todo", "text": "Call mum", "notes": "", "dueDate": "2026-10-01"}
    assert hass.states.get(TODOS).state == "3"

    mock_api.delete(f"{API}/tasks/{new_id}", status=200, json={"ok": True})
    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.REMOVE_ITEM,
        {ATTR_ITEM: [new_id]},
        target={"entity_id": TODOS},
        blocking=True,
    )
    assert request_at(mock_api, -1)[:2] == ("DELETE", f"{API}/tasks/{new_id}")
    assert hass.states.get(TODOS).state == "2"


async def test_move_todo(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(f"{API}/tasks/{TAXES}/move/0", json={"ids": [TAXES, CARROTS]})
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "todo/item/move", "entity_id": TODOS, "uid": TAXES})
    reply = await client.receive_json()
    assert reply["success"], reply
    assert request_at(mock_api, -1)[:2] == ("POST", f"{API}/tasks/{TAXES}/move/0")
    items = await get_items(hass, TODOS)
    assert [item["summary"] for item in items][:2] == ["Taxes", "Buy carrots"]


async def test_api_error_surfaces_as_validation_error(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(f"{API}/cron", json={"ran": False, "daysMissed": 0, "user": USER})
    mock_api.post(
        f"{API}/tasks/{STRETCH}/score/down",
        status=400,
        json={"error": {"code": "bad_request", "message": "Nope"}},
    )
    with pytest.raises(ServiceValidationError, match="Nope"):
        await hass.services.async_call(
            TODO_DOMAIN,
            TodoServices.UPDATE_ITEM,
            {ATTR_ITEM: "Stretch", ATTR_STATUS: "needs_action"},
            target={"entity_id": DAILIES},
            blocking=True,
        )
