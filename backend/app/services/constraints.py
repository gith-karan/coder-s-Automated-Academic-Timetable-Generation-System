"""Catalogue of configurable constraints (shown on the Constraints page) and mapping to solver options."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.academic import ConstraintMode, ConstraintSetting
from app.scheduling.domain import Options

# category matches the UI tabs: Faculty · Rooms · Subjects · Global
CATALOGUE: list[dict] = [
    {"key": "faculty_max_per_day", "category": "Faculty", "label": "Maximum periods per day",
     "description": "Default daily teaching limit for faculty who have no personal limit.",
     "modes": ["HARD", "OFF"], "default_mode": "HARD", "default_value": 5, "has_value": True},
    {"key": "faculty_preferred_slots", "category": "Faculty", "label": "Honour preferred teaching slots",
     "description": "Try to place sessions inside each faculty member's preferred slots.",
     "modes": ["SOFT", "OFF"], "default_mode": "SOFT", "default_weight": 3},
    {"key": "theory_in_lab", "category": "Rooms", "label": "Allow theory classes in laboratories",
     "description": "If classrooms run out, labs with enough seats may host theory periods.",
     "modes": ["SOFT", "OFF"], "default_mode": "OFF"},
    {"key": "subject_spread", "category": "Subjects", "label": "One period of a subject per day",
     "description": "Spread a subject's theory periods across different days of the week.",
     "modes": ["HARD", "SOFT", "OFF"], "default_mode": "SOFT", "default_weight": 5},
    {"key": "avoid_last_period", "category": "Subjects", "label": "Avoid the last period of the day",
     "description": "Prefer not to schedule sessions in the final period.",
     "modes": ["SOFT", "OFF"], "default_mode": "SOFT", "default_weight": 1},
    {"key": "group_max_per_day", "category": "Global", "label": "Maximum periods per day for a class",
     "description": "Students never have more than this many periods on one day.",
     "modes": ["HARD", "OFF"], "default_mode": "OFF", "default_value": 6, "has_value": True},
    {"key": "stability", "category": "Global", "label": "Keep sessions in place when regenerating",
     "description": "When regenerating, move as few existing sessions as possible.",
     "modes": ["SOFT", "OFF"], "default_mode": "SOFT", "default_weight": 4},
]
_BY_KEY = {c["key"]: c for c in CATALOGUE}

# Rules from the problem statement that can never be switched off (displayed as locked "HARD").
MANDATORY_RULES = [
    "Sessions fall within working hours and avoid breaks",
    "Faculty are scheduled only when available",
    "No faculty member, room or student group has overlapping sessions",
    "Whole-class sessions never overlap a practical of any of that class's batches",
    "Room capacity meets class or batch strength",
    "Practicals use a suitable laboratory and consecutive periods",
    "Every subject receives all its weekly periods and sessions",
    "Fixed and locked sessions stay in their slots",
]


def is_known(key: str) -> bool:
    return key in _BY_KEY


def current(db: Session) -> list[dict]:
    stored = {c.key: c for c in db.query(ConstraintSetting).all()}
    out = []
    for c in CATALOGUE:
        s = stored.get(c["key"])
        out.append({**c,
                    "mode": s.mode.value if s else c["default_mode"],
                    "weight": s.weight if s else c.get("default_weight", 5),
                    "value": (s.value if s and s.value is not None else c.get("default_value"))})
    return out


def validate_setting(key: str, mode: ConstraintMode) -> str | None:
    c = _BY_KEY.get(key)
    if c is None:
        return f"Unknown constraint '{key}'"
    if mode.value not in c["modes"]:
        return f"'{c['label']}' cannot be set to {mode.value}"
    return None


def to_options(db: Session) -> Options:
    cfg = {c["key"]: c for c in current(db)}
    o = Options()
    sp = cfg["subject_spread"]
    o.spread_mode, o.spread_weight = sp["mode"], sp["weight"]
    pref = cfg["faculty_preferred_slots"]
    o.preferred_weight = pref["weight"] if pref["mode"] != "OFF" else 0
    st = cfg["stability"]
    o.stability_weight = st["weight"] if st["mode"] != "OFF" else 0
    late = cfg["avoid_last_period"]
    o.late_weight = late["weight"] if late["mode"] != "OFF" else 0
    o.allow_theory_in_lab = cfg["theory_in_lab"]["mode"] != "OFF"
    fm = cfg["faculty_max_per_day"]
    o.faculty_daily_default = fm["value"] if fm["mode"] == "HARD" else None
    gm = cfg["group_max_per_day"]
    o.group_daily_default = gm["value"] if gm["mode"] == "HARD" else None
    return o
