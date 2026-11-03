from __future__ import annotations

from datetime import date

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import DOMAIN, EVENT_TASK_COMPLETED

from .conftest import (
    API,
    SHOWER,
    USER,
    EventStream,
    daily,
    habit,
    request_at,
    setup_entry,
    todo,
)

DISH_OLD = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
DISH_NEW = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
DISH_DONE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
DISH_DAILY = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
DISH_HABIT = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


async def add_dishwasher_tasks(stream: EventStream) -> None:
    await stream.connected.wait()
    for task in (
        todo(DISH_OLD, "Empty dishwasher", 2, alias="dishwasher-20261102-1900"),
        todo(
            DISH_NEW, "Empty dishwasher", 3, alias="dishwasher-20261103-0700", dueDate="2026-11-03"
        ),
        todo(
            DISH_DONE,
            "Empty dishwasher",
            6,
            alias="dishwasher-20261101-1900",
            completed=True,
        ),
        daily(DISH_DAILY, "Clean dishwasher filter", 3, alias="dishwasher-filter"),
        habit(DISH_HABIT, "Load dishwasher properly", 1, alias="dishwasher-habit"),
    ):
        await stream.emit("task.upserted", {"task": task})


async def test_score_by_alias(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(f"{API}/cron", json={"ran": True, "daysMissed": 1, "user": USER})
    scored = daily(SHOWER, "Shower", 0, alias="shower", completed=True, streak=4)
    mock_api.post(f"{API}/tasks/shower/score/up", json={"task": scored, "delta": 1})

    response = await hass.services.async_call(
        DOMAIN,
        "score",
        {"task": "shower"},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert response == {
        "id": SHOWER,
        "type": "daily",
        "title": "Shower",
        "alias": "shower",
        "value": 0,
        "completed": True,
        "streak": 4,
        "due_date": None,
        "delta": 1,
    }
    calls = [request_at(mock_api, i)[:2] for i in range(len(mock_api.mock_calls))]
    assert ("POST", f"{API}/cron") in calls
    assert calls.index(("POST", f"{API}/cron")) < calls.index(
        ("POST", f"{API}/tasks/shower/score/up")
    )


async def test_score_without_rollover(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(
        f"{API}/tasks/stairs/score/down",
        json={"task": daily(SHOWER, "x"), "delta": -1},
    )
    await hass.services.async_call(
        DOMAIN,
        "score",
        {"task": "stairs", "direction": "down", "rollover": False},
        blocking=True,
    )
    assert request_at(mock_api, -1)[:2] == ("POST", f"{API}/tasks/stairs/score/down")
    assert all(str(call[1]) != f"{API}/cron" for call in mock_api.mock_calls)


async def test_score_unknown_task(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(
        f"{API}/tasks/nope/score/up",
        status=404,
        json={"error": {"code": "not_found", "message": "Task not found"}},
    )
    with pytest.raises(ServiceValidationError, match="Task not found"):
        await hass.services.async_call(
            DOMAIN, "score", {"task": "nope", "rollover": False}, blocking=True
        )


async def test_run_rollover(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    mock_api.post(f"{API}/cron", json={"ran": True, "daysMissed": 2, "user": USER})
    response = await hass.services.async_call(
        DOMAIN, "run_rollover", {}, blocking=True, return_response=True
    )
    assert response == {"ran": True, "days_missed": 2}


async def test_add_task(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    new_id = "99999999-9999-4999-8999-999999999999"
    mock_api.post(
        f"{API}/tasks",
        json=todo(new_id, "Water plants", 0, alias="plants", dueDate="2026-10-03"),
        status=201,
    )
    response = await hass.services.async_call(
        DOMAIN,
        "add_task",
        {
            "type": "todo",
            "title": "Water plants",
            "alias": "plants",
            "due_date": date(2026, 10, 3),
        },
        blocking=True,
        return_response=True,
    )
    method, url, body = request_at(mock_api, -1)
    assert (method, url) == ("POST", f"{API}/tasks")
    assert body == {
        "type": "todo",
        "text": "Water plants",
        "notes": "",
        "alias": "plants",
        "dueDate": "2026-10-03",
    }
    assert response["id"] == new_id
    assert hass.states.get("sensor.karotto_max_open_to_dos").state == "3"


async def test_services_need_a_loaded_entry(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "run_rollover", {}, blocking=True)


async def find(hass: HomeAssistant, **data: object) -> list[str]:
    response = await hass.services.async_call(
        DOMAIN, "find_tasks", data, blocking=True, return_response=True
    )
    return [task["id"] for task in response["tasks"]]


async def test_find_tasks_filters(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await add_dishwasher_tasks(stream)

    assert await find(hass, alias_prefix="dishwasher-") == [
        DISH_HABIT,
        DISH_DAILY,
        DISH_OLD,
        DISH_NEW,
        DISH_DONE,
    ]
    assert await find(hass, type="todo", status="open", alias_prefix="dishwasher-") == [
        DISH_OLD,
        DISH_NEW,
    ]
    assert await find(hass, status="completed", alias_prefix="dishwasher-") == [DISH_DONE]
    assert await find(hass, alias="shower") == [SHOWER]
    assert await find(hass, alias_prefix="dryer-") == []


async def test_find_tasks_response_shape(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await add_dishwasher_tasks(stream)
    response = await hass.services.async_call(
        DOMAIN,
        "find_tasks",
        {"alias": "dishwasher-20261103-0700"},
        blocking=True,
        return_response=True,
    )
    assert response == {
        "tasks": [
            {
                "id": DISH_NEW,
                "type": "todo",
                "title": "Empty dishwasher",
                "alias": "dishwasher-20261103-0700",
                "value": 0,
                "completed": False,
                "streak": None,
                "due_date": "2026-11-03",
            }
        ]
    }


async def test_find_tasks_rejects_empty_prefix(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    with pytest.raises(vol.Invalid):
        await find(hass, alias_prefix="")


async def test_complete_tasks_by_prefix(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await add_dishwasher_tasks(stream)
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)
    for task_id, alias in (
        (DISH_OLD, "dishwasher-20261102-1900"),
        (DISH_NEW, "dishwasher-20261103-0700"),
    ):
        mock_api.post(
            f"{API}/tasks/{task_id}/score/up",
            json={
                "task": todo(task_id, "Empty dishwasher", 0, alias=alias, completed=True),
                "delta": 1,
            },
        )

    response = await hass.services.async_call(
        DOMAIN,
        "complete_tasks",
        {"alias_prefix": "dishwasher-"},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()

    assert [task["id"] for task in response["tasks"]] == [DISH_OLD, DISH_NEW]
    assert all(task["completed"] for task in response["tasks"])
    calls = [request_at(mock_api, i)[:2] for i in range(len(mock_api.mock_calls))]
    scored = [url for method, url in calls if method == "POST"]
    assert scored == [f"{API}/tasks/{DISH_OLD}/score/up", f"{API}/tasks/{DISH_NEW}/score/up"]
    assert [event.data["alias"] for event in events] == [
        "dishwasher-20261102-1900",
        "dishwasher-20261103-0700",
    ]
    assert await find(hass, type="todo", status="open", alias_prefix="dishwasher-") == []


async def test_complete_tasks_skips_one_completed_elsewhere(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await add_dishwasher_tasks(stream)
    mock_api.post(
        f"{API}/tasks/{DISH_OLD}/score/up",
        status=409,
        json={"error": {"code": "already_completed", "message": "Task is already completed"}},
    )
    response = await hass.services.async_call(
        DOMAIN,
        "complete_tasks",
        {"alias": "dishwasher-20261102-1900"},
        blocking=True,
        return_response=True,
    )
    assert response == {"tasks": []}


async def test_complete_tasks_without_matches(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await add_dishwasher_tasks(stream)
    mock_api.clear_requests()
    response = await hass.services.async_call(
        DOMAIN,
        "complete_tasks",
        {"alias_prefix": "dryer-"},
        blocking=True,
        return_response=True,
    )
    assert response == {"tasks": []}
    assert mock_api.mock_calls == []


async def test_complete_tasks_needs_an_alias(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(DOMAIN, "complete_tasks", {}, blocking=True)
