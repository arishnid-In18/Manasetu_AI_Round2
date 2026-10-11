"""Kiosk endpoints (the person completing the check-in).

The person is NEVER taken from the request body after the initial ID lookup: it is bound to
the server-side kiosk session, so one person cannot read or write another person's data."""
import json
import time
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, instruments, services
from ..audit import write_audit
from ..avatars import avatar_svg
from ..connectors.mock_registry import get_connector
from ..db import get_db
from ..models import (AuthSession, Consent, KioskSession, Notification, Person, ScreeningSession, User, utcnow)
from ..profiles import get_profile
from ..security import (KIOSK_COOKIE, STAFF_COOKIE, get_kiosk, in_scope, new_token, set_session_cookie, token_hash)

router = APIRouter()

_FAILED_LOOKUPS: dict = {}          # ip -> [timestamps]; tiny in-memory throttle for the demo
_MAX_FAILS, _WINDOW_S = 10, 300


def _throttled(ip: str) -> bool:
    now = time.time()
    hits = [t for t in _FAILED_LOOKUPS.get(ip, []) if now - t < _WINDOW_S]
    _FAILED_LOOKUPS[ip] = hits
    return len(hits) >= _MAX_FAILS


def _profile_card(person: Person, source_label: str, due: str) -> dict:
    prof = get_profile(config.PROFILE)
    return {
        "person_id": person.person_id, "display_name": person.display_name,
        "group_label": prof["group_label"], "group_code": person.group_code,
        "group_name": prof["groups"].get(person.group_code, person.group_code),
        "language": person.language_pref, "photo_url": f"/api/photo/{person.person_id}",
        "identity_source": source_label, "check_in_status": due,
        "identity_verified_note": "Identity verified against demonstration records",
    }


def _get_person(db: Session, ks: KioskSession) -> Person:
    p = db.get(Person, ks.person_id)
    if not p or p.record_status != "active":
        raise HTTPException(404, "Profile unavailable.")
    return p


def _owned_session(db: Session, ks: KioskSession, sid: str) -> ScreeningSession:
    s = db.get(ScreeningSession, sid)
    if not s or s.person_id != ks.person_id:
        raise HTTPException(404, "Check-in not found.")
    return s


class LookupIn(BaseModel):
    person_id: str = Field(min_length=1, max_length=30)


@router.post("/lookup")
def lookup(body: LookupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if _throttled(ip):
        raise HTTPException(429, "Too many attempts. Please wait a few minutes or ask a staff member.")
    conn = get_connector()
    res = conn.lookup(body.person_id)
    generic = "Unable to retrieve this profile. Please check the ID or contact an authorized staff member."
    if res.status != "found":
        _FAILED_LOOKUPS.setdefault(ip, []).append(time.time())
        write_audit(db, actor_type="kiosk", action="identity_lookup", actor_ref=None, outcome="failure",
                    record_type="identity", record_id=None, request=request,
                    details={"result": res.status})          # the typed ID is deliberately not logged
        db.commit()
        raise HTTPException(404, generic)                    # same message for unknown / unavailable
    rec = res.record
    person = db.get(Person, rec["person_id"])
    if person is None:                                       # first-time sync of the minimal fields
        person = Person(person_id=rec["person_id"], display_name=rec["display_name"], photo_ref=rec["person_id"].lower(),
                        group_code=rec["group_code"], language_pref=rec["language_pref"], external_ref=rec["external_ref"],
                        record_status="active", is_synthetic=True)
        db.add(person)
        db.flush()
    else:                                                    # keep identity fields in sync with the source
        person.display_name, person.group_code = rec["display_name"], rec["group_code"]
        person.language_pref, person.external_ref = rec["language_pref"], rec["external_ref"]
    token, csrf = new_token(), new_token()
    pref = person.language_pref if person.language_pref in instruments.available_languages() else "en"
    ks = KioskSession(token_hash=token_hash(token), person_id=person.person_id, csrf_token=csrf,
                      language=pref,
                      expires_at=utcnow() + timedelta(minutes=config.KIOSK_SESSION_TTL_MIN))
    db.add(ks)
    cfg = services.get_config(db)
    due = services.due_info(db, person, cfg)["due_status"]
    write_audit(db, actor_type="kiosk", action="identity_lookup", actor_ref=person.person_id, outcome="success",
                record_type="person", record_id=person.person_id, request=request)
    db.commit()
    set_session_cookie(response, KIOSK_COOKIE, token, config.KIOSK_SESSION_TTL_MIN)
    return {"csrf_token": csrf, "profile": _profile_card(person, res.source_label, due), "language": ks.language}


@router.get("/me")
def me(ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    person = _get_person(db, ks)
    conn = get_connector()
    cfg = services.get_config(db)
    open_s = services.open_session_for(db, person)
    return {"profile": _profile_card(person, conn.source_label, services.due_info(db, person, cfg)["due_status"]),
            "csrf_token": ks.csrf_token, "language": ks.language, "consented": bool(ks.consent_id),
            "open_screening_id": open_s.screening_id if open_s else None}


class LanguageIn(BaseModel):
    language: str


@router.post("/language")
def set_language(body: LanguageIn, request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    if body.language not in instruments.LANGUAGE_CODES:
        raise HTTPException(422, "Unsupported language.")
    if body.language not in instruments.available_languages():
        raise HTTPException(422, "The questionnaire has no approved translation in this language yet. Please choose another language or ask a staff member.")
    ks.language = body.language
    write_audit(db, actor_type="kiosk", action="language_selected", actor_ref=ks.person_id, request=request,
                details={"language": body.language})
    db.commit()
    return {"language": ks.language}


class IntentIn(BaseModel):
    decision: str     # yes | not_now | no


@router.post("/intent")
def intent(body: IntentIn, request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    person = _get_person(db, ks)
    if body.decision not in ("yes", "not_now", "no"):
        raise HTTPException(422, "Decision must be yes, not_now or no.")
    if body.decision == "yes":
        write_audit(db, actor_type="kiosk", action="check_in_accepted", actor_ref=person.person_id,
                    record_type="person", record_id=person.person_id, request=request)
        db.commit()
        return {"next": "language"}
    status = "postponed" if body.decision == "not_now" else "declined"
    # an open (in-progress) session is left alone: the person simply chose not to continue now
    s = services.record_attempt(db, person, status, ks.language)
    write_audit(db, actor_type="kiosk", action=f"check_in_{status}", actor_ref=person.person_id,
                record_type="screening_session", record_id=s.screening_id, request=request)
    db.commit()
    return {"next": "done", "status": status}


@router.get("/consent")
def consent_text(ks: KioskSession = Depends(get_kiosk)):
    return instruments.consent_view(ks.language)


class ConsentIn(BaseModel):
    acknowledged: List[str] = []
    staff_assistance: bool = False


@router.post("/consent")
def give_consent(body: ConsentIn, request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    person = _get_person(db, ks)
    required = {a["id"] for a in instruments.CONSENT["acknowledgements"]}
    if body.staff_assistance:
        c = Consent(person_id=person.person_id, consent_version=instruments.CONSENT_VERSION, language=ks.language,
                    acknowledged_json=json.dumps(sorted(set(body.acknowledged) & required)), staff_assistance_requested=True)
        db.add(c)
        db.add(Notification(kind="consent_assistance", person_id=person.person_id,
                            message=f"{person.person_id} asked for a staff member to explain the check-in."))
        write_audit(db, actor_type="kiosk", action="consent_staff_assistance_requested", actor_ref=person.person_id,
                    record_type="person", record_id=person.person_id, request=request)
        db.commit()
        return {"status": "staff_assistance_requested"}
    if set(body.acknowledged) != required:
        raise HTTPException(422, "Please read and confirm each statement to continue, or ask a staff member to explain.")
    c = Consent(person_id=person.person_id, consent_version=instruments.CONSENT_VERSION, language=ks.language,
                acknowledged_json=json.dumps(sorted(required)), staff_assistance_requested=False)
    db.add(c)
    db.flush()
    ks.consent_id = c.consent_id
    write_audit(db, actor_type="kiosk", action="consent_acknowledged", actor_ref=person.person_id,
                record_type="consent", record_id=c.consent_id, request=request,
                details={"version": instruments.CONSENT_VERSION, "language": ks.language})
    db.commit()
    return {"status": "consented", "consent_id": c.consent_id}


def _view(lang: str) -> dict:
    try:
        return instruments.public_view(lang)
    except LookupError as e:
        raise HTTPException(409, str(e))


def _require_consent(ks: KioskSession):
    if not ks.consent_id:
        raise HTTPException(409, "Please read and acknowledge the privacy information first.")


@router.get("/instrument")
def instrument(ks: KioskSession = Depends(get_kiosk)):
    _require_consent(ks)
    return _view(ks.language)


@router.post("/session/start")
def start(request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    _require_consent(ks)
    person = _get_person(db, ks)
    s, resumed = services.start_or_resume_session(db, person, ks.language, ks.consent_id)
    ks.screening_id = s.screening_id
    write_audit(db, actor_type="kiosk", action="assessment_resumed" if resumed else "assessment_started",
                actor_ref=person.person_id, record_type="screening_session", record_id=s.screening_id, request=request)
    db.commit()
    return {"screening_id": s.screening_id, "resumed": resumed, "responses": services.get_responses(db, s.screening_id),
            "instrument": _view(ks.language)}


class ResponseIn(BaseModel):
    question_id: str
    value: Optional[int] = None
    skipped: bool = False
    input_mode: str = Field(default="touch", pattern="^(touch|voice)$")


@router.put("/session/{sid}/responses")
def put_response(sid: str, body: ResponseIn, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    s = _owned_session(db, ks, sid)
    services.save_response(db, s, body.question_id, body.value, body.skipped, input_mode=body.input_mode)
    db.commit()
    return {"saved": True}


@router.get("/session/{sid}")
def get_session(sid: str, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    s = _owned_session(db, ks, sid)
    return {"screening_id": s.screening_id, "status": s.status, "responses": services.get_responses(db, sid)}


@router.post("/session/{sid}/submit")
def submit(sid: str, request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    s = _owned_session(db, ks, sid)
    out = services.finalize_session(db, s)
    if not out["already_submitted"]:
        write_audit(db, actor_type="kiosk", action=f"assessment_{out['status']}", actor_ref=s.person_id,
                    record_type="screening_session", record_id=sid, request=request)
    db.commit()
    # Deliberately minimal: no score, category or explanation is ever shown to the person at the kiosk.
    return {"status": out["status"], "already_submitted": out["already_submitted"]}


@router.post("/session/{sid}/save-exit")
def save_exit(sid: str, request: Request, response: Response, ks: KioskSession = Depends(get_kiosk),
              db: Session = Depends(get_db)):
    s = _owned_session(db, ks, sid)
    write_audit(db, actor_type="kiosk", action="assessment_saved_for_later", actor_ref=s.person_id,
                record_type="screening_session", record_id=sid, request=request)
    db.delete(ks)
    db.commit()
    response.delete_cookie(KIOSK_COOKIE, path="/")
    return {"saved": True}


@router.post("/end")
def end(request: Request, response: Response, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    write_audit(db, actor_type="kiosk", action="kiosk_session_ended", actor_ref=ks.person_id, request=request)
    db.delete(ks)
    db.commit()
    response.delete_cookie(KIOSK_COOKIE, path="/")
    return {"ended": True}


# ---- photo: synthetic illustration, only for the kiosk owner or in-scope staff
photo_router = APIRouter()


@photo_router.get("/photo/{person_id}")
def photo(person_id: str, request: Request, db: Session = Depends(get_db)):
    pid = person_id.strip().upper()
    allowed = False
    ktoken = request.cookies.get(KIOSK_COOKIE)
    if ktoken:
        ks = db.get(KioskSession, token_hash(ktoken))
        allowed = bool(ks and ks.expires_at > utcnow() and ks.person_id == pid)
    stoken = request.cookies.get(STAFF_COOKIE)
    person = db.get(Person, pid)
    if not allowed and stoken and person:
        sess = db.get(AuthSession, token_hash(stoken))
        if sess and sess.expires_at > utcnow():
            user = db.get(User, sess.user_id)
            allowed = bool(user and user.account_status == "active" and in_scope(user, person))
    if not allowed or not person:
        raise HTTPException(404, "Not found.")
    return Response(content=avatar_svg(person.display_name, person.person_id), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, no-store"})


class VoiceEventIn(BaseModel):
    event: str = Field(pattern="^(started|stopped|unsupported|permission_denied)$")


@router.post("/voice-event")
def voice_event(body: VoiceEventIn, request: Request, ks: KioskSession = Depends(get_kiosk), db: Session = Depends(get_db)):
    """Audit only. Audio and transcripts are never sent to or stored by the server."""
    write_audit(db, actor_type="kiosk", action=f"voice_assistant_{body.event}", actor_ref=ks.person_id,
                record_type="screening_session", record_id=ks.screening_id, request=request,
                details={"language": ks.language})
    db.commit()
    return {"ok": True}
