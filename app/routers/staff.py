"""Authentication + officer / clinician endpoints. Role AND scope are enforced server-side."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, services
from ..audit import write_audit
from ..db import get_db
from ..models import (AuditLog, AuthSession, ClinicalNote, FollowUp, Notification, Person, Referral,
                      ScreeningSession, SupportRecommendation, User, utcnow)
from ..profiles import get_profile
from ..security import (STAFF_COOKIE, get_staff, in_scope, load_person_in_scope, new_token, set_session_cookie,
                        staff_role, token_hash, verify_password)

router = APIRouter()
CASE_ROLES = ("officer", "clinician")


# ------------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)


def _user_out(u: User) -> dict:
    return {"user_id": u.user_id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "group_scope": u.group_scope}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username.strip().lower()).first()
    now = utcnow()
    bad = HTTPException(401, "Incorrect username or password.")
    if user and user.locked_until and user.locked_until > now:
        write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="login_blocked_locked",
                    outcome="denied", request=request)
        db.commit()
        raise HTTPException(423, "Account temporarily locked after repeated failed attempts. Try again later.")
    if not user or user.account_status != "active" or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_count += 1
            if user.failed_count >= config.MAX_FAILED_LOGINS:
                user.locked_until = now + timedelta(minutes=config.LOCKOUT_MIN)
                user.failed_count = 0
        write_audit(db, actor_type="staff", user_id=user.user_id if user else None,
                    actor_ref=(user.username if user else body.username[:40]), action="login_failed",
                    outcome="failure", request=request)
        db.commit()
        raise bad
    user.failed_count, user.locked_until = 0, None
    token, csrf = new_token(), new_token()
    db.add(AuthSession(token_hash=token_hash(token), user_id=user.user_id, csrf_token=csrf,
                       expires_at=now + timedelta(minutes=config.STAFF_SESSION_TTL_MIN)))
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="login", request=request)
    db.commit()
    set_session_cookie(response, STAFF_COOKIE, token, config.STAFF_SESSION_TTL_MIN)
    return {"user": _user_out(user), "csrf_token": csrf}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user: User = Depends(get_staff), db: Session = Depends(get_db)):
    sess = request.state.auth_session
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="logout", request=request)
    db.delete(sess)
    db.commit()
    response.delete_cookie(STAFF_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request, user: User = Depends(get_staff)):
    return {"user": _user_out(user), "csrf_token": request.state.auth_session.csrf_token}


# -------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(request: Request, search: str = "", group: str = "", priority: str = "", review_status: str = "",
              due: str = "", sort: str = "priority", order: str = Query("desc", pattern="^(asc|desc)$"),
              page: int = Query(1, ge=1), page_size: int = Query(15, ge=1, le=50),
              user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    out = services.dashboard(db, user, search=search, group=group, priority=priority, review_status=review_status,
                             due=due, sort=sort, order=order, page=page, page_size=page_size)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="dashboard_viewed",
                request=request, details={"filters": {k: v for k, v in dict(search=bool(search), group=group,
                                                      priority=priority, due=due).items() if v}})
    db.commit()
    return out


@router.get("/notifications")
def notifications(user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    out = []
    for n in db.query(Notification).filter(Notification.acknowledged_at.is_(None)).order_by(Notification.created_at.desc()).all():
        p = db.get(Person, n.person_id)
        if p and in_scope(user, p):
            out.append({"notification_id": n.notification_id, "kind": n.kind, "person_id": n.person_id,
                        "message": n.message, "created_at": n.created_at.isoformat()})
    return {"items": out, "urgent_count": sum(1 for o in out if o["kind"] == "urgent_review")}


@router.post("/notifications/{nid}/ack")
def ack_notification(nid: str, request: Request, user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    n = db.get(Notification, nid)
    p = db.get(Person, n.person_id) if n else None
    if not n or not p or not in_scope(user, p):
        raise HTTPException(404, "Notification not found.")
    if n.kind == "urgent_review":
        raise HTTPException(409, "Urgent alerts are cleared by recording a human review on the case.")
    n.acknowledged_by, n.acknowledged_at = user.user_id, utcnow()
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="notification_acknowledged",
                record_type="notification", record_id=nid, request=request)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ cases
@router.get("/cases/{person_id}")
def case(person_id: str, request: Request, user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    out = services.case_detail(db, user, person)
    prof = get_profile(config.PROFILE)
    out["profile"]["group_name"] = prof["groups"].get(person.group_code, person.group_code)
    out["profile"]["identity_source"] = prof["identity_source"]
    out["destinations"] = prof["destinations"]
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="case_viewed",
                record_type="person", record_id=person.person_id, request=request)
    db.commit()
    return out


class ReviewIn(BaseModel):
    recommendation_id: str
    decision: str
    note: Optional[str] = Field(default=None, max_length=2000)


def _rec_for(db: Session, person: Person, rec_id: str) -> SupportRecommendation:
    rec = db.get(SupportRecommendation, rec_id)
    if not rec or rec.person_id != person.person_id:
        raise HTTPException(404, "Recommendation not found for this case.")
    return rec


@router.post("/cases/{person_id}/review")
def review(person_id: str, body: ReviewIn, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
           db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    rec = _rec_for(db, person, body.recommendation_id)
    r = services.record_review(db, user, person, rec, body.decision, body.note)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="human_review_recorded",
                record_type="support_recommendation", record_id=rec.recommendation_id, request=request,
                details={"decision": body.decision})
    db.commit()
    return {"review_id": r.review_id, "review_status": rec.review_status}


class ReferralIn(BaseModel):
    recommendation_id: str
    destination: str
    reason: str = Field(min_length=1, max_length=1000)
    follow_up_date: Optional[str] = None      # YYYY-MM-DD


def _parse_date(value: Optional[str], field: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{field} must be a valid date (YYYY-MM-DD).")


@router.post("/cases/{person_id}/referrals")
def create_referral(person_id: str, body: ReferralIn, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
                    db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    rec = _rec_for(db, person, body.recommendation_id)
    valid = [d["key"] for d in get_profile(config.PROFILE)["destinations"]]
    ref = services.create_referral(db, user, person, rec, body.destination, body.reason,
                                   _parse_date(body.follow_up_date, "follow_up_date"), valid)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="referral_created",
                record_type="referral", record_id=ref.referral_id, request=request,
                details={"destination": body.destination})
    db.commit()
    return services.referral_dict(ref)


class ReferralStatusIn(BaseModel):
    status: str
    appointment_at: Optional[str] = None
    outcome_status: Optional[str] = Field(default=None, max_length=60)


def _referral_in_scope(db: Session, user: User, rid: str, request: Request) -> Referral:
    ref = db.get(Referral, rid)
    if not ref:
        raise HTTPException(404, "Referral not found.")
    load_person_in_scope(db, user, ref.person_id, request)
    return ref


@router.patch("/referrals/{rid}/status")
def referral_status(rid: str, body: ReferralStatusIn, request: Request,
                    user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    ref = _referral_in_scope(db, user, rid, request)
    old = ref.status
    services.update_referral_status(db, user, ref, body.status, _parse_date(body.appointment_at, "appointment_at"),
                                    body.outcome_status)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="referral_status_updated",
                record_type="referral", record_id=rid, request=request, details={"from": old, "to": body.status})
    db.commit()
    return services.referral_dict(ref)


@router.get("/referrals")
def list_referrals(status: str = "", user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    ids = [p.person_id for p in services.persons_in_scope(db, user)]
    q = db.query(Referral).filter(Referral.person_id.in_(ids)) if ids else None
    rows = []
    if q is not None:
        if status:
            q = q.filter(Referral.status == status)
        for r in q.order_by(Referral.updated_at.desc()).limit(200).all():
            d = services.referral_dict(r)
            d["person_id"] = r.person_id
            rows.append(d)
    return {"items": rows}


class FollowUpIn(BaseModel):
    when: str
    recommendation_id: Optional[str] = None
    referral_id: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=500)


@router.post("/cases/{person_id}/follow-ups")
def add_follow_up(person_id: str, body: FollowUpIn, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
                  db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    when = _parse_date(body.when, "when")
    if when is None:
        raise HTTPException(422, "A follow-up date is required.")
    rec = _rec_for(db, person, body.recommendation_id) if body.recommendation_id else None
    ref = None
    if body.referral_id:
        ref = db.get(Referral, body.referral_id)
        if not ref or ref.person_id != person.person_id:
            raise HTTPException(404, "Referral not found for this case.")
    f = services.schedule_follow_up(db, user, person, when, rec, ref, body.note)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="follow_up_scheduled",
                record_type="follow_up", record_id=f.follow_up_id, request=request)
    db.commit()
    return {"follow_up_id": f.follow_up_id, "scheduled_for": f.scheduled_for.date().isoformat(), "status": f.status}


@router.patch("/follow-ups/{fid}/complete")
def complete_follow_up(fid: str, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
                       db: Session = Depends(get_db)):
    f = db.get(FollowUp, fid)
    if not f:
        raise HTTPException(404, "Follow-up not found.")
    load_person_in_scope(db, user, f.person_id, request)
    services.complete_follow_up(db, f)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="follow_up_completed",
                record_type="follow_up", record_id=fid, request=request)
    db.commit()
    return {"status": f.status}


@router.get("/follow-ups")
def list_follow_ups(status: str = "pending", user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    ids = [p.person_id for p in services.persons_in_scope(db, user)]
    items = []
    if ids:
        q = db.query(FollowUp).filter(FollowUp.person_id.in_(ids))
        if status:
            q = q.filter(FollowUp.status == status)
        for f in q.order_by(FollowUp.scheduled_for.asc()).limit(200).all():
            items.append({"follow_up_id": f.follow_up_id, "person_id": f.person_id, "status": f.status,
                          "scheduled_for": f.scheduled_for.date().isoformat(), "note": f.note,
                          "overdue": f.status == "pending" and f.scheduled_for.date() < utcnow().date()})
    return {"items": items}


class AssignIn(BaseModel):
    user_id: str


@router.get("/staff/clinicians")
def clinicians(user: User = Depends(staff_role(*CASE_ROLES)), db: Session = Depends(get_db)):
    return {"items": [{"user_id": u.user_id, "display_name": u.display_name}
                      for u in db.query(User).filter(User.role == "clinician", User.account_status == "active").all()]}


@router.post("/cases/{person_id}/assign")
def assign(person_id: str, body: AssignIn, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
           db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    target = db.get(User, body.user_id)
    if not target or target.role != "clinician" or target.account_status != "active" or not in_scope(target, person):
        raise HTTPException(422, "The assigned professional must be an active clinician authorised for this case.")
    person.assigned_professional_id = target.user_id
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="professional_assigned",
                record_type="person", record_id=person.person_id, request=request, details={"assignee": target.username})
    db.commit()
    return {"assigned_to": target.display_name}


class NoteIn(BaseModel):
    kind: str = Field(pattern="^(note|support_plan)$")
    body: str = Field(min_length=1, max_length=4000)


@router.post("/cases/{person_id}/notes")
def add_note(person_id: str, body: NoteIn, request: Request, user: User = Depends(staff_role("clinician")),
             db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    n = ClinicalNote(person_id=person.person_id, author_id=user.user_id, kind=body.kind, body=body.body.strip())
    db.add(n)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action=f"clinical_{body.kind}_added",
                record_type="person", record_id=person.person_id, request=request)
    db.commit()
    return {"note_id": n.note_id}


@router.post("/cases/{person_id}/baseline-reset")
def baseline_reset(person_id: str, request: Request, user: User = Depends(staff_role("clinician")),
                   db: Session = Depends(get_db)):
    """Clinician-approved re-baselining (e.g. after treatment, or an instrument change).
    History is kept; analysis simply starts a new reference period from now."""
    person = load_person_in_scope(db, user, person_id, request)
    person.baseline_anchor_date = utcnow()
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="baseline_reset",
                record_type="person", record_id=person.person_id, request=request)
    db.commit()
    return {"baseline_anchor_date": person.baseline_anchor_date.date().isoformat()}


@router.get("/cases/{person_id}/audit")
def case_audit(person_id: str, request: Request, user: User = Depends(staff_role(*CASE_ROLES)),
               db: Session = Depends(get_db)):
    person = load_person_in_scope(db, user, person_id, request)
    ids = {person.person_id}
    ids |= {r[0] for r in db.query(SupportRecommendation.recommendation_id).filter(SupportRecommendation.person_id == person.person_id)}
    ids |= {r[0] for r in db.query(Referral.referral_id).filter(Referral.person_id == person.person_id)}
    ids |= {r[0] for r in db.query(ScreeningSession.screening_id).filter(ScreeningSession.person_id == person.person_id)}
    rows = (db.query(AuditLog).filter(AuditLog.record_id.in_(ids)).order_by(AuditLog.audit_id.desc()).limit(100).all())
    return {"items": [{"ts": r.ts.isoformat(), "actor": r.actor_ref, "actor_type": r.actor_type, "action": r.action,
                       "record_type": r.record_type, "outcome": r.outcome} for r in rows]}
