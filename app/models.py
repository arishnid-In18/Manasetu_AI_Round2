"""Database models.

Mapping to the specification's table list:
  inmates              -> persons          (profile-neutral: inmate / complainant)
  users                -> users
  screening_sessions   -> screening_sessions
  screening_responses  -> screening_responses
  assessment_results   -> assessment_results
  trend_analysis       -> trend_analysis
  support_recommendations -> support_recommendations
  referrals            -> referrals
  audit_logs           -> audit_logs
Additional tables support consent, human review, follow-ups, clinician notes,
authorised case events, urgent notifications, sessions and configuration.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, CheckConstraint, Index, text,
)
from sqlalchemy.orm import relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


SESSION_STATUSES = ("in_progress", "completed", "partial", "declined", "postponed", "failed")
PRIORITIES = ("Routine Monitoring", "Monitor", "Human Follow-Up Recommended", "Urgent Human Review")
REFERRAL_STATUSES = ("recommended", "accepted", "appointment_scheduled",
                     "appointment_completed", "follow_up_pending", "closed")


class Person(Base):
    __tablename__ = "persons"
    person_id = Column(String(20), primary_key=True)
    display_name = Column(String(120), nullable=False)
    photo_ref = Column(String(120))
    group_code = Column(String(10), nullable=False, index=True)       # block / district
    language_pref = Column(String(10), nullable=False, default="en")
    external_ref = Column(String(60), nullable=False)                 # id in the source system
    record_status = Column(String(20), nullable=False, default="active")
    assigned_professional_id = Column(String(30), ForeignKey("users.user_id"))
    baseline_anchor_date = Column(DateTime)                           # set by a clinician baseline reset
    is_synthetic = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class User(Base):
    __tablename__ = "users"
    user_id = Column(String(30), primary_key=True, default=lambda: new_id("USR"))
    username = Column(String(60), nullable=False, unique=True)
    display_name = Column(String(120), nullable=False)
    password_hash = Column(String(300), nullable=False)
    role = Column(String(20), nullable=False)                         # officer | clinician | admin
    account_status = Column(String(20), nullable=False, default="active")   # active | disabled
    group_scope = Column(String(80), nullable=False, default="*")     # "A,B" or "*"
    failed_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (CheckConstraint("role IN ('officer','clinician','admin')", name="ck_user_role"),)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(String(30), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    csrf_token = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False, default=utcnow)


class KioskSession(Base):
    __tablename__ = "kiosk_sessions"
    token_hash = Column(String(64), primary_key=True)
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    csrf_token = Column(String(64), nullable=False)
    language = Column(String(10), nullable=False, default="en")
    consent_id = Column(String(30))
    screening_id = Column(String(30))
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)


class Consent(Base):
    __tablename__ = "consents"
    consent_id = Column(String(30), primary_key=True, default=lambda: new_id("CON"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    consent_version = Column(String(40), nullable=False)
    language = Column(String(10), nullable=False)
    acknowledged_json = Column(Text, nullable=False, default="[]")
    staff_assistance_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ScreeningSession(Base):
    __tablename__ = "screening_sessions"
    screening_id = Column(String(30), primary_key=True, default=lambda: new_id("SCR"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    instrument_id = Column(String(40), nullable=False)
    instrument_version = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime)
    language = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="in_progress")
    consent_id = Column(String(30), ForeignKey("consents.consent_id"))
    __table_args__ = (
        CheckConstraint("status IN ('in_progress','completed','partial','declined','postponed','failed')",
                        name="ck_session_status"),
    )


# At most one open (in-progress) session per person -> prevents duplicate sessions.
Index("uq_one_open_session", ScreeningSession.person_id, unique=True,
      sqlite_where=text("status = 'in_progress'"), postgresql_where=text("status = 'in_progress'"))


class ScreeningResponse(Base):
    __tablename__ = "screening_responses"
    response_id = Column(String(30), primary_key=True, default=lambda: new_id("RSP"))
    screening_id = Column(String(30), ForeignKey("screening_sessions.screening_id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String(20), nullable=False)
    value = Column(Integer)                       # NULL when skipped -- never silently 0
    skipped = Column(Boolean, nullable=False, default=False)
    input_mode = Column(String(10), nullable=False, default="touch", server_default="touch")   # touch | voice
    responded_at = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (UniqueConstraint("screening_id", "question_id", name="uq_response_per_question"),)


class AssessmentResult(Base):
    __tablename__ = "assessment_results"
    result_id = Column(String(30), primary_key=True, default=lambda: new_id("RES"))
    screening_id = Column(String(30), ForeignKey("screening_sessions.screening_id", ondelete="CASCADE"),
                          nullable=False, unique=True)
    score = Column(Integer)                       # NULL unless fully answered per approved scoring rules
    scoring_status = Column(String(30), nullable=False)       # scored | not_scored_incomplete
    items_answered = Column(Integer, nullable=False)
    items_total = Column(Integer, nullable=False)
    completeness = Column(Float, nullable=False)
    safety_item_value = Column(Integer)
    analysis_version = Column(String(40), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class TrendAnalysis(Base):
    __tablename__ = "trend_analysis"
    analysis_id = Column(String(30), primary_key=True, default=lambda: new_id("TRN"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    screening_id = Column(String(30), ForeignKey("screening_sessions.screening_id", ondelete="CASCADE"),
                          nullable=False, unique=True)
    analysis_date = Column(DateTime, nullable=False, default=utcnow)
    baseline_status = Column(String(30), nullable=False)      # established | not_established
    baseline_value = Column(Float)
    current_value = Column(Float)
    change_from_baseline = Column(Float)
    trend_category = Column(String(40), nullable=False)
    data_sufficiency = Column(String(300), nullable=False)
    valid_observations = Column(Integer, nullable=False)
    evidence_json = Column(Text, nullable=False, default="{}")


class SupportRecommendation(Base):
    __tablename__ = "support_recommendations"
    recommendation_id = Column(String(30), primary_key=True, default=lambda: new_id("REC"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    screening_id = Column(String(30), ForeignKey("screening_sessions.screening_id", ondelete="CASCADE"),
                          nullable=False, unique=True)
    priority_category = Column(String(40), nullable=False)
    explanation = Column(Text, nullable=False)
    reasons_json = Column(Text, nullable=False, default="[]")
    rule_set_version = Column(String(40), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    review_status = Column(String(20), nullable=False, default="pending")   # pending | reviewed
    __table_args__ = (
        CheckConstraint("priority_category IN ('Routine Monitoring','Monitor','Human Follow-Up Recommended',"
                        "'Urgent Human Review')", name="ck_priority"),
    )


class HumanReview(Base):
    __tablename__ = "human_reviews"
    review_id = Column(String(30), primary_key=True, default=lambda: new_id("HRV"))
    recommendation_id = Column(String(30), ForeignKey("support_recommendations.recommendation_id", ondelete="CASCADE"),
                               nullable=False, index=True)
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    reviewer_id = Column(String(30), ForeignKey("users.user_id"), nullable=False)
    decision = Column(String(40), nullable=False)
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class Referral(Base):
    __tablename__ = "referrals"
    referral_id = Column(String(30), primary_key=True, default=lambda: new_id("REF"))
    recommendation_id = Column(String(30), ForeignKey("support_recommendations.recommendation_id", ondelete="CASCADE"),
                               nullable=False, index=True)
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    screening_id = Column(String(30), ForeignKey("screening_sessions.screening_id"), nullable=False)
    destination = Column(String(40), nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="recommended")
    follow_up_date = Column(DateTime)
    appointment_at = Column(DateTime)
    outcome_status = Column(String(60))
    created_by = Column(String(30), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow)
    __table_args__ = (
        CheckConstraint("status IN ('recommended','accepted','appointment_scheduled','appointment_completed',"
                        "'follow_up_pending','closed')", name="ck_referral_status"),
    )


class FollowUp(Base):
    __tablename__ = "follow_ups"
    follow_up_id = Column(String(30), primary_key=True, default=lambda: new_id("FUP"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    recommendation_id = Column(String(30), ForeignKey("support_recommendations.recommendation_id"))
    referral_id = Column(String(30), ForeignKey("referrals.referral_id"))
    scheduled_for = Column(DateTime, nullable=False)
    status = Column(String(20), nullable=False, default="pending")    # pending | completed | cancelled
    completed_at = Column(DateTime)
    note = Column(Text)
    created_by = Column(String(30), ForeignKey("users.user_id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ClinicalNote(Base):
    """Clinician-only. Officers and admins can never read these."""
    __tablename__ = "clinical_notes"
    note_id = Column(String(30), primary_key=True, default=lambda: new_id("CLN"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(String(30), ForeignKey("users.user_id"), nullable=False)
    kind = Column(String(20), nullable=False, default="note")         # note | support_plan
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class CaseEvent(Base):
    """Authorised context events from the (simulated) source system. Shown for context
    only; never used in scoring and never described as a cause."""
    __tablename__ = "case_events"
    event_id = Column(String(30), primary_key=True, default=lambda: new_id("EVT"))
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True)
    event_date = Column(DateTime, nullable=False)
    label = Column(String(160), nullable=False)
    source = Column(String(80), nullable=False, default="simulated source system")


class Notification(Base):
    __tablename__ = "notifications"
    notification_id = Column(String(30), primary_key=True, default=lambda: new_id("NTF"))
    kind = Column(String(30), nullable=False)                         # urgent_review | consent_assistance
    person_id = Column(String(20), ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False)
    recommendation_id = Column(String(30))
    message = Column(String(300), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    acknowledged_by = Column(String(30))
    acknowledged_at = Column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, nullable=False, default=utcnow)
    actor_type = Column(String(10), nullable=False)                   # staff | kiosk | system
    user_id = Column(String(30))                                      # no FK: logs outlive accounts
    actor_ref = Column(String(60))                                    # username / person_id
    action = Column(String(60), nullable=False)
    record_type = Column(String(40))
    record_id = Column(String(60))
    outcome = Column(String(12), nullable=False, default="success")  # success | denied | failure
    ip = Column(String(60))
    user_agent = Column(String(200))
    details_json = Column(Text, nullable=False, default="{}")
    prev_hash = Column(String(64), nullable=False)
    hash = Column(String(64), nullable=False)


class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String(60), primary_key=True)
    value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=utcnow)
