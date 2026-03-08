import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.excel_service import ensure_storage_dirs
from app.models import Template, TemplateCollaborator, User
from app.permissions import require_template_manage
from app.schemas import MappingRule, TemplateCollaboratorRequest, TemplateResponse
from app.security import get_current_user


router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("", response_model=TemplateResponse)
def create_template(
    name: str = Form(...),
    schema_json: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported")
    try:
        schema = json.loads(schema_json)
        _ = [MappingRule(**rule) for rule in schema]
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid schema JSON: {exc}")

    ensure_storage_dirs()
    destination = Path(settings.storage_dir) / "templates" / f"{uuid.uuid4()}.xlsx"
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    now = datetime.utcnow()
    template = Template(
        owner_id=user.id,
        name=name,
        workbook_path=str(destination),
        schema_json=schema,
        created_at=now,
        updated_at=now,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("", response_model=list[TemplateResponse])
def list_templates(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned = db.query(Template).filter(Template.owner_id == user.id)
    shared_ids = db.query(TemplateCollaborator.template_id).filter(TemplateCollaborator.user_id == user.id)
    shared = db.query(Template).filter(Template.id.in_(shared_ids))
    templates = owned.union(shared).order_by(Template.created_at.desc()).all()
    return templates


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(template_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    require_template_manage(db, template, user)
    return template


@router.put("/{template_id}/schema", response_model=TemplateResponse)
def update_schema(
    template_id: int,
    schema: list[MappingRule],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    require_template_manage(db, template, user)
    template.schema_json = [rule.model_dump() for rule in schema]
    template.updated_at = datetime.utcnow()
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.post("/{template_id}/collaborators")
def add_collaborator(
    template_id: int,
    payload: TemplateCollaboratorRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if template.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner can share template")
    target = db.query(User).filter(User.email == payload.email.lower()).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    collab = (
        db.query(TemplateCollaborator)
        .filter(
            TemplateCollaborator.template_id == template.id,
            TemplateCollaborator.user_id == target.id,
        )
        .first()
    )
    if collab:
        collab.can_manage = payload.can_manage
    else:
        collab = TemplateCollaborator(
            template_id=template.id, user_id=target.id, can_manage=payload.can_manage
        )
    db.add(collab)
    db.commit()
    return {"ok": True}
