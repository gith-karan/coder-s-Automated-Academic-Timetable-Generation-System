from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints

from app.core.roles import Role
from app.schemas.common import Name, ReadModel, StrictModel

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64,
                                            pattern=r"^[a-zA-Z0-9._-]+$")]


class LoginIn(StrictModel):
    identifier: Identifier
    password: Password
    remember_me: bool = False


class OtpRequestIn(StrictModel):
    identifier: Identifier


class OtpVerifyIn(StrictModel):
    identifier: Identifier
    code: Annotated[str, StringConstraints(pattern=r"^\d{6}$")]
    remember_me: bool = False


class PasswordChangeIn(StrictModel):
    current_password: Password
    new_password: Password


class PreferencesIn(StrictModel):
    theme_mode: Literal["light", "dark", "system"] = "system"
    color_theme: Literal["nfsu", "blue", "green", "purple", "orange", "teal"] = "nfsu"
    compact_sidebar: bool = False
    show_tooltips: bool = True
    animations: bool = True
    time_format: Literal["12h", "24h"] = "12h"


class ProfileIn(StrictModel):
    full_name: Name


class UserBrief(ReadModel):
    id: str
    full_name: str
    email: str
    role: Role


class UserOut(ReadModel):
    id: str
    email: str
    username: str | None
    full_name: str
    role: Role
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
    created_by: UserBrief | None = None
    faculty_id: str | None
    enrollment_no: str | None
    group_id: str | None
    batch_id: str | None
    preferences: dict = Field(default_factory=dict)


class MeOut(UserOut):
    permissions: list[str] = Field(default_factory=list)
    csrf_token: str | None = None


class UserCreateIn(StrictModel):
    email: EmailStr
    username: Username | None = None
    full_name: Name
    role: Role
    faculty_id: str | None = None
    enrollment_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    group_id: str | None = None
    batch_id: str | None = None


class UserUpdateIn(StrictModel):
    full_name: Name | None = None
    role: Role | None = None
    is_active: bool | None = None
    faculty_id: str | None = None
    enrollment_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    group_id: str | None = None
    batch_id: str | None = None


class UserCreatedOut(UserOut):
    temporary_password: str


class NotificationOut(ReadModel):
    id: str
    kind: str
    title: str
    body: str
    link: str | None
    data: dict
    created_at: datetime
    read_at: datetime | None


class AuditOut(ReadModel):
    seq: int
    at: datetime
    actor_id: str | None
    actor_email: str | None
    actor_role: str | None
    action: str
    category: str
    outcome: str
    entity: str | None
    entity_id: str | None
    summary: str
    data: dict
    ip: str | None
    request_id: str | None
    hash: str
