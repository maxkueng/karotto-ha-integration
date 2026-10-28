from __future__ import annotations

from homeassistant.components.todo import ATTR_ITEM, ATTR_STATUS, TodoServices
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import EVENT_TASK_COMPLETED

from .conftest import (
    API,
    CARROTS,
    SHOWER,
    STRETCH,
    USER,
    EventStream,
    active_tasks,
    completed_todos,
    daily,
    setup_entry,
    todo,
)


async def test_setup_fires_nothing_for_already_completed_tasks(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)
    await setup_entry(hass, config_entry)
    assert events == []


async def test_stream_completion_fires_once(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)

    done = todo(CARROTS, "Buy carrots", 0, completed=True, alias="carrots")
    await stream.emit("task.upserted", {"task": done})
    await stream.emit("task.upserted", {"task": {**done, "notes": "edited after"}})
    await hass.async_block_till_done()

    assert [event.data for event in events] == [
        {
            "config_entry_id": config_entry.entry_id,
            "task_id": CARROTS,
            "type": "todo",
            "title": "Buy carrots",
            "alias": "carrots",
        }
    ]


async def test_uncompleting_fires_nothing(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)

    await stream.emit("task.upserted", {"task": daily(STRETCH, "Stretch", 1, completed=False)})
    await hass.async_block_till_done()
    assert events == []


async def test_refetch_fires_for_completions_missed_by_the_stream(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)
    mock_api.clear_requests()
    mock_api.get(f"{API}/user", json=USER)
    mock_api.get(
        f"{API}/tasks?type=completedTodos",
        json=[*completed_todos(), todo(CARROTS, "Buy carrots", 0, completed=True)],
    )
    mock_api.get(
        f"{API}/tasks",
        json=[task for task in active_tasks() if task["id"] != CARROTS],
    )

    await stream.emit("tasks.invalidated", {})
    await hass.async_block_till_done()
    assert [event.data["task_id"] for event in events] == [CARROTS]


async def test_completing_from_home_assistant_fires(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    events = async_capture_events(hass, EVENT_TASK_COMPLETED)
    mock_api.post(f"{API}/cron", json={"ran": False, "daysMissed": 0, "user": USER})
    scored = daily(SHOWER, "Shower", 0, alias="shower", completed=True)
    mock_api.post(f"{API}/tasks/{SHOWER}/score/up", json={"task": scored, "delta": 1})

    await hass.services.async_call(
        TODO_DOMAIN,
        TodoServices.UPDATE_ITEM,
        {ATTR_ITEM: SHOWER, ATTR_STATUS: "completed"},
        target={"entity_id": "todo.karotto_max_dailies"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert [(event.data["type"], event.data["alias"]) for event in events] == [("daily", "shower")]
