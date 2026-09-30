from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import KarottoConfigEntry
from .const import CONF_TOKEN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: KarottoConfigEntry,
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {key: value for key, value in entry.data.items() if key != CONF_TOKEN},
        "stream_connected": coordinator.stream_connected,
        "user": data.user if data else None,
        "task_counts": {kind: len(data.of_type(kind)) for kind in ("habit", "daily", "todo")}
        if data
        else None,
    }
