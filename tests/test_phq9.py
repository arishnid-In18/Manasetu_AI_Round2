"""PHQ-9 reference instrument: scoring, published bands, published change threshold, language handling."""
import json, os, subprocess, sys, tempfile
from datetime import datetime, timedelta

from app import analysis, instruments
from app.analysis import Obs, analyze, rules_for

PHQ = rules_for("PHQ-9")
T0 = datetime(2026, 1, 1)


def run(scores, item9=0):
    obs = [Obs(f"S{i}", T0 + timedelta(days=14 * i), s, {f"Q{k}": 0 for k in range(1, 10)}) for i, s in enumerate(scores)]
    obs[-1].items["Q9"] = item9
    return analyze(obs[:-1], obs[-1], safety_id="Q9", rules=PHQ)


def test_instrument_definition_matches_published_phq9():
    inst = instruments.INSTRUMENTS["PHQ-9"]
    assert len(inst["items"]) == 9 and inst["scale_max"] == 3 and inst["score_range"] == (0, 27)
    assert [o["en"] for o in inst["options"].values()] == ["Not at all", "Several days", "More than half the days", "Nearly every day"]
    assert inst["items"][0]["text"]["en"] == "Little interest or pleasure in doing things"
    assert inst["items"][8]["safety"] and not any(i["safety"] for i in inst["items"][:8])
    assert inst["translations"] == ["en"], "Hindi/Tamil must NOT be added until official versions are checked by a clinician"


def test_total_is_sum_of_nine_items_and_partial_is_never_scored():
    assert instruments.score_responses({f"Q{k}": 3 for k in range(1, 10)}, instruments.INSTRUMENTS["PHQ-9"])[0] == 27
    r = {f"Q{k}": 1 for k in range(1, 10)}; r["Q4"] = None
    assert instruments.score_responses(r, instruments.INSTRUMENTS["PHQ-9"])[:2] == (None, "not_scored_incomplete")


def test_published_cutpoints_5_10_15_20_drive_the_thresholds():
    assert PHQ["thresholds"] == {"monitor": 5, "follow_up": 10, "urgent_with_persistence": 20}
    assert run([2, 2, 2, 2]).priority == "Routine Monitoring"          # 2: minimal
    assert run([4, 4, 4, 4]).priority == "Routine Monitoring"          # 4: minimal
    assert run([5, 5, 5, 5]).priority == "Monitor"                     # 5: mild band starts
    assert run([9, 9, 9, 9]).priority == "Monitor"                     # 9: still mild
    assert run([10, 10, 10, 10]).priority == "Human Follow-Up Recommended"   # >=10: usual cut-point
    assert run([22, 21, 22, 22]).priority == "Human Follow-Up Recommended"   # severe, but not persistent-rise: still follow-up, not 'urgent' by score alone


def test_published_minimal_clinically_important_change_is_five_points():
    assert PHQ["deviation_delta"] == 5
    a = run([1, 1, 2, 6])             # baseline 1, +5  -> meaningful change
    assert a.change_from_baseline == 5.0 and a.priority == "Monitor"
    b = run([1, 1, 2, 5])             # baseline 1, +4  -> below the published threshold, but 5 is the mild band anyway
    assert b.change_from_baseline == 4.0
    c = run([1, 1, 1, 4])             # +3 and score 4: neither a meaningful change nor in the mild band (5+)
    assert c.change_from_baseline == 3.0 and c.priority == "Routine Monitoring"


def test_item9_any_nonzero_response_needs_attention_and_two_or_more_is_urgent_by_project_rule():
    assert run([3, 3, 3, 3], item9=0).priority == "Routine Monitoring"
    assert run([3, 3, 3, 3], item9=1).priority == "Human Follow-Up Recommended"     # published: any positive response -> clinical attention
    assert run([3, 3, 3, 3], item9=2).priority == "Urgent Human Review"             # project choice, needs clinical sign-off
    assert run([3, 3, 3, 3], item9=3).priority == "Urgent Human Review"


def test_improvement_is_not_called_recovery():
    r = run([15, 14, 12, 8])
    assert r.trend_category == analysis.TREND_IMPROVING and "recover" not in r.explanation.lower()


def test_published_values_vs_project_choices_are_documented_in_source():
    src = open(analysis.__file__, encoding="utf-8").read()
    assert "PUBLISHED numbers" in src and "PROJECT CHOICES" in src


def _api(code: str) -> dict:
    env = dict(os.environ, MANASETU_INSTRUMENT="PHQ-9", MANASETU_DATA_DIR=tempfile.mkdtemp(), PYTHONUTF8="1")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=os.path.dirname(os.path.dirname(__file__)))
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_phq9_mode_end_to_end_enforces_english_only_and_uses_phq9_rules():
    res = _api('''
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    meta = c.get("/api/meta").json()["instrument"]
    r = c.post("/api/kiosk/lookup", json={"person_id": "CMP1002"}); csrf = {"X-CSRF-Token": r.json()["csrf_token"]}
    lang_default = r.json()["language"]                                  # CMP1002 prefers hi/ta, but PHQ-9 only has English
    ta = c.post("/api/kiosk/language", json={"language": "ta"}, headers=csrf).status_code
    en = c.post("/api/kiosk/language", json={"language": "en"}, headers=csrf).status_code
    c.post("/api/kiosk/consent", json={"acknowledged": ["a1","a2","a3"]}, headers=csrf)
    inst = c.get("/api/kiosk/instrument").json()
    sid = c.post("/api/kiosk/session/start", headers=csrf).json()["screening_id"]
    for i, v in enumerate([1,1,1,1,1,1,1,1,2], start=1):                 # total 10, item 9 = 2
        c.put(f"/api/kiosk/session/{sid}/responses", json={"question_id": f"Q{i}", "value": v}, headers=csrf)
    sub = c.post(f"/api/kiosk/session/{sid}/submit", headers=csrf).json()
    s = TestClient(app); l = s.post("/api/auth/login", json={"username": "clinician1", "password": "Clinician#2026"})
    case = s.get("/api/cases/CMP1002").json()
    print(json.dumps({"meta_langs": meta["languages"], "score_max": meta["score_max"], "default_lang": lang_default, "ta": ta, "en": en,
        "n_items": len(inst["items"]), "stem": inst["stem"], "status": sub["status"], "priority": case["recommendation"]["priority"],
        "rules": case["recommendation"]["rule_set_version"], "score": case["recommendation"]["current_value"], "info": case["instrument"]["id"]}))
''')
    assert res["meta_langs"] == ["en"] and res["score_max"] == 27 and res["default_lang"] == "en"
    assert res["ta"] == 422 and res["en"] == 200
    assert res["n_items"] == 9 and res["stem"].startswith("Over the last 2 weeks")
    assert res["status"] == "completed" and res["score"] == 10 and res["info"] == "PHQ-9"
    assert res["priority"] == "Urgent Human Review" and res["rules"] == "rules-phq9-v0.1"     # item 9 = 2
