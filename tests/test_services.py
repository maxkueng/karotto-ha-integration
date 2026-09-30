from __future__ import annotations

from datetime import date

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import DOMAIN

from .conftest import API, SHOWER, USER, EventStream, daily, request_at, setup_entry, todo


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
