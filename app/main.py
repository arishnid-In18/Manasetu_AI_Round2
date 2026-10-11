"""MANASETU AI — application entry point.  Run:  uvicorn app.main:app"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from sqlalchemy.orm import Session
from .db import get_db
from .security import peek_kiosk, peek_staff
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, instruments
from .profiles import get_profile
from .routers import admin, kiosk, staff
from .seed import ensure_seeded

STATIC = Path(__file__).resolve().parent.parent / "static"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_seeded()          # first run: create tables and load the 50 synthetic people
    yield


app = FastAPI(title="MANASETU AI", version=config.APP_VERSION, lifespan=lifespan,
              description="Multilingual mental-health early-warning and support-prioritisation prototype. "
                          "Synthetic data only. AI identifies meaningful changes; professionals decide care.")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                               "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    if request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/meta")
def meta(db: Session = Depends(get_db)):
    from . import services
    prof = get_profile(config.PROFILE)
    cfg = services.get_config(db)
    inst = instruments.get_instrument()
    return {
        "app": "MANASETU AI", "tagline": "Bridging Minds to Mental Health Support.",
        "core_statement": "AI detects the signal. Humans understand the person.",
        "version": config.APP_VERSION,
        "profile": {k: prof[k] for k in ("key", "title", "short", "person_label", "id_prefix", "id_example",
                                         "group_label", "groups", "identity_source", "identity_note", "context_label",
                                         "destinations", "strings")},
        "languages": instruments.LANGUAGES,
        "instrument": {"id": inst["id"], "version": inst["version"], "title": inst["title"],
                       "validated": inst["validated"], "status_note": inst["status_note"],
                       "languages": instruments.available_languages(inst), "score_max": inst["score_range"][1]},
        "features": {"voice_assistant": cfg["voice_assistant_enabled"] == 1},
        "synthetic_data_notice": "All people, histories and photographs in this prototype are synthetic.",
    }


@app.get("/api/session")
def session_status(request: Request, db: Session = Depends(get_db)):
    """Quiet probe used on page load: always 200, reveals only the caller's OWN session state."""
    out = {"staff": None, "kiosk": None}
    st = peek_staff(request, db)
    if st:
        u, sess = st
        out["staff"] = {"user": {"user_id": u.user_id, "username": u.username, "display_name": u.display_name,
                                 "role": u.role, "group_scope": u.group_scope}, "csrf_token": sess.csrf_token}
    ks = peek_kiosk(request, db)
    if ks:
        out["kiosk"] = {"csrf_token": ks.csrf_token, "language": ks.language}
    return out


@app.get("/api/public/privacy")
def public_privacy(lang: str = "en"):
    return instruments.consent_view(lang)


app.include_router(kiosk.router, prefix="/api/kiosk")
app.include_router(kiosk.photo_router, prefix="/api")
app.include_router(staff.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
