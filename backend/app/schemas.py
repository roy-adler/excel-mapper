from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


FieldType = Literal["number", "string", "boolean", "date"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: EmailStr

    class Config:
        from_attributes = True


class MappingRule(BaseModel):
    sheet: str
    range: str
    type: FieldType
    label: str | None = None


class TemplateResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    schema_json: list[MappingRule]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionResponse(BaseModel):
    id: int
    template_id: int
    creator_id: int
    name: str
    share_token: str
    expires_at: datetime
    last_activity_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class TemplateCollaboratorRequest(BaseModel):
    email: EmailStr
    can_manage: bool = True


class SessionCreateRequest(BaseModel):
    name: str


class SessionCollaboratorRequest(BaseModel):
    email: EmailStr
    can_manage: bool = True


class SessionUpdateRequest(BaseModel):
    values: dict[str, Any]


class FormField(BaseModel):
    key: str
    sheet: str
    cell: str
    type: FieldType
    label: str
    value: Any


class SessionFormResponse(BaseModel):
    session_id: int
    session_name: str
    template_id: int
    fields: list[FormField]
