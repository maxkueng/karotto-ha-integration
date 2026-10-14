from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KarottoConfigEntry
from .api import KarottoApiError, KarottoConnectionError
from .entity import KarottoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KarottoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([PausedSwitch(entry)])


class PausedSwitch(KarottoEntity, SwitchEntity):
    """Vacation mode: days roll over, but nothing missed is penalised."""

    def __init__(self, entry: KarottoConfigEntry) -> None:
        super().__init__(entry.runtime_data, entry, "paused")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.user["preferences"].get("paused"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, paused: bool) -> None:
        try:
            user = await self.coordinator.client.update_preferences({"paused": paused})
        except KarottoApiError as error:
            raise HomeAssistantError(error.args[0]) from error
        except KarottoConnectionError as error:
            raise HomeAssistantError(f"karotto is unreachable: {error}") from error
        self.coordinator.data.user = user
        self.coordinator.async_set_updated_data(self.coordinator.data)
