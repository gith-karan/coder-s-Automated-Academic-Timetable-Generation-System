"""CRUD through the API, configurable permissions with delegation, custom rules, duplicate names."""
from __future__ import annotations

import time

import pytest

from tests.conftest import ADMIN, DEMO_PW, Api


def fresh(client) -> Api:
    return Api(client.__class__(client.app, base_url="http://testserver"))


@pytest.fixture(scope="module")
def admin(client) -> Api:
    api = Api(client)
    api.login(*ADMIN)
    r = api.post("/demo/seed")
    assert r.status_code in (200, 409)
    return api


def wait_run(api: Api, run_id: str) -> dict:
    for _ in range(300):
        r = api.get(f"/runs/{run_id}").json()
        if r["status"] not in ("QUEUED", "RUNNING"):
            return r
        time.sleep(0.3)
    raise AssertionError("run did not finish")


def test_crud_create_and_update_through_api(admin):
    """Regression: create/update bodies were not parsed (postponed annotations in the CRUD factory)."""
    r = admin.post("/rooms", {"code": "TEST-101", "name": "Test Room", "kind": "CLASSROOM", "capacity": 50})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    r = admin.patch(f"/rooms/{rid}", {"code": "TEST-101", "name": "Test Room", "kind": "CLASSROOM", "capacity": 50,
                                      "building": None, "is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False, r.text
    f = admin.get("/faculty?q=Krupali").json()["items"][0]
    r = admin.patch(f"/faculty/{f['id']}", {"max_periods_per_day": 3, "max_periods_per_week": None})
    assert r.status_code == 200 and r.json()["max_periods_per_day"] == 3, r.text
    # strength limits are enforced
    prog = admin.get("/programmes?q=MSC-DFIS").json()["items"][0]
    r = admin.post("/groups", {"programme_id": prog["id"], "semester": 1, "section": "Z", "strength": 999999999})
    assert r.status_code == 422
    # a second "Semester 1 Section A" is refused with a clear message
    r = admin.post("/groups", {"programme_id": prog["id"], "semester": 1, "section": "A", "strength": 40})
    assert r.status_code == 400 and "already has Semester 1 Section A" in r.json()["detail"]


def test_faculty_programme_restriction(admin):
    hp = admin.get("/faculty?q=Himanshu").json()["items"][0]      # teaches only in M.Sc. DFIS
    mtai = admin.get("/programmes?q=MTECH-AIDS").json()["items"][0]
    r = admin.post("/subjects", {"code": "MTAI-TEST-1", "name": "Test", "short_name": "TST", "programme_id": mtai["id"], "semester": 1,
                                 "kind": "THEORY", "periods_per_week": 1, "faculty_ids": [hp["id"]]})
    assert r.status_code == 400 and "not allowed to teach" in r.json()["detail"]


def test_permission_matrix_and_delegation(client, admin):
    coord = fresh(client)
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    fac = fresh(client)
    fac.login("krupali.panchal@nfsu.ac.in", DEMO_PW)

    # by default only the admin manages permissions
    assert coord.get("/permissions").status_code == 403
    m = admin.get("/permissions").json()
    assert set(m["editable_roles"]) == {"COORDINATOR", "FACULTY", "STUDENT"}

    # a student can never be given 'publish' (ceiling)
    r = admin.put("/permissions/STUDENT", {"permissions": ["timetable.view_published", "timetable.publish"]})
    assert r.status_code == 400

    # admin delegates permission management to coordinators
    cperms = m["matrix"]["COORDINATOR"] + ["permissions.manage"]
    assert admin.put("/permissions/COORDINATOR", {"permissions": cperms}).status_code == 200
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    cm = coord.get("/permissions").json()
    assert set(cm["editable_roles"]) == {"FACULTY", "STUDENT"}
    # coordinator cannot change coordinators (own level) …
    assert coord.put("/permissions/COORDINATOR", {"permissions": []}).status_code == 403
    # … nor grant faculty something the coordinator does not hold itself
    fperms = cm["matrix"]["FACULTY"]
    assert coord.put("/permissions/FACULTY", {"permissions": fperms + ["availability.edit_own"]}).status_code == 403
    # coordinator lets faculty manage student permissions and see drafts
    r = coord.put("/permissions/FACULTY", {"permissions": fperms + ["permissions.manage", "timetable.view_drafts"]})
    assert r.status_code == 200, r.text
    fac.login("krupali.panchal@nfsu.ac.in", DEMO_PW)
    fm = fac.get("/permissions").json()
    assert fm["editable_roles"] == ["STUDENT"]
    assert fac.get("/timetables").status_code == 200
    # faculty removes 'export' from students
    assert fac.put("/permissions/STUDENT", {"permissions": ["timetable.view_published"]}).status_code == 200
    stu = fresh(client)
    stu.login("student.demo@nfsu.ac.in", DEMO_PW)
    tt = admin.get("/timetables").json()[0]
    assert stu.get(f"/timetables/{tt['id']}/export?format=csv").status_code == 403
    # admin overrides anything below, restoring defaults
    for role in ("STUDENT", "FACULTY", "COORDINATOR"):
        assert admin.put(f"/permissions/{role}", {"permissions": m["matrix"][role]}).status_code == 200
    assert fac.get("/permissions").status_code == 403
    # every change was audited as a SECURITY event
    logs = admin.get("/audit-logs?q=permissions").json()
    assert logs["total"] >= 5


def test_custom_rule_class_block_is_respected(admin):
    grp = next(g for g in admin.get("/groups").json()["items"] if g["label"].startswith("MSC-CS"))
    r = admin.post("/custom-rules", {"kind": "CLASS_BLOCK", "mode": "HARD", "note": "Library / Project",
                                     "params": {"group_id": grp["id"], "label": "Library / Project",
                                                "ranges": [{"day": 4, "start": "14:30", "end": "17:30"}]}})
    assert r.status_code == 201, r.text
    rule_id = r.json()["id"]
    bad = admin.post("/custom-rules", {"kind": "FACULTY_MAX_CONSECUTIVE", "mode": "HARD", "params": {"max": 0}})
    assert bad.status_code == 400
    name = "Rule test draft"
    tt = admin.post("/timetables", {"name": name, "academic_year": "2026-27", "term": "ODD"}).json()
    res = wait_run(admin, admin.post(f"/timetables/{tt['id']}/generate", {"mode": "full"}).json()["run_id"])
    assert res["status"] == "SUCCESS", res["diagnostics"]
    view = admin.get(f"/timetables/{tt['id']}?by=group&ref={grp['id']}").json()
    assert not [e for e in view["entries"] if e["day"] == 4 and e["start_period"] + e["length"] - 1 >= 3]
    # duplicate names are refused with a ready-to-use suggestion
    r = admin.post("/timetables", {"name": name})
    assert r.status_code == 409 and r.json()["suggestion"] == f"{name} (2)"
    assert admin.c.delete(f"/api/v1/custom-rules/{rule_id}", headers={"X-CSRF-Token": admin.csrf}).status_code == 204


def test_audit_access_is_controlled_and_mirrored_to_file(client, admin):
    import os

    from app.core.config import get_settings

    m = admin.get("/permissions").json()
    coord = fresh(client)
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    assert coord.get("/audit-logs").status_code == 403          # off by default
    # faculty and students can never be given the audit log (ceiling = coordinator)
    assert admin.put("/permissions/FACULTY", {"permissions": m["matrix"]["FACULTY"] + ["audit.view"]}).status_code == 400
    # the admin may grant read-only access to coordinators …
    assert admin.put("/permissions/COORDINATOR", {"permissions": m["matrix"]["COORDINATOR"] + ["audit.view"]}).status_code == 200
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    assert coord.get("/audit-logs").status_code == 200
    assert coord.get("/audit-logs/verify").json()["ok"]
    # … and take it back
    assert admin.put("/permissions/COORDINATOR", {"permissions": m["matrix"]["COORDINATOR"]}).status_code == 200
    assert coord.get("/audit-logs").status_code == 403
    path = os.path.join(get_settings().log_dir, "audit-trail.jsonl")
    assert os.path.exists(path) and os.path.getsize(path) > 0


def test_personal_data_minimised_for_students(client, admin):
    stu = fresh(client)
    stu.login("student.demo@nfsu.ac.in", DEMO_PW)
    assert stu.get("/faculty").status_code == 403          # emails + availability are not public
    tt = next(t for t in admin.get("/timetables").json() if t["total_sessions"])
    d = admin.get(f"/timetables/{tt['id']}/directory").json()
    assert d["group"] and d["faculty"] and d["room"]
    assert all(set(x) <= {"id", "label", "programme_id"} for x in d["faculty"])  # names only


def test_scope_errors_and_safe_pdf(admin):
    r = admin.get("/readiness?term=EVEN").json()
    assert not r["ready"]
    assert any(d["code"] == "NO_CLASSES_IN_SCOPE" and "Sem I" in d["message"] for d in r["diagnostics"]), r
    # markup in user data must not break or inject into the PDF
    tt = admin.post("/timetables", {"name": "<b>Odd</b> & <font size=40>X</font>", "term": "ODD"}).json()
    pdf = admin.get(f"/timetables/{tt['id']}/export?format=pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_search_and_filters_work(admin):
    """Regression: a stray comment once disabled faculty search."""
    r = admin.get("/faculty?q=Himanshu").json()
    assert r["total"] == 1 and r["items"][0]["name"] == "Dr. Himanshu Patel"
    assert admin.get("/rooms?q=BL").json()["total"] == 4
    assert all(s["kind"] == "PRACTICAL" for s in admin.get("/subjects?kind=PRACTICAL&size=100").json()["items"])


def test_temporary_password_unlocks_nothing_else(client, admin):
    r = admin.post("/users", {"email": "temp.user@nfsu.ac.in", "full_name": "Temp User", "role": "STUDENT"})
    temp = r.json()["temporary_password"]
    u = fresh(client)
    u.login("temp.user@nfsu.ac.in", temp)
    assert u.get("/auth/me").status_code == 200
    for path in ("/dashboard", "/notifications", "/timetables"):
        assert u.get(path).json().get("code") == "password_change_required", path


def test_student_sees_only_own_class_by_default(client, admin):
    tt = next(t for t in admin.get("/timetables").json() if t["status"] == "PUBLISHED")
    stu = fresh(client)
    me = stu.login("student.demo@nfsu.ac.in", DEMO_PW)
    d = stu.get(f"/timetables/{tt['id']}/directory").json()
    assert [g["id"] for g in d["group"]] == [me["group_id"]] and d["faculty"] == [] and d["room"] == []
    other = next(g for g in admin.get(f"/timetables/{tt['id']}/directory").json()["group"] if g["id"] != me["group_id"])
    assert stu.get(f"/timetables/{tt['id']}?by=group&ref={me['group_id']}").status_code == 200
    assert stu.get(f"/timetables/{tt['id']}?by=group&ref={other['id']}").status_code == 403
    assert stu.get(f"/timetables/{tt['id']}").status_code == 403                      # whole timetable
    f = admin.get(f"/timetables/{tt['id']}/directory").json()["faculty"][0]
    assert stu.get(f"/timetables/{tt['id']}?by=faculty&ref={f['id']}").status_code == 403
    assert stu.get(f"/timetables/{tt['id']}/export?format=csv&by=group&ref={other['id']}").status_code == 403
    # the admin can widen it …
    m = admin.get("/permissions").json()["matrix"]
    admin.put("/permissions/STUDENT", {"permissions": m["STUDENT"] + ["timetable.view_all_classes"]})
    assert stu.get(f"/timetables/{tt['id']}?by=group&ref={other['id']}").status_code == 200
    admin.put("/permissions/STUDENT", {"permissions": m["STUDENT"]})
    # faculty always see their own teaching
    fac = fresh(client)
    fme = fac.login("krupali.panchal@nfsu.ac.in", DEMO_PW)
    assert fac.get(f"/timetables/{tt['id']}?by=faculty&ref={fme['faculty_id']}").status_code == 200


def test_publishing_replaces_previous_version_without_archive(client, admin):
    def publish_new(name: str) -> dict:
        tt = admin.post("/timetables", {"name": name, "academic_year": "2026-27", "term": "ODD"}).json()
        res = wait_run(admin, admin.post(f"/timetables/{tt['id']}/generate", {"mode": "full"}).json()["run_id"])
        assert res["status"] == "SUCCESS", res["diagnostics"]
        r = admin.post(f"/timetables/{tt['id']}/submit", {"note": "publish"})
        assert r.status_code == 200 and r.json()["published"] is True, r.text
        return tt

    old = publish_new("Version A")
    new = publish_new("Version B")
    statuses = {t["id"]: t for t in admin.get("/timetables").json()}
    assert statuses[new["id"]]["status"] == "PUBLISHED"
    assert statuses[old["id"]]["status"] == "DRAFT" and "replaced by 'Version B'" in statuses[old["id"]]["notice"]
    assert all(t["status"] in ("DRAFT", "IN_REVIEW", "PUBLISHED") for t in statuses.values())
    stu = fresh(client)
    stu.login("student.demo@nfsu.ac.in", DEMO_PW)
    assert [t["id"] for t in stu.get("/timetables").json()] == [new["id"]]


def test_subject_short_name_is_required_and_shown(admin):
    prog = admin.get("/programmes?q=MSC-DFIS").json()["items"][0]
    kp = admin.get("/faculty?q=Krupali").json()["items"][0]
    base = {"code": "MSDF-TEST-9", "name": "Test Subject", "programme_id": prog["id"], "semester": 1, "kind": "THEORY",
            "periods_per_week": 1, "faculty_ids": [kp["id"]]}
    assert admin.post("/subjects", base).status_code == 422                     # short name is mandatory
    r = admin.post("/subjects", {**base, "short_name": "TS"})
    assert r.status_code == 201 and r.json()["short_name"] == "TS"
    subj = admin.get("/subjects?q=MSDF26-PC-102").json()["items"][0]
    assert subj["short_name"] == "IRM" and "[" not in subj["name"]
    admin.c.delete(f"/api/v1/subjects/{r.json()['id']}", headers={"X-CSRF-Token": admin.csrf})
