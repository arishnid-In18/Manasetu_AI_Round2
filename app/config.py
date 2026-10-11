"""Runtime configuration for MANASETU AI (all values overridable via environment)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Deployment profile. The analysis engine, workflow, RBAC and audit trail are
# identical across profiles; only labels, identity-source wording, groupings and
# referral destinations differ (see app/profiles.py).
#   atrocity_victims : SIH26094 beneficiaries (victims/complainants, PoA Act)  [default]
#   correctional     : prison adaptation (inmates)
PROFILE = os.environ.get("MANASETU_PROFILE", "atrocity_victims")

DATA_ROOT = Path(os.environ.get("MANASETU_DATA_DIR", BASE_DIR / "data"))
DATA_DIR = DATA_ROOT / PROFILE
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite for the prototype. Everything goes through SQLAlchemy so moving to
# PostgreSQL is a one-line change:  DATABASE_URL=postgresql+psycopg2://user:pw@host/db
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'manasetu.db').as_posix()}")

# The mock "authorised prison / portal system" lives in its OWN database file so
# identity data stays separate from sensitive wellbeing data.
MOCK_REGISTRY_PATH = DATA_DIR / "mock_registry.db"

# Audit-chain key. Generated on first run and kept out of the frontend.
SECRET_FILE = DATA_DIR / "secret.key"

STAFF_SESSION_TTL_MIN = int(os.environ.get("MANASETU_STAFF_SESSION_MIN", "60"))
KIOSK_SESSION_TTL_MIN = int(os.environ.get("MANASETU_KIOSK_SESSION_MIN", "20"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MIN = 5
COOKIE_SECURE = os.environ.get("MANASETU_COOKIE_SECURE", "0") == "1"   # set to 1 behind HTTPS

APP_VERSION = "0.1.0-prototype"
