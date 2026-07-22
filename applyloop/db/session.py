from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from applyloop.db.models import Base


def make_engine(url: str):
    return create_engine(url)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
