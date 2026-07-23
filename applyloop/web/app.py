from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from applyloop.db.models import Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.settings import get_settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="applyloop")

    @app.get("/")
    def feed(request: Request, min_score: int = 0):
        session = session_factory()
        try:
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(Job.status == "scored", Job.score >= min_score)
                    .order_by(Job.score.desc())
                    .limit(200)
                )
            )
            total = session.scalar(select(func.count(Job.id))) or 0
            scored = session.scalar(select(func.count(Job.id)).where(Job.status == "scored")) or 0
            return TEMPLATES.TemplateResponse(
                request,
                "feed.html",
                {"jobs": jobs, "min_score": min_score, "total": total, "scored": scored},
            )
        finally:
            session.close()

    @app.get("/healthz")
    def healthz():
        session = session_factory()
        try:
            last = session.scalar(
                select(Event.created_at)
                .where(Event.stage == "discovery")
                .order_by(Event.created_at.desc())
                .limit(1)
            )
            return {"ok": True, "last_discovery": last.isoformat() if last else None}
        finally:
            session.close()

    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    uvicorn.run(create_app(make_session_factory(engine)), host="0.0.0.0", port=8000)
