"""Real NFSU dataset — School of Cyber Security & Digital Forensics (SCSDF), Gandhinagar, Semester I, 2026-27.

Source: the official class timetables effective 12/10/2026 for M.Tech. AI & DS (Cyber Security),
M.Sc. Cyber Security, B.Tech.–M.Tech. CSE (Cyber Security) and M.Sc. DFIS. Faculty names, subject codes
and names, rooms, university timings and weekly teaching load (periods counted per subject) are taken
from those timetables. Faculty availability is NOT copied from them: everyone is available all week,
so the generator builds its own conflict-free timetable.

Where the source shows two faculty members for one course (e.g. MFAI: Dr. Himesh Patel teaches the
lectures and Dr. Ashutosh Tripathi the 2-hour block), the course is split into components that keep
the official code plus a suffix (-L = 2-period lab/tutorial block, -T2 = second lecturer).

ASSUMPTIONS (not in the source; editable in the app): class strengths, room capacities, the
Physics Lab and Drawing Hall rooms (their names are not given), faculty e-mail addresses.

Run:  python -m app.seed            (seeds an empty database)
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.core.security import hash_password
from app.models.academic import (
    Break, CalendarSettings, ConstraintMode, ConstraintSetting, Faculty, LabType, Level, Programme, Room, RoomKind,
    StudentGroup, Subject, SubjectKind,
)
from app.models.identity import User
from app.models.timetable import Timetable
from app.services import audit

SCSDF = "School of Cyber Security & Digital Forensics"

LAB_TYPES = [
    ("Computer Lab", "Networked computer laboratory (lab sessions and 2-hour practical blocks)"),
    ("Research Lab", "Cyber Security & Forensics Research Lab"),
    ("Physics Lab", "Engineering physics practicals"),
    ("Drawing Hall", "Engineering graphics / drawing practice"),
]

ROOMS = [  # code, name, kind, lab type, capacity (ASSUMED), building
    ("IFS 311", "IFS 311", "CLASSROOM", None, 40, "IFS Building"),
    ("BL 209-210", "BL 209-210", "CLASSROOM", None, 60, "BL Building"),
    ("LL", "Language Lab (LL)", "CLASSROOM", None, 45, "SCSDF"),
    ("SEMINAR HALL", "Seminar Hall", "CLASSROOM", None, 120, "SCSDF"),
    ("IFS 002", "IFS 002", "LAB", "Computer Lab", 60, "IFS Building"),
    ("IFS 302", "IFS 302", "LAB", "Computer Lab", 45, "IFS Building"),
    ("BL 302", "BL 302", "LAB", "Computer Lab", 45, "BL Building"),
    ("BL 303", "BL 303", "LAB", "Computer Lab", 45, "BL Building"),
    ("BL 304", "BL 304", "LAB", "Computer Lab", 45, "BL Building"),
    ("CSFRL", "Cyber Security & Forensics Research Lab (CSFRL)", "LAB", "Research Lab", 40, "SCSDF"),
    ("PHY LAB", "Physics Lab", "LAB", "Physics Lab", 60, "SCSDF"),
    ("DRAWING HALL", "Engineering Drawing Hall", "LAB", "Drawing Hall", 70, "SCSDF"),
]

PROGRAMMES = [  # code, name, level, semesters, coordinator e-mail
    ("MTECH-AIDS", "M.Tech. AI and DS (Cyber Security)", "PG", 4, "ahlad.kumar@nfsu.ac.in"),
    ("MSC-CS", "M.Sc. Cyber Security", "PG", 4, "pruthvish.rajput@nfsu.ac.in"),
    ("BTECH-MTECH-CSE", "B.Tech.–M.Tech. Computer Science and Engineering (Cyber Security)", "INTEGRATED", 10, None),
    ("MSC-DFIS", "M.Sc. Digital Forensics and Information Security", "PG", 4, None),
]

GROUPS = [  # programme, semester, section, strength (ASSUMED), home room ("Venue" on the timetable)
    ("MTECH-AIDS", 1, "A", 30, "IFS 311"),
    ("MSC-CS", 1, "A", 40, "BL 209-210"),
    ("BTECH-MTECH-CSE", 1, "A", 60, "SEMINAR HALL"),
    ("MSC-DFIS", 1, "A", 40, "LL"),
]

FACULTY = [  # code (initials used on the timetables), name, designation, e-mail (ASSUMED)
    ("HAP", "Dr. Himesh A. Patel", "Faculty", "himesh.patel"),
    ("AT", "Dr. Ashutosh Tripathi", "Faculty", "ashutosh.tripathi"),
    ("VK", "Dr. Vijeta Khare", "Faculty", "vijeta.khare"),
    ("PK", "Mr. Prakash Khasor", "Faculty", "prakash.khasor"),
    ("NP", "Dr. Nilesh Panchal", "Faculty", "nilesh.panchal"),
    ("KP", "Ms. Krupali Panchal", "Faculty", "krupali.panchal"),
    ("MP", "Dr. Mukti Padhya", "Faculty", "mukti.padhya"),
    ("DR", "Prof. (Dr.) Digvijaysinh Rathod", "Professor", "digvijaysinh.rathod"),
    ("NG", "Dr. Neha Gahlan", "Faculty", "neha.gahlan"),
    ("DD", "Mr. Dharmesh Dave", "Faculty", "dharmesh.dave"),
    ("MM", "Dr. Modhuparna Manna", "Faculty", "modhuparna.manna"),
    ("RK", "Dr. Ravinder Kumar", "Faculty", "ravinder.kumar"),
    ("VA", "Mr. Vivek Ayar", "Faculty", "vivek.ayar"),
    ("DM", "Dr. Deepak Mashru", "Faculty", "deepak.mashru"),
    ("RT", "Dr. Rasik Tanna", "Faculty", "rasik.tanna"),
    ("PR", "Prof. (Dr.) Parag Rughani", "Professor", "parag.rughani"),
    ("SR", "Mr. Sarang Rajvansh", "Faculty", "sarang.rajvansh"),
    ("RS", "Dr. Ramya Shah", "Faculty", "ramya.shah"),
    ("HP", "Dr. Himanshu Patel", "Faculty", "himanshu.patel"),
]

# code, name, short name (shown on timetables), programme, kind,
# weekly (theory: periods | practical: (sessions, consecutive, lab type)), faculty
T, P = "THEORY", "PRACTICAL"
LAB2 = (1, 2, "Computer Lab")
SUBJECTS = [
    # ---- M.Tech. AI & DS (Cyber Security) – I
    ("MTAI26-PC-101", "Mathematical Foundation for Artificial Intelligence", "MFAI", "MTECH-AIDS", T, 3, ["HAP"]),
    ("MTAI26-PC-101-L", "MFAI — 2-hour block", "MFAI Lab", "MTECH-AIDS", P, LAB2, ["AT"]),
    ("MTAI26-PC-102", "Network Security and Forensics", "NSF", "MTECH-AIDS", T, 3, ["VK"]),
    ("MTAI26-PC-102-L", "NSF — 2-hour lab", "NSF Lab", "MTECH-AIDS", P, LAB2, ["VK"]),
    ("MTAI26-PC-103", "Vulnerability Assessment and Penetration Testing", "VAPT", "MTECH-AIDS", T, 3, ["PK"]),
    ("MTAI26-PC-103-L", "VAPT — 2-hour lab", "VAPT Lab", "MTECH-AIDS", P, LAB2, ["PK"]),
    ("MTAI26-PC-104", "Fundamentals of Data Science for Cybersecurity", "FDSC", "MTECH-AIDS", T, 3, ["NP"]),
    ("MTAI26-PC-104-L", "FDSC — 2-hour lab", "FDSC Lab", "MTECH-AIDS", P, LAB2, ["NP"]),
    ("MTAI26-UC-101", "Introduction to Forensic Science and Law", "IFSL", "MTECH-AIDS", T, 3, ["KP"]),
    ("MTAI26-SE-101", "Research Methodology", "RM", "MTECH-AIDS", T, 2, ["KP"]),
    # ---- M.Sc. Cyber Security – I
    ("MSCS26-PC-101", "Applied Cryptography", "AC", "MSC-CS", T, 3, ["MP"]),
    ("MSCS26-PC-101-L", "AC — 2-hour lab", "AC Lab", "MSC-CS", P, LAB2, ["MP"]),
    ("MSCS26-PC-102", "Web Application Security", "WAS", "MSC-CS", T, 3, ["DR"]),
    ("MSCS26-PC-102-L", "WAS — 2-hour lab", "WAS Lab", "MSC-CS", P, LAB2, ["DR"]),
    ("MSCS26-PC-103", "Artificial Intelligence for Cyber Security", "AICS", "MSC-CS", T, 3, ["NG"]),
    ("MSCS26-PC-103-L", "AICS — 2-hour lab", "AICS Lab", "MSC-CS", P, LAB2, ["NG"]),
    ("MSCS26-PC-104", "Cyber Security Audit and Compliance", "CSAC", "MSC-CS", T, 4, ["DD"]),
    ("MSCS26-UC-101", "Introduction to Forensic Science and Law", "IFSL", "MSC-CS", T, 3, ["PK"]),
    ("MSCS26-SE-101", "Research Methodology", "RM", "MSC-CS", T, 2, ["KP"]),
    # ---- B.Tech.–M.Tech. CSE (Cyber Security) – I
    ("CTBT24-BSC-101", "Engineering Mathematics – 1", "EM-1", "BTECH-MTECH-CSE", T, 4, ["HAP"]),
    ("CTBT-BSC-102", "Engineering Physics", "EP", "BTECH-MTECH-CSE", T, 3, ["RK"]),
    ("CTBT-BSC-102-L", "Engineering Physics Lab", "EP Lab", "BTECH-MTECH-CSE", P, (1, 2, "Physics Lab"), ["RK"]),
    ("CTBT-ESC-101", "Basic of Electrical Engineering", "BEE", "BTECH-MTECH-CSE", T, 3, ["MM"]),
    ("CTBT-ESC-102", "Programming for Problem Solving", "PPS", "BTECH-MTECH-CSE", T, 3, ["KP"]),
    ("CTBT-ESC-102-L", "PPS Lab", "PPS Lab", "BTECH-MTECH-CSE", P, LAB2, ["KP"]),
    ("CTBT-ESC-103", "Engineering Graphics", "EG", "BTECH-MTECH-CSE", T, 2, ["VA"]),
    ("CTBT-ESC-103-L", "EG — 2-hour drawing session", "EG Drawing", "BTECH-MTECH-CSE", P, (1, 2, "Drawing Hall"), ["VA"]),
    ("CTBT-HSM-101", "Communication Skills", "CS", "BTECH-MTECH-CSE", T, 2, ["RT"]),
    ("CTBT-HSM-101-T2", "Communication Skills (second lecturer)", "CS", "BTECH-MTECH-CSE", T, 1, ["DM"]),
    # ---- M.Sc. Digital Forensics and Information Security – I
    ("MSDF26-PC-101", "Digital Forensics", "DF", "MSC-DFIS", T, 3, ["SR"]),
    ("MSDF26-PC-101-L", "DF — 2-hour lab", "DF Lab", "MSC-DFIS", P, LAB2, ["SR"]),
    ("MSDF26-PC-101-T2", "Digital Forensics (second lecturer)", "DF", "MSC-DFIS", T, 1, ["PR"]),
    ("MSDF26-PC-102", "Incident Response Management", "IRM", "MSC-DFIS", T, 3, ["RS"]),
    ("MSDF26-PC-102-L", "IRM — 2-hour lab", "IRM Lab", "MSC-DFIS", P, LAB2, ["RS"]),
    ("MSDF26-PC-103", "Programming for Digital Forensics", "PDF", "MSC-DFIS", T, 3, ["HP"]),
    ("MSDF26-PC-103-L", "PDF — 2-hour lab", "PDF Lab", "MSC-DFIS", P, LAB2, ["HP"]),
    ("MSDF26-PC-104", "Cyber Security Audit and Compliance", "CSAC", "MSC-DFIS", T, 4, ["DD"]),
    ("MSDF26-UC-101", "Introduction to Forensic Science and Law", "IFSL", "MSC-DFIS", T, 3, ["NP"]),
    ("MSDF26-SE-101", "Research Methodology", "RM", "MSC-DFIS", T, 2, ["KP"]),
]

DEMO_USERS = [  # email, name, role, extra   (dev only; created only when NFSU_DEMO_PASSWORD is set)
    ("ahlad.kumar@nfsu.ac.in", "Ahlad Kumar", Role.COORDINATOR, {}),
    ("pruthvish.rajput@nfsu.ac.in", "Pruthvish Rajput", Role.COORDINATOR, {}),
    ("krupali.panchal@nfsu.ac.in", "Ms. Krupali Panchal", Role.FACULTY, {"faculty": "KP"}),
    ("student.demo@nfsu.ac.in", "Demo Student", Role.STUDENT,
     {"enrollment_no": "NFSU26MSDF001", "group": ("MSC-DFIS", 1, "A")}),
]


def is_seeded(db: Session) -> bool:
    return db.execute(select(func.count()).select_from(Programme)).scalar_one() > 0


def seed_demo(db: Session, *, actor: User | None = None, demo_password: str | None = None) -> dict:
    cal = db.get(CalendarSettings, 1) or CalendarSettings(id=1)
    cal.working_days, cal.day_start, cal.day_end, cal.period_minutes = [0, 1, 2, 3, 4], "10:30", "17:30", 60
    db.merge(cal)
    db.add(Break(name="Lunch Break", start_time="13:30", end_time="14:30", days=None))
    # Lectures may use labs when classrooms are busy — the source timetables do this (e.g. IFSL in CSFRL).
    db.merge(ConstraintSetting(key="theory_in_lab", mode=ConstraintMode.SOFT, weight=5, value=None))

    lab_types = {n: LabType(name=n, description=d) for n, d in LAB_TYPES}
    db.add_all(lab_types.values())
    db.flush()
    rooms = {}
    for code, name, kind, lt, cap, bld in ROOMS:
        rooms[code] = Room(code=code, name=name, kind=RoomKind(kind), lab_type_id=lab_types[lt].id if lt else None,
                           capacity=cap, building=bld, unavailable=[])
    db.add_all(rooms.values())

    users: dict[str, User] = {}
    created_users = []
    if demo_password:
        for email, name, role, _ in DEMO_USERS:
            u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if u is None:
                u = User(email=email, full_name=name, role=role, password_hash=hash_password(demo_password),
                         created_by_id=actor.id if actor else None)
                db.add(u)
                created_users.append(email)
            users[email] = u
        db.flush()

    progs = {}
    for code, name, lv, sem, coord in PROGRAMMES:
        progs[code] = Programme(code=code, name=name, level=Level(lv), school=SCSDF, duration_semesters=sem,
                                coordinator_id=users[coord].id if coord in users else None)
    db.add_all(progs.values())
    db.flush()
    groups = {}
    for pc, sem, sec, strength, home in GROUPS:
        groups[(pc, sem, sec)] = StudentGroup(programme_id=progs[pc].id, semester=sem, section=sec, strength=strength,
                                              home_room_id=rooms[home].id)
    db.add_all(groups.values())

    fac = {}
    for code, name, desig, mail in FACULTY:
        fac[code] = Faculty(code=code, name=name, designation=desig, school=SCSDF, email=f"{mail}@nfsu.ac.in",
                            availability={})
    db.add_all(fac.values())
    db.flush()

    # Each faculty member may teach in the programmes where the official timetables show them teaching.
    teaches_in: dict[str, set[str]] = {}
    for _code, _name, _short, pc, _kind, _req, fcodes in SUBJECTS:
        for fc in fcodes:
            teaches_in.setdefault(fc, set()).add(pc)
    for code, f in fac.items():
        f.programmes = [progs[pc] for pc in sorted(teaches_in.get(code, ()))]

    for code, name, short, pc, kind, req, fcodes in SUBJECTS:
        s = Subject(code=code, name=name, short_name=short, programme_id=progs[pc].id, semester=1, kind=SubjectKind(kind),
                    faculty=[fac[c] for c in fcodes])
        if kind == T:
            s.periods_per_week = req
        else:
            s.sessions_per_week, s.consecutive_periods, lt = req
            s.lab_type_id = lab_types[lt].id
        db.add(s)

    for email, _, _, extra in DEMO_USERS:
        u = users.get(email)
        if u is None:
            continue
        if "faculty" in extra:
            u.faculty_id = fac[extra["faculty"]].id
        if "group" in extra:
            u.group_id = groups[extra["group"]].id
            u.enrollment_no = extra["enrollment_no"]

    db.add(Timetable(name="SCSDF Odd Semester 2026-27", academic_year="2026-27", term="ODD",
                     created_by_id=actor.id if actor else None))
    db.flush()
    audit.record(db, action="system.seed_demo", category="SYSTEM", actor=actor,
                 summary="Loaded SCSDF Semester I 2026-27 data (from official class timetables)",
                 data={"programmes": len(progs), "subjects": len(SUBJECTS), "faculty": len(fac), "users": created_users})
    db.commit()
    return {"programmes": len(progs), "classes": len(groups), "subjects": len(SUBJECTS), "faculty": len(fac),
            "rooms": len(ROOMS), "users": created_users}


if __name__ == "__main__":  # pragma: no cover
    from app.core.db import SessionLocal
    from app.main import init_db

    init_db()
    session = SessionLocal()
    if is_seeded(session):
        print("Database already contains data; nothing to do.")
    else:
        from app.core.config import get_settings

        print(seed_demo(session, demo_password=get_settings().demo_password))
    session.close()
