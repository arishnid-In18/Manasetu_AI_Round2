"""Kiosk (inmate / complainant) workflow tests."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import Api

ALL_ACK = ["a1", "a2", "a3"]


def full_flow_to_session(k):
    assert k.post("/api/kiosk/intent", {"decision": "yes"}).status_code == 200
    assert k.post("/api/kiosk/language", {"language": "ta"}).status_code == 200
    r = k.post("/api/kiosk/consent", {"acknowledged": ALL_ACK})
    assert r.status_code == 200, r.text
    s = k.post("/api/kiosk/session/start")
    assert s.status_code == 200, s.text
    return s.json()["screening_id"]


def answer_all(k, sid, values):
    for i, v in enumerate(values, start=1):
        r = k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": f"Q{i}", "value": v})
        assert r.status_code == 200, r.text


def test_valid_id_returns_profile_without_clinical_data(kiosk, prefix):
    k = kiosk(f"{prefix}1021")
    p = k.profile
    assert p["display_name"] == "Ravi Kumar" and p["language"] == "ta"
    assert p["group_code"] == "B" and p["photo_url"].endswith(f"{prefix}1021")
    assert "Simulated" in p["identity_source"]
    for forbidden in ("score", "priority", "baseline", "history", "risk"):
        assert forbidden not in " ".join(p.keys()).lower()


def test_invalid_and_unavailable_ids_get_identical_friendly_error(_boot, prefix):
    a = Api()
    msgs = set()
    for bad in ("NOPE", f"{prefix}9999", f"{prefix}1051", f"{prefix}1052", "' OR 1=1 --", "x" * 25):
        r = a.post("/api/kiosk/lookup", {"person_id": bad}, csrf=False)
        assert r.status_code in (404, 422), (bad, r.status_code)
        if r.status_code == 404:
            msgs.add(r.json()["detail"])
    assert msgs == {"Unable to retrieve this profile. Please check the ID or contact an authorized staff member."}


def test_lookup_is_case_insensitive_and_trimmed(_boot, prefix):
    a = Api()
    r = a.post("/api/kiosk/lookup", {"person_id": f"  {prefix.lower()}1021 "}, csrf=False)
    assert r.status_code == 200 and r.json()["profile"]["person_id"] == f"{prefix}1021"


def test_cannot_start_assessment_without_consent(kiosk, prefix):
    k = kiosk(f"{prefix}1030")
    assert k.post("/api/kiosk/session/start").status_code == 409
    assert k.get("/api/kiosk/instrument").status_code == 409


def test_consent_requires_every_acknowledgement(kiosk, prefix):
    k = kiosk(f"{prefix}1030")
    assert k.post("/api/kiosk/consent", {"acknowledged": ["a1"]}).status_code == 422
    assert k.post("/api/kiosk/consent", {"acknowledged": ALL_ACK}).status_code == 200


def test_staff_assistance_option_does_not_start_assessment(kiosk, prefix, staff):
    k = kiosk(f"{prefix}1031")
    r = k.post("/api/kiosk/consent", {"acknowledged": [], "staff_assistance": True})
    assert r.json()["status"] == "staff_assistance_requested"
    assert k.post("/api/kiosk/session/start").status_code == 409
    o = staff("officer1", "Officer#2026")
    items = o.get("/api/notifications").json()["items"]
    assert any(i["kind"] == "consent_assistance" and i["person_id"] == f"{prefix}1031" for i in items)


def test_postpone_and_decline_are_recorded_without_scores_or_inference(kiosk, prefix, staff):
    k = kiosk(f"{prefix}1010")
    assert k.post("/api/kiosk/intent", {"decision": "not_now"}).json()["status"] == "postponed"
    assert k.post("/api/kiosk/intent", {"decision": "no"}).json()["status"] == "declined"
    c = staff("clinician1", "Clinician#2026")
    hist = c.get(f"/api/cases/{prefix}1010").json()["history"]
    assert {"postponed", "declined"} <= {h["status"] for h in hist}
    for h in hist:
        if h["status"] in ("postponed", "declined"):
            assert h["score"] is None and h["priority"] is None


def test_full_completed_checkin_and_idempotent_submit(kiosk, prefix, staff):
    pid = f"{prefix}1002"            # persistent-change archetype (already has history)
    k = kiosk(pid)
    sid = full_flow_to_session(k)
    answer_all(k, sid, [2, 2, 2, 2, 2, 2, 2, 0])
    r1 = k.post(f"/api/kiosk/session/{sid}/submit")
    assert r1.status_code == 200 and r1.json() == {"status": "completed", "already_submitted": False}
    r2 = k.post(f"/api/kiosk/session/{sid}/submit")
    assert r2.json()["already_submitted"] is True and r2.json()["status"] == "completed"
    # kiosk response reveals NO score / category
    assert set(r1.json().keys()) == {"status", "already_submitted"}
    c = staff("clinician1", "Clinician#2026")
    case = c.get(f"/api/cases/{pid}").json()
    completed = [h for h in case["history"] if h["screening_id"] == sid]
    assert len(completed) == 1 and completed[0]["score"] == 14      # submitted twice -> still one result


def test_skipped_answer_is_not_zero_and_assessment_is_not_scored(kiosk, prefix, staff):
    pid = f"{prefix}1004"
    k = kiosk(pid)
    sid = full_flow_to_session(k)
    answer_all(k, sid, [0, 0, 0, 0, 0, 0, 0])
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q8", "skipped": True}).status_code == 200
    assert k.get(f"/api/kiosk/session/{sid}").json()["responses"]["Q8"] == {"value": None, "skipped": True}
    out = k.post(f"/api/kiosk/session/{sid}/submit").json()
    assert out["status"] == "partial"
    c = staff("clinician1", "Clinician#2026")
    row = next(h for h in c.get(f"/api/cases/{pid}").json()["history"] if h["screening_id"] == sid)
    assert row["score"] is None and row["priority"] is None and row["completeness"] == 0.875


def test_cannot_submit_with_unanswered_questions(kiosk, prefix):
    k = kiosk(f"{prefix}1006")
    sid = full_flow_to_session(k)
    answer_all(k, sid, [1, 1, 1])
    r = k.post(f"/api/kiosk/session/{sid}/submit")
    assert r.status_code == 422


def test_answer_value_validation(kiosk, prefix):
    k = kiosk(f"{prefix}1008")
    sid = full_flow_to_session(k)
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q1", "value": 9}).status_code == 422
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q99", "value": 1}).status_code == 422
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q1", "value": -1}).status_code == 422


def test_resume_reuses_the_same_open_session_no_duplicates(kiosk, prefix):
    pid = f"{prefix}1012"
    k = kiosk(pid)
    sid = full_flow_to_session(k)
    answer_all(k, sid, [1, 2])
    again = k.post("/api/kiosk/session/start").json()
    assert again["screening_id"] == sid and again["resumed"] is True
    assert again["responses"]["Q2"]["value"] == 2


def test_kiosk_user_cannot_touch_another_persons_session(kiosk, prefix):
    a = kiosk(f"{prefix}1014")
    sid = full_flow_to_session(a)
    b = kiosk(f"{prefix}1016")
    assert b.get(f"/api/kiosk/session/{sid}").status_code == 404
    assert b.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q1", "value": 1}).status_code == 404
    assert b.post(f"/api/kiosk/session/{sid}/submit").status_code == 404


def test_kiosk_session_cannot_reach_staff_endpoints(kiosk, prefix):
    k = kiosk(f"{prefix}1018")
    for url in ("/api/dashboard", f"/api/cases/{prefix}1018", "/api/admin/users", "/api/notifications"):
        assert k.get(url).status_code == 401


def test_kiosk_state_changes_need_csrf_token(kiosk, prefix):
    k = kiosk(f"{prefix}1020")
    assert k.post("/api/kiosk/intent", {"decision": "yes"}, csrf=False).status_code == 403


def test_photo_only_visible_to_owner_or_scoped_staff(kiosk, prefix, staff, _boot):
    k = kiosk(f"{prefix}1021")
    assert k.get(f"/api/photo/{prefix}1021").headers["content-type"].startswith("image/svg")
    assert k.get(f"/api/photo/{prefix}1022").status_code == 404           # someone else's photo
    anon = TestClient(app)
    assert anon.get(f"/api/photo/{prefix}1021").status_code == 404
    o2 = staff("officer2", "Officer#2026")                                 # scope C only
    assert o2.get(f"/api/photo/{prefix}1021").status_code == 404           # 1021 is in block B
    assert o2.get(f"/api/photo/{prefix}1040").status_code == 200


def test_languages_supported_and_texts_available(kiosk, prefix):
    k = kiosk(f"{prefix}1024")
    for lang in ("ta", "en", "hi"):
        assert k.post("/api/kiosk/language", {"language": lang}).status_code == 200
        c = k.get("/api/kiosk/consent").json()
        assert c["language"] == lang and len(c["acknowledgements"]) == 3
    assert k.post("/api/kiosk/language", {"language": "fr"}).status_code == 422
    k.post("/api/kiosk/consent", {"acknowledged": ALL_ACK})
    inst = k.get("/api/kiosk/instrument").json()
    assert inst["validated"] is False and len(inst["items"]) == 8 and len(inst["options"]) == 5
    assert "domain" not in inst["items"][0] and "safety" not in inst["items"][0]


# ------------------------------------------------------------------ voice assistant (backend side)
def test_voice_flag_hides_sensitive_item_from_voice_and_exposes_no_clinical_flags(kiosk, prefix):
    k = kiosk(f"{prefix}1026")
    k.post("/api/kiosk/consent", {"acknowledged": ALL_ACK})
    items = k.get("/api/kiosk/instrument").json()["items"]
    assert [i["voice_ok"] for i in items] == [True] * 7 + [False]          # Q8 (sensitive) is touch-only
    assert all(set(i.keys()) == {"id", "text", "voice_ok"} for i in items)


def test_input_mode_is_recorded_and_validated(kiosk, prefix, staff):
    k = kiosk(f"{prefix}1028")
    sid = full_flow_to_session(k)
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q1", "value": 2, "input_mode": "voice"}).status_code == 200
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q2", "value": 1}).status_code == 200
    assert k.put(f"/api/kiosk/session/{sid}/responses", {"question_id": "Q3", "value": 1, "input_mode": "telepathy"}).status_code == 422
    from app.db import SessionLocal
    from app.models import ScreeningResponse
    db = SessionLocal()
    try:
        modes = {r.question_id: r.input_mode for r in db.query(ScreeningResponse).filter(ScreeningResponse.screening_id == sid)}
    finally:
        db.close()
    assert modes == {"Q1": "voice", "Q2": "touch"}
    a = staff("admin1", "Admin#2026")
    h = a.get("/api/admin/health").json()
    assert h["answers_by_input_mode"].get("voice", 0) >= 1 and 0 <= h["voice_answer_share"] < 1


def test_voice_events_are_audited_without_transcripts(kiosk, prefix, staff):
    k = kiosk(f"{prefix}1029")
    assert k.post("/api/kiosk/voice-event", {"event": "started"}).status_code == 200
    assert k.post("/api/kiosk/voice-event", {"event": "permission_denied"}).status_code == 200
    assert k.post("/api/kiosk/voice-event", {"event": "my transcript here"}).status_code == 422
    a = staff("admin1", "Admin#2026")
    items = a.get("/api/admin/audit?action=voice_assistant&page_size=50").json()["items"]
    assert {"voice_assistant_started", "voice_assistant_permission_denied"} <= {i["action"] for i in items}


def test_voice_can_be_switched_off_by_admin(staff, _boot):
    a = staff("admin1", "Admin#2026")
    assert TestClient(app).get("/api/meta").json()["features"]["voice_assistant"] is True
    assert a.put("/api/admin/config", {"key": "voice_assistant_enabled", "value": 2}).status_code == 422
    assert a.put("/api/admin/config", {"key": "voice_assistant_enabled", "value": 0}).status_code == 200
    assert TestClient(app).get("/api/meta").json()["features"]["voice_assistant"] is False
    assert a.put("/api/admin/config", {"key": "voice_assistant_enabled", "value": 1}).status_code == 200
