"""Staff / clinician / admin API tests: auth, RBAC, scope, CSRF, workflow, audit."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import Api, OFFICER, OFFICER2, CLIN, ADMIN

FUTURE = "2099-01-01"


def rec_id(api, pid):
    return api.get(f"/api/cases/{pid}").json()["recommendation"]["recommendation_id"]


# ---------------------------------------------------------------- auth
def test_login_failure_is_generic_and_unauthenticated_requests_are_rejected(_boot):
    a = Api()
    assert a.post("/api/auth/login", {"username": "officer1", "password": "wrong"}, csrf=False).status_code == 401
    assert a.post("/api/auth/login", {"username": "nobody", "password": "x"}, csrf=False).status_code == 401
    for url in ("/api/dashboard", "/api/cases/CMP1001", "/api/admin/users", "/api/auth/me"):
        assert a.get(url).status_code == 401


def test_account_lockout_after_repeated_failures(_boot):
    a = Api()
    for _ in range(5):
        assert a.post("/api/auth/login", {"username": "officer2", "password": "bad"}, csrf=False).status_code == 401
    r = a.post("/api/auth/login", {"username": "officer2", "password": OFFICER2[1]}, csrf=False)
    assert r.status_code == 423                                  # correct password still blocked while locked
    admin = Api()
    r = admin.post("/api/auth/login", {"username": "admin1", "password": ADMIN[1]}, csrf=False)
    admin.csrf = r.json()["csrf_token"]
    uid = next(u["user_id"] for u in admin.get("/api/admin/users").json()["items"] if u["username"] == "officer2")
    assert admin.patch(f"/api/admin/users/{uid}", {"unlock": True}).status_code == 200
    assert a.post("/api/auth/login", {"username": "officer2", "password": OFFICER2[1]}, csrf=False).status_code == 200


def test_state_changing_calls_require_csrf(staff, prefix):
    o = staff(*OFFICER)
    rid = rec_id(o, f"{prefix}1002")
    r = o.c.post(f"/api/cases/{prefix}1002/review", json={"recommendation_id": rid, "decision": "monitor_only"})
    assert r.status_code == 403


def test_logout_invalidates_session(staff):
    o = staff(*OFFICER)
    assert o.get("/api/auth/me").status_code == 200
    assert o.post("/api/auth/logout").status_code == 200
    assert o.get("/api/auth/me").status_code == 401


def test_passwords_are_hashed_not_plaintext(_boot):
    from app.db import SessionLocal
    from app.models import User
    db = SessionLocal()
    try:
        for u in db.query(User):
            assert u.password_hash.startswith("pbkdf2_sha256$") and "#2026" not in u.password_hash
    finally:
        db.close()


# ------------------------------------------------------------ dashboard
def test_dashboard_summary_counts_come_from_database_and_respect_scope(staff, prefix):
    o1, o2, c = staff(*OFFICER), staff(*OFFICER2), staff(*CLIN)
    d1 = o1.get("/api/dashboard?page_size=50").json()
    d2 = o2.get("/api/dashboard?page_size=50").json()
    dc = c.get("/api/dashboard?page_size=50").json()
    assert d1["summary"]["total_in_scope"] == 34 and d2["summary"]["total_in_scope"] == 16 and dc["summary"]["total_in_scope"] == 50
    assert {r["group_code"] for r in d1["rows"]} == {"A", "B"} and {r["group_code"] for r in d2["rows"]} == {"C"}
    s = dc["summary"]
    assert s["urgent"] >= 1 and s["follow_up"] >= 5 and s["follow_ups_pending"] >= 1 and s["assessments_due"] >= 1
    assert s["urgent"] + s["follow_up"] + s["monitor"] + s["routine"] + s["unassessed"] == 50
    # table rows hold no names or scores (data minimisation)
    assert all("display_name" not in r and "score" not in r for r in dc["rows"])


def test_dashboard_filters_search_sort_pagination(staff, prefix):
    c = staff(*CLIN)
    urgent = c.get("/api/dashboard?priority=Urgent Human Review&page_size=50").json()
    assert urgent["total"] >= 2 and all(r["priority"] == "Urgent Human Review" for r in urgent["rows"])
    assert c.get(f"/api/dashboard?search={prefix}1003").json()["rows"][0]["person_id"] == f"{prefix}1003"
    first = c.get("/api/dashboard?sort=priority&order=desc&page_size=5").json()["rows"]
    assert first[0]["priority"] == "Urgent Human Review"
    p1 = c.get("/api/dashboard?page=1&page_size=10").json()
    p2 = c.get("/api/dashboard?page=2&page_size=10").json()
    assert p1["pages"] == 5 and {r["person_id"] for r in p1["rows"]}.isdisjoint({r["person_id"] for r in p2["rows"]})
    assert c.get("/api/dashboard?due=Declined").json()["total"] >= 1
    assert c.get("/api/dashboard?order=sideways").status_code == 422


# ------------------------------------------------------------- RBAC/scope
def test_officer_cannot_open_out_of_scope_case_and_attempt_is_audited(staff, prefix):
    o2 = staff(*OFFICER2)                      # block C only
    assert o2.get(f"/api/cases/{prefix}1003").status_code == 404
    assert o2.get(f"/api/cases/{prefix}9999").status_code == 404           # same answer: no enumeration
    admin = staff(*ADMIN)
    items = admin.get("/api/admin/audit?action=access_denied_scope&page_size=100").json()["items"]
    assert any(i["actor"] == "officer2" and i["outcome"] == "denied" for i in items)


def test_admin_cannot_read_case_level_data(staff, prefix):
    a = staff(*ADMIN)
    assert a.get(f"/api/cases/{prefix}1003").status_code == 403
    assert a.get("/api/dashboard").status_code == 403
    h = a.get("/api/admin/health").json()
    assert "individual responses" in h["case_level_access"]
    assert not any(k in h for k in ("responses", "cases", "notes"))


def test_officers_and_clinicians_cannot_use_admin_endpoints(staff):
    for creds in (OFFICER, CLIN):
        s = staff(*creds)
        assert s.get("/api/admin/users").status_code == 403
        assert s.get("/api/admin/audit").status_code == 403


def test_officer_sees_less_clinical_detail_than_clinician(staff, prefix):
    o, c = staff(*OFFICER), staff(*CLIN)
    pid = f"{prefix}1002"
    co, cc = o.get(f"/api/cases/{pid}").json(), c.get(f"/api/cases/{pid}").json()
    assert co["notes"] is None and co["domains"] is None
    assert "changed_dimensions" not in co["recommendation"] and "changed_dimension_count" in co["recommendation"]
    assert isinstance(cc["notes"], list) and cc["domains"] and len(cc["domains"]) == 8
    assert any(d["safety"] for d in cc["domains"])
    assert o.post(f"/api/cases/{pid}/notes", {"kind": "note", "body": "x"}).status_code == 403
    assert c.post(f"/api/cases/{pid}/notes", {"kind": "support_plan", "body": "Weekly counselling"}).status_code == 200
    assert any(n["body"] == "Weekly counselling" for n in c.get(f"/api/cases/{pid}").json()["notes"])


def test_case_detail_explanation_matches_data(staff, prefix):
    c = staff(*CLIN)
    d = c.get(f"/api/cases/{prefix}1003").json()                  # urgent safety demo
    r = d["recommendation"]
    assert r["priority"] == "Urgent Human Review" and r["safety_flag"] == "urgent"
    assert r["clinical_diagnosis"] == "Not provided by the system"
    assert "protocol" in r["explanation"].lower()
    assert any("safety" in x.lower() for x in r["reasons"])
    d2 = c.get(f"/api/cases/{prefix}1016").json()["recommendation"]  # persistent change
    assert d2["persistent"] is True and d2["baseline_status"] == "established"
    assert d2["change_from_baseline"] == d2["current_value"] - d2["baseline_value"]
    d3 = c.get(f"/api/cases/{prefix}1020").json()["recommendation"]   # one assessment only
    assert d3["baseline_status"] == "not_established" and "not established" in d3["data_sufficiency"].lower() or "Insufficient" in d3["data_sufficiency"]


# --------------------------------------------------------------- workflow
def test_urgent_alert_is_visible_and_cleared_only_by_human_review(staff, prefix):
    o = staff(*OFFICER)
    n = o.get("/api/notifications").json()
    assert n["urgent_count"] >= 1 and any(i["person_id"] == f"{prefix}1003" for i in n["items"])
    pid = f"{prefix}1003"
    nid = next(i["notification_id"] for i in n["items"] if i["person_id"] == pid)
    assert o.post(f"/api/notifications/{nid}/ack").status_code == 409       # cannot just dismiss it
    rid = rec_id(o, pid)
    assert o.post(f"/api/cases/{pid}/review", {"recommendation_id": rid, "decision": "escalated_to_protocol",
                                               "note": "Followed facility protocol."}).status_code == 200
    assert not any(i["person_id"] == pid for i in o.get("/api/notifications").json()["items"])
    assert o.get(f"/api/cases/{pid}").json()["recommendation"]["review_status"] == "reviewed"


def test_review_decision_validated(staff, prefix):
    o = staff(*OFFICER)
    pid = f"{prefix}1027"
    rid = rec_id(o, pid)
    assert o.post(f"/api/cases/{pid}/review", {"recommendation_id": rid, "decision": "banana"}).status_code == 422
    assert o.post(f"/api/cases/{pid}/review", {"recommendation_id": "REC-NOPE", "decision": "monitor_only"}).status_code == 404


def test_referral_state_machine_and_roles(staff, prefix):
    o, c = staff(*OFFICER), staff(*CLIN)
    pid = f"{prefix}1032"
    rid = rec_id(c, pid)
    r = o.post(f"/api/cases/{pid}/referrals", {"recommendation_id": rid, "destination": "counselling", "reason": "Persistent rise"})
    assert r.status_code == 200 and r.json()["status"] == "recommended"        # created != completed
    ref = r.json()["referral_id"]
    assert o.post(f"/api/cases/{pid}/referrals", {"recommendation_id": rid, "destination": "nonsense", "reason": "x"}).status_code == 422
    assert o.patch(f"/api/referrals/{ref}/status", {"status": "accepted"}).status_code == 403    # officer can't advance
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "appointment_completed"}).status_code == 409  # no skipping
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "accepted"}).json()["status"] == "accepted"
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "appointment_scheduled"}).status_code == 422  # needs date
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "appointment_scheduled", "appointment_at": "2099-02-01T10:00"}).status_code == 200
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "appointment_completed"}).json()["status"] == "appointment_completed"
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "closed"}).status_code == 422            # needs outcome
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "follow_up_pending"}).status_code == 200
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "closed", "outcome_status": "Care plan agreed"}).json()["status"] == "closed"
    assert c.patch(f"/api/referrals/{ref}/status", {"status": "accepted"}).status_code == 409          # closed is final


def test_officer_can_withdraw_unaccepted_referral_with_outcome(staff, prefix):
    o = staff(*OFFICER)
    pid = f"{prefix}1006"
    rid = rec_id(o, pid)
    ref = o.post(f"/api/cases/{pid}/referrals", {"recommendation_id": rid, "destination": "tele_manas", "reason": "Offer support"}).json()["referral_id"]
    assert o.patch(f"/api/referrals/{ref}/status", {"status": "closed", "outcome_status": "Withdrawn"}).status_code == 200


def test_follow_up_scheduling_and_completion(staff, prefix):
    o = staff(*OFFICER)
    pid = f"{prefix}1010"
    assert o.post(f"/api/cases/{pid}/follow-ups", {"when": "2001-01-01"}).status_code == 422       # past date
    assert o.post(f"/api/cases/{pid}/follow-ups", {"when": "not-a-date"}).status_code == 422
    r = o.post(f"/api/cases/{pid}/follow-ups", {"when": FUTURE, "note": "Check in"})
    assert r.status_code == 200
    fid = r.json()["follow_up_id"]
    assert any(i["follow_up_id"] == fid for i in o.get("/api/follow-ups").json()["items"])
    assert o.patch(f"/api/follow-ups/{fid}/complete").status_code == 200
    assert o.patch(f"/api/follow-ups/{fid}/complete").status_code == 409                           # not twice
    assert not any(i["follow_up_id"] == fid for i in o.get("/api/follow-ups").json()["items"])


def test_cannot_act_on_another_scopes_referral(staff, prefix):
    c = staff(*CLIN)
    pid = f"{prefix}1003"                                   # block A
    rid = rec_id(c, pid)
    ref = c.post(f"/api/cases/{pid}/referrals", {"recommendation_id": rid, "destination": "psychiatric", "reason": "Urgent"}).json()["referral_id"]
    o2 = staff(*OFFICER2)                                   # block C only
    assert o2.patch(f"/api/referrals/{ref}/status", {"status": "closed", "outcome_status": "x"}).status_code == 404


def test_assign_requires_authorised_clinician(staff, prefix):
    o, c = staff(*OFFICER), staff(*CLIN)
    pid = f"{prefix}1007"
    clin = o.get("/api/staff/clinicians").json()["items"][0]["user_id"]
    me = o.get("/api/auth/me").json()["user"]["user_id"]
    assert o.post(f"/api/cases/{pid}/assign", {"user_id": me}).status_code == 422          # an officer isn't assignable
    assert o.post(f"/api/cases/{pid}/assign", {"user_id": clin}).status_code == 200
    assert o.get(f"/api/cases/{pid}").json()["snapshot"]["assigned_professional"]


def test_baseline_reset_is_clinician_only_and_changes_analysis_window(staff, prefix):
    o, c = staff(*OFFICER), staff(*CLIN)
    pid = f"{prefix}1034"
    assert o.post(f"/api/cases/{pid}/baseline-reset").status_code == 403
    assert c.post(f"/api/cases/{pid}/baseline-reset").status_code == 200
    assert c.get(f"/api/cases/{pid}").json()["profile"]["baseline_anchor_date"]


# ----------------------------------------------------------- admin/audit
def test_admin_user_management_validation(staff):
    a = staff(*ADMIN)
    bad = {"username": "newofficer", "display_name": "N", "role": "officer", "password": "short", "group_scope": "A"}
    assert a.post("/api/admin/users", bad).status_code == 422
    ok = {**bad, "password": "Longenough#123"}
    assert a.post("/api/admin/users", ok).status_code == 200
    assert a.post("/api/admin/users", ok).status_code == 409
    assert a.post("/api/admin/users", {**ok, "username": "x2user", "group_scope": "Z"}).status_code == 422
    me = a.get("/api/auth/me").json()["user"]["user_id"]
    assert a.patch(f"/api/admin/users/{me}", {"account_status": "disabled"}).status_code == 409


def test_disabled_user_loses_access_immediately(staff):
    a = staff(*ADMIN)
    a.post("/api/admin/users", {"username": "tempofficer", "display_name": "T", "role": "officer",
                                "password": "Longenough#123", "group_scope": "A"})
    t = Api()
    r = t.post("/api/auth/login", {"username": "tempofficer", "password": "Longenough#123"}, csrf=False)
    t.csrf = r.json()["csrf_token"]
    assert t.get("/api/dashboard").status_code == 200
    uid = next(u["user_id"] for u in a.get("/api/admin/users").json()["items"] if u["username"] == "tempofficer")
    a.patch(f"/api/admin/users/{uid}", {"account_status": "disabled"})
    assert t.get("/api/dashboard").status_code == 401


def test_config_change_is_validated_and_audited(staff):
    a = staff(*ADMIN)
    assert a.put("/api/admin/config", {"key": "assessment_interval_days", "value": 0}).status_code == 422
    assert a.put("/api/admin/config", {"key": "nonsense", "value": 5}).status_code == 422
    assert a.put("/api/admin/config", {"key": "assessment_interval_days", "value": 14}).status_code == 200
    assert any(i["action"] == "config_changed" for i in a.get("/api/admin/audit?action=config&page_size=5").json()["items"])


def test_audit_log_covers_key_events_and_never_contains_scores(staff, prefix):
    c = staff(*CLIN)
    c.get(f"/api/cases/{prefix}1005")
    a = staff(*ADMIN)
    items = a.get("/api/admin/audit?page_size=100").json()["items"]
    actions = {i["action"] for i in items}
    assert {"login", "case_viewed"} <= actions
    assert all(set(i.keys()) == {"audit_id", "ts", "actor_type", "actor", "action", "record_type", "record_id", "outcome", "ip"} for i in items)


def test_audit_chain_verifies_and_detects_tampering(staff):
    a = staff(*ADMIN)
    assert a.get("/api/admin/audit/verify").json()["valid"] is True
    from app.db import SessionLocal
    from app.models import AuditLog
    db = SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.audit_id.asc()).offset(3).first()
        original = row.action
        row.action = "tampered"
        db.commit()
        res = a.get("/api/admin/audit/verify").json()
        assert res["valid"] is False and res["first_invalid_audit_id"] == row.audit_id
        row.action = original
        db.commit()
        assert a.get("/api/admin/audit/verify").json()["valid"] is True
    finally:
        db.close()


def test_security_headers_present(_boot):
    r = TestClient(app).get("/api/meta")
    assert r.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["instrument"]["validated"] is False


def test_live_submission_updates_dashboard_and_urgent_rule_fires(kiosk, staff, prefix):
    """End-to-end: a new check-in with a safety response raises an urgent alert for staff."""
    pid = f"{prefix}1045"
    k = kiosk(pid)
    k.post("/api/kiosk/intent", {"decision": "yes"})
    k.post("/api/kiosk/consent", {"acknowledged": ["a1", "a2", "a3"]})
    sid = k.post("/api/kiosk/session/start").json()["screening_id"]
    for i, v in enumerate([1, 1, 1, 1, 1, 1, 1, 3], start=1):
        k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": f"Q{i}", "value": v})
    assert k.post(f"/api/kiosk/session/{sid}/submit").json()["status"] == "completed"
    o = staff(*OFFICER)                                    # block C belongs to officer2; use clinician for scope
    c = staff(*CLIN)
    row = c.get(f"/api/dashboard?search={pid}").json()["rows"][0]
    assert row["priority"] == "Urgent Human Review" and row["review_status"] == "pending"
    assert any(i["person_id"] == pid for i in c.get("/api/notifications").json()["items"])
