"""Business logic. Routers stay thin; everything testable lives here."""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import analysis, instruments
from .analysis import Obs, PRIORITY_ORDER
from .models import (
    AppConfig, AssessmentResult, CaseEvent, ClinicalNote, Consent, FollowUp, HumanReview, Notification,
    Person, Referral, ScreeningResponse, ScreeningSession, SupportRecommendation, TrendAnalysis, User, utcnow,
)

DEFAULT_CONFIG = {
    "assessment_interval_days": 14,     # approved screening schedule (admin-configurable)
    "overdue_grace_days": 7,
    "postpone_retry_days": 2,
    "decline_retry_days": 7,
    "welfare_check_after_declines": 2,  # policy flag after N consecutive declines (administrative, not clinical)
    "stale_session_hours": 24,
    "voice_assistant_enabled": 1,       # 1 = offer the voice assistant at the kiosk, 0 = touch only
}


# ------------------------------------------------------------------ config
def get_config(db: Session) -> Dict[str, int]:
    cfg = dict(DEFAULT_CONFIG)
    for row in db.query(AppConfig).all():
        if row.key in cfg:
            try:
                cfg[row.key] = int(row.value)
            except ValueError:
                pass
    return cfg


def set_config(db: Session, key: str, value: int):
    if key not in DEFAULT_CONFIG:
        raise HTTPException(422, f"Unknown setting '{key}'.")
    if key == "voice_assistant_enabled":
        if value not in (0, 1):
            raise HTTPException(422, "Value must be 0 (off) or 1 (on).")
    elif not (1 <= value <= 365):
        raise HTTPException(422, "Value must be between 1 and 365.")
    row = db.get(AppConfig, key)
    if row:
        row.value, row.updated_at = str(value), utcnow()
    else:
        db.add(AppConfig(key=key, value=str(value)))


# ---------------------------------------------------------- kiosk sessions
def open_session_for(db: Session, person: Person) -> Optional[ScreeningSession]:
    return (db.query(ScreeningSession)
            .filter(ScreeningSession.person_id == person.person_id, ScreeningSession.status == "in_progress")
            .first())


def start_or_resume_session(db: Session, person: Person, language: str, consent_id: str,
                            now: Optional[datetime] = None) -> Tuple[ScreeningSession, bool]:
    now = now or utcnow()
    cfg = get_config(db)
    existing = open_session_for(db, person)
    if existing:
        if existing.started_at < now - timedelta(hours=cfg["stale_session_hours"]):
            existing.status = "partial"                      # stale: close it, never silently reuse
            db.flush()
        else:
            existing.language = language
            return existing, True
    inst = instruments.get_instrument()
    s = ScreeningSession(person_id=person.person_id, instrument_id=inst["id"], instrument_version=inst["version"],
                         started_at=now, language=language, status="in_progress", consent_id=consent_id)
    db.add(s)
    try:
        db.flush()
    except IntegrityError:                                   # race: another request opened one first
        db.rollback()
        return open_session_for(db, person), True
    return s, False


def record_attempt(db: Session, person: Person, status: str, language: str, consent_id: Optional[str] = None,
                   now: Optional[datetime] = None) -> ScreeningSession:
    """Record a postponed / declined check-in. No score and no distress inference."""
    assert status in ("postponed", "declined")
    inst = instruments.get_instrument()
    now = now or utcnow()
    s = ScreeningSession(person_id=person.person_id, instrument_id=inst["id"], instrument_version=inst["version"],
                         started_at=now, completed_at=now, language=language, status=status, consent_id=consent_id)
    db.add(s)
    db.flush()
    return s


def save_response(db: Session, session: ScreeningSession, question_id: str, value: Optional[int],
                  skipped: bool, now: Optional[datetime] = None, input_mode: str = "touch"):
    inst = instruments.get_instrument(session.instrument_id)
    if session.status != "in_progress":
        raise HTTPException(409, "This check-in is no longer open.")
    if question_id not in instruments.item_ids(inst):
        raise HTTPException(422, "Unknown question.")
    if skipped:
        value = None
    elif value is None or not (inst["scale_min"] <= value <= inst["scale_max"]):
        raise HTTPException(422, f"Answer must be between {inst['scale_min']} and {inst['scale_max']}, or skipped.")
    row = (db.query(ScreeningResponse)
           .filter(ScreeningResponse.screening_id == session.screening_id,
                   ScreeningResponse.question_id == question_id).first())
    if row:
        row.value, row.skipped, row.responded_at, row.input_mode = value, skipped, now or utcnow(), input_mode
    else:
        db.add(ScreeningResponse(screening_id=session.screening_id, question_id=question_id, value=value,
                                 skipped=skipped, responded_at=now or utcnow(), input_mode=input_mode))
    db.flush()


def get_responses(db: Session, screening_id: str) -> Dict[str, dict]:
    rows = db.query(ScreeningResponse).filter(ScreeningResponse.screening_id == screening_id).all()
    return {r.question_id: {"value": r.value, "skipped": r.skipped} for r in rows}


# --------------------------------------------------------- history & events
def valid_history(db: Session, person: Person, session: ScreeningSession, before: datetime) -> Tuple[List[Obs], int]:
    """Valid, compatible, scored prior observations (same instrument + major version, after any
    clinician baseline reset) and the count of excluded incomplete assessments."""
    inst_major = instruments.major(session.instrument_version)
    q = (db.query(ScreeningSession, AssessmentResult)
         .join(AssessmentResult, AssessmentResult.screening_id == ScreeningSession.screening_id)
         .filter(ScreeningSession.person_id == person.person_id,
                 ScreeningSession.instrument_id == session.instrument_id,
                 ScreeningSession.status == "completed",
                 ScreeningSession.screening_id != session.screening_id,
                 ScreeningSession.completed_at < before,
                 AssessmentResult.score.isnot(None)))
    if person.baseline_anchor_date:
        q = q.filter(ScreeningSession.completed_at >= person.baseline_anchor_date)
    obs: List[Obs] = []
    for s, r in q.order_by(ScreeningSession.completed_at.asc()).all():
        if instruments.major(s.instrument_version) != inst_major:
            continue                                         # incompatible scoring version
        items = {k: v["value"] for k, v in get_responses(db, s.screening_id).items() if v["value"] is not None}
        obs.append(Obs(s.screening_id, s.completed_at, int(r.score), items))
    excl_q = db.query(func.count(ScreeningSession.screening_id)).filter(
        ScreeningSession.person_id == person.person_id, ScreeningSession.status.in_(("partial", "failed")),
        ScreeningSession.instrument_id == session.instrument_id, ScreeningSession.started_at < before)
    if person.baseline_anchor_date:
        excl_q = excl_q.filter(ScreeningSession.started_at >= person.baseline_anchor_date)
    return obs, int(excl_q.scalar() or 0)


def nearby_event(db: Session, person_id: str, when: datetime, window_days: int = 10) -> Optional[str]:
    best = None
    for e in db.query(CaseEvent).filter(CaseEvent.person_id == person_id).all():
        d = abs((e.event_date - when).days)
        if d <= window_days and (best is None or d < best[0]):
            best = (d, e)
    return f"{best[1].label}, {best[1].event_date.date().isoformat()}" if best else None


# ---------------------------------------------------------------- finalise
def _result_payload(session: ScreeningSession, rec: Optional[SupportRecommendation], dup: bool = False) -> dict:
    return {"screening_id": session.screening_id, "status": session.status, "already_submitted": dup,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None}


def finalize_session(db: Session, session: ScreeningSession, now: Optional[datetime] = None,
                     notify: bool = True) -> dict:
    """Submit a check-in. Idempotent: submitting twice never creates a second result."""
    now = now or utcnow()
    if session.status in ("completed", "partial", "failed"):
        return _result_payload(session, None, dup=True)
    if session.status != "in_progress":
        raise HTTPException(409, "This check-in is not open for submission.")
    inst = instruments.get_instrument(session.instrument_id)
    ids = instruments.item_ids(inst)
    resp = get_responses(db, session.screening_id)
    missing = [q for q in ids if q not in resp]
    if missing:
        raise HTTPException(422, "Please answer, or choose 'prefer not to answer' for, every question before submitting.")
    values = {q: resp[q]["value"] for q in ids}
    score, scoring_status, answered, total = instruments.score_responses(values, inst)
    safety_id = instruments.safety_item_id(inst)
    safety_val = values.get(safety_id) if safety_id else None
    person = db.get(Person, session.person_id)

    try:
        session.completed_at = now
        session.status = "completed" if scoring_status == "scored" else "partial"
        res = AssessmentResult(screening_id=session.screening_id, score=score, scoring_status=scoring_status,
                               items_answered=answered, items_total=total, completeness=round(answered / total, 3),
                               safety_item_value=safety_val, analysis_version=analysis.RULESET["version"], created_at=now)
        db.add(res)
        db.flush()
        prior, excluded = valid_history(db, person, session, now)

        if session.status == "completed":
            current = Obs(session.screening_id, now, int(score), {q: int(v) for q, v in values.items() if v is not None})
            ar = analysis.analyze(prior, current, safety_id=safety_id, excluded_incomplete=excluded,
                                  event_context=nearby_event(db, person.person_id, now),
                                  rules=analysis.rules_for(session.instrument_id))
            rec = _persist_analysis(db, person, session, ar, now, notify)
        else:
            rec = _persist_partial(db, person, session, prior, excluded, safety_val, now, notify, analysis.rules_for(session.instrument_id))
        db.flush()
    except IntegrityError:
        db.rollback()                                        # concurrent double-submit: first one wins
        fresh = db.get(ScreeningSession, session.screening_id)
        return _result_payload(fresh, None, dup=True)
    except Exception:
        db.rollback()
        s = db.get(ScreeningSession, session.screening_id)
        if s:
            s.status = "failed"                              # responses are preserved; staff can see 'failed'
            db.commit()
        raise HTTPException(503, "We could not process this check-in. Your answers were saved. Please tell a staff member.")
    return _result_payload(session, rec)


def _persist_analysis(db, person, session, ar: analysis.AnalysisResult, now, notify) -> SupportRecommendation:
    db.add(TrendAnalysis(
        person_id=person.person_id, screening_id=session.screening_id, analysis_date=now,
        baseline_status=ar.baseline_status, baseline_value=ar.baseline_value, current_value=ar.current_value,
        change_from_baseline=ar.change_from_baseline, trend_category=ar.trend_category,
        data_sufficiency=ar.data_sufficiency, valid_observations=ar.valid_observations,
        evidence_json=json.dumps(ar.evidence())))
    rec = SupportRecommendation(person_id=person.person_id, screening_id=session.screening_id,
                                priority_category=ar.priority, explanation=ar.explanation,
                                reasons_json=json.dumps(ar.reasons), rule_set_version=ar.rule_set_version,
                                created_at=now)
    db.add(rec)
    db.flush()
    if ar.priority == "Urgent Human Review" and notify:
        _notify_urgent(db, person, rec, now)
    return rec


def _persist_partial(db, person, session, prior, excluded, safety_val, now, notify, rules=None) -> Optional[SupportRecommendation]:
    """Partial assessment: never auto-scored. The safety item is still honoured if it was answered."""
    rules = rules or analysis.RULESET
    flag = analysis.safety_flag(safety_val, rules)
    b_status, b_value, _ = analysis.compute_baseline(prior, rules)
    db.add(TrendAnalysis(
        person_id=person.person_id, screening_id=session.screening_id, analysis_date=now,
        baseline_status=b_status, baseline_value=b_value, current_value=None, change_from_baseline=None,
        trend_category=analysis.TREND_INSUFFICIENT, data_sufficiency="Insufficient \u2014 assessment incomplete (not scored)",
        valid_observations=len(prior),
        evidence_json=json.dumps({"reasons": ["Assessment was incomplete and was not scored."], "partial": True})))
    if flag == "none":
        return None
    priority = "Urgent Human Review" if flag == "urgent" else "Human Follow-Up Recommended"
    reason = "A safety-related item in an incomplete assessment received a response that meets the configured review rule."
    rec = SupportRecommendation(
        person_id=person.person_id, screening_id=session.screening_id, priority_category=priority,
        explanation=f"{'Urgent human review' if flag == 'urgent' else 'Human follow-up'} is recommended: {reason[0].lower()}{reason[1:]}",
        reasons_json=json.dumps([reason, "The rest of the assessment was incomplete and was not scored."]),
        rule_set_version=analysis.RULESET["version"], created_at=now)
    db.add(rec)
    db.flush()
    if priority == "Urgent Human Review" and notify:
        _notify_urgent(db, person, rec, now)
    return rec


def _notify_urgent(db: Session, person: Person, rec: SupportRecommendation, now: datetime):
    db.add(Notification(kind="urgent_review", person_id=person.person_id, recommendation_id=rec.recommendation_id,
                        message=f"Urgent human review recommended for {person.person_id} ({person.group_code}).",
                        created_at=now))


# --------------------------------------------------------------- snapshots
def latest_recommendation(db: Session, person_id: str) -> Optional[SupportRecommendation]:
    return (db.query(SupportRecommendation).filter(SupportRecommendation.person_id == person_id)
            .order_by(SupportRecommendation.created_at.desc()).first())


def due_info(db: Session, person: Person, cfg: Dict[str, int], now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    sessions = (db.query(ScreeningSession).filter(ScreeningSession.person_id == person.person_id)
                .order_by(ScreeningSession.started_at.desc()).all())
    last_completed = next((s for s in sessions if s.status == "completed"), None)
    latest = sessions[0] if sessions else None
    consecutive_declines = 0
    for s in sessions:
        if s.status == "declined":
            consecutive_declines += 1
        elif s.status in ("postponed", "in_progress"):
            continue
        else:
            break
    welfare = consecutive_declines >= cfg["welfare_check_after_declines"]
    next_due = (last_completed.completed_at + timedelta(days=cfg["assessment_interval_days"])) if last_completed else now
    status = "Up to date"
    if latest and latest.status == "in_progress":
        status = "In progress"
    elif (latest and latest.status == "postponed" and
          latest.started_at + timedelta(days=cfg["postpone_retry_days"]) > now):
        status = "Postponed"
    elif (latest and latest.status == "declined" and
          latest.started_at + timedelta(days=cfg["decline_retry_days"]) > now):
        status = "Declined"
    elif not last_completed:
        status = "Due"
    elif latest and latest.status == "partial" and latest.started_at > last_completed.completed_at:
        status = "Incomplete"
    elif now >= next_due + timedelta(days=cfg["overdue_grace_days"]):
        status = "Overdue"
    elif now >= next_due:
        status = "Due"
    needs_assessment = status in ("Due", "Overdue", "Incomplete") or (status in ("Postponed", "Declined"))
    return {
        "due_status": status, "needs_assessment": needs_assessment,
        "last_assessment_at": (last_completed.completed_at if last_completed else None),
        "latest_attempt_at": latest.started_at if latest else None,
        "latest_attempt_status": latest.status if latest else None,
        "next_due": next_due, "welfare_check_suggested": welfare,
        "consecutive_declines": consecutive_declines,
    }


def snapshot(db: Session, person: Person, cfg: Dict[str, int], now: Optional[datetime] = None) -> dict:
    rec = latest_recommendation(db, person.person_id)
    trend = None
    if rec:
        t = db.query(TrendAnalysis).filter(TrendAnalysis.screening_id == rec.screening_id).first()
        trend = t.trend_category if t else None
    due = due_info(db, person, cfg, now)
    next_fu = (db.query(FollowUp).filter(FollowUp.person_id == person.person_id, FollowUp.status == "pending")
               .order_by(FollowUp.scheduled_for.asc()).first())
    assigned = db.get(User, person.assigned_professional_id) if person.assigned_professional_id else None
    unack = (db.query(Notification).filter(Notification.person_id == person.person_id, Notification.kind == "urgent_review",
                                           Notification.acknowledged_at.is_(None)).count() > 0)
    return {
        "person_id": person.person_id, "case_id": person.person_id, "group_code": person.group_code,
        "language": person.language_pref,
        "latest_assessment_date": (due["last_assessment_at"].date().isoformat() if due["last_assessment_at"] else None),
        "latest_attempt_status": due["latest_attempt_status"],
        "trend": trend, "priority": rec.priority_category if rec else None,
        "review_status": rec.review_status if rec else None,
        "recommendation_id": rec.recommendation_id if rec else None,
        "recommendation_at": rec.created_at.isoformat() if rec else None,
        "assigned_professional": assigned.display_name if assigned else None,
        "next_follow_up": next_fu.scheduled_for.date().isoformat() if next_fu else None,
        "due_status": due["due_status"], "needs_assessment": due["needs_assessment"],
        "next_due": due["next_due"].date().isoformat(),
        "welfare_check_suggested": due["welfare_check_suggested"], "unacknowledged_urgent": unack,
    }


def scope_filter(user: User):
    scope = (user.group_scope or "").strip()
    if scope == "*":
        return None
    return {s.strip() for s in scope.split(",") if s.strip()}


def persons_in_scope(db: Session, user: User) -> List[Person]:
    if user.role == "admin":
        return []
    q = db.query(Person).filter(Person.record_status == "active")
    groups = scope_filter(user)
    if groups is not None:
        q = q.filter(Person.group_code.in_(groups))
    return q.order_by(Person.person_id).all()


def dashboard(db: Session, user: User, *, search: str = "", group: str = "", priority: str = "",
              review_status: str = "", due: str = "", sort: str = "priority", order: str = "desc",
              page: int = 1, page_size: int = 15) -> dict:
    cfg = get_config(db)
    now = utcnow()
    rows = [snapshot(db, p, cfg, now) for p in persons_in_scope(db, user)]

    counts = {"urgent": 0, "follow_up": 0, "monitor": 0, "routine": 0, "unassessed": 0, "unreviewed_flagged": 0}
    for r in rows:
        p = r["priority"]
        if p == "Urgent Human Review": counts["urgent"] += 1
        elif p == "Human Follow-Up Recommended": counts["follow_up"] += 1
        elif p == "Monitor": counts["monitor"] += 1
        elif p == "Routine Monitoring": counts["routine"] += 1
        else: counts["unassessed"] += 1
        if p in ("Urgent Human Review", "Human Follow-Up Recommended") and r["review_status"] == "pending":
            counts["unreviewed_flagged"] += 1
    ids = [r["person_id"] for r in rows]
    fu_pending = (db.query(FollowUp).filter(FollowUp.person_id.in_(ids), FollowUp.status == "pending").count() if ids else 0)
    summary = {**counts, "follow_ups_pending": fu_pending,
               "assessments_due": sum(1 for r in rows if r["needs_assessment"]),
               "welfare_checks_suggested": sum(1 for r in rows if r["welfare_check_suggested"]),
               "total_in_scope": len(rows)}

    s = search.strip().upper()
    if s:
        rows = [r for r in rows if s in r["person_id"]]
    if group:
        rows = [r for r in rows if r["group_code"] == group]
    if priority:
        rows = [r for r in rows if (r["priority"] or "Not yet assessed") == priority]
    if review_status:
        rows = [r for r in rows if r["review_status"] == review_status]
    if due:
        rows = [r for r in rows if r["due_status"] == due]

    def key(r):
        if sort == "priority":
            return (PRIORITY_ORDER.get(r["priority"], -1), r["recommendation_at"] or "")
        if sort in ("person_id", "group_code", "trend", "due_status"):
            return (r.get(sort) or "")
        if sort in ("latest_assessment_date", "next_follow_up"):
            return (r.get(sort) or "")
        return (PRIORITY_ORDER.get(r["priority"], -1),)
    rows.sort(key=key, reverse=(order == "desc"))
    total = len(rows)
    page = max(1, page)
    start = (page - 1) * page_size
    return {"summary": summary, "rows": rows[start:start + page_size], "total": total, "page": page,
            "page_size": page_size, "pages": max(1, -(-total // page_size))}


# ------------------------------------------------------------ case detail
def attempts_history(db: Session, person: Person) -> List[dict]:
    out = []
    sessions = (db.query(ScreeningSession).filter(ScreeningSession.person_id == person.person_id,
                                                  ScreeningSession.status != "in_progress")
                .order_by(ScreeningSession.started_at.asc()).all())
    for s in sessions:
        r = db.query(AssessmentResult).filter(AssessmentResult.screening_id == s.screening_id).first()
        t = db.query(TrendAnalysis).filter(TrendAnalysis.screening_id == s.screening_id).first()
        rec = db.query(SupportRecommendation).filter(SupportRecommendation.screening_id == s.screening_id).first()
        out.append({
            "screening_id": s.screening_id, "date": (s.completed_at or s.started_at).date().isoformat(),
            "status": s.status, "language": s.language,
            "instrument": f"{s.instrument_id} v{s.instrument_version}",
            "score": r.score if r else None, "completeness": r.completeness if r else None,
            "baseline_value": t.baseline_value if t else None, "trend": t.trend_category if t else None,
            "priority": rec.priority_category if rec else None,
        })
    return out


def domain_view(db: Session, person: Person, session_id: str, rules=None) -> List[dict]:
    """Clinician-only item/domain view: current values vs baseline-period medians."""
    s = db.get(ScreeningSession, session_id)
    if not s:
        return []
    rules = rules or analysis.rules_for(s.instrument_id)
    inst = instruments.get_instrument(s.instrument_id)
    resp = get_responses(db, s.screening_id)
    prior, _ = valid_history(db, person, s, s.completed_at or utcnow())
    _, _, ref = analysis.compute_baseline(prior, rules)
    from statistics import median
    out = []
    for item in inst["items"]:
        cur = resp.get(item["id"], {}).get("value")
        base_vals = [o.items[item["id"]] for o in ref if item["id"] in o.items]
        out.append({"question_id": item["id"], "domain": item["domain"], "safety": item.get("safety", False),
                    "current": cur, "baseline_median": (float(median(base_vals)) if base_vals else None),
                    "scale_max": inst["scale_max"]})
    return out


def case_detail(db: Session, user: User, person: Person) -> dict:
    cfg = get_config(db)
    snap = snapshot(db, person, cfg)
    is_clin = user.role == "clinician"
    rec = latest_recommendation(db, person.person_id)
    detail_rec = None
    domains = None
    if rec:
        t = db.query(TrendAnalysis).filter(TrendAnalysis.screening_id == rec.screening_id).first()
        ev = json.loads(t.evidence_json) if t else {}
        reasons = json.loads(rec.reasons_json)
        res = db.query(AssessmentResult).filter(AssessmentResult.screening_id == rec.screening_id).first()
        detail_rec = {
            "recommendation_id": rec.recommendation_id, "screening_id": rec.screening_id,
            "priority": rec.priority_category, "explanation": rec.explanation, "reasons": reasons,
            "rule_set_version": rec.rule_set_version, "created_at": rec.created_at.isoformat(),
            "review_status": rec.review_status,
            "baseline_status": t.baseline_status if t else None,
            "baseline_value": t.baseline_value if t else None,
            "current_value": t.current_value if t else None,
            "change_from_baseline": t.change_from_baseline if t else None,
            "trend": t.trend_category if t else None,
            "data_sufficiency": t.data_sufficiency if t else None,
            "valid_observations": t.valid_observations if t else None,
            "completeness": res.completeness if res else None,
            "analysis_version": res.analysis_version if res else None,
            "persistent": ev.get("persistent"), "sudden": ev.get("sudden"),
            "changed_dimension_count": len(ev.get("changed_dimensions", [])),
            "safety_flag": ev.get("safety_flag"),
            "event_context": ev.get("event_context"),
            "clinical_diagnosis": "Not provided by the system",
        }
        if is_clin:
            detail_rec["changed_dimensions"] = ev.get("changed_dimensions", [])
            domains = domain_view(db, person, rec.screening_id)

    hist = attempts_history(db, person)
    counts = {k: sum(1 for h in hist if h["status"] == k) for k in ("completed", "partial", "declined", "postponed", "failed")}
    events = [{"date": e.event_date.date().isoformat(), "label": e.label, "source": e.source}
              for e in db.query(CaseEvent).filter(CaseEvent.person_id == person.person_id).order_by(CaseEvent.event_date)]
    reviews = [{"review_id": r.review_id, "decision": r.decision, "note": r.note, "at": r.created_at.isoformat(),
                "reviewer": (db.get(User, r.reviewer_id).display_name if db.get(User, r.reviewer_id) else None),
                "recommendation_id": r.recommendation_id}
               for r in db.query(HumanReview).filter(HumanReview.person_id == person.person_id).order_by(HumanReview.created_at)]
    referrals = [referral_dict(r) for r in db.query(Referral).filter(Referral.person_id == person.person_id)
                 .order_by(Referral.created_at)]
    follow_ups = [{"follow_up_id": f.follow_up_id, "scheduled_for": f.scheduled_for.date().isoformat(), "status": f.status,
                   "completed_at": f.completed_at.isoformat() if f.completed_at else None,
                   "referral_id": f.referral_id, "recommendation_id": f.recommendation_id, "note": f.note}
                  for f in db.query(FollowUp).filter(FollowUp.person_id == person.person_id).order_by(FollowUp.scheduled_for)]
    notes = None
    if is_clin:
        notes = [{"note_id": n.note_id, "kind": n.kind, "body": n.body, "at": n.created_at.isoformat(),
                  "author": (db.get(User, n.author_id).display_name if db.get(User, n.author_id) else None)}
                 for n in db.query(ClinicalNote).filter(ClinicalNote.person_id == person.person_id).order_by(ClinicalNote.created_at.desc())]
    return {
        "profile": {"person_id": person.person_id, "display_name": person.display_name, "group_code": person.group_code,
                    "language": person.language_pref, "record_status": person.record_status,
                    "baseline_anchor_date": person.baseline_anchor_date.date().isoformat() if person.baseline_anchor_date else None,
                    "assigned_professional_id": person.assigned_professional_id,
                    "is_synthetic": person.is_synthetic},
        "snapshot": snap, "recommendation": detail_rec, "history": hist, "attempt_counts": counts,
        "events": events, "reviews": reviews, "referrals": referrals, "follow_ups": follow_ups,
        "notes": notes, "domains": domains, "timeline": timeline(reviews, referrals, follow_ups, hist),
        "viewer_role": user.role,
        "instrument": instrument_info(),
    }


def instrument_info() -> dict:
    inst = instruments.get_instrument()
    return {"id": inst["id"], "version": inst["version"], "title": inst["title"], "validated": inst["validated"],
            "score_max": inst["score_range"][1], "higher_means": inst["higher_means"], "threshold_note": inst["threshold_note"],
            "languages": instruments.available_languages(inst), "rule_set_version": analysis.rules_for(inst["id"])["version"]}


def referral_dict(r: Referral) -> dict:
    return {"referral_id": r.referral_id, "recommendation_id": r.recommendation_id, "screening_id": r.screening_id,
            "destination": r.destination, "reason": r.reason, "status": r.status,
            "follow_up_date": r.follow_up_date.date().isoformat() if r.follow_up_date else None,
            "appointment_at": r.appointment_at.isoformat() if r.appointment_at else None,
            "outcome_status": r.outcome_status, "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat()}


def timeline(reviews, referrals, follow_ups, hist) -> List[dict]:
    ev = []
    for h in hist:
        ev.append({"date": h["date"], "kind": "assessment",
                   "text": f"Assessment {h['status']}" + (f" (score {h['score']})" if h["score"] is not None else "")})
    for r in reviews:
        ev.append({"date": r["at"][:10], "kind": "review", "text": f"Human review recorded: {r['decision'].replace('_', ' ')}"})
    for r in referrals:
        ev.append({"date": r["created_at"][:10], "kind": "referral",
                   "text": f"Referral {r['status'].replace('_', ' ')} \u2192 {r['destination'].replace('_', ' ')}"})
    for f in follow_ups:
        ev.append({"date": f["scheduled_for"], "kind": "follow_up", "text": f"Follow-up {f['status']}"})
    return sorted(ev, key=lambda e: e["date"])


# ------------------------------------------------------ human-review flow
REVIEW_DECISIONS = {"no_concern_found", "monitor_only", "follow_up_planned", "referral_decided", "escalated_to_protocol"}


def record_review(db: Session, user: User, person: Person, rec: SupportRecommendation, decision: str,
                  note: Optional[str], now: Optional[datetime] = None) -> HumanReview:
    if rec.person_id != person.person_id:
        raise HTTPException(404, "Recommendation not found for this case.")
    if decision not in REVIEW_DECISIONS:
        raise HTTPException(422, f"Decision must be one of: {', '.join(sorted(REVIEW_DECISIONS))}.")
    r = HumanReview(recommendation_id=rec.recommendation_id, person_id=person.person_id, reviewer_id=user.user_id,
                    decision=decision, note=(note or "").strip()[:2000] or None, created_at=now or utcnow())
    db.add(r)
    rec.review_status = "reviewed"
    for n in db.query(Notification).filter(Notification.person_id == person.person_id, Notification.kind == "urgent_review",
                                           Notification.acknowledged_at.is_(None)):
        n.acknowledged_by, n.acknowledged_at = user.user_id, now or utcnow()
    db.flush()
    return r


REFERRAL_TRANSITIONS = {
    "recommended": {"accepted", "closed"},
    "accepted": {"appointment_scheduled", "closed"},
    "appointment_scheduled": {"appointment_completed", "closed"},
    "appointment_completed": {"follow_up_pending", "closed"},
    "follow_up_pending": {"closed"},
    "closed": set(),
}


def create_referral(db: Session, user: User, person: Person, rec: SupportRecommendation, destination: str,
                    reason: str, follow_up_date: Optional[datetime], valid_destinations: List[str],
                    now: Optional[datetime] = None) -> Referral:
    if rec.person_id != person.person_id:
        raise HTTPException(404, "Recommendation not found for this case.")
    if destination not in valid_destinations:
        raise HTTPException(422, "Unknown referral destination.")
    if not reason.strip():
        raise HTTPException(422, "A referral reason is required.")
    now = now or utcnow()
    ref = Referral(recommendation_id=rec.recommendation_id, person_id=person.person_id, screening_id=rec.screening_id,
                   destination=destination, reason=reason.strip()[:1000], status="recommended",
                   follow_up_date=follow_up_date, created_by=user.user_id, created_at=now, updated_at=now)
    db.add(ref)
    db.flush()
    return ref


def update_referral_status(db: Session, user: User, ref: Referral, new_status: str,
                           appointment_at: Optional[datetime], outcome_status: Optional[str],
                           now: Optional[datetime] = None) -> Referral:
    if new_status not in REFERRAL_TRANSITIONS.get(ref.status, set()):
        raise HTTPException(409, f"A referral cannot move from '{ref.status}' to '{new_status}'.")
    officer_ok = (ref.status == "recommended" and new_status == "closed")
    if user.role != "clinician" and not officer_ok:
        raise HTTPException(403, "Only a clinician can advance a referral beyond 'recommended'.")
    if new_status == "appointment_scheduled":
        if not appointment_at:
            raise HTTPException(422, "An appointment date/time is required.")
        ref.appointment_at = appointment_at
    if new_status == "closed":
        if not (outcome_status or "").strip():
            raise HTTPException(422, "Closing a referral requires an outcome.")
        ref.outcome_status = outcome_status.strip()[:60]
    ref.status = new_status
    ref.updated_at = now or utcnow()
    db.flush()
    return ref


def schedule_follow_up(db: Session, user: User, person: Person, when: datetime,
                       rec: Optional[SupportRecommendation], ref: Optional[Referral], note: Optional[str],
                       now: Optional[datetime] = None) -> FollowUp:
    now = now or utcnow()
    if when.date() < now.date():
        raise HTTPException(422, "Follow-up date cannot be in the past.")
    f = FollowUp(person_id=person.person_id, recommendation_id=rec.recommendation_id if rec else None,
                 referral_id=ref.referral_id if ref else None, scheduled_for=when, status="pending",
                 note=(note or "")[:500] or None, created_by=user.user_id, created_at=now)
    db.add(f)
    db.flush()
    return f


def complete_follow_up(db: Session, f: FollowUp, now: Optional[datetime] = None) -> FollowUp:
    if f.status != "pending":
        raise HTTPException(409, f"Follow-up is already {f.status}.")
    f.status, f.completed_at = "completed", now or utcnow()
    db.flush()
    return f
