from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from applyloop.db.models import Base


def make_engine(url: str):
    if ":memory:" in url:
        # SQLite's default per-thread pool gives each thread its own private
        # in-memory database, which breaks any consumer (e.g. FastAPI's
        # TestClient) that accesses the session factory from a different
        # thread than the one that ran init_db(). A single shared connection
        # keeps the in-memory database consistent across threads.
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(url)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
