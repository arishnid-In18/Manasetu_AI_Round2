import os
import tempfile
from pathlib import Path

# Isolated data dir + default profile, set BEFORE the app is imported.
_TMP = tempfile.mkdtemp(prefix="manasetu_tests_")
os.environ["MANASETU_DATA_DIR"] = _TMP
os.environ.setdefault("MANASETU_PROFILE", "atrocity_victims")

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture(scope="session")
def prefix():
    from app.profiles import get_profile
    return get_profile(config.PROFILE)["id_prefix"]


@pytest.fixture(scope="session")
def _boot():
    import shutil
    with TestClient(app) as c:      # triggers startup -> seeding
        # snapshot of the freshly seeded DB, so seed-expectation tests are immune to other tests' writes
        if config.DATABASE_URL.startswith("sqlite"):
            shutil.copy(config.DATA_DIR / "manasetu.db", Path(_TMP) / "pristine.db")
        yield c


@pytest.fixture(scope="session")
def pristine(_boot):
    if not config.DATABASE_URL.startswith("sqlite"):
        from app.db import SessionLocal      # PostgreSQL run: no file snapshot; use -k to skip order-sensitive seed tests
        return SessionLocal
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    eng = create_engine(f"sqlite:///{(Path(_TMP) / 'pristine.db').as_posix()}", connect_args={"check_same_thread": False})
    S = sessionmaker(bind=eng, expire_on_commit=False)
    return S


class Api:
    """Small wrapper that keeps cookies + CSRF token for one actor."""
    def __init__(self):
        self.c = TestClient(app)
        self.csrf = None

    def _h(self):
        return {"X-CSRF-Token": self.csrf} if self.csrf else {}

    def get(self, url, **kw): return self.c.get(url, **kw)
    def post(self, url, json=None, csrf=True): return self.c.post(url, json=json, headers=self._h() if csrf else {})
    def put(self, url, json=None): return self.c.put(url, json=json, headers=self._h())
    def patch(self, url, json=None): return self.c.patch(url, json=json, headers=self._h())


@pytest.fixture()
def staff(_boot):
    def make(username, password):
        a = Api()
        r = a.post("/api/auth/login", {"username": username, "password": password}, csrf=False)
        assert r.status_code == 200, r.text
        a.csrf = r.json()["csrf_token"]
        return a
    return make


@pytest.fixture()
def kiosk(_boot):
    def make(pid):
        a = Api()
        r = a.post("/api/kiosk/lookup", {"person_id": pid}, csrf=False)
        assert r.status_code == 200, r.text
        a.csrf = r.json()["csrf_token"]
        a.profile = r.json()["profile"]
        return a
    return make


OFFICER = ("officer1", "Officer#2026")
OFFICER2 = ("officer2", "Officer#2026")
CLIN = ("clinician1", "Clinician#2026")
ADMIN = ("admin1", "Admin#2026")
