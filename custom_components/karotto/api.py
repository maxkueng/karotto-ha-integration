from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import API_PREFIX

STREAM_TIMEOUT = ClientTimeout(total=None, connect=15, sock_read=90)
REQUEST_TIMEOUT = ClientTimeout(total=30)


class KarottoError(Exception):
    """Base error for the karotto client."""


class KarottoConnectionError(KarottoError):
    """The server could not be reached."""


class KarottoAuthError(KarottoError):
    """The token or credentials were rejected."""


class KarottoApiError(KarottoError):
    """The server answered with an error body."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


class KarottoClient:
    def __init__(
        self,
        session: ClientSession,
        url: str,
        token: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self._session = session
        self._base = f"{normalize_url(url)}{API_PREFIX}"
        self._token = token
        self._client_id = client_id

    @property
    def token(self) -> str | None:
        return self._token

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        if self._client_id:
            headers["x-client-id"] = self._client_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                headers=self._headers(),
                json=body,
                params=params,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                return await self._read(response)
        except ClientError as error:
            raise KarottoConnectionError(str(error)) from error
        except TimeoutError as error:
            raise KarottoConnectionError("Request timed out") from error

    async def _read(self, response: ClientResponse) -> Any:
        if response.status == 204:
            return None
        text = await response.text()
        payload: Any = None
        if text:
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
        if response.status < 400:
            return payload
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            error = {}
        code = error.get("code", "error")
        message = error.get("message") or text or response.reason or "error"
        if response.status == 401:
            raise KarottoAuthError(message)
        raise KarottoApiError(response.status, code, message)

    async def login(self, username: str, password: str, name: str) -> dict[str, Any]:
        created = await self._request(
            "POST",
            "/auth/token",
            body={"username": username, "password": password, "name": name},
        )
        self._token = created["token"]
        return created

    async def get_user(self) -> dict[str, Any]:
        return await self._request("GET", "/user")

    async def update_preferences(self, patch: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", "/user/preferences", body=patch)

    async def list_tasks(self, kind: str | None = None) -> list[dict[str, Any]]:
        params = {"type": kind} if kind else None
        return await self._request("GET", "/tasks", params=params)

    async def create_task(self, task: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/tasks", body=task)

    async def update_task(self, ref: str, patch: dict[str, Any]) -> dict[str, Any]:
        return await self._request("PATCH", f"/tasks/{ref}", body=patch)

    async def delete_task(self, ref: str) -> None:
        await self._request("DELETE", f"/tasks/{ref}")

    async def score(self, ref: str, direction: str) -> dict[str, Any]:
        return await self._request("POST", f"/tasks/{ref}/score/{direction}")

    async def move_task(self, ref: str, position: int) -> list[str]:
        result = await self._request("POST", f"/tasks/{ref}/move/{position}")
        return result["ids"]

    async def run_cron(self) -> dict[str, Any]:
        return await self._request("POST", "/cron")

    async def stream_events(
        self,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]],
        on_connect: Callable[[], None] | None = None,
    ) -> None:
        """Read the SSE stream until the connection drops."""
        headers = {**self._headers(), "accept": "text/event-stream"}
        try:
            async with self._session.get(
                f"{self._base}/events",
                headers=headers,
                timeout=STREAM_TIMEOUT,
            ) as response:
                await self._read_stream(response, handler, on_connect)
        except ClientError as error:
            raise KarottoConnectionError(str(error)) from error
        except TimeoutError as error:
            raise KarottoConnectionError("Event stream timed out") from error

    async def _read_stream(
        self,
        response: ClientResponse,
        handler: Callable[[str, dict[str, Any]], Awaitable[None]],
        on_connect: Callable[[], None] | None,
    ) -> None:
        if response.status >= 400:
            await self._read(response)
        if on_connect:
            on_connect()
        event_type = ""
        data_lines: list[str] = []
        async for raw in response.content:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line == "":
                if data_lines:
                    payload = json.loads("\n".join(data_lines))
                    await handler(event_type or payload.get("type", ""), payload)
                event_type = ""
                data_lines = []
            elif line.startswith(":"):
                continue
            elif line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
