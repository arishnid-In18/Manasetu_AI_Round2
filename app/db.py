from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if _is_sqlite else {}, future=True)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):          # enforce foreign keys in SQLite
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_columns():
    """Additive migration so a database created by an earlier build keeps working."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "screening_responses" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("screening_responses")}
        if "input_mode" not in cols:
            with engine.begin() as c:
                c.execute(text("ALTER TABLE screening_responses ADD COLUMN input_mode VARCHAR(10) NOT NULL DEFAULT 'touch'"))
