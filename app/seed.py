"""Synthetic demonstration data (50 fictional people). NOTHING here is real.

Every archetype has a hand-specified expected output (EXPECTED below) so the engine's
behaviour is testable. Synthetic examples are NOT evidence of clinical accuracy.

CLI:  python -m app.seed --reset        (wipe + reseed this profile's databases)
"""
import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from . import config, instruments, services
from .audit import write_audit
from .connectors.mock_registry import get_connector
from .db import Base, SessionLocal, engine
from .models import (CaseEvent, Consent, Person, ScreeningSession, SupportRecommendation, User, utcnow)
from .profiles import get_profile
from .security import hash_password

FIRST = ["Ravi", "Suresh", "Manoj", "Anil", "Arjun", "Vikram", "Deepak", "Sanjay", "Praveen", "Ashok", "Karthik",
         "Rajesh", "Mohan", "Naveen", "Ramesh", "Lakshmi", "Meena", "Priya", "Kavitha", "Sunita", "Anita", "Geetha",
         "Revathi", "Pooja", "Neha", "Sandhya", "Divya", "Radha", "Savitri", "Kamala", "Murugan", "Senthil", "Balaji",
         "Dinesh", "Prakash", "Harish", "Mahesh", "Ganesh", "Vijay", "Sathish", "Kiran", "Rohit", "Amit", "Sumit",
         "Rakesh", "Mukesh", "Jyoti", "Seema", "Usha", "Bharathi"]
LAST = ["Kumar", "Pillai", "Verma", "Yadav", "Nair", "Singh", "Rathore", "Gupta", "Menon", "Chauhan", "Raja", "Iyer",
        "Das", "Reddy", "Sharma", "Devi", "Selvam", "Murthy", "Naidu", "Patel", "Joshi", "Mishra", "Rao", "Bhat",
        "Kulkarni", "Shetty", "Pandey", "Tiwari", "Banerjee", "Mukherjee", "Chatterjee", "Ghosh", "Sen", "Dutta",
        "Bose", "Thakur", "Kaur", "Gill", "Sandhu", "Khan", "Ansari", "Siddiqui", "Fernandes", "Lobo", "Thomas",
        "George", "Mathew", "Varghese", "Paul", "Jacob"]

# index (1..50) -> archetype
PLAN = {1: "stable_low", 2: "persistent_change", 3: "urgent_safety", 4: "stable_low", 5: "improving",
        6: "gradual_increase", 7: "insufficient_none", 8: "stable_moderate", 9: "sudden_change", 10: "stable_low",
        11: "insufficient_high", 12: "improving", 13: "high_stays_high", 14: "stable_low", 15: "postponed_latest",
        16: "persistent_change", 17: "gradual_increase", 18: "stable_low", 19: "urgent_persistent_high",
        20: "insufficient_one", 21: "demo_live", 22: "stable_moderate", 23: "persistent_change", 24: "improving",
        25: "incomplete_latest_partial", 26: "stable_low", 27: "sudden_change", 28: "insufficient_two",
        29: "gradual_increase", 30: "stable_low", 31: "declined_once", 32: "persistent_change", 33: "improving",
        34: "stable_low", 35: "high_stays_high", 36: "insufficient_mod", 37: "stable_low", 38: "incomplete_mixed",
        39: "gradual_increase", 40: "persistent_change", 41: "improving", 42: "stable_moderate",
        43: "declined_twice", 44: "sudden_change", 45: "stable_low", 46: "gradual_increase", 47: "high_stays_high",
        48: "insufficient_two", 49: "incomplete_mixed2", 50: "improving"}

R, M, F, U = "Routine Monitoring", "Monitor", "Human Follow-Up Recommended", "Urgent Human Review"
# archetype -> (expected priority of the LATEST recommendation, expected latest trend, description)
EXPECTED = {
    "stable_low": (R, "Stable", "Small fluctuations around a low personal baseline."),
    "stable_moderate": (R, "Stable", "Steady moderate scores below the monitoring threshold."),
    "improving": (R, "Improving", "Scores falling across assessments."),
    "gradual_increase": (M, "Increasing difficulty", "Gradual rise; +3 above baseline; not yet persistent."),
    "persistent_change": (F, "Persistent change", "Jump above baseline that persists for 3 assessments."),
    "sudden_change": (F, "Sudden change", "Large single-assessment rise versus the previous one."),
    "high_stays_high": (F, "Stable", "Baseline already high; high current result is NOT dismissed."),
    "urgent_safety": (U, "Stable", "Safety-item response meets the configured urgent rule."),
    "urgent_persistent_high": (U, "Persistent change", "Persistent change AND high score (demonstration rule)."),
    "insufficient_none": (None, None, "No assessment yet: first check-in due."),
    "insufficient_one": (R, "Insufficient information", "One valid assessment: baseline not established."),
    "insufficient_two": (R, "Insufficient information", "Two valid assessments: baseline not established."),
    "insufficient_high": (F, "Insufficient information", "Single HIGH result still reviewed despite no baseline."),
    "insufficient_mod": (M, "Insufficient information", "Single moderately high result -> monitor."),
    "incomplete_latest_partial": (R, "Stable", "Latest attempt incomplete: not scored; excluded from analysis."),
    "incomplete_mixed": (R, "Stable", "A partial assessment is excluded; remaining valid history used."),
    "incomplete_mixed2": (R, "Stable", "Two partial assessments excluded."),
    "postponed_latest": (R, "Stable", "Latest check-in postponed: no inference from postponement."),
    "declined_once": (R, "Stable", "Latest check-in declined: no score or distress inferred."),
    "declined_twice": (R, "Stable", "Two consecutive declines: administrative welfare-check flag only."),
    "demo_live": (R, "Stable", "Spec example history 4,4,5,6 -> complete a live check-in to see the comparison."),
}
SEQUENCES_FIXED = {
    "urgent_safety": [6, 7, 6, 7, 6, 9], "urgent_persistent_high": [18, 19, 19, 24, 25, 26],
    "insufficient_one": [5], "insufficient_two": [5, 6], "insufficient_high": [21], "insufficient_mod": [15],
    "insufficient_none": [], "demo_live": [4, 4, 5, 6],
    "incomplete_latest_partial": [6, 6, 5, "P"], "incomplete_mixed": [5, 5, 6, "P", 6],
    "incomplete_mixed2": [4, 5, "P", 5, "P", 5],
    "postponed_latest": [5, 5, 6, 5, 6, "POSTPONED"], "declined_once": [5, 6, 5, 5, 6, "DECLINED"],
    "declined_twice": [5, 5, 6, 5, 6, "DECLINED", "DECLINED"],
}

EVENT_LABELS = {
    "atrocity_victims": ["Court hearing", "Case stage update", "Relief / compensation update", "Protection review meeting"],
    "correctional": ["Court hearing", "Block transfer", "Family visit", "Parole / review board"],
}


def sequence_for(arch: str, idx: int) -> list:
    if arch in SEQUENCES_FIXED:
        return list(SEQUENCES_FIXED[arch])
    rng = random.Random(idx * 97 + 13)
    if arch == "stable_low":
        base = rng.choice([4, 5, 5, 6])
        return [max(1, base + rng.choice([-1, 0, 1])) for _ in range(6)]
    if arch == "stable_moderate":
        base = rng.choice([11, 12])
        return [base + rng.choice([-1, 0, 1]) for _ in range(6)]
    if arch == "improving":
        s = rng.choice([14, 15, 16])
        return [s, s - 1, s - 3, s - 5, s - 7, s - 8]
    if arch == "gradual_increase":
        s = rng.choice([3, 4, 5])
        return [s, s + 1, s + 1, s + 2, s + 3, s + 4]
    if arch == "persistent_change":
        b = rng.choice([3, 4, 5])
        return [b, b, b + 1, b + 5, b + 6, b + 7]
    if arch == "sudden_change":
        b = rng.choice([4, 5, 6])
        return [b, b, b + 1, b, b + 1, b + 9]
    if arch == "high_stays_high":
        b = rng.choice([19, 20])
        return [b, b + 1, b, b + 1, b + 2, b + 2]
    raise KeyError(arch)


def distribute(total: int, rng: random.Random, safety_value: int = 0, favour: Optional[List[int]] = None) -> List[int]:
    items, remaining = [0] * 7, total - safety_value
    assert 0 <= remaining <= 28, (total, safety_value)
    while remaining > 0:
        i = rng.choice(favour) if favour and rng.random() < 0.6 else rng.randrange(7)
        if items[i] < 4:
            items[i] += 1
            remaining -= 1
    return items + [safety_value]


# --------------------------------------------------------------------------
def build_people(profile: dict) -> List[dict]:
    rng = random.Random(2026)
    prefix = profile["id_prefix"]
    people = []
    for i in range(1, 51):
        name = f"{FIRST[i - 1]} {LAST[(i * 7) % 50]}"
        group = "A" if i <= 17 else ("B" if i <= 34 else "C")
        lang = rng.choices(["ta", "hi", "en"], weights=[40, 35, 25])[0]
        if i == 21:
            name, lang = "Ravi Kumar", "ta"      # the example record in the specification
        people.append({"idx": i, "person_id": f"{prefix}{1000 + i}", "external_ref": f"SIM-{prefix}-{100000 + i * 37}",
                       "display_name": name, "group_code": group, "language_pref": lang, "record_status": "active",
                       "context_note": None, "archetype": PLAN[i]})
    return people


def reset_databases():
    if str(config.DATABASE_URL).startswith("sqlite"):
        engine.dispose()
        path = config.DATABASE_URL.replace("sqlite:///", "")
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    else:
        Base.metadata.drop_all(engine)
    if config.MOCK_REGISTRY_PATH.exists():
        config.MOCK_REGISTRY_PATH.unlink()


def seed(db: Session, password: Optional[str] = None, now: Optional[datetime] = None) -> dict:
    now = now or utcnow()
    profile = get_profile(config.PROFILE)
    Base.metadata.create_all(engine)
    pw = password or os.environ.get("MANASETU_SEED_PASSWORD")

    # ---- staff accounts (DEMO passwords; override with MANASETU_SEED_PASSWORD)
    accounts = [
        ("officer1", "Officer #1 (screening officer)", "officer", "A,B", pw or "Officer#2026"),
        ("officer2", "Officer #2 (screening officer)", "officer", "C", pw or "Officer#2026"),
        ("clinician1", "Dr. Meera Iyer (clinical psychologist)", "clinician", "*", pw or "Clinician#2026"),
        ("clinician2", "Dr. Arvind Rao (psychiatrist)", "clinician", "*", pw or "Clinician#2026"),
        ("admin1", "System administrator", "admin", "*", pw or "Admin#2026"),
    ]
    users: Dict[str, User] = {}
    for uname, dname, role, scope, passwd in accounts:
        u = User(username=uname, display_name=dname, role=role, group_scope=scope, password_hash=hash_password(passwd))
        db.add(u)
        users[uname] = u
    db.flush()

    people = build_people(profile)
    # ---- mock registry (separate DB) incl. two UNAVAILABLE records to demo the error path
    registry_people = [{k: p[k] for k in ("person_id", "external_ref", "display_name", "group_code", "language_pref",
                                          "record_status", "context_note")} for p in people]
    pre = profile["id_prefix"]
    registry_people += [
        {"person_id": f"{pre}1051", "external_ref": f"SIM-{pre}-199951", "display_name": "Unavailable Record A", "group_code": "A",
         "language_pref": "en", "record_status": "released" if pre == "INM" else "closed", "context_note": None},
        {"person_id": f"{pre}1052", "external_ref": f"SIM-{pre}-199952", "display_name": "Unavailable Record B", "group_code": "B",
         "language_pref": "en", "record_status": "transferred", "context_note": None},
    ]
    registry_events: List[dict] = []

    # ---- local person rows (as if synced from the registry)
    for p in people:
        db.add(Person(person_id=p["person_id"], display_name=p["display_name"], photo_ref=p["person_id"].lower(),
                      group_code=p["group_code"], language_pref=p["language_pref"], external_ref=p["external_ref"],
                      record_status="active", is_synthetic=True))
    db.flush()

    labels = EVENT_LABELS[config.PROFILE]
    manifest: List[dict] = []
    ev_n = 0

    for p in people:
        idx, arch, pid = p["idx"], p["archetype"], p["person_id"]
        person = db.get(Person, pid)
        seq = sequence_for(arch, idx) if instruments.ACTIVE_INSTRUMENT == "DEMO-WB-1" else []   # demo histories are on the 0-32 demo scale
        rng = random.Random(idx * 7919)
        consent = Consent(person_id=pid, consent_version=instruments.CONSENT_VERSION, language=p["language_pref"],
                          acknowledged_json=json.dumps(["a1", "a2", "a3"]), staff_assistance_requested=False,
                          created_at=now - timedelta(days=120))
        db.add(consent)
        db.flush()

        n_att = len(seq)
        if arch.startswith("urgent"):
            last_offset = 1 if arch == "urgent_safety" else 2
        elif arch == "demo_live":
            last_offset = 15
        elif arch in ("postponed_latest",):
            last_offset = 1
        elif arch.startswith("declined"):
            last_offset = 2
        elif idx % 6 == 0:
            last_offset = rng.randint(16, 24)            # some people are due / overdue
        else:
            last_offset = rng.randint(2, 11)

        completed_seen = 0
        first_completed_score = None
        dts: List[datetime] = []
        for j, token in enumerate(seq):
            if arch == "declined_twice" and token == "DECLINED":
                off = last_offset + (7 if j == n_att - 2 else 0)
            else:
                off = last_offset + 14 * (n_att - 1 - j)
            dt = (now - timedelta(days=off)).replace(hour=10, minute=30 + rng.randint(0, 25), second=0, microsecond=0)
            dts.append(dt)
            if token in ("POSTPONED", "DECLINED"):
                services.record_attempt(db, person, "postponed" if token == "POSTPONED" else "declined",
                                        p["language_pref"], consent.consent_id, now=dt)
                continue
            inst = instruments.get_instrument()
            s = ScreeningSession(person_id=pid, instrument_id=inst["id"], instrument_version=inst["version"],
                                 started_at=dt - timedelta(minutes=7), language=p["language_pref"],
                                 status="in_progress", consent_id=consent.consent_id)
            db.add(s)
            db.flush()
            if token == "P":                                                   # partial: 3 items skipped
                vals = distribute(10, rng)
                for k, q in enumerate(instruments.item_ids(inst)):
                    skipped = k in (2, 5, 6)
                    services.save_response(db, s, q, None if skipped else vals[k], skipped, now=dt)
            else:
                completed_seen += 1
                if first_completed_score is None:
                    first_completed_score = token
                safety_val = 3 if (arch == "urgent_safety" and j == n_att - 1) else 0
                favour = [1, 2, 3] if token > (first_completed_score + 2) else None
                vals = distribute(int(token), rng, safety_val, favour)
                for k, q in enumerate(instruments.item_ids(inst)):
                    services.save_response(db, s, q, vals[k], False, now=dt)
            services.finalize_session(db, s, now=dt, notify=True)
            db.flush()

        # ---- authorised context events (shown for context only)
        if arch in ("persistent_change", "urgent_persistent_high", "sudden_change", "improving") and len(dts) >= 4:
            ev_date = (dts[3] - timedelta(days=5)) if arch != "sudden_change" else (dts[-1] - timedelta(days=4))
            ev_n += 1
            label = labels[(idx + ev_n) % len(labels)]
            registry_events.append({"event_id": f"EVT-{ev_n:04d}", "person_id": pid, "event_date": ev_date.isoformat(), "label": label})

        exp = EXPECTED[arch]
        manifest.append({"person_id": pid, "group": p["group_code"], "archetype": arch, "expected_priority": exp[0],
                         "expected_trend": exp[1], "description": exp[2], "scores": [t for t in seq]})

    # sync events to the local table (cache of the authorised source)
    for e in registry_events:
        db.add(CaseEvent(event_id=e["event_id"], person_id=e["person_id"], event_date=datetime.fromisoformat(e["event_date"]),
                         label=e["label"], source=profile["identity_source"]))
    db.flush()

    if instruments.ACTIVE_INSTRUMENT == "DEMO-WB-1":
        _seed_workflow(db, users, now)
    conn = get_connector()
    conn.load(registry_people, registry_events)

    write_audit(db, actor_type="system", action="seed_completed", details={"people": len(people), "profile": config.PROFILE})
    db.commit()
    (config.DATA_DIR / "seed_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"people": len(people), "manifest": manifest}


def _first_rec(db, pid) -> Optional[SupportRecommendation]:
    return (db.query(SupportRecommendation).filter(SupportRecommendation.person_id == pid)
            .order_by(SupportRecommendation.created_at.asc()).first())


def _last_rec(db, pid) -> Optional[SupportRecommendation]:
    return services.latest_recommendation(db, pid)


def _seed_workflow(db: Session, users: Dict[str, User], now: datetime):
    """Reviews / referrals / follow-ups so the dashboard, pipeline and recovery views are populated."""
    profile = get_profile(config.PROFILE)
    dest_ok = [d["key"] for d in profile["destinations"]]
    cl1, cl2, off1, off2 = users["clinician1"], users["clinician2"], users["officer1"], users["officer2"]
    arch_by_pid = {}
    for p in build_people(profile):
        arch_by_pid[p["person_id"]] = p
    pre = profile["id_prefix"]

    def P(i): return db.get(Person, f"{pre}{1000 + i}")

    def adv(ref, path, appt_days=3, outcome=None, t0=None):
        t = t0 or ref.created_at
        for k, st in enumerate(path):
            t = t + timedelta(days=2)
            services.update_referral_status(db, cl1, ref, st, (t + timedelta(days=appt_days)) if st == "appointment_scheduled" else None,
                                            outcome if st == "closed" else None, now=t)

    # recovery view: improving cases had support earlier, then scores fell
    for i in (5, 12):
        per = P(i)
        rec = _first_rec(db, per.person_id)
        if rec:
            services.record_review(db, cl1, per, rec, "referral_decided", "Discussed support options.", now=rec.created_at + timedelta(days=1))
            ref = services.create_referral(db, cl1, per, rec, "counselling", "Elevated reported difficulty; counselling support offered.",
                                           None, dest_ok, now=rec.created_at + timedelta(days=1))
            adv(ref, ["accepted", "appointment_scheduled", "appointment_completed", "follow_up_pending", "closed"],
                outcome="Support plan completed; continue periodic check-ins")
            per.assigned_professional_id = cl1.user_id

    # persistent change cases at different pipeline stages
    stages = {2: ["accepted", "appointment_scheduled", "appointment_completed", "follow_up_pending"],
              16: [], 23: ["accepted", "appointment_scheduled"], 32: None, 40: None}
    for i, path in stages.items():
        per = P(i)
        rec = _last_rec(db, per.person_id)
        if path is None:
            if i == 40:
                services.record_review(db, off1 if per.group_code in "AB" else off2, per, rec, "monitor_only",
                                       "Reviewed evidence; will re-check at next assessment.", now=rec.created_at + timedelta(hours=5))
                services.schedule_follow_up(db, off1 if per.group_code in "AB" else off2, per,
                                            now + timedelta(days=6), rec, None, "Re-check wellbeing.", now=rec.created_at + timedelta(hours=6))
            continue                                        # 32: left unreviewed (pending queue)
        services.record_review(db, cl2, per, rec, "referral_decided", "Persistent change reviewed; referral agreed.",
                               now=rec.created_at + timedelta(hours=4))
        ref = services.create_referral(db, cl2, per, rec, "psychological" if i == 2 else "counselling",
                                       "Persistent increase from personal baseline across recent assessments.",
                                       now + timedelta(days=10), dest_ok, now=rec.created_at + timedelta(hours=5))
        per.assigned_professional_id = cl2.user_id
        adv(ref, path)
        if i == 2:
            services.schedule_follow_up(db, cl2, per, now + timedelta(days=9), rec, ref, "Post-session check.", now=rec.created_at + timedelta(days=3))

    # sudden-change
    for i in (9, 44):
        per = P(i); rec = _last_rec(db, per.person_id)
        services.record_review(db, cl1, per, rec, "follow_up_planned", "Rapid change noted; follow-up arranged.", now=rec.created_at + timedelta(hours=3))
        ref = services.create_referral(db, cl1, per, rec, "tele_manas", "Offer talk-based support while awaiting assessment.",
                                       None, dest_ok, now=rec.created_at + timedelta(hours=4))
        services.schedule_follow_up(db, cl1, per, (now + timedelta(days=4)) if i == 9 else (rec.created_at + timedelta(days=1)), rec, ref, None, now=rec.created_at + timedelta(hours=4))
    # i == 27 left unreviewed

    # high-stays-high
    per = P(13); rec = _last_rec(db, per.person_id)
    services.record_review(db, cl2, per, rec, "referral_decided", "Persistently elevated; psychological assessment arranged.", now=rec.created_at + timedelta(hours=2))
    ref = services.create_referral(db, cl2, per, rec, "psychological", "Sustained elevated scores.", None, dest_ok, now=rec.created_at + timedelta(hours=3))
    adv(ref, ["accepted", "appointment_scheduled", "appointment_completed", "closed"], outcome="Assessment completed; care plan agreed")
    per = P(47); rec = _last_rec(db, per.person_id)
    services.record_review(db, off2, per, rec, "monitor_only", "Aware; will discuss with clinician at next round.", now=rec.created_at + timedelta(hours=6))

    # urgent: #19 handled; #3 deliberately left unreviewed so the urgent alert is visible on first login
    per = P(19); rec = _last_rec(db, per.person_id)
    services.record_review(db, cl1, per, rec, "escalated_to_protocol", "Escalated per facility clinical protocol.", now=rec.created_at + timedelta(hours=1))
    ref = services.create_referral(db, cl1, per, rec, "psychiatric", "Persistent high scores; clinician assessment requested.",
                                   None, dest_ok, now=rec.created_at + timedelta(hours=2))
    adv(ref, ["accepted", "appointment_scheduled"], appt_days=1)
    per.assigned_professional_id = cl1.user_id
    services.schedule_follow_up(db, cl1, per, now + timedelta(days=2), rec, ref, "Review after psychiatric assessment.", now=rec.created_at + timedelta(hours=2))
    db.flush()


def ensure_seeded():
    """Called at app start: if the database is empty, seed it automatically."""
    Base.metadata.create_all(engine)
    from .db import ensure_columns
    ensure_columns()
    db = SessionLocal()
    try:
        if db.query(Person).count() == 0:
            seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe and reseed the current profile")
    args = ap.parse_args()
    if args.reset:
        reset_databases()
        Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(Person).count() and not args.reset:
            print("Database already seeded. Use --reset to rebuild.")
            sys.exit(0)
        out = seed(db)
        print(f"Seeded profile '{config.PROFILE}': {out['people']} synthetic people.")
    finally:
        db.close()
