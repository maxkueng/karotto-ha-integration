from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_URL, CONF_USERNAME, DOMAIN
from .coordinator import KarottoCoordinator


class KarottoEntity(CoordinatorEntity[KarottoCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KarottoCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        owner = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{owner}-{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, owner)},
            name=f"Karotto ({entry.data[CONF_USERNAME]})",
            manufacturer="karotto",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=entry.data[CONF_URL],
        )
