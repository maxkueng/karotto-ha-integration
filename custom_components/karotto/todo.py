from __future__ import annotations

from datetime import date, datetime
from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import KarottoConfigEntry
from .api import KarottoApiError, KarottoConnectionError
from .coordinator import KarottoCoordinator
from .entity import KarottoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KarottoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KarottoTodoList(coordinator, entry),
            KarottoDailyList(coordinator, entry),
        ]
    )


def status_of(task: dict[str, Any]) -> TodoItemStatus:
    return TodoItemStatus.COMPLETED if task["completed"] else TodoItemStatus.NEEDS_ACTION


def due_of(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


class KarottoList(KarottoEntity, TodoListEntity):
    task_type: str

    async def _call(self, action):  # type: ignore[no-untyped-def]
        try:
            return await action
        except KarottoApiError as error:
            if error.code in ("already_completed", "not_completed"):
                return None
            raise ServiceValidationError(error.args[0]) from error
        except KarottoConnectionError as error:
            raise HomeAssistantError(f"karotto is unreachable: {error}") from error

    def _task(self, uid: str | None) -> dict[str, Any]:
        task = self.coordinator.data.tasks.get(uid or "")
        if task is None or task["type"] != self.task_type:
            raise ServiceValidationError(f"Unknown {self.task_type} {uid}")
        return task

    async def _apply_update(self, item: TodoItem, rollover: bool) -> None:
        task = self._task(item.uid)
        patch: dict[str, Any] = {}
        if item.summary is not None and item.summary != task["text"]:
            patch["text"] = item.summary
        notes = item.description or ""
        if notes != task["notes"]:
            patch["notes"] = notes
        if self.task_type == "todo" and due_of(item.due) != task["dueDate"]:
            patch["dueDate"] = due_of(item.due)
        if patch:
            updated = await self._call(self.coordinator.client.update_task(task["id"], patch))
            if updated:
                self.coordinator.apply_task(updated)
        if item.status is not None and item.status != status_of(task):
            direction = "up" if item.status == TodoItemStatus.COMPLETED else "down"
            await self._call(self.coordinator.async_score(task["id"], direction, rollover))


class KarottoTodoList(KarottoList):
    task_type = "todo"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.MOVE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: KarottoCoordinator, entry: KarottoConfigEntry) -> None:
        super().__init__(coordinator, entry, "todos")

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if self.coordinator.data is None:
            return None
        return [
            TodoItem(
                uid=task["id"],
                summary=task["text"],
                status=status_of(task),
                due=date.fromisoformat(task["dueDate"]) if task["dueDate"] else None,
                description=task["notes"] or None,
            )
            for task in self.coordinator.data.of_type("todo")
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        created = await self._call(
            self.coordinator.client.create_task(
                {
                    "type": "todo",
                    "text": item.summary or "",
                    "notes": item.description or "",
                    "dueDate": due_of(item.due),
                }
            )
        )
        self.coordinator.apply_task(created)
        if item.status == TodoItemStatus.COMPLETED:
            await self._call(self.coordinator.async_score(created["id"], "up", False))

    async def async_update_todo_item(self, item: TodoItem) -> None:
        await self._apply_update(item, rollover=False)

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            task = self._task(uid)
            await self._call(self.coordinator.client.delete_task(task["id"]))
            self.coordinator.data.tasks.pop(task["id"], None)
        self.coordinator.async_set_updated_data(self.coordinator.data)

    async def async_move_todo_item(self, uid: str, previous_uid: str | None = None) -> None:
        task = self._task(uid)
        others = [
            row["id"]
            for row in self.coordinator.data.of_type("todo")
            if not row["completed"] and row["id"] != task["id"]
        ]
        position = 0 if previous_uid is None else others.index(previous_uid) + 1
        ids = await self._call(self.coordinator.client.move_task(task["id"], position))
        self.coordinator.apply_order("todo", ids)


class KarottoDailyList(KarottoList):
    task_type = "daily"
    _attr_supported_features = (
        TodoListEntityFeature.UPDATE_TODO_ITEM | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, coordinator: KarottoCoordinator, entry: KarottoConfigEntry) -> None:
        super().__init__(coordinator, entry, "dailies")

    @property
    def todo_items(self) -> list[TodoItem] | None:
        if self.coordinator.data is None:
            return None
        return [
            TodoItem(
                uid=task["id"],
                summary=task["text"],
                status=status_of(task),
                description=task["notes"] or None,
            )
            for task in self.coordinator.data.of_type("daily")
            if task["isDue"]
        ]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        await self._apply_update(item, rollover=True)
