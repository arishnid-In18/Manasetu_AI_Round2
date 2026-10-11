# What is tested, where, and what cannot be tested by code

| Area | Status | How |
|---|---|---|
| Rule engine, scoring, RBAC/scope, CSRF, referrals, audit chain, voice back-end | **Tested** | `pytest` (79 tests) on Linux with SQLite **and** PostgreSQL 16 |
| Voice matcher (Tamil/Hindi/English answers, commands, yes/no, intent) | **Tested** | `node --test` (11 tests) |
| Browser UI (kiosk flow, voice flow with a scripted fake mic, staff, admin, PHQ-9 mode) | **Tested in Chromium** | Playwright |
| `run.ps1` | **Tested under PowerShell 7.4 on Linux**: creates venv, installs requirements from scratch, runs both test suites, starts the server and serves both profiles | |
| Windows 10/11, Windows PowerShell 5.1, macOS, Firefox, WebKit/Safari | **Not run by the author** (no such machine / downloads blocked). **A ready CI does it for you**: push the folder to GitHub and open Actions -> CI (`.github/workflows/ci.yml`: Windows + macOS + Linux x Python 3.10/3.12, run.ps1 under PowerShell 5.1 and 7, Chromium/Firefox/WebKit smoke test). Or locally: `.\run.ps1 -Test`, `python tests\browser_smoke.py firefox` |
| Real microphone + real Chrome speech recognition + installed Tamil/Hindi voices | **Cannot be tested by code**: needs a person speaking Tamil/Hindi on a real device. Use the checklist below |
| Clinical validity of thresholds / the instrument for victims or people in custody | **Cannot be tested by software.** Needs clinicians and outcome data (see docs/INSTRUMENTS.md) |

## Real-device voice checklist (15 minutes, Chrome or Edge, with internet)
1. Install the Tamil and Hindi OS voices. 2. For each language: say every option by name and by number, say *repeat / skip / back / stop*, answer *no* to a read-back, stay silent.
3. Try with background noise and with two different speakers. 4. Count how often the heard answer was wrong *before* confirmation. 5. Confirm Q8/Q9 is never listened to.
Record results; expand the word lists in `static/voice.js` from what real speakers actually say.
