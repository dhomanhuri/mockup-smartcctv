import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://smart_cctv_ai:smart_cctv_ai@postgres:5432/smart_cctv_ai"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def wait_for_db(retries: int = 30, delay: float = 2.0) -> None:
    last_error = None
    for _ in range(retries):
        try:
            with engine.connect():
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"database not reachable: {last_error}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
