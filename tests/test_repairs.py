from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import API_REVISION_HEADER, DOMAIN

from .conftest import API, USER, EventStream, active_tasks, completed_todos, setup_entry


def serve(mocker: AiohttpClientMocker, revision: str | None) -> None:
    mocker.clear_requests()
    headers = {} if revision is None else {API_REVISION_HEADER: revision}
    mocker.get(f"{API}/user", json=USER, headers=headers)
    mocker.get(f"{API}/tasks?type=completedTodos", json=completed_todos(), headers=headers)
    mocker.get(f"{API}/tasks", json=active_tasks(), headers=headers)


def outdated_issue(hass: HomeAssistant, entry: MockConfigEntry) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, f"outdated_server_{entry.entry_id}")


@pytest.fixture
def requires_revision_2():
    with patch("custom_components.karotto.coordinator.REQUIRED_API_REVISION", 2):
        yield


async def test_no_issue_when_server_is_current(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    serve(aioclient_mock, "1")
    await setup_entry(hass, config_entry)
    assert outdated_issue(hass, config_entry) is None


@pytest.mark.usefixtures("requires_revision_2")
async def test_outdated_server_raises_issue_and_keeps_working(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    serve(aioclient_mock, "1")
    await setup_entry(hass, config_entry)

    issue = outdated_issue(hass, config_entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    assert issue.translation_key == "outdated_server"
    assert issue.translation_placeholders == {
        "title": config_entry.title,
        "server_revision": "1",
        "required_revision": "2",
    }
    assert hass.states.get("todo.karotto_max_to_dos").state == "2"


@pytest.mark.usefixtures("requires_revision_2")
async def test_server_without_header_counts_as_first_revision(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    serve(aioclient_mock, None)
    await setup_entry(hass, config_entry)

    issue = outdated_issue(hass, config_entry)
    assert issue is not None
    assert issue.translation_placeholders["server_revision"] == "1"


@pytest.mark.usefixtures("requires_revision_2")
async def test_issue_clears_once_the_server_is_updated(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    serve(aioclient_mock, "1")
    await setup_entry(hass, config_entry)
    assert outdated_issue(hass, config_entry) is not None

    serve(aioclient_mock, "2")
    await config_entry.runtime_data.async_refresh()
    assert outdated_issue(hass, config_entry) is None


@pytest.mark.usefixtures("requires_revision_2")
async def test_removing_the_entry_removes_its_issue(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    serve(aioclient_mock, "1")
    await setup_entry(hass, config_entry)
    assert outdated_issue(hass, config_entry) is not None

    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert outdated_issue(hass, config_entry) is None
