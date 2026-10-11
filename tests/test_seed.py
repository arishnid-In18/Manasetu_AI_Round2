"""The 50 synthetic people must produce their hand-specified expected outputs."""
import json
from collections import Counter

from app import config, services
from app.models import Person, TrendAnalysis


def test_fifty_people_across_three_groups(pristine):
    db = pristine()
    try:
        people = db.query(Person).all()
        assert len(people) == 50
        assert Counter(p.group_code for p in people) == {"A": 17, "B": 17, "C": 16}
        assert all(p.is_synthetic for p in people)
        assert {p.language_pref for p in people} == {"ta", "hi", "en"}
    finally:
        db.close()


def test_every_archetype_matches_expected_output(pristine):
    manifest = json.loads((config.DATA_DIR / "seed_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 50
    db = pristine()
    try:
        for m in manifest:
            rec = services.latest_recommendation(db, m["person_id"])
            if m["expected_priority"] is None:
                assert rec is None, m
                continue
            t = db.query(TrendAnalysis).filter(TrendAnalysis.screening_id == rec.screening_id).first()
            assert rec.priority_category == m["expected_priority"], m
            assert t.trend_category == m["expected_trend"], m
    finally:
        db.close()


def test_all_required_scenarios_present(_boot):
    kinds = {m["archetype"] for m in json.loads((config.DATA_DIR / "seed_manifest.json").read_text(encoding="utf-8"))}
    for needed in ("stable_low", "improving", "gradual_increase", "persistent_change", "insufficient_one",
                   "incomplete_mixed", "urgent_safety", "declined_twice", "postponed_latest"):
        assert needed in kinds


def test_declines_cause_no_distress_inference(pristine):
    db = pristine()
    try:
        cfg = services.get_config(db)
        for m in json.loads((config.DATA_DIR / "seed_manifest.json").read_text(encoding="utf-8")):
            if m["archetype"].startswith(("declined", "postponed")):
                p = db.get(Person, m["person_id"])
                rec = services.latest_recommendation(db, p.person_id)
                assert rec.priority_category == "Routine Monitoring"
        twice = next(m for m in json.loads((config.DATA_DIR / "seed_manifest.json").read_text(encoding="utf-8"))
                     if m["archetype"] == "declined_twice")
        info = services.due_info(db, db.get(Person, twice["person_id"]), cfg)
        assert info["welfare_check_suggested"] and info["due_status"] == "Declined"
    finally:
        db.close()
