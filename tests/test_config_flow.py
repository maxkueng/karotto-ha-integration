from __future__ import annotations

from aiohttp import ClientConnectionError
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.karotto.const import (
    CONF_TOKEN,
    CONF_URL,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)

from .conftest import API, URL, USER, request_at

TOKEN_RESPONSE = {
    "id": "t1",
    "name": "Home Assistant",
    "prefix": "krt_abc",
    "createdAt": "2026-09-29T00:00:00.000Z",
    "lastUsedAt": None,
    "expiresAt": None,
    "token": "krt_abcdef",
}


async def test_user_flow_creates_entry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post("https://karotto.test/api/v1/auth/token", json=TOKEN_RESPONSE, status=201)
    aioclient_mock.get("https://karotto.test/api/v1/user", json=USER)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "karotto.test/", CONF_USERNAME: "max", CONF_PASSWORD: "hunter22"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "max @ karotto.test"
    assert result["data"] == {
        CONF_URL: "https://karotto.test",
        CONF_TOKEN: "krt_abcdef",
        CONF_USER_ID: USER["id"],
        CONF_USERNAME: "max",
    }
    method, url, body = request_at(aioclient_mock, 0)
    assert (method, url) == ("POST", "https://karotto.test/api/v1/auth/token")
    assert body == {"username": "max", "password": "hunter22", "name": "Home Assistant"}


async def test_user_flow_rejects_bad_password(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(
        f"{API}/auth/token",
        status=401,
        json={"error": {"code": "invalid_credentials", "message": "nope"}},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: URL, CONF_USERNAME: "max", CONF_PASSWORD: "wrong"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_reports_unreachable_server(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(f"{API}/auth/token", exc=ClientConnectionError("down"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: URL, CONF_USERNAME: "max", CONF_PASSWORD: "hunter22"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_same_account_aborts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.post(f"{API}/auth/token", json=TOKEN_RESPONSE, status=201)
    aioclient_mock.get(f"{API}/user", json=USER)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: URL, CONF_USERNAME: "max", CONF_PASSWORD: "hunter22"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_token(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    config_entry.add_to_hass(hass)
    aioclient_mock.post(f"{API}/auth/token", json=TOKEN_RESPONSE, status=201)
    aioclient_mock.get(f"{API}/user", json=USER)

    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "hunter22"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_TOKEN] == "krt_abcdef"
