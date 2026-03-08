from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Session as MapperSession
from app.models import SessionCollaborator, Template, TemplateCollaborator, User


def can_manage_template(db: Session, template: Template, user: User) -> bool:
    if template.owner_id == user.id:
        return True
    collab = (
        db.query(TemplateCollaborator)
        .filter(
            TemplateCollaborator.template_id == template.id,
            TemplateCollaborator.user_id == user.id,
            TemplateCollaborator.can_manage.is_(True),
        )
        .first()
    )
    return collab is not None


def can_edit_session(db: Session, session_obj: MapperSession, user: User) -> bool:
    if session_obj.creator_id == user.id:
        return True
    if can_manage_template(db, session_obj.template, user):
        return True
    collab = (
        db.query(SessionCollaborator)
        .filter(
            SessionCollaborator.session_id == session_obj.id,
            SessionCollaborator.user_id == user.id,
        )
        .first()
    )
    return collab is not None


def require_template_manage(db: Session, template: Template, user: User) -> None:
    if not can_manage_template(db, template, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def require_session_manage(db: Session, session_obj: MapperSession, user: User) -> None:
    if not can_edit_session(db, session_obj, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
