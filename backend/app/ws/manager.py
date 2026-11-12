"""In-process WebSocket hub.

Rooms:
  * project room  -> only sockets whose user is a verified member of that project
  * user room     -> every socket belonging to one user (personal events)

Nothing is ever broadcast globally. Routes are sync (run in a threadpool), so they publish
through `publish_*` which hands the coroutine to the server's event loop.
"""
import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("taskflow.ws")


class Conn:
    def __init__(self, ws: WebSocket, user_id: int):
        self.ws = ws
        self.user_id = user_id
        self.projects: set[int] = set()


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conns: set[Conn] = set()
        self.by_project: dict[int, set[Conn]] = defaultdict(set)
        self.by_user: dict[int, set[Conn]] = defaultdict(set)

    # --- connection lifecycle (called on the event loop) ---
    def add(self, conn: Conn) -> None:
        self.conns.add(conn)
        self.by_user[conn.user_id].add(conn)

    def remove(self, conn: Conn) -> None:
        self.conns.discard(conn)
        self.by_user[conn.user_id].discard(conn)
        for pid in list(conn.projects):
            self.by_project[pid].discard(conn)

    def join(self, conn: Conn, project_id: int) -> None:
        conn.projects.add(project_id)
        self.by_project[project_id].add(conn)

    def leave(self, conn: Conn, project_id: int) -> None:
        conn.projects.discard(project_id)
        self.by_project[project_id].discard(conn)

    async def _send(self, targets: list[Conn], message: dict[str, Any]) -> None:
        text = json.dumps(message, default=str)
        for c in targets:
            try:
                await c.ws.send_text(text)
            except Exception:  # dead socket; its receive loop will clean up
                log.debug("send failed for user %s", c.user_id)

    async def to_project(self, project_id: int, message: dict[str, Any]) -> None:
        await self._send(list(self.by_project.get(project_id, ())), message)

    async def to_user(self, user_id: int, message: dict[str, Any]) -> None:
        await self._send(list(self.by_user.get(user_id, ())), message)

    async def evict(self, user_id: int, project_id: int) -> None:
        for c in list(self.by_user.get(user_id, ())):
            self.leave(c, project_id)

    # --- thread-safe entry points for sync route handlers ---
    def _run(self, coro) -> None:
        if self.loop is None or self.loop.is_closed():
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    def publish_project(self, project_id: int, message: dict[str, Any]) -> None:
        self._run(self.to_project(project_id, message))

    def publish_user(self, user_id: int, message: dict[str, Any]) -> None:
        self._run(self.to_user(user_id, message))

    def evict_user(self, user_id: int, project_id: int) -> None:
        self._run(self.evict(user_id, project_id))


hub = Hub()
