# Architecture

```
Browser (vanilla JS, Chart.js vendored, no CDN)           Kiosk: person bound to a server-side kiosk session
   │  fetch /api  (httpOnly SameSite=Strict cookies + X-CSRF-Token)
   ▼
FastAPI  ── routers: kiosk | staff (officer, clinician) | admin
   │          security.py  (PBKDF2, sessions, CSRF, role + group-scope checks)
   │          audit.py     (HMAC hash-chained audit log)
   │          services.py  (workflow)      analysis.py (pure rule engine)
   │          instruments.py (instrument + consent registry)
   ├── SQLAlchemy ──► SQLite  manasetu.db   (wellbeing data)        ← PostgreSQL via DATABASE_URL (untested)
   └── IdentityConnector ──► MockRegistryConnector ──► mock_registry.db   (identity only, SEPARATE file)
```

## Pipeline
completed assessment → validation → instrument scoring (never scores partials; skipped ≠ 0) → valid-history selection
(same instrument + major version, after any clinician baseline reset) → baseline (median of first 3 valid, needs ≥3 prior)
→ trend (slope, sudden, persistent) → absolute-threshold + safety-item rules → priority category → explanation + data
sufficiency → professional review → referral / follow-up.

All thresholds live in `analysis.RULESET` (version `rules-v0.1-demo`) and are **placeholders**. Output is one of four workflow
categories, never a diagnosis or a probability. Event context is displayed but never used in scoring or called a cause.

## Production integration (not built)
Implement `IdentityConnector` against an approved e-Prisons / NHAA-Integrated-Portal interface under a data-sharing
agreement with authentication and authorisation, mapping only: id, name, group, language, status. Keep identity and wellbeing stores separate.

## Roles
| | Kiosk person | Officer | Clinician | Admin |
|---|---|---|---|---|
| Own check-in | ✔ | | | |
| Dashboard / priority, trend, evidence | | ✔ (scope) | ✔ (scope) | aggregates only |
| Item-level dimensions, notes, baseline reset | | ✘ | ✔ | ✘ |
| Referral beyond "recommended" | | ✘ | ✔ | ✘ |
| Users, config, audit log, health | | | | ✔ |

## Known limitations
Placeholder instrument and thresholds; unreviewed Tamil/Hindi; voice answers rely on the browser's speech service (see VOICE.md); in-memory lookup throttle; no HTTPS/reverse proxy;
SQLite and PostgreSQL 16 tested on Linux only; no retention job (policy must be set by the deploying organisation); single-process audit chain.
