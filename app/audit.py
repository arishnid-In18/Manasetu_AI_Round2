"""Tamper-evident audit log: each row's hash covers the previous row's hash (HMAC chain)."""
import hashlib
import hmac
import json
import secrets
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import config
from .models import AuditLog, utcnow


def _key() -> bytes:
    if not config.SECRET_FILE.exists():
        config.SECRET_FILE.write_text(secrets.token_hex(32), encoding="utf-8")
    return config.SECRET_FILE.read_text(encoding="utf-8").strip().encode()


def _digest(prev: str, row: dict) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":"))
    return hmac.new(_key(), (prev + payload).encode(), hashlib.sha256).hexdigest()


def _row_dict(r: AuditLog) -> dict:
    return {"ts": r.ts.isoformat(), "actor_type": r.actor_type, "user_id": r.user_id, "actor_ref": r.actor_ref,
            "action": r.action, "record_type": r.record_type, "record_id": r.record_id, "outcome": r.outcome,
            "ip": r.ip, "ua": r.user_agent, "details": r.details_json}


def write_audit(db: Session, *, actor_type: str, action: str, user_id: Optional[str] = None,
                actor_ref: Optional[str] = None, record_type: Optional[str] = None,
                record_id: Optional[str] = None, outcome: str = "success",
                request: Optional[Request] = None, details: Optional[dict] = None) -> AuditLog:
    last = db.query(AuditLog).order_by(AuditLog.audit_id.desc()).first()
    prev = last.hash if last else "GENESIS"
    row = AuditLog(
        ts=utcnow(), actor_type=actor_type, user_id=user_id, actor_ref=(actor_ref or None) and actor_ref[:60], action=action[:60],
        record_type=(record_type or None) and record_type[:40], record_id=(record_id or None) and record_id[:60], outcome=outcome,
        ip=(request.client.host if request and request.client else None),
        user_agent=((request.headers.get("user-agent") or "")[:200] if request else None),
        details_json=json.dumps(details or {}, sort_keys=True), prev_hash=prev, hash="",
    )
    row.hash = _digest(prev, _row_dict(row))
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> dict:
    prev = "GENESIS"
    checked = 0
    for r in db.query(AuditLog).order_by(AuditLog.audit_id.asc()).yield_per(500):
        if r.prev_hash != prev or r.hash != _digest(prev, _row_dict(r)):
            return {"valid": False, "checked": checked, "first_invalid_audit_id": r.audit_id}
        prev = r.hash
        checked += 1
    return {"valid": True, "checked": checked, "first_invalid_audit_id": None}
