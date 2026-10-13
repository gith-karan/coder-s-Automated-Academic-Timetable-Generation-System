"""Maker–checker workflow: changes that need a higher role's approval before they take effect."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, IdMixin, TimestampMixin
from app.core.roles import Role
from app.models.identity import User


class RequestKind(StrEnum):
    AVAILABILITY = "AVAILABILITY"            # faculty -> coordinator
    SESSION_MOVE = "SESSION_MOVE"            # faculty -> coordinator
    TIMETABLE_PUBLISH = "TIMETABLE_PUBLISH"  # coordinator -> admin


class RequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ChangeRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "change_requests"

    kind: Mapped[RequestKind] = mapped_column(Enum(RequestKind, native_enum=False, length=24), index=True)
    status: Mapped[RequestStatus] = mapped_column(Enum(RequestStatus, native_enum=False, length=16),
                                                  default=RequestStatus.PENDING, index=True)
    reviewer_role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16))  # minimum role to review
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_comment: Mapped[str | None] = mapped_column(Text)

    requested_by: Mapped[User] = relationship(foreign_keys=[requested_by_id], lazy="joined")
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id], lazy="joined")


class SystemSetting(Base):
    """Admin-controlled switches, e.g. whether publishing needs admin approval."""

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


DEFAULT_SYSTEM_SETTINGS: dict[str, object] = {
    "publish_requires_admin_approval": True,
    "faculty_availability_requires_approval": True,
    "solver_time_limit_s": 30,
}
