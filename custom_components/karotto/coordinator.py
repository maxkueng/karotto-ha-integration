from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    KarottoApiError,
    KarottoAuthError,
    KarottoClient,
    KarottoConnectionError,
)
from .const import DOMAIN, POLL_INTERVAL, STREAM_RETRY_MAX, STREAM_RETRY_MIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class KarottoData:
    user: dict[str, Any]
    tasks: dict[str, dict[str, Any]] = field(default_factory=dict)

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        rows = [task for task in self.tasks.values() if task["type"] == kind]
        rows.sort(key=lambda task: task["position"])
        return rows

    def find(self, ref: str) -> dict[str, Any] | None:
        if ref in self.tasks:
            return self.tasks[ref]
        for task in self.tasks.values():
            if task.get("alias") == ref:
                return task
        return None


class KarottoCoordinator(DataUpdateCoordinator[KarottoData]):
    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: KarottoClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.stream_connected = False
        self._stream_task: asyncio.Task[None] | None = None

    async def _async_update_data(self) -> KarottoData:
        try:
            user = await self.client.get_user()
            active = await self.client.list_tasks()
            completed = await self.client.list_tasks("completedTodos")
        except KarottoAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except (KarottoConnectionError, KarottoApiError) as error:
            raise UpdateFailed(str(error)) from error
        return KarottoData(user, {task["id"]: task for task in [*active, *completed]})

    def start_stream(self) -> None:
        self._stream_task = self.config_entry.async_create_background_task(
            self.hass,
            self._stream_loop(),
            name=f"{DOMAIN} events {self.config_entry.entry_id}",
        )

    async def _stream_loop(self) -> None:
        delay = STREAM_RETRY_MIN
        first = True
        while True:
            try:
                await self.client.stream_events(self._handle_event, self._on_stream_connect)
            except KarottoAuthError:
                self.stream_connected = False
                self.config_entry.async_start_reauth(self.hass)
                return
            except (KarottoConnectionError, KarottoApiError, ValueError) as error:
                _LOGGER.debug("Event stream dropped: %s", error)
            if self.stream_connected:
                delay = STREAM_RETRY_MIN
            self.stream_connected = False
            first = False
            await asyncio.sleep(delay)
            delay = min(delay * 2, STREAM_RETRY_MAX)
            if not first:
                await self.async_request_refresh()

    def _on_stream_connect(self) -> None:
        self.stream_connected = True

    async def _handle_event(self, kind: str, payload: dict[str, Any]) -> None:
        data = self.data
        if data is None:
            return
        if kind == "task.upserted":
            task = payload["task"]
            data.tasks[task["id"]] = task
        elif kind == "task.deleted":
            data.tasks.pop(payload["id"], None)
        elif kind == "tasks.reordered":
            for index, task_id in enumerate(payload["ids"]):
                if task_id in data.tasks:
                    data.tasks[task_id]["position"] = index
        elif kind == "tasks.invalidated":
            await self.async_request_refresh()
            return
        elif kind == "user.updated":
            data.user = payload["user"]
        else:
            return
        self.async_set_updated_data(data)

    def apply_task(self, task: dict[str, Any]) -> None:
        self.data.tasks[task["id"]] = task
        self.async_set_updated_data(self.data)

    def apply_order(self, kind: str, ids: list[str]) -> None:
        for index, task_id in enumerate(ids):
            if task_id in self.data.tasks:
                self.data.tasks[task_id]["position"] = index
        self.async_set_updated_data(self.data)

    async def async_run_rollover(self) -> dict[str, Any]:
        result = await self.client.run_cron()
        self.data.user = result["user"]
        if result["ran"]:
            await self.async_request_refresh()
        else:
            self.async_set_updated_data(self.data)
        return result

    async def async_score(
        self,
        ref: str,
        direction: str,
        rollover: bool,
    ) -> dict[str, Any]:
        if rollover:
            await self.async_run_rollover()
        result = await self.client.score(ref, direction)
        self.apply_task(result["task"])
        return result
