import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.locks import lock_manager
from app.models import Session as MapperSession
from app.models import User


router = APIRouter(tags=["locks"])


def _user_from_token(token: str, db: Session) -> User | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        return None
    return db.query(User).filter(User.id == user_id).first()


@router.websocket("/ws/locks/sessions/{session_id}")
async def locks_authenticated(websocket: WebSocket, session_id: int, token: str, db: Session = Depends(get_db)):
    await websocket.accept()
    user = _user_from_token(token, db)
    if not user:
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return
    owner = f"user:{user.id}"
    session_key = f"session:{session_id}"
    try:
        while True:
            text = await websocket.receive_text()
            payload = json.loads(text)
            action = payload.get("action")
            field_key = payload.get("field")
            if not field_key:
                continue
            if action == "lock":
                ok = lock_manager.acquire(session_key, field_key, owner)
                await websocket.send_json({"type": "lock", "field": field_key, "ok": ok, "owner": owner})
            elif action == "unlock":
                lock_manager.release(session_key, field_key, owner)
                await websocket.send_json({"type": "unlock", "field": field_key, "ok": True})
            elif action == "heartbeat":
                ok = lock_manager.heartbeat(session_key, field_key, owner)
                await websocket.send_json({"type": "heartbeat", "field": field_key, "ok": ok})
    except WebSocketDisconnect:
        return


@router.websocket("/ws/locks/public/{share_token}")
async def locks_public(websocket: WebSocket, share_token: str, name: str = "guest", db: Session = Depends(get_db)):
    await websocket.accept()
    session_obj = db.query(MapperSession).filter(MapperSession.share_token == share_token).first()
    if not session_obj:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return
    owner = f"guest:{name}"
    session_key = f"session:{session_obj.id}"
    try:
        while True:
            text = await websocket.receive_text()
            payload = json.loads(text)
            action = payload.get("action")
            field_key = payload.get("field")
            if not field_key:
                continue
            if action == "lock":
                ok = lock_manager.acquire(session_key, field_key, owner)
                await websocket.send_json({"type": "lock", "field": field_key, "ok": ok, "owner": owner})
            elif action == "unlock":
                lock_manager.release(session_key, field_key, owner)
                await websocket.send_json({"type": "unlock", "field": field_key, "ok": True})
            elif action == "heartbeat":
                ok = lock_manager.heartbeat(session_key, field_key, owner)
                await websocket.send_json({"type": "heartbeat", "field": field_key, "ok": ok})
    except WebSocketDisconnect:
        return
