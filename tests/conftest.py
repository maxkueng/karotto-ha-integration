from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import (
    CONF_TOKEN,
    CONF_URL,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)

URL = "http://karotto.test"
API = f"{URL}/api/v1"
USER_ID = "0d1b5f36-9a4c-4c55-8f4b-2b7a1e6f1a01"

USER: dict[str, Any] = {
    "id": USER_ID,
    "username": "max",
    "createdAt": "2026-01-01T00:00:00.000Z",
    "lastCron": "2026-09-29T00:00:00.000Z",
    "needsCron": False,
    "preferences": {
        "dayStart": 0,
        "timezone": "Europe/Zurich",
        "dateFormat": "yyyy-MM-dd",
        "completedTodoRetentionDays": None,
        "paused": False,
    },
}


def base(kind: str, task_id: str, text: str, position: int, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": task_id,
        "type": kind,
        "text": text,
        "notes": "",
        "alias": None,
        "value": 0,
        "tags": [],
        "reminders": [],
        "position": position,
        "createdAt": "2026-09-01T00:00:00.000Z",
        "updatedAt": "2026-09-01T00:00:00.000Z",
    }
    row.update(extra)
    return row


def habit(task_id: str, text: str, position: int = 0, **extra: Any) -> dict[str, Any]:
    return base(
        "habit",
        task_id,
        text,
        position,
        up=True,
        down=True,
        counterUp=0,
        counterDown=0,
        frequency="daily",
        **extra,
    )


def daily(task_id: str, text: str, position: int = 0, **extra: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "completed": False,
        "collapseChecklist": False,
        "checklist": [],
        "frequency": "weekly",
        "everyX": 1,
        "startDate": "2026-09-01",
        "repeat": {k: True for k in ("su", "m", "t", "w", "th", "f", "s")},
        "streak": 3,
        "daysOfMonth": [],
        "weeksOfMonth": [],
        "yesterdaily": True,
        "isDue": True,
    }
    fields.update(extra)
    return base("daily", task_id, text, position, **fields)


def todo(task_id: str, text: str, position: int = 0, **extra: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "completed": False,
        "collapseChecklist": False,
        "checklist": [],
        "dueDate": None,
        "dateCompleted": None,
    }
    fields.update(extra)
    return base("todo", task_id, text, position, **fields)


SHOWER = "11111111-1111-4111-8111-111111111111"
STRETCH = "22222222-2222-4222-8222-222222222222"
SKIPPED = "33333333-3333-4333-8333-333333333333"
CARROTS = "44444444-4444-4444-8444-444444444444"
TAXES = "55555555-5555-4555-8555-555555555555"
DONE = "66666666-6666-4666-8666-666666666666"
STAIRS = "77777777-7777-4777-8777-777777777777"


def active_tasks() -> list[dict[str, Any]]:
    return [
        habit(STAIRS, "Take the stairs", 0),
        daily(SHOWER, "Shower", 0, alias="shower"),
        daily(STRETCH, "Stretch", 1, completed=True),
        daily(SKIPPED, "Sunday only", 2, isDue=False),
        todo(CARROTS, "Buy carrots", 0, dueDate="2020-01-01", notes="orange ones"),
        todo(TAXES, "Taxes", 1, dueDate="2999-12-31"),
    ]


def completed_todos() -> list[dict[str, Any]]:
    return [todo(DONE, "Already done", 5, completed=True, dateCompleted="2026-09-28T10:00:00.000Z")]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    return None


class EventStream:
    """Feeds fake SSE events to the coordinator and keeps the stream open."""

    def __init__(self) -> None:
        self.handler: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None
        self.connected = asyncio.Event()
        self.closed = asyncio.Event()

    async def run(
        self,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]],
        on_connect: Callable[[], None] | None = None,
    ) -> None:
        self.handler = handler
        if on_connect:
            on_connect()
        self.connected.set()
        await self.closed.wait()

    async def emit(self, kind: str, payload: dict[str, Any]) -> None:
        assert self.handler is not None
        await self.handler(kind, {**payload, "type": kind, "origin": None})


@pytest.fixture
def stream() -> AsyncIterator[EventStream]:
    fake = EventStream()
    with patch(
        "custom_components.karotto.api.KarottoClient.stream_events",
        side_effect=fake.run,
    ):
        yield fake
    fake.closed.set()


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    aioclient_mock.get(f"{API}/user", json=USER)
    aioclient_mock.get(f"{API}/tasks?type=completedTodos", json=completed_todos())
    aioclient_mock.get(f"{API}/tasks", json=active_tasks())
    return aioclient_mock


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=USER_ID,
        title="max @ karotto.test",
        data={
            CONF_URL: URL,
            CONF_TOKEN: "krt_test",
            CONF_USER_ID: USER_ID,
            CONF_USERNAME: "max",
        },
    )


def request_at(mocker: AiohttpClientMocker, index: int = -1) -> tuple[str, str, Any]:
    method, url, data, _headers = mocker.mock_calls[index]
    return method.upper(), str(url), data


async def setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
