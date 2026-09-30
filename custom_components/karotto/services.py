from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import KarottoApiError, KarottoConnectionError
from .const import (
    ATTR_ALIAS,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DIRECTION,
    ATTR_DUE_DATE,
    ATTR_NOTES,
    ATTR_ROLLOVER,
    ATTR_TASK,
    ATTR_TITLE,
    ATTR_TYPE,
    DOMAIN,
    SERVICE_ADD_TASK,
    SERVICE_RUN_ROLLOVER,
    SERVICE_SCORE,
)
from .coordinator import KarottoCoordinator

ENTRY_FIELD = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}

SCORE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TASK): cv.string,
        vol.Optional(ATTR_DIRECTION, default="up"): vol.In(["up", "down"]),
        vol.Optional(ATTR_ROLLOVER, default=True): cv.boolean,
        **ENTRY_FIELD,
    }
)

RUN_ROLLOVER_SCHEMA = vol.Schema(ENTRY_FIELD)

ADD_TASK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TYPE): vol.In(["habit", "daily", "todo"]),
        vol.Required(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_NOTES, default=""): cv.string,
        vol.Optional(ATTR_ALIAS): cv.string,
        vol.Optional(ATTR_DUE_DATE): cv.date,
        **ENTRY_FIELD,
    }
)


def coordinator_for(hass: HomeAssistant, call: ServiceCall) -> KarottoCoordinator:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if not entries:
        raise ServiceValidationError("No loaded karotto account matches this call")
    if len(entries) > 1:
        raise ServiceValidationError(
            "Several karotto accounts are configured; pass config_entry_id"
        )
    return entries[0].runtime_data


async def guarded(action):  # type: ignore[no-untyped-def]
    try:
        return await action
    except KarottoApiError as error:
        raise ServiceValidationError(error.args[0]) from error
    except KarottoConnectionError as error:
        raise HomeAssistantError(f"karotto is unreachable: {error}") from error


def task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "type": task["type"],
        "title": task["text"],
        "alias": task["alias"],
        "value": task["value"],
        "completed": task.get("completed"),
        "streak": task.get("streak"),
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    async def score(call: ServiceCall) -> ServiceResponse:
        coordinator = coordinator_for(hass, call)
        result = await guarded(
            coordinator.async_score(
                call.data[ATTR_TASK],
                call.data[ATTR_DIRECTION],
                call.data[ATTR_ROLLOVER],
            )
        )
        return {**task_summary(result["task"]), "delta": result["delta"]}

    async def run_rollover(call: ServiceCall) -> ServiceResponse:
        coordinator = coordinator_for(hass, call)
        result = await guarded(coordinator.async_run_rollover())
        return {"ran": result["ran"], "days_missed": result["daysMissed"]}

    async def add_task(call: ServiceCall) -> ServiceResponse:
        coordinator = coordinator_for(hass, call)
        body: dict[str, Any] = {
            "type": call.data[ATTR_TYPE],
            "text": call.data[ATTR_TITLE],
            "notes": call.data[ATTR_NOTES],
        }
        if ATTR_ALIAS in call.data:
            body["alias"] = call.data[ATTR_ALIAS]
        if call.data[ATTR_TYPE] == "todo" and ATTR_DUE_DATE in call.data:
            body["dueDate"] = call.data[ATTR_DUE_DATE].isoformat()
        created = await guarded(coordinator.client.create_task(body))
        coordinator.apply_task(created)
        return task_summary(created)

    hass.services.async_register(
        DOMAIN, SERVICE_SCORE, score, SCORE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_ROLLOVER,
        run_rollover,
        RUN_ROLLOVER_SCHEMA,
        SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_TASK, add_task, ADD_TASK_SCHEMA, SupportsResponse.OPTIONAL
    )
