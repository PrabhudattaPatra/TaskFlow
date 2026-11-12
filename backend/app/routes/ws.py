import asyncio
import json

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.deps import get_membership
from app.models import User
from app.ws.manager import Conn, hub

router = APIRouter()


def _authenticate(token: str | None) -> int | None:
    if not token:
        return None
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError:
        return None
    with SessionLocal() as db:
        return user_id if db.get(User, user_id) else None


def _is_member(project_id: int, user_id: int) -> bool:
    with SessionLocal() as db:
        return get_membership(db, project_id, user_id) is not None


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str | None = None):
    """Authenticated at handshake via the access JWT. Events only flow to rooms the user has
    been verified (against the DB) to belong to."""
    user_id = await run_in_threadpool(_authenticate, token)
    if user_id is None:
        await ws.close(code=4401)  # unauthorized
        return
    await ws.accept()
    hub.loop = asyncio.get_running_loop()
    conn = Conn(ws, user_id)
    hub.add(conn)
    await ws.send_text(json.dumps({"type": "ready"}))
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                continue
            kind, pid = msg.get("action"), msg.get("project_id")
            if kind == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif kind == "subscribe" and isinstance(pid, int):
                if await run_in_threadpool(_is_member, pid, user_id):
                    hub.join(conn, pid)
                    await ws.send_text(json.dumps({"type": "subscribed", "project_id": pid}))
                else:
                    await ws.send_text(json.dumps({"type": "error", "project_id": pid, "detail": "forbidden"}))
            elif kind == "unsubscribe" and isinstance(pid, int):
                hub.leave(conn, pid)
    except WebSocketDisconnect:
        pass
    finally:
        hub.remove(conn)
