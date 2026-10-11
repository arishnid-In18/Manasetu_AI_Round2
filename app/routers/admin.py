"""Administrator endpoints. Admins manage the system but deliberately get NO case-level data:
they see aggregates only (counts, completion rates), never an individual's responses or notes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import analysis, config, instruments, services
from ..audit import verify_chain, write_audit
from ..db import get_db
from ..models import (AuditLog, AuthSession, Person, ScreeningResponse, ScreeningSession, SupportRecommendation, User, FollowUp,
                      Referral, new_id, utcnow)
from ..profiles import get_profile
from ..security import hash_password, staff_role

router = APIRouter(prefix="/admin")
ADMIN = staff_role("admin")


def _u(u: User) -> dict:
    return {"user_id": u.user_id, "username": u.username, "display_name": u.display_name, "role": u.role,
            "account_status": u.account_status, "group_scope": u.group_scope,
            "locked": bool(u.locked_until and u.locked_until > utcnow())}


@router.get("/users")
def users(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return {"items": [_u(u) for u in db.query(User).order_by(User.role, User.username).all()]}


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern="^[a-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(officer|clinician|admin)$")
    password: str = Field(min_length=10, max_length=100)
    group_scope: str = Field(default="*", max_length=80)


def _check_scope(scope: str):
    prof = get_profile(config.PROFILE)
    if scope.strip() == "*":
        return
    bad = [g for g in (s.strip() for s in scope.split(",")) if g not in prof["groups"]]
    if bad or not scope.strip():
        raise HTTPException(422, f"group_scope must be '*' or a comma list of: {', '.join(prof['groups'])}.")


@router.post("/users")
def create_user(body: UserIn, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    _check_scope(body.group_scope)
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "That username already exists.")
    u = User(username=body.username, display_name=body.display_name, role=body.role,
             password_hash=hash_password(body.password), group_scope=body.group_scope.strip())
    db.add(u)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="user_created",
                record_type="user", record_id=u.user_id, request=request, details={"role": body.role})
    db.commit()
    return _u(u)


class UserPatch(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(officer|clinician|admin)$")
    account_status: Optional[str] = Field(default=None, pattern="^(active|disabled)$")
    group_scope: Optional[str] = None
    new_password: Optional[str] = Field(default=None, min_length=10, max_length=100)
    unlock: bool = False


@router.patch("/users/{uid}")
def patch_user(uid: str, body: UserPatch, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "User not found.")
    if u.user_id == user.user_id and (body.account_status == "disabled" or (body.role and body.role != "admin")):
        raise HTTPException(409, "You cannot disable or demote your own account.")
    changed = []
    if body.role: u.role = body.role; changed.append("role")
    if body.account_status:
        u.account_status = body.account_status; changed.append("status")
        if body.account_status == "disabled":
            db.query(AuthSession).filter(AuthSession.user_id == u.user_id).delete()   # kill live sessions
    if body.group_scope is not None:
        _check_scope(body.group_scope); u.group_scope = body.group_scope.strip(); changed.append("scope")
    if body.new_password: u.password_hash = hash_password(body.new_password); changed.append("password")
    if body.unlock: u.locked_until, u.failed_count = None, 0; changed.append("unlock")
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="user_updated",
                record_type="user", record_id=uid, request=request, details={"changed": changed})
    db.commit()
    return _u(u)


@router.get("/languages")
def languages(user: User = Depends(ADMIN)):
    return {"supported": instruments.LANGUAGES,
            "note": ("Questionnaire and consent wording is stored per language in app/instruments.py. New Indian "
                     "languages are added there with professionally reviewed translations of the selected validated "
                     "instrument; the UI language packs live in static/app.js."),
            "instrument": {k: v for k, v in instruments.get_instrument().items() if k in
                           ("id", "version", "title", "validated", "status_note", "recall_period", "higher_means")}}


@router.get("/config")
def get_config(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return {"config": services.get_config(db), "rules": analysis.rules_for(instruments.ACTIVE_INSTRUMENT),
            "rules_note": "Rule thresholds are code-defined, versioned and tied to the active instrument. Published values and project choices "
                          "are separated in app/analysis.py; changing them requires clinical approval and a release."}


class ConfigIn(BaseModel):
    key: str
    value: int


@router.put("/config")
def put_config(body: ConfigIn, request: Request, user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    services.set_config(db, body.key, body.value)
    write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username, action="config_changed",
                record_type="config", record_id=body.key, request=request, details={"value": body.value})
    db.commit()
    return {"config": services.get_config(db)}


@router.get("/audit")
def audit(request: Request, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), action: str = "",
          outcome: str = "", actor: str = "", user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    if action: q = q.filter(AuditLog.action.like(f"%{action}%"))
    if outcome: q = q.filter(AuditLog.outcome == outcome)
    if actor: q = q.filter(AuditLog.actor_ref.like(f"%{actor}%"))
    total = q.count()
    rows = q.order_by(AuditLog.audit_id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "pages": max(1, -(-total // page_size)),
            "items": [{"audit_id": r.audit_id, "ts": r.ts.isoformat(), "actor_type": r.actor_type, "actor": r.actor_ref,
                       "action": r.action, "record_type": r.record_type, "record_id": r.record_id,
                       "outcome": r.outcome, "ip": r.ip} for r in rows]}


@router.get("/audit/verify")
def audit_verify(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    return verify_chain(db)


@router.get("/health")
def health(user: User = Depends(ADMIN), db: Session = Depends(get_db)):
    """Application health + data quality, aggregate only."""
    status_counts = dict(db.query(ScreeningSession.status, func.count()).group_by(ScreeningSession.status).all())
    attempts = sum(status_counts.values()) or 1
    persons = db.query(func.count(Person.person_id)).scalar()
    with_valid = db.query(func.count(func.distinct(ScreeningSession.person_id))).filter(ScreeningSession.status == "completed").scalar()
    modes = dict(db.query(ScreeningResponse.input_mode, func.count()).group_by(ScreeningResponse.input_mode).all())
    voice_n, total_n = modes.get("voice", 0), (sum(modes.values()) or 1)
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    chain = verify_chain(db)
    return {
        "app_version": config.APP_VERSION, "profile": config.PROFILE, "database_ok": db_ok,
        "audit_chain_valid": chain["valid"], "audit_rows": chain["checked"],
        "registered_people": persons, "people_with_a_completed_assessment": with_valid,
        "sessions_by_status": status_counts,
        "completion_rate": round(status_counts.get("completed", 0) / attempts, 3),
        "incomplete_or_failed": status_counts.get("partial", 0) + status_counts.get("failed", 0),
        "failed_sessions": status_counts.get("failed", 0),
        "answers_by_input_mode": modes, "voice_answer_share": round(voice_n / total_n, 3),
        "recommendations": dict(db.query(SupportRecommendation.priority_category, func.count()).group_by(SupportRecommendation.priority_category).all()),
        "pending_follow_ups": db.query(func.count(FollowUp.follow_up_id)).filter(FollowUp.status == "pending").scalar(),
        "open_referrals": db.query(func.count(Referral.referral_id)).filter(Referral.status != "closed").scalar(),
        "active_staff_sessions": db.query(func.count(AuthSession.token_hash)).filter(AuthSession.expires_at > utcnow()).scalar(),
        "case_level_access": "Administrators do not have access to individual responses, notes or case detail.",
    }
