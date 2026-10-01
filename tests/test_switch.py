from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from .conftest import API, USER, EventStream, request_at, setup_entry

PAUSED = "switch.karotto_max_paused"


async def test_paused_switch_follows_and_sets_the_preference(
    hass: HomeAssistant,
    mock_api: AiohttpClientMocker,
    stream: EventStream,
    config_entry: MockConfigEntry,
) -> None:
    await setup_entry(hass, config_entry)
    assert hass.states.get(PAUSED).state == "off"

    paused_user = {**USER, "preferences": {**USER["preferences"], "paused": True}}
    mock_api.patch(f"{API}/user/preferences", json=paused_user)
    await hass.services.async_call("switch", "turn_on", {"entity_id": PAUSED}, blocking=True)
    method, url, body = request_at(mock_api, -1)
    assert (method, url) == ("PATCH", f"{API}/user/preferences")
    assert body == {"paused": True}
    assert hass.states.get(PAUSED).state == "on"

    await stream.connected.wait()
    await stream.emit("user.updated", {"user": USER})
    await hass.async_block_till_done()
    assert hass.states.get(PAUSED).state == "off"
