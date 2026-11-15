from datetime import timedelta
from typing import Final

DOMAIN: Final = "karotto"

CONF_URL: Final = "url"
CONF_TOKEN: Final = "token"
CONF_USER_ID: Final = "user_id"
CONF_USERNAME: Final = "username"

TOKEN_NAME: Final = "Home Assistant"
API_PREFIX: Final = "/api/v1"
CARD_FILE: Final = "karotto-card.js"
CARD_URL: Final = f"/{DOMAIN}/{CARD_FILE}"
API_REVISION_HEADER: Final = "x-karotto-api-revision"
BASELINE_API_REVISION: Final = 1
REQUIRED_API_REVISION: Final = 1
POLL_INTERVAL: Final = timedelta(minutes=10)
STREAM_RETRY_MIN: Final = 5
STREAM_RETRY_MAX: Final = 120

SERVICE_SCORE: Final = "score"
SERVICE_RUN_ROLLOVER: Final = "run_rollover"
SERVICE_ADD_TASK: Final = "add_task"
SERVICE_FIND_TASKS: Final = "find_tasks"
SERVICE_COMPLETE_TASKS: Final = "complete_tasks"

EVENT_TASK_COMPLETED: Final = "karotto_task_completed"

ISSUE_OUTDATED_SERVER: Final = "outdated_server"

ATTR_TASK: Final = "task"
ATTR_DIRECTION: Final = "direction"
ATTR_ROLLOVER: Final = "rollover"
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_TYPE: Final = "type"
ATTR_TITLE: Final = "title"
ATTR_NOTES: Final = "notes"
ATTR_ALIAS: Final = "alias"
ATTR_DUE_DATE: Final = "due_date"
ATTR_ALIAS_PREFIX: Final = "alias_prefix"
ATTR_STATUS: Final = "status"
