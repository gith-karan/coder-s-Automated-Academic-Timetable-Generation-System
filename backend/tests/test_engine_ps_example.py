"""Acceptance tests built directly from Problem Statement §5 (M.Sc. DFIS, Semester I)."""
from __future__ import annotations

from app.scheduling.domain import CLASSROOM, LAB, FacultyInfo, GroupInfo, Pin, Problem, RoomInfo, SessionUnit
from app.scheduling.engine import generate
from app.scheduling.prechecks import run_prechecks
from app.scheduling.timegrid import BreakSpec, TimeGrid, to_minutes
from app.scheduling.validator import hard, validate


def make_grid() -> TimeGrid:
    # Mon–Fri, 09:00–17:00, 60-minute periods, tea 11:00–11:15, lunch 13:15–14:00
    return TimeGrid([0, 1, 2, 3, 4], to_minutes("09:00"), to_minutes("17:00"), 60,
                    [BreakSpec("Tea", to_minutes("11:00"), to_minutes("11:15")),
                     BreakSpec("Lunch", to_minutes("13:15"), to_minutes("14:00"))])


def ps_problem(faculty_slots=None) -> Problem:
    grid = make_grid()
    all_slots = frozenset(grid.all_slots())
    avail = frozenset(faculty_slots) if faculty_slots is not None else all_slots
    fac = {"F1": FacultyInfo("F1", "F001", "Dr. R. Sharma", avail),
           "F2": FacultyInfo("F2", "F002", "Dr. P. Mehta", all_slots)}
    rooms = {"R101": RoomInfo("R101", "SCSDF-101", "Classroom 101", CLASSROOM, None, 60),
             "L1": RoomInfo("L1", "DF-LAB-1", "Digital Forensics Lab 1", LAB, "Digital Forensics Lab", 25),
             "L2": RoomInfo("L2", "DF-LAB-2", "Digital Forensics Lab 2", LAB, "Digital Forensics Lab", 25)}
    grp = GroupInfo("G1", "MSC-DFIS Sem 1-A", 40, ("B1", "B2"), {"B1": "B1", "B2": "B2"})
    units = [SessionUnit(f"DFIS103|G1|-|{n}", "S1", "DFIS103", "Cyber Laws & Digital Evidence", "THEORY", "G1", None,
                         "MSC-DFIS Sem 1-A", 40, 1, ("F1",), ("B1", "B2"), CLASSROOM, None, n) for n in range(3)]
    for b in ("B1", "B2"):
        units.append(SessionUnit(f"DFIS151|G1|{b}|0", "S2", "DFIS151", "Digital Forensics Lab", "PRACTICAL", "G1", b,
                                 f"MSC-DFIS Sem 1-A / {b}", 20, 2, ("F2",), (b,), LAB, "Digital Forensics Lab", 0))
    return Problem(grid, rooms, fac, {"G1": grp}, units)


def test_grid_skips_breaks():
    g = make_grid()
    labels = [p.label for p in g.periods[0]]
    assert labels == ["09:00–10:00", "10:00–11:00", "11:15–12:15", "12:15–13:15", "14:00–15:00", "15:00–16:00",
                      "16:00–17:00"]
    assert not g.contiguous(0, 1, 2)   # 10:00–11:00 + 11:15 crosses tea break
    assert not g.contiguous(0, 3, 2)   # crosses lunch
    assert g.contiguous(0, 4, 3)


def test_ps_example_schedules_everything():
    problem = ps_problem()
    out = generate(problem, time_limit_s=10, workers=4)
    assert out.status == "SUCCESS", out.diagnostics
    assert len(out.placements) == 5  # 3 theory + 2 batch practicals
    assert not hard(validate(problem, out.placements))

    theory = [out.placements[f"DFIS103|G1|-|{n}"] for n in range(3)]
    practicals = [out.placements[f"DFIS151|G1|{b}|0"] for b in ("B1", "B2")]
    # theory in a classroom big enough for 40, practicals in a DF lab, 2 consecutive periods (no break crossing)
    assert all(p.room_id == "R101" for p in theory)
    assert all(p.room_id in ("L1", "L2") for p in practicals)
    assert all(problem.grid.contiguous(p.day, p.period, 2) for p in practicals)
    # whole-class lecture never overlaps either batch practical
    for t in theory:
        for pr in practicals:
            assert not (t.day == pr.day and pr.period <= t.period < pr.period + 2)
    # soft preference: theory spread over different days
    assert len({t.day for t in theory}) == 3


def test_ps_infeasible_message_matches_statement():
    problem = ps_problem(faculty_slots=[(0, 0), (1, 0)])  # Dr. Sharma free for only two periods
    diags = run_prechecks(problem)
    msgs = [d.message for d in diags if d.code == "FACULTY_AVAIL_LT_REQUIRED"]
    assert msgs, diags
    assert "DFIS103 requires 3 weekly periods" in msgs[0]
    assert "available for only 2 periods" in msgs[0]
    out = generate(problem, time_limit_s=5, workers=2)
    assert out.status == "PRECHECK_FAILED"
    assert not out.placements  # never presents an incomplete timetable as a success


def test_solver_level_infeasibility_is_explained():
    # Both labs blocked except one 2-period window -> the two batch practicals cannot both fit,
    # but simple counting checks pass. The solver must prove infeasibility and explain it.
    problem = ps_problem()
    allowed = {(0, 4), (0, 5)}
    blocked = frozenset(s for s in problem.grid.all_slots() if s not in allowed)
    problem.rooms["L1"] = RoomInfo("L1", "DF-LAB-1", "DF Lab 1", LAB, "Digital Forensics Lab", 25, blocked)
    problem.rooms["L2"] = RoomInfo("L2", "DF-LAB-2", "DF Lab 2", LAB, "Digital Forensics Lab", 25, blocked)
    problem.faculty["F2"] = FacultyInfo("F2", "F002", "Dr. P. Mehta", frozenset(problem.grid.all_slots()))
    out = generate(problem, time_limit_s=10, workers=2)
    assert out.status == "INFEASIBLE"
    assert len(out.placements) == 4          # best partial plan
    assert len(out.unassigned) == 1
    assert "Dr. P. Mehta" in out.unassigned[0]["reason"] or "faculty" in out.unassigned[0]["reason"].lower()
    assert any(d["code"] == "CONFLICTING_REQUIREMENTS" for d in out.diagnostics)


def test_locked_session_is_respected():
    problem = ps_problem()
    problem.pins["DFIS103|G1|-|0"] = Pin("DFIS103|G1|-|0", 4, 6, "R101", "locked")
    out = generate(problem, time_limit_s=10, workers=2)
    assert out.status == "SUCCESS"
    p = out.placements["DFIS103|G1|-|0"]
    assert (p.day, p.period, p.room_id) == (4, 6, "R101")
