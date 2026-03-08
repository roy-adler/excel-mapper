import secrets
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.excel_service import (
    build_fields_from_workbook,
    ensure_session_active,
    ensure_storage_dirs,
    touch_session,
    update_workbook_values,
)
from app.models import Session as MapperSession
from app.models import SessionCollaborator, Template, User
from app.permissions import require_session_manage, require_template_manage
from app.schemas import (
    SessionCollaboratorRequest,
    SessionCreateRequest,
    SessionFormResponse,
    SessionResponse,
    SessionUpdateRequest,
)
from app.security import get_current_user


router = APIRouter(prefix="/api", tags=["sessions"])


@router.post("/templates/{template_id}/sessions", response_model=SessionResponse)
def create_session_from_template(
    template_id: int,
    payload: SessionCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    require_template_manage(db, template, user)

    ensure_storage_dirs()
    session_path = Path(settings.storage_dir) / "sessions" / f"{uuid.uuid4()}.xlsx"
    shutil.copyfile(template.workbook_path, session_path)
    now = datetime.utcnow()
    session_obj = MapperSession(
        template_id=template.id,
        creator_id=user.id,
        name=payload.name,
        workbook_path=str(session_path),
        share_token=secrets.token_urlsafe(18),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_activity_at=now,
        created_at=now,
    )
    db.add(session_obj)
    db.commit()
    db.refresh(session_obj)
    return session_obj


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    own = db.query(MapperSession).filter(MapperSession.creator_id == user.id)
    shared_ids = db.query(SessionCollaborator.session_id).filter(SessionCollaborator.user_id == user.id)
    shared = db.query(MapperSession).filter(MapperSession.id.in_(shared_ids))
    sessions = own.union(shared).order_by(MapperSession.created_at.desc()).all()
    return sessions


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    require_session_manage(db, session_obj, user)
    ensure_session_active(session_obj)
    touch_session(db, session_obj)
    return session_obj


@router.get("/sessions/{session_id}/form", response_model=SessionFormResponse)
def get_session_form(
    session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    require_session_manage(db, session_obj, user)
    ensure_session_active(session_obj)
    fields = build_fields_from_workbook(session_obj.workbook_path, session_obj.template.schema_json)
    touch_session(db, session_obj)
    return SessionFormResponse(
        session_id=session_obj.id,
        session_name=session_obj.name,
        template_id=session_obj.template_id,
        fields=fields,
    )


@router.post("/sessions/{session_id}/update")
def update_session_values(
    session_id: int,
    payload: SessionUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    require_session_manage(db, session_obj, user)
    ensure_session_active(session_obj)
    update_workbook_values(session_obj.workbook_path, session_obj.template.schema_json, payload.values)
    touch_session(db, session_obj)
    return {"ok": True}


@router.get("/sessions/{session_id}/download")
def download_session(
    session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    require_session_manage(db, session_obj, user)
    ensure_session_active(session_obj)
    touch_session(db, session_obj)
    return FileResponse(
        session_obj.workbook_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{session_obj.name}.xlsx",
    )


@router.post("/sessions/{session_id}/collaborators")
def add_session_collaborator(
    session_id: int,
    payload: SessionCollaboratorRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_obj = db.query(MapperSession).filter(MapperSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session_obj.creator_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only session creator can share")
    target = db.query(User).filter(User.email == payload.email.lower()).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    collab = (
        db.query(SessionCollaborator)
        .filter(SessionCollaborator.session_id == session_id, SessionCollaborator.user_id == target.id)
        .first()
    )
    if collab:
        collab.can_manage = payload.can_manage
    else:
        collab = SessionCollaborator(
            session_id=session_id, user_id=target.id, can_manage=payload.can_manage
        )
    db.add(collab)
    db.commit()
    return {"ok": True}


@router.get("/public/sessions/{share_token}", response_model=SessionFormResponse)
def get_public_form(share_token: str, db: Session = Depends(get_db)):
    session_obj = db.query(MapperSession).filter(MapperSession.share_token == share_token).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    ensure_session_active(session_obj)
    fields = build_fields_from_workbook(session_obj.workbook_path, session_obj.template.schema_json)
    touch_session(db, session_obj)
    return SessionFormResponse(
        session_id=session_obj.id,
        session_name=session_obj.name,
        template_id=session_obj.template_id,
        fields=fields,
    )


@router.post("/public/sessions/{share_token}/update")
def update_public_values(share_token: str, payload: SessionUpdateRequest, db: Session = Depends(get_db)):
    session_obj = db.query(MapperSession).filter(MapperSession.share_token == share_token).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    ensure_session_active(session_obj)
    update_workbook_values(session_obj.workbook_path, session_obj.template.schema_json, payload.values)
    touch_session(db, session_obj)
    return {"ok": True}
