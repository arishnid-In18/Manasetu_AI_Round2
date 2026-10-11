"""Unit tests for the pure rule engine (no database)."""
from datetime import datetime, timedelta

from app import analysis, instruments
from app.analysis import Obs, analyze

T0 = datetime(2026, 1, 1)


def mk(scores, safety=None, base_items=None):
    obs = []
    for i, s in enumerate(scores):
        items = {f"Q{k}": 0 for k in range(1, 9)}
        items.update(base_items or {})
        obs.append(Obs(f"S{i}", T0 + timedelta(days=14 * i), s, items))
    return obs


def run(scores, safety_value=0, items_override=None):
    obs = mk(scores)
    cur = obs[-1]
    cur.items["Q8"] = safety_value
    if items_override:
        cur.items.update(items_override)
    return analyze(obs[:-1], cur, safety_id="Q8")


def test_single_observation_never_establishes_baseline():
    r = run([5])
    assert r.baseline_status == "not_established" and r.baseline_value is None
    assert r.trend_category == analysis.TREND_INSUFFICIENT


def test_two_prior_still_not_established():
    r = run([4, 4, 7])
    assert r.baseline_status == "not_established"


def test_spec_example_current_7_previous_4_4_5_6():
    r = run([4, 4, 5, 6, 7])
    assert r.baseline_status == "established" and r.baseline_value == 4.0
    assert r.change_from_baseline == 3.0
    assert r.trend_category == analysis.TREND_INCREASING
    assert r.priority == "Monitor"                       # illustrative thresholds, not clinical


def test_same_history_larger_jump_requires_human_followup():
    r = run([4, 4, 5, 6, 10])
    assert r.priority == "Human Follow-Up Recommended"
    assert any("personal baseline" in x for x in r.reasons)


def test_persistent_change_detected():
    r = run([4, 4, 5, 9, 10, 11])
    assert r.persistent and r.trend_category == analysis.TREND_PERSISTENT
    assert r.priority == "Human Follow-Up Recommended"
    assert any("persisted" in x for x in r.reasons)


def test_one_bad_day_is_not_persistent():
    r = run([4, 4, 5, 5, 5, 9])
    assert not r.persistent


def test_sudden_change():
    r = run([5, 5, 6, 5, 6, 14])
    assert r.sudden and r.trend_category == analysis.TREND_SUDDEN
    assert r.priority == "Human Follow-Up Recommended"


def test_high_baseline_does_not_dismiss_high_current_result():
    r = run([19, 20, 19, 20, 21, 21])
    assert abs(r.change_from_baseline) < 3                  # looks "normal" for this person...
    assert r.priority == "Human Follow-Up Recommended"       # ...but is still surfaced


def test_single_high_result_without_baseline_still_reviewed():
    assert run([21]).priority == "Human Follow-Up Recommended"


def test_improving_trend_is_not_called_recovery():
    r = run([15, 14, 12, 10, 8, 7])
    assert r.trend_category == analysis.TREND_IMPROVING and r.priority == "Routine Monitoring"
    assert "recover" not in r.explanation.lower()


def test_stable_low():
    r = run([5, 4, 5, 6, 5, 4])
    assert r.trend_category == analysis.TREND_STABLE and r.priority == "Routine Monitoring"


def test_safety_item_rules():
    assert run([6, 7, 6, 7, 6, 9], safety_value=3).priority == "Urgent Human Review"
    assert run([6, 7, 6, 7, 6, 9], safety_value=2).priority == "Urgent Human Review"
    assert run([5, 5, 5, 5], safety_value=1).priority == "Human Follow-Up Recommended"
    assert run([5, 5, 5, 5], safety_value=0).priority == "Routine Monitoring"


def test_urgent_for_persistent_high():
    r = run([18, 19, 19, 24, 25, 26])
    assert r.priority == "Urgent Human Review"
    assert "protocol" in r.explanation.lower()


def test_explanation_never_claims_diagnosis_or_probability():
    for s in ([5], [4, 4, 5, 9, 10, 11], [6, 7, 6, 7, 6, 9]):
        r = run(s, safety_value=3 if s == [6, 7, 6, 7, 6, 9] else 0)
        text = (r.explanation + " ".join(r.reasons)).lower()
        assert "diagnos" not in text and "%" not in text and "probab" not in text


def test_data_sufficiency_is_qualitative():
    assert run([4, 4, 5, 6]).data_sufficiency.startswith("Sufficient")
    assert run([4, 5]).data_sufficiency.startswith("Limited")
    assert run([4]).data_sufficiency.startswith("Insufficient")


def test_event_context_is_never_causal():
    obs = mk([4, 4, 5, 9, 10, 11])
    r = analyze(obs[:-1], obs[-1], safety_id="Q8", event_context="Court hearing, 2026-03-01")
    text = " ".join(r.reasons).lower()
    assert "context only" in text and "cause" in text and "caused" not in text and "because of" not in text


def test_changed_dimensions_from_item_level_history():
    prior = mk([4, 4, 5])
    cur = Obs("S9", T0 + timedelta(days=100), 12, {**{f"Q{k}": 0 for k in range(1, 9)}, "Q3": 4, "Q2": 3})
    r = analyze(prior, cur, safety_id="Q8")
    assert r.changed_dimensions == ["Q2", "Q3"]


def test_partial_assessment_is_never_scored_as_zero():
    resp = {f"Q{k}": 2 for k in range(1, 9)}
    resp["Q3"] = None
    score, status, answered, total = instruments.score_responses(resp)
    assert score is None and status == "not_scored_incomplete" and answered == 7 and total == 8


def test_complete_assessment_scores_sum():
    score, status, a, t = instruments.score_responses({f"Q{k}": 1 for k in range(1, 9)})
    assert (score, status, a, t) == (8, "scored", 8, 8)
