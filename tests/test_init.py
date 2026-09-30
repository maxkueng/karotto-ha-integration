from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import (
    API,
    CARROTS,
    SHOWER,
    USER,
    EventStream,
    daily,
    setup_entry,
    todo,
)


async def test_setup_creates_entities(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    assert hass.states.get("sensor.karotto_max_dailies_remaining").state == "1"
    assert hass.states.get("sensor.karotto_max_dailies_completed").state == "1"
    assert hass.states.get("sensor.karotto_max_open_to_dos").state == "2"
    todos_due = hass.states.get("sensor.karotto_max_to_dos_due")
    assert todos_due.state == "1"
    assert todos_due.attributes["tasks"] == ["Buy carrots"]
    assert hass.states.get("binary_sensor.karotto_max_rollover_pending").state == "off"
    assert hass.states.get("sensor.karotto_max_last_rollover").state == "2026-09-29T00:00:00+00:00"
    assert hass.states.get("todo.karotto_max_to_dos").state == "2"
    assert hass.states.get("todo.karotto_max_dailies").state == "1"

    await stream.connected.wait()
    assert config_entry.runtime_data.stream_connected


async def test_setup_fails_on_bad_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    aioclient_mock.get(
        f"{API}/user",
        status=401,
        json={"error": {"code": "unauthorized", "message": "Authentication required"}},
    )
    config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler("karotto")
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_stream_events_update_state(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()

    await stream.emit("task.upserted", {"task": daily(SHOWER, "Shower", 0, completed=True)})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.karotto_max_dailies_remaining").state == "0"
    assert hass.states.get("sensor.karotto_max_dailies_completed").state == "2"

    await stream.emit("task.deleted", {"id": CARROTS})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.karotto_max_open_to_dos").state == "1"
    assert hass.states.get("sensor.karotto_max_to_dos_due").state == "0"

    await stream.emit("user.updated", {"user": {**USER, "needsCron": True}})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.karotto_max_rollover_pending").state == "on"


async def test_invalidated_event_refetches(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    await stream.connected.wait()
    mock_api.clear_requests()
    mock_api.get(f"{API}/user", json=USER)
    mock_api.get(f"{API}/tasks?type=completedTodos", json=[])
    mock_api.get(f"{API}/tasks", json=[todo(CARROTS, "Only one left", 0)])

    await stream.emit("tasks.invalidated", {})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.karotto_max_open_to_dos").state == "1"
    assert hass.states.get("sensor.karotto_max_dailies_remaining").state == "0"
