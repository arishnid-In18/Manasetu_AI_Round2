# Voice assistant (Tamil · Hindi · English)

Built for people who find reading or touch-typing hard, including people in custody. Works in both profiles (`correctional` and `atrocity_victims`).
Admin can switch it off: Administration → Screening schedule → `voice_assistant_enabled` (1/0).

## What it does
| Where | Voice behaviour |
|---|---|
| Yes / Not now / No | "Read this page aloud" and "Answer by voice" (say *yes*, *not now*, *no*; the choice is read back and must be confirmed) |
| Consent | "Read this page aloud" (text-to-speech only). Consent is **never given by voice**: the three acknowledgements are ticked by touch |
| Questionnaire | Opt-in per session. Reads each question and numbered options, listens, **reads the heard answer back and asks yes/no** before saving. Commands: *repeat · skip · back · next · stop* (Tamil/Hindi equivalents) |
| Sensitive item (Q8) | **Never answered aloud** (others may hear). The assistant tells the person to use the screen |
| Review / Submit | Voice reads a reminder, then **stops**. Submitting is always by touch |
Touch always works; tapping an answer while voice is on cancels listening. Answers are stored with `input_mode = voice|touch` so staff can see data quality.

## Privacy design
* Manasetu **never records, uploads or stores audio or transcripts**. The server only receives the final answer value and an audit event (`voice_assistant_started/stopped/permission_denied`).
* Opt-in notice (3 languages) says the **browser may send audio to its own speech service** and that people nearby can hear.

## Requirements and limits — read before deploying in a prison
1. **Speech recognition uses the browser's engine (Chrome / Edge).** It normally needs an **internet connection** to the browser vendor's speech service. Many prison networks are isolated, so voice *answers* may not work there.
   Production fix: an **on-premise/offline recogniser** (e.g. a local Whisper/Vosk service behind the same `listen()` interface in `static/voice.js`). Not built.
2. **Spoken prompts need an installed voice** for the language (Windows: Settings → Time & language → Speech). The app warns when none is found.
3. Tamil/Hindi recognition accuracy varies by accent, noise and device. That is why every answer is **confirmed aloud**, and why the vocabulary list is demonstration-level.
4. Shared, noisy halls are a poor setting: use headphones or a private booth.
5. Not tested with real microphones or real Tamil/Hindi voices (see below).

## How it was tested
* `node --test tests/` — 11 unit tests of the answer/command/yes-no/intent matcher in all three languages (found and fixed two real bugs: Tamil *ஒருபோதும்* "never" was triggering *stop*; digit conversion).
* Playwright/Chromium with a **scripted fake microphone and speech engine**: full Tamil flow (number, label, skip, correction after "no", repeat), Q8 never listened to, Hindi answer + "stop", mic denied, unsupported browser, voice "not now". Stored `input_mode` verified in the database.
* **Not tested:** a real microphone, real Chrome speech recognition, installed Tamil/Hindi OS voices.
