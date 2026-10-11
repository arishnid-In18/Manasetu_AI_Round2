# MANASETU AI — Multilingual Mental-Health Early-Warning & Support Prioritisation (prototype)

*Bridging Minds to Mental Health Support. AI detects the signal. Humans understand the person.*

**Synthetic data only. Not a medical device. Not clinically validated.** The questionnaire (`DEMO-WB-1`) and every threshold are placeholders.

## Which population?
SIH26094 concerns **victims/complainants under the PoA Act (NHAA 14566 / Integrated Portal)**. The engine is profile-driven:

| Profile | Run | People (50 synthetic) |
|---|---|---|
| `atrocity_victims` (default, matches SIH26094) | `.\run.ps1` | `CMP1001–CMP1050`, Districts A/B/C |
| `correctional` (prison adaptation) | `.\run.ps1 -Profile correctional` | `INM1001–INM1050`, Blocks A/B/C |

Each profile has its own databases under `data/<profile>/`. Registry also holds `…1051/1052` (unavailable records) to demo the error path.

## Run (Windows PowerShell, Python 3.10+)
```powershell
cd manasetu_ai
.\run.ps1            # creates .venv, installs, seeds on first start, opens http://127.0.0.1:8000
.\run.ps1 -Test      # Python tests (+ Node voice-matcher tests if Node is installed)
.\run.ps1 -Reset     # re-seed
```
Demo accounts: `officer1` (blocks/districts A,B), `officer2` (C), `clinician1`, `clinician2`, `admin1` — passwords `Officer#2026`, `Clinician#2026`, `Admin#2026`
(override all with `MANASETU_SEED_PASSWORD`). API docs: `/docs`.

## What it demonstrates
Mock identity connector (separate DB) · Yes / Not now / No gate · language + consent (staff-assist option) · 8-question accessible check-in with save/resume, skip, read-aloud ·
never scores partials · personal baseline (median of first 3 valid) · trend / sudden / persistent change · safety-item rule · explainable four-level priority with data-sufficiency (no probabilities) ·
control-room dashboard · urgent alerts cleared only by human review · referral state machine · follow-ups · recovery-neutral wording · role + scope enforcement · hash-chained audit log.

## Layout
`app/` (analysis, services, security, audit, routers, seed, connectors) · `static/` (UI, vendored Chart.js) · `tests/` · `docs/` (ARCHITECTURE, DEMO_SCRIPT, RESEARCH_NOTES).
Spec's `inmates` table = `persons` here (profile-neutral).

## Languages: Tamil · Hindi · English
Every kiosk screen, the consent text, the 8 questions, the answer options and all **spoken** prompts exist in all three languages. The UI language follows the person's
registry preference and can be changed at any time (selector in the header). Wording is **demonstration-level, not professionally translated**.

## Voice assistant
Spoken questions, voice answers with read-back confirmation, voice commands, voice Yes / Not now / No, read-aloud for consent. The sensitive item and final submission are always by touch.
Details, privacy design and **limits for prison networks** (browser speech recognition normally needs internet): `docs/VOICE.md`.

## Instruments
`MANASETU_INSTRUMENT=DEMO-WB-1` (default, placeholder, 3 languages) or `PHQ-9` (published scoring and cut-points, **English only** until official translations are added). See `docs/INSTRUMENTS.md`.
PowerShell: `$env:MANASETU_INSTRUMENT = "PHQ-9"; .\run.ps1 -Reset`. (PHQ-9 mode starts with the 50 people but no demo histories.)

## Tested on
`run.ps1` under PowerShell 7 (Linux). Linux: SQLite **and PostgreSQL 16** (`DATABASE_URL=postgresql+psycopg2://user:pw@host/db`, `pip install psycopg2-binary`; PostgreSQL testing found and fixed a column-length bug SQLite hid).
Chromium (Playwright). Python 79 tests + Node 11 tests. **Not run by the author:** real Windows / Windows PowerShell 5.1, macOS, Firefox, Safari, real microphones, real Tamil/Hindi voices. A GitHub Actions workflow (`.github/workflows/ci.yml`) runs all of these except the microphone for you: see `docs/TESTING.md`.

## Honest limitations
Default instrument is a placeholder (PHQ-9 mode uses published cut-points but is English-only and not validated for this population); Tamil/Hindi wording unreviewed; voice answers need Chrome/Edge + usually internet (see docs/VOICE.md); Not run on real Windows by the author (CI provided); no HTTPS; consent flow needs legal/ethics review
(people in custody or in legal proceedings are not in a position of free choice by default); the SIH brief's Emotion-AI / voice-stress / predictive-ML parts are intentionally not implemented.
