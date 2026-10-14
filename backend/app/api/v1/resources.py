"""Coordinator input resources — all built from the single generic CRUD factory."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.api.crud import crud_router
from app.api.deps import Principal
from app.core.errors import bad_request
from app.core.roles import EVERYONE, Role
from app.models.academic import (
    Batch, ConstraintMode, CustomRule, Faculty, FixedSession, LabType, Programme, Room, RoomKind, RuleKind,
    StudentGroup, Subject, SubjectKind,
)
from app.scheduling.timegrid import to_minutes
from app.models.identity import User
from app.schemas import academic as s

router = APIRouter()


def _require(db: Session, model, id_: str | None, what: str):
    if id_ is None:
        return None
    obj = db.get(model, id_)
    if obj is None:
        raise bad_request(f"Selected {what} does not exist.")
    return obj


# ---------------------------------------------------------------- rooms
def _room_apply(db: Session, room: Room, data: dict, p: Principal) -> None:
    for k, v in data.items():
        setattr(room, k, v)
    if room.kind == RoomKind.LAB and not room.lab_type_id:
        raise bad_request("Choose the laboratory type for a lab.")
    if room.kind == RoomKind.CLASSROOM:
        room.lab_type_id = None
    _require(db, LabType, room.lab_type_id, "laboratory type")


# ---------------------------------------------------------------- programmes
def _programme_apply(db: Session, prog: Programme, data: dict, p: Principal) -> None:
    for k, v in data.items():
        setattr(prog, k, v)
    if prog.coordinator_id:
        u = db.get(User, prog.coordinator_id)
        if u is None or not u.is_active or u.role not in (Role.COORDINATOR, Role.ADMIN):
            raise bad_request("The programme coordinator must be an active coordinator or admin account.")


# ---------------------------------------------------------------- groups + batches
def _sync_batches(group: StudentGroup, batches: list[dict]) -> None:
    names = [b["name"] for b in batches]
    if len(set(n.lower() for n in names)) != len(names):
        raise bad_request("Batch names must be unique within a class.")
    existing = {b.name: b for b in group.batches}
    keep = []
    for b in batches:
        cur = existing.get(b["name"])
        if cur is None:
            cur = Batch(name=b["name"], strength=b["strength"])
        cur.strength = b["strength"]
        keep.append(cur)
    group.batches = keep


def _group_apply(db: Session, group: StudentGroup, data: dict, p: Principal) -> None:
    batches = data.pop("batches", None)
    for k, v in data.items():
        setattr(group, k, v)
    prog = _require(db, Programme, group.programme_id, "programme")
    _require(db, Room, group.home_room_id, "home classroom")
    if prog and group.semester > prog.duration_semesters:
        raise bad_request(f"{prog.code} has only {prog.duration_semesters} semesters.")
    dup = db.query(StudentGroup).filter(StudentGroup.programme_id == group.programme_id,
                                        StudentGroup.semester == group.semester,
                                        StudentGroup.section == group.section, StudentGroup.id != group.id).first()
    if dup:
        raise bad_request(f"{prog.code if prog else 'This programme'} already has Semester {group.semester} "
                          f"Section {group.section}. Use a different section letter (e.g. B).")
    if batches is not None:
        _sync_batches(group, batches)
    if group.batches and any(b.strength > group.strength for b in group.batches):
        raise bad_request("A batch cannot be larger than its class.")


# ---------------------------------------------------------------- faculty
def _faculty_apply(db: Session, fac: Faculty, data: dict, p: Principal) -> None:
    pids = data.pop("programme_ids", None)
    for k, v in data.items():
        setattr(fac, k, v)
    if fac.email:
        fac.email = fac.email.lower()
    if pids is not None:
        progs = [db.get(Programme, i) for i in dict.fromkeys(pids)]
        if any(x is None for x in progs):
            raise bad_request("One of the selected programmes does not exist.")
        fac.programmes = progs
        clash = [s.code for s in fac.subjects if progs and s.programme_id not in {x.id for x in progs}]
        if clash:
            raise bad_request(f"{fac.name} still teaches {', '.join(clash[:5])} in a programme you removed. "
                              "Reassign those subjects first.")


# ---------------------------------------------------------------- subjects
def _subject_apply(db: Session, subj: Subject, data: dict, p: Principal) -> None:
    fids = data.pop("faculty_ids", None)
    for k, v in data.items():
        setattr(subj, k, v)
    _require(db, Programme, subj.programme_id, "programme")
    if subj.kind == SubjectKind.PRACTICAL:
        if not subj.lab_type_id:
            raise bad_request("Choose the laboratory type required by this practical.")
        _require(db, LabType, subj.lab_type_id, "laboratory type")
        if subj.sessions_per_week < 1:
            raise bad_request("A practical needs at least 1 session per week.")
        subj.periods_per_week = 0
    else:
        if subj.periods_per_week < 1:
            raise bad_request("A theory subject needs at least 1 period per week.")
        subj.lab_type_id, subj.sessions_per_week, subj.consecutive_periods = None, 0, 1
    if fids is not None:
        fac = [db.get(Faculty, f) for f in dict.fromkeys(fids)]
        if any(f is None for f in fac):
            raise bad_request("One of the selected faculty members does not exist.")
        for f in fac:
            if f.programmes and subj.programme_id not in {x.id for x in f.programmes}:
                prog = db.get(Programme, subj.programme_id)
                raise bad_request(f"{f.name} is not allowed to teach in {prog.code if prog else 'this programme'}. "
                                  "Add it under Faculty → Can teach in, or choose another faculty member.")
        subj.faculty = fac


def _fixed_apply(db: Session, fs: FixedSession, data: dict, p: Principal) -> None:
    for k, v in data.items():
        setattr(fs, k, v)
    subj = _require(db, Subject, fs.subject_id, "subject")
    grp = _require(db, StudentGroup, fs.group_id, "class")
    if subj and grp and (subj.programme_id, subj.semester) != (grp.programme_id, grp.semester):
        raise bad_request("The subject does not belong to this class's programme and semester.")
    if fs.batch_id:
        b = _require(db, Batch, fs.batch_id, "batch")
        if b.group_id != fs.group_id:
            raise bad_request("The batch does not belong to this class.")
    _require(db, Room, fs.room_id, "room")


class _FixedUpdate(s.FixedSessionIn):
    pass


# ---------------------------------------------------------------- custom rules
def _rule_apply(db: Session, rule: CustomRule, data: dict, p: Principal) -> None:
    for k, v in data.items():
        setattr(rule, k, v)
    prm = dict(rule.params or {})
    kind = rule.kind

    def times_ok(start: str, end: str) -> None:
        if to_minutes(start) >= to_minutes(end):
            raise bad_request("Start time must be before end time.")

    if kind == RuleKind.CLASS_BLOCK:
        _require(db, StudentGroup, prm.get("group_id") or "-", "class")
        ranges = prm.get("ranges") or []
        if not ranges:
            raise bad_request("Choose at least one day and time range.")
        for r in ranges:
            times_ok(r["start"], r["end"])
        rule.mode = ConstraintMode.HARD
        prm = {"group_id": prm["group_id"], "label": str(prm.get("label") or "Blocked")[:60],
               "ranges": [{"day": int(r["day"]), "start": r["start"], "end": r["end"]} for r in ranges]}
    elif kind == RuleKind.SUBJECT_WINDOW:
        _require(db, Subject, prm.get("subject_id") or "-", "subject")
        days = sorted({int(d) for d in prm.get("days") or []})
        if not days:
            raise bad_request("Choose at least one day.")
        times_ok(prm.get("start", ""), prm.get("end", ""))
        prm = {"subject_id": prm["subject_id"], "days": days, "start": prm["start"], "end": prm["end"]}
    elif kind == RuleKind.FACULTY_MAX_CONSECUTIVE:
        if prm.get("faculty_id"):
            _require(db, Faculty, prm["faculty_id"], "faculty member")
        n = int(prm.get("max") or 0)
        if not 1 <= n <= 8:
            raise bad_request("Maximum consecutive periods must be between 1 and 8.")
        prm = {"faculty_id": prm.get("faculty_id") or None, "max": n}
    elif kind == RuleKind.ROOM_RESERVED:
        _require(db, Room, prm.get("room_id") or "-", "room")
        pids = list(dict.fromkeys(prm.get("programme_ids") or []))
        if not pids or any(db.get(Programme, i) is None for i in pids):
            raise bad_request("Choose at least one valid programme.")
        rule.mode = ConstraintMode.HARD
        prm = {"room_id": prm["room_id"], "programme_ids": pids}
    if rule.mode == ConstraintMode.OFF:
        rule.enabled, rule.mode = False, ConstraintMode.SOFT
    rule.params = prm


router.include_router(crud_router(
    model=LabType, entity="lab type", create_schema=s.LabTypeIn, update_schema=s.LabTypeIn, out_schema=s.LabTypeOut,
    read_roles=EVERYONE, write_perm="setup.edit", search=[LabType.name], order_by=[LabType.name],
    label=lambda o: o.name), prefix="/lab-types", tags=["lab types"])

router.include_router(crud_router(
    model=Room, entity="room", create_schema=s.RoomIn, update_schema=s.RoomUpdate, out_schema=s.RoomOut,
    read_roles=EVERYONE, write_perm="setup.edit", search=[Room.code, Room.name, Room.building],
    filters={"kind": Room.kind, "lab_type_id": Room.lab_type_id}, order_by=[Room.kind, Room.code],
    on_create=_room_apply, on_update=_room_apply), prefix="/rooms", tags=["rooms"])

router.include_router(crud_router(
    model=Programme, entity="programme", create_schema=s.ProgrammeIn, update_schema=s.ProgrammeUpdate,
    out_schema=s.ProgrammeOut, read_roles=EVERYONE, write_perm="setup.edit",
    search=[Programme.code, Programme.name, Programme.school], filters={"level": Programme.level},
    order_by=[Programme.code], on_create=_programme_apply, on_update=_programme_apply),
    prefix="/programmes", tags=["programmes"])

router.include_router(crud_router(
    model=StudentGroup, entity="class", create_schema=s.GroupIn, update_schema=s.GroupUpdate, out_schema=s.GroupOut,
    read_roles=EVERYONE, write_perm="setup.edit", search=[StudentGroup.section],
    filters={"programme_id": StudentGroup.programme_id, "semester": StudentGroup.semester},
    order_by=[StudentGroup.programme_id, StudentGroup.semester, StudentGroup.section],
    on_create=_group_apply, on_update=_group_apply, label=lambda o: o.label), prefix="/groups", tags=["classes"])

# Faculty records include e-mails and availability (personal data): readable only with "setup.view".
router.include_router(crud_router(
    model=Faculty, entity="faculty", create_schema=s.FacultyIn, update_schema=s.FacultyUpdate, out_schema=s.FacultyOut,
    read_perm="setup.view", write_perm="setup.edit", search=[Faculty.code, Faculty.name, Faculty.email, Faculty.designation],
    filters={"school": Faculty.school}, order_by=[Faculty.code],
    on_create=_faculty_apply, on_update=_faculty_apply), prefix="/faculty", tags=["faculty"])

router.include_router(crud_router(
    model=Subject, entity="subject", create_schema=s.SubjectIn, update_schema=s.SubjectUpdate, out_schema=s.SubjectOut,
    read_roles=EVERYONE, write_perm="setup.edit", search=[Subject.code, Subject.name],
    filters={"programme_id": Subject.programme_id, "semester": Subject.semester, "kind": Subject.kind},
    order_by=[Subject.code], on_create=_subject_apply, on_update=_subject_apply), prefix="/subjects", tags=["subjects"])

router.include_router(crud_router(
    model=FixedSession, entity="fixed session", create_schema=s.FixedSessionIn, update_schema=_FixedUpdate,
    out_schema=s.FixedSessionOut, read_perm="setup.view", write_perm="setup.edit", order_by=[FixedSession.day],
    on_create=_fixed_apply, on_update=_fixed_apply, label=lambda o: f"{o.day}/{o.start_period}"),
    prefix="/fixed-sessions", tags=["constraints"])

router.include_router(crud_router(
    model=CustomRule, entity="custom rule", create_schema=s.CustomRuleIn, update_schema=s.CustomRuleUpdate,
    out_schema=s.CustomRuleOut, read_perm="setup.view", write_perm="setup.edit", order_by=[CustomRule.created_at],
    on_create=_rule_apply, on_update=_rule_apply, label=lambda o: o.kind.value), prefix="/custom-rules", tags=["constraints"])
