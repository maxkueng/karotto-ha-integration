from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KarottoConfigEntry
from .entity import KarottoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KarottoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RolloverPendingSensor(entry)])


class RolloverPendingSensor(KarottoEntity, BinarySensorEntity):
    def __init__(self, entry: KarottoConfigEntry) -> None:
        super().__init__(entry.runtime_data, entry, "rollover_pending")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.user["needsCron"])
