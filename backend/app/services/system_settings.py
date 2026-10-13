from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.workflow import DEFAULT_SYSTEM_SETTINGS, SystemSetting


def get(db: Session, key: str) -> Any:
    row = db.get(SystemSetting, key)
    return row.value.get("v") if row else DEFAULT_SYSTEM_SETTINGS[key]


def all_settings(db: Session) -> dict[str, Any]:
    return {k: get(db, k) for k in DEFAULT_SYSTEM_SETTINGS}


def set_value(db: Session, key: str, value: Any) -> None:
    if key not in DEFAULT_SYSTEM_SETTINGS:
        raise KeyError(key)
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value={"v": value}))
    else:
        row.value = {"v": value}
