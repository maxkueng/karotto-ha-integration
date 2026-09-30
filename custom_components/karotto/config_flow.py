from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    KarottoAuthError,
    KarottoClient,
    KarottoConnectionError,
    KarottoError,
    normalize_url,
)
from .const import CONF_TOKEN, CONF_URL, CONF_USER_ID, CONF_USERNAME, DOMAIN, TOKEN_NAME

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


@dataclass
class AuthResult:
    url: str
    token: str
    user_id: str
    username: str


async def authenticate(
    hass: HomeAssistant,
    url: str,
    username: str,
    password: str,
) -> AuthResult:
    url = normalize_url(url)
    client = KarottoClient(async_get_clientsession(hass), url)
    created = await client.login(username, password, TOKEN_NAME)
    user = await client.get_user()
    return AuthResult(url, created["token"], user["id"], user["username"])


def error_key(error: KarottoError) -> str:
    if isinstance(error, KarottoAuthError):
        return "invalid_auth"
    if isinstance(error, KarottoConnectionError):
        return "cannot_connect"
    return "unknown"


class KarottoConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                auth = await authenticate(
                    self.hass,
                    user_input[CONF_URL],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except KarottoError as error:
                errors["base"] = error_key(error)
            else:
                await self.async_set_unique_id(auth.user_id)
                self._abort_if_unique_id_configured()
                host = urlparse(auth.url).netloc
                return self.async_create_entry(
                    title=f"{auth.username} @ {host}",
                    data={
                        CONF_URL: auth.url,
                        CONF_TOKEN: auth.token,
                        CONF_USER_ID: auth.user_id,
                        CONF_USERNAME: auth.username,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                auth = await authenticate(
                    self.hass,
                    entry.data[CONF_URL],
                    entry.data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except KarottoError as error:
                errors["base"] = error_key(error)
            else:
                await self.async_set_unique_id(auth.user_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_TOKEN: auth.token},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={
                CONF_USERNAME: entry.data[CONF_USERNAME],
                CONF_URL: entry.data[CONF_URL],
            },
            errors=errors,
        )
