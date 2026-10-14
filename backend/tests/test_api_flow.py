"""End-to-end API flow: security, hierarchy, generation, editing, approval workflow, audit integrity."""
from __future__ import annotations

import time

import pytest
from sqlalchemy import text

from app.core.db import engine
from tests.conftest import ADMIN, DEMO_PW, Api


def wait_run(api: Api, run_id: str, timeout: float = 90) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = api.get(f"/runs/{run_id}").json()
        if r["status"] not in ("QUEUED", "RUNNING"):
            return r
        time.sleep(0.3)
    raise AssertionError("run did not finish")


@pytest.fixture(scope="module")
def admin(client) -> Api:
    api = Api(client)
    api.login(*ADMIN)
    assert api.post("/demo/seed").status_code == 200
    return api


def test_unauthenticated_and_csrf(client, admin):
    anon = Api(client.__class__(client.app, base_url="http://testserver"))
    assert anon.get("/rooms").status_code == 401
    # state-changing request without the CSRF header is rejected
    r = admin.c.post("/api/v1/rooms", json={"code": "X1", "name": "X", "kind": "CLASSROOM", "capacity": 10})
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
    # unknown fields are rejected (mass-assignment protection)
    r = admin.post("/rooms", json={"code": "X1", "name": "X", "kind": "CLASSROOM", "capacity": 10, "id": "hack"})
    assert r.status_code == 422


def test_security_headers(admin):
    r = admin.get("/auth/me")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store"


def test_bad_login_is_generic(client):
    api = Api(client.__class__(client.app, base_url="http://testserver"))
    r1 = api.c.post("/api/v1/auth/login", json={"identifier": "nobody@nfsu.ac.in", "password": "x" * 12})
    r2 = api.c.post("/api/v1/auth/login", json={"identifier": "admin@nfsu.ac.in", "password": "wrong-password1"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_generate_edit_lock_publish(client, admin):
    ready = admin.get("/readiness").json()
    assert ready["ready"], ready["diagnostics"]
    tt = admin.get("/timetables").json()[0]
    run = admin.post(f"/timetables/{tt['id']}/generate", json={"mode": "full", "time_limit_s": 20}).json()
    res = wait_run(admin, run["run_id"])
    assert res["status"] == "SUCCESS", res["diagnostics"]
    assert res["stats"]["scheduled"] == res["stats"]["total"] > 50

    val = admin.get(f"/timetables/{tt['id']}/validate").json()
    assert val["valid"], val["violations"]

    view = admin.get(f"/timetables/{tt['id']}").json()
    entry = next(e for e in view["entries"] if e["subject"]["code"] == "MTAI26-PC-102")
    opts = admin.get(f"/timetables/{tt['id']}/entries/{entry['id']}/options").json()
    blocked = next(c for c in opts["cells"] if c["status"] == "blocked")
    ok = next(c for c in opts["cells"] if c["status"] in ("ok", "warning") and not c.get("current"))
    r = admin.patch(f"/timetables/{tt['id']}/entries/{entry['id']}", {"day": blocked["day"], "start_period": blocked["period"]})
    assert r.status_code == 409 and r.json()["reasons"] and "suggestions" in r.json()
    r = admin.patch(f"/timetables/{tt['id']}/entries/{entry['id']}", {"day": ok["day"], "start_period": ok["period"]})
    assert r.status_code == 200, r.text

    # lock it and regenerate the rest: the locked session must not move
    admin.post(f"/timetables/{tt['id']}/lock", {"entry_ids": [entry["id"]], "locked": True})
    run = admin.post(f"/timetables/{tt['id']}/generate", json={"mode": "unlocked", "time_limit_s": 20}).json()
    assert wait_run(admin, run["run_id"])["status"] == "SUCCESS"
    after = next(e for e in admin.get(f"/timetables/{tt['id']}").json()["entries"] if e["id"] == entry["id"])
    assert (after["day"], after["start_period"]) == (ok["day"], ok["period"]) and after["locked"]

    # coordinator submits -> admin approves -> published
    coord = Api(client.__class__(client.app, base_url="http://testserver"))
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    sub = coord.post(f"/timetables/{tt['id']}/submit", {"note": "Ready for odd semester"}).json()
    assert sub["published"] is False and sub["summary"]["status"] == "IN_REVIEW"
    # coordinator cannot approve their own request
    assert coord.post(f"/requests/{sub['request_id']}/review", {"approve": True}).status_code == 403
    notes = admin.get("/notifications").json()
    assert any(n["kind"] == "approval_request" for n in notes["items"])
    assert admin.post(f"/requests/{sub['request_id']}/review", {"approve": True, "comment": "Approved"}).status_code == 200
    assert admin.get(f"/timetables/{tt['id']}/validate").json()["summary"]["status"] == "PUBLISHED"

    # student sees the published timetable (own class) and can export it; cannot see drafts
    stu = Api(client.__class__(client.app, base_url="http://testserver"))
    me = stu.login("student.demo@nfsu.ac.in", DEMO_PW)
    v = stu.get(f"/timetables/{tt['id']}?by=group&ref={me['group_id']}")
    assert v.status_code == 200 and v.json()["entries"]
    pdf = stu.get(f"/timetables/{tt['id']}/export?format=pdf&by=group&ref={me['group_id']}")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert stu.get("/rooms").status_code == 200  # read-only directory
    assert stu.post("/rooms", {"code": "Z", "name": "Z", "kind": "CLASSROOM", "capacity": 5}).status_code == 403
    for fmt in ("xlsx", "csv", "ics"):
        assert admin.get(f"/timetables/{tt['id']}/export?format={fmt}").status_code == 200


def test_user_hierarchy_and_notifications(client, admin):
    fac = Api(client.__class__(client.app, base_url="http://testserver"))
    fac.login("krupali.panchal@nfsu.ac.in", DEMO_PW)
    # faculty cannot create a coordinator
    r = fac.post("/users", {"email": "evil@nfsu.ac.in", "full_name": "Evil", "role": "COORDINATOR"})
    assert r.status_code == 403
    # faculty can add a student -> coordinators and admins are notified
    r = fac.post("/users", {"email": "new.student@nfsu.ac.in", "full_name": "Diya Patel", "role": "STUDENT"})
    assert r.status_code == 201, r.text
    assert r.json()["must_change_password"] and r.json()["temporary_password"]
    coord = Api(client.__class__(client.app, base_url="http://testserver"))
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    assert any("Diya Patel" in n["body"] for n in coord.get("/notifications").json()["items"])
    assert any("Diya Patel" in n["body"] for n in admin.get("/notifications").json()["items"])
    # coordinator adds faculty -> only admins notified
    r = coord.post("/users", {"email": "new.faculty@nfsu.ac.in", "full_name": "Dr. New Faculty", "role": "FACULTY"})
    assert r.status_code == 201
    assert coord.post("/users", {"email": "x@nfsu.ac.in", "full_name": "X", "role": "ADMIN"}).status_code == 403
    assert any("Dr. New Faculty" in n["body"] for n in admin.get("/notifications").json()["items"])
    assert not any("Dr. New Faculty" in n["body"] for n in fac.get("/notifications").json()["items"])
    # faculty cannot read the audit log
    assert fac.get("/audit-logs").status_code == 403


def test_faculty_availability_needs_approval(client, admin):
    fac = Api(client.__class__(client.app, base_url="http://testserver"))
    me = fac.login("krupali.panchal@nfsu.ac.in", DEMO_PW)
    body = {"availability": {"unavailable": [{"day": 4, "start": "09:00", "end": "11:00"}]}, "reason": "Court duty"}
    r = fac.put(f"/faculty/{me['faculty_id']}/availability", body).json()
    assert r["applied"] is False and r["request_id"]
    other = admin.get("/faculty?q=Dharmesh").json()["items"][0]
    assert fac.put(f"/faculty/{other['id']}/availability", body).status_code == 403
    coord = Api(client.__class__(client.app, base_url="http://testserver"))
    coord.login("ahlad.kumar@nfsu.ac.in", DEMO_PW)
    assert coord.post(f"/requests/{r['request_id']}/review", {"approve": False}).status_code == 400  # needs reason
    assert coord.post(f"/requests/{r['request_id']}/review", {"approve": True}).status_code == 200
    f = admin.get(f"/faculty/{me['faculty_id']}").json()
    assert f["availability"]["unavailable"][0]["day"] == 4


def test_infeasible_scenario_is_reported(client, admin):
    admin.post("/demo/scenario/infeasible")
    tt = admin.post("/timetables", {"name": "What-if draft"}).json()
    run = admin.post(f"/timetables/{tt['id']}/generate", json={"time_limit_s": 10}).json()
    res = wait_run(admin, run["run_id"])
    assert res["status"] == "PRECHECK_FAILED"
    msgs = [d["message"] for d in res["diagnostics"]]
    assert any("MTAI26-PC-102 requires 3 weekly periods" in m and "Dr. Vijeta Khare is available for only 2 periods" in m for m in msgs), msgs
    admin.post("/demo/scenario/reset")


def test_audit_log_is_immutable_and_verifiable(admin):
    v = admin.get("/audit-logs/verify").json()
    assert v["ok"], v
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("UPDATE audit_logs SET summary='tampered' WHERE seq=1"))
    with pytest.raises(Exception):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM audit_logs WHERE seq=1"))
    logs = admin.get("/audit-logs?category=SECURITY").json()
    assert logs["total"] > 0  # denied actions were recorded
