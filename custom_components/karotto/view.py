from __future__ import annotations

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView

from .api import KarottoConnectionError
from .const import CARD_URL, DOMAIN


class KarottoCardView(HomeAssistantView):
    """Serves the card the karotto server builds, so it always matches that server."""

    url = CARD_URL
    name = f"{DOMAIN}:card"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[KEY_HASS]
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return web.Response(status=404, text="No karotto account is set up")
        try:
            status, body, etag = await entries[0].runtime_data.client.fetch_card(
                request.headers.get("If-None-Match")
            )
        except KarottoConnectionError as error:
            return web.Response(status=502, text=f"karotto is unreachable: {error}")
        headers = {"Cache-Control": "no-cache", **({"ETag": etag} if etag else {})}
        if status == 304:
            return web.Response(status=304, headers=headers)
        if status != 200:
            return web.Response(status=502, text=f"karotto answered {status} for the card")
        return web.Response(body=body, content_type="text/javascript", headers=headers)
