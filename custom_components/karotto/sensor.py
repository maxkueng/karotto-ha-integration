from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KarottoConfigEntry
from .coordinator import KarottoCoordinator, KarottoData
from .entity import KarottoEntity


def user_today(data: KarottoData) -> str:
    timezone = data.user["preferences"]["timezone"]
    try:
        zone = ZoneInfo(timezone)
    except KeyError, ValueError:
        zone = dt_util.get_default_time_zone()
    return dt_util.now(zone).date().isoformat()


def due_dailies(data: KarottoData) -> list[dict[str, Any]]:
    return [task for task in data.of_type("daily") if task["isDue"]]


def open_todos(data: KarottoData) -> list[dict[str, Any]]:
    return [task for task in data.of_type("todo") if not task["completed"]]


def titles(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"tasks": [task["text"] for task in tasks]}


@dataclass(frozen=True, kw_only=True)
class KarottoSensorDescription(SensorEntityDescription):
    value_fn: Callable[[KarottoData], int | datetime | None]
    attributes_fn: Callable[[KarottoData], dict[str, Any]] | None = None


SENSORS: tuple[KarottoSensorDescription, ...] = (
    KarottoSensorDescription(
        key="dailies_remaining",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(1 for task in due_dailies(data) if not task["completed"]),
        attributes_fn=lambda data: titles([t for t in due_dailies(data) if not t["completed"]]),
    ),
    KarottoSensorDescription(
        key="dailies_completed",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(1 for task in due_dailies(data) if task["completed"]),
        attributes_fn=lambda data: titles([t for t in due_dailies(data) if t["completed"]]),
    ),
    KarottoSensorDescription(
        key="todos_open",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: len(open_todos(data)),
    ),
    KarottoSensorDescription(
        key="todos_due",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: sum(
            1
            for task in open_todos(data)
            if task["dueDate"] and task["dueDate"] <= user_today(data)
        ),
        attributes_fn=lambda data: titles(
            [t for t in open_todos(data) if t["dueDate"] and t["dueDate"] <= user_today(data)]
        ),
    ),
    KarottoSensorDescription(
        key="last_rollover",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda data: dt_util.parse_datetime(data.user["lastCron"]),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KarottoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(KarottoSensor(coordinator, entry, description) for description in SENSORS)


class KarottoSensor(KarottoEntity, SensorEntity):
    entity_description: KarottoSensorDescription

    def __init__(
        self,
        coordinator: KarottoCoordinator,
        entry: KarottoConfigEntry,
        description: KarottoSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | datetime | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data)
