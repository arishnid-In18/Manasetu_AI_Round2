"""Password hashing, server-side sessions, CSRF checks and role/scope enforcement."""
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AuthSession, KioskSession, Person, User, utcnow
from .audit import write_audit

STAFF_COOKIE = "ms_staff"
KIOSK_COOKIE = "ms_kiosk"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# ---------------------------------------------------------------- passwords
def hash_password(password: str, iterations: int = 200_000) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


# ------------------------------------------------------------------ tokens
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_session_cookie(response, name: str, token: str, max_age_min: int):
    response.set_cookie(name, token, max_age=max_age_min * 60, httponly=True, samesite="strict",
                        secure=config.COOKIE_SECURE, path="/")


# ------------------------------------------------------------------- staff
def get_staff(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(STAFF_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in.")
    sess = db.get(AuthSession, token_hash(token))
    now = utcnow()
    if not sess or sess.expires_at < now:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    user = db.get(User, sess.user_id)
    if not user or user.account_status != "active":
        raise HTTPException(status_code=401, detail="Account unavailable.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, sess.csrf_token):
            write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username,
                        action="csrf_rejected", outcome="denied", request=request)
            db.commit()
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    sess.last_seen = now
    sess.expires_at = now + timedelta(minutes=config.STAFF_SESSION_TTL_MIN)   # sliding expiry
    request.state.auth_session = sess
    return user


def staff_role(*roles: str):
    def dep(request: Request, user: User = Depends(get_staff), db: Session = Depends(get_db)) -> User:
        if user.role not in roles:
            write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username,
                        action="access_denied_role", record_type="endpoint", record_id=request.url.path,
                        outcome="denied", request=request)
            db.commit()
            raise HTTPException(status_code=403, detail="Your role is not permitted to do this.")
        return user
    return dep


def in_scope(user: User, person: Person) -> bool:
    if user.role == "admin":
        return False                       # admins never get case-level clinical data
    scope = (user.group_scope or "").strip()
    if scope == "*":
        return True
    return person.group_code in {s.strip() for s in scope.split(",") if s.strip()}


def load_person_in_scope(db: Session, user: User, person_id: str, request: Request) -> Person:
    person = db.get(Person, person_id.strip().upper())
    if not person or not in_scope(user, person):
        # identical response for "missing" and "out of scope": no record enumeration
        write_audit(db, actor_type="staff", user_id=user.user_id, actor_ref=user.username,
                    action="access_denied_scope", record_type="person", record_id=person_id[:30],
                    outcome="denied", request=request)
        db.commit()
        raise HTTPException(status_code=404, detail="Case not found in your authorised scope.")
    return person


# ------------------------------------------------------------------- kiosk
def get_kiosk(request: Request, db: Session = Depends(get_db)) -> KioskSession:
    token = request.cookies.get(KIOSK_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please enter your ID to start.")
    ks = db.get(KioskSession, token_hash(token))
    now = utcnow()
    if not ks or ks.expires_at < now:
        raise HTTPException(status_code=401, detail="Your session timed out. Please start again.")
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not sent or not hmac.compare_digest(sent, ks.csrf_token):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token.")
    ks.expires_at = now + timedelta(minutes=config.KIOSK_SESSION_TTL_MIN)
    return ks


# ---------------------------------------------------------------- non-throwing peeks (for /api/session)
def peek_staff(request: Request, db: Session):
    token = request.cookies.get(STAFF_COOKIE)
    if not token:
        return None
    sess = db.get(AuthSession, token_hash(token))
    if not sess or sess.expires_at < utcnow():
        return None
    user = db.get(User, sess.user_id)
    return (user, sess) if user and user.account_status == "active" else None


def peek_kiosk(request: Request, db: Session):
    token = request.cookies.get(KIOSK_COOKIE)
    if not token:
        return None
    ks = db.get(KioskSession, token_hash(token))
    return ks if ks and ks.expires_at >= utcnow() else None
