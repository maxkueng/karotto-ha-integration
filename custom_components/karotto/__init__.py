from __future__ import annotations

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import KarottoClient
from .const import CARD_URL, CONF_TOKEN, CONF_URL, DOMAIN
from .coordinator import KarottoCoordinator, outdated_server_issue_id
from .services import async_setup_services
from .view import KarottoCardView
from .websocket import async_setup_websocket

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH, Platform.TODO]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type KarottoConfigEntry = ConfigEntry[KarottoCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_setup_services(hass)
    async_setup_websocket(hass)
    hass.http.register_view(KarottoCardView())
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, CARD_URL)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: KarottoConfigEntry) -> bool:
    client = KarottoClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        client_id=f"home-assistant-{entry.entry_id[:8]}",
    )
    coordinator = KarottoCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.start_stream()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KarottoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: KarottoConfigEntry) -> None:
    ir.async_delete_issue(hass, DOMAIN, outdated_server_issue_id(entry.entry_id))
