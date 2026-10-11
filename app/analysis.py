"""Transparent, configurable, rule-based analysis engine.

This is NOT a machine-learning model and makes no clinical claim. Every threshold
below is a PLACEHOLDER for the demonstration instrument (DEMO-WB-1, score 0-32,
higher = greater reported difficulty). With a real validated instrument these must
be replaced by cut-offs and follow-up rules approved by qualified clinicians.

Pipeline (see docs/ARCHITECTURE.md):
  valid history -> baseline -> trend -> persistence / sudden change -> absolute
  threshold check -> safety-item rule -> support-priority category -> explanation

The engine is pure: (history, current, context, rules) -> AnalysisResult.
"""
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median
from typing import Dict, List, Optional

import numpy as np

RULESET: Dict = {
    "version": "rules-v0.1-demo",
    "baseline": {
        # Reference period = the first N valid scored assessments of the same instrument
        # (major version) after the person's baseline anchor. A clinician can reset the anchor.
        "reference_n": 3,
        "min_prior_obs": 3,
        "method": "median",
    },
    "trend": {"window": 5, "min_obs": 3, "slope_threshold": 0.75, "min_total_change": 3},
    "deviation_delta": 3,       # score points above baseline considered a meaningful difference
    "persist_n": 3,             # consecutive recent assessments that must all stay elevated
    "sudden_delta": 6,          # rise versus the previous valid assessment
    "dimension_delta": 2,       # per-dimension rise versus its baseline median
    "thresholds": {             # PLACEHOLDER demo thresholds on the 0-32 total
        "monitor": 14,
        "follow_up": 20,
        "urgent_with_persistence": 24,
    },
    "safety": {"follow_up_min": 1, "urgent_min": 2},   # PLACEHOLDER rule for the demo safety item
}

# PHQ-9 rule set. PUBLISHED numbers: severity bands 5/10/15/20 and cut-point >=10 (Kroenke, Spitzer & Williams 2001); minimal clinically
# important change ~5 points (Lowe et al. 2004); any non-zero item 9 needs clinical attention. PROJECT CHOICES (not published, need clinical
# sign-off): persistence window, baseline reference, sudden-change size (2 x 5), item-9 'urgent' level (>=2), slope threshold.
RULESET_PHQ9: Dict = {
    "version": "rules-phq9-v0.1",
    "baseline": {"reference_n": 3, "min_prior_obs": 3, "method": "median"},
    "trend": {"window": 5, "min_obs": 3, "slope_threshold": 1.0, "min_total_change": 5},
    "deviation_delta": 5, "persist_n": 3, "sudden_delta": 10, "dimension_delta": 2,
    "thresholds": {"monitor": 5, "follow_up": 10, "urgent_with_persistence": 20},
    "safety": {"follow_up_min": 1, "urgent_min": 2},
}
RULESETS = {"DEMO-WB-1": RULESET, "PHQ-9": RULESET_PHQ9}


def rules_for(instrument_id: str) -> Dict:
    return RULESETS.get(instrument_id, RULESET)


PRIORITY_ORDER = {"Routine Monitoring": 0, "Monitor": 1, "Human Follow-Up Recommended": 2, "Urgent Human Review": 3}

TREND_STABLE = "Stable"
TREND_INCREASING = "Increasing difficulty"
TREND_IMPROVING = "Improving"
TREND_SUDDEN = "Sudden change"
TREND_PERSISTENT = "Persistent change"
TREND_INSUFFICIENT = "Insufficient information"


@dataclass
class Obs:
    screening_id: str
    date: datetime
    score: int
    items: Dict[str, int] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    baseline_status: str                       # established | not_established
    baseline_value: Optional[float]
    current_value: float
    change_from_baseline: Optional[float]
    trend_category: str
    persistent: bool
    sudden: bool
    valid_observations: int                    # prior valid + current
    data_sufficiency: str
    priority: str
    reasons: List[str]
    explanation: str
    changed_dimensions: List[str]
    safety_value: Optional[int]
    safety_flag: str                           # none | follow_up | urgent
    excluded_incomplete: int
    event_context: Optional[str]
    rule_set_version: str

    def evidence(self) -> dict:
        return {
            "reasons": self.reasons, "changed_dimensions": self.changed_dimensions,
            "persistent": self.persistent, "sudden": self.sudden, "safety_flag": self.safety_flag,
            "excluded_incomplete": self.excluded_incomplete, "event_context": self.event_context,
            "rule_set_version": self.rule_set_version,
        }


# ------------------------------------------------------------------ pieces
def compute_baseline(prior: List[Obs], rules: Dict = RULESET):
    """Return (status, value, reference_obs). Median of the first N valid observations.
    A single observation never establishes a baseline."""
    b = rules["baseline"]
    if len(prior) < b["min_prior_obs"]:
        return "not_established", None, []
    ref = prior[: b["reference_n"]]
    return "established", float(median(o.score for o in ref)), ref


def compute_slope(scores: List[float]) -> float:
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores), dtype=float)
    return float(np.polyfit(x, np.array(scores, dtype=float), 1)[0])


def classify_trend(series: List[float], baseline_status: str, baseline_value: Optional[float],
                   rules: Dict = RULESET):
    """Return (category, persistent, sudden). `series` = valid scores in order, current last."""
    t = rules["trend"]
    if len(series) < t["min_obs"]:
        return TREND_INSUFFICIENT, False, False
    current = series[-1]
    sudden = (current - series[-2]) >= rules["sudden_delta"]
    persistent = False
    if baseline_status == "established" and len(series) >= rules["persist_n"]:
        recent = series[-rules["persist_n"]:]
        persistent = all(s >= baseline_value + rules["deviation_delta"] for s in recent)
    window = series[-t["window"]:]
    slope = compute_slope(window)
    total_change = window[-1] - window[0]
    if sudden:
        return TREND_SUDDEN, persistent, True
    if persistent:
        return TREND_PERSISTENT, True, False
    if slope >= t["slope_threshold"] and total_change >= t["min_total_change"]:
        return TREND_INCREASING, False, False
    improving_vs_baseline = (baseline_status == "established" and
                             current <= baseline_value - rules["deviation_delta"])
    if (slope <= -t["slope_threshold"] and -total_change >= t["min_total_change"]) or improving_vs_baseline:
        return TREND_IMPROVING, False, False
    return TREND_STABLE, False, False


def changed_dimensions(ref: List[Obs], current: Obs, safety_id: Optional[str], rules: Dict = RULESET) -> List[str]:
    """Item/domain ids whose current value is meaningfully above their baseline median."""
    if not ref:
        return []
    out = []
    for q, v in current.items.items():
        if q == safety_id:
            continue
        base_vals = [o.items[q] for o in ref if q in o.items]
        if base_vals and v >= median(base_vals) + rules["dimension_delta"]:
            out.append(q)
    return sorted(out)


def safety_flag(value: Optional[int], rules: Dict = RULESET) -> str:
    if value is None:
        return "none"
    s = rules["safety"]
    if value >= s["urgent_min"]:
        return "urgent"
    if value >= s["follow_up_min"]:
        return "follow_up"
    return "none"


# -------------------------------------------------------------------- main
def analyze(prior: List[Obs], current: Obs, *, safety_id: Optional[str] = None,
            excluded_incomplete: int = 0, event_context: Optional[str] = None,
            rules: Dict = RULESET) -> AnalysisResult:
    prior = sorted(prior, key=lambda o: o.date)
    n_valid = len(prior) + 1
    b_status, b_value, ref = compute_baseline(prior, rules)
    series = [o.score for o in prior] + [current.score]
    category, persistent, sudden = classify_trend(series, b_status, b_value, rules)
    change = round(current.score - b_value, 1) if b_value is not None else None
    sflag = safety_flag(current.items.get(safety_id) if safety_id else None, rules)
    dims = changed_dimensions(ref, current, safety_id, rules)
    th = rules["thresholds"]
    score = current.score

    # ---- priority (precedence: urgent > follow-up > monitor > routine)
    if sflag == "urgent" or (persistent and score >= th["urgent_with_persistence"]):
        priority = "Urgent Human Review"
    elif (sflag == "follow_up" or persistent or sudden or score >= th["follow_up"] or
          (category == TREND_INCREASING and change is not None and change >= 2 * rules["deviation_delta"])):
        priority = "Human Follow-Up Recommended"
    elif (category == TREND_INCREASING or (change is not None and change >= rules["deviation_delta"]) or
          score >= th["monitor"]):
        priority = "Monitor"
    else:
        priority = "Routine Monitoring"

    # ---- data sufficiency (qualitative -- deliberately NOT a probability)
    if b_status == "established":
        sufficiency = "Sufficient for trend analysis"
    elif len(prior) == 0:
        sufficiency = "Insufficient \u2014 first valid assessment; baseline not established"
    else:
        sufficiency = f"Limited \u2014 baseline not established ({len(prior)} prior valid assessment(s); {rules['baseline']['min_prior_obs']} needed)"
    if excluded_incomplete:
        sufficiency += f"; {excluded_incomplete} incomplete assessment(s) excluded from analysis"

    # ---- evidence reasons (every line corresponds to something computed above)
    reasons: List[str] = []
    if sflag == "urgent":
        reasons.append("A safety-related item received a response that meets the configured urgent-review rule.")
    elif sflag == "follow_up":
        reasons.append("A safety-related item received a non-zero response, which meets the configured follow-up rule.")
    if b_status == "established" and change is not None and change >= rules["deviation_delta"]:
        reasons.append(f"Current result differs from the established personal baseline "
                       f"(baseline {b_value:g}, current {score}, difference {change:+g}).")
    if persistent:
        reasons.append(f"The elevated result has persisted across the last {rules['persist_n']} valid assessments.")
    if sudden:
        reasons.append("The result rose sharply compared with the previous valid assessment.")
    if score >= th["follow_up"]:
        reasons.append(f"The current result is at or above the configured demonstration threshold ({th['follow_up']}).")
    elif score >= th["monitor"]:
        reasons.append(f"The current result is at or above the configured monitoring threshold ({th['monitor']}).")
    if category == TREND_INCREASING:
        reasons.append("The recent trend shows gradually increasing reported difficulty.")
    if category == TREND_IMPROVING:
        reasons.append("The recent trend shows reduced reported difficulty compared with earlier assessments.")
    if dims:
        reasons.append(f"{len(dims)} symptom dimension(s) are higher than during the baseline period.")
    if b_status != "established":
        reasons.append("Baseline not established: personal comparison is not yet possible.")
    if event_context:
        reasons.append(f"An authorised case event was recorded close to this assessment ({event_context}). "
                       "This is shown for context only and is not treated as a cause.")
    reasons.append(f"Assessment history available for review: {n_valid} valid assessment(s).")

    lead = next((r for r in reasons if not r.startswith(("Assessment history", "Baseline not established"))),
                "No meaningful change from the personal baseline was detected.")
    explanations = {
        "Urgent Human Review": "Urgent human review is recommended: " + lead[0].lower() + lead[1:] +
                               " Follow the facility's approved emergency or clinical protocol.",
        "Human Follow-Up Recommended": "Human follow-up is recommended: " + lead[0].lower() + lead[1:],
        "Monitor": "Continued monitoring is suggested: " + lead[0].lower() + lead[1:],
        "Routine Monitoring": "Routine monitoring: " + (lead[0].lower() + lead[1:]),
    }
    return AnalysisResult(
        baseline_status=b_status, baseline_value=b_value, current_value=float(score),
        change_from_baseline=change, trend_category=category, persistent=persistent, sudden=sudden,
        valid_observations=n_valid, data_sufficiency=sufficiency, priority=priority, reasons=reasons,
        explanation=explanations[priority], changed_dimensions=dims,
        safety_value=current.items.get(safety_id) if safety_id else None, safety_flag=sflag,
        excluded_incomplete=excluded_incomplete, event_context=event_context,
        rule_set_version=rules["version"],
    )
