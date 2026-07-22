import logging
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from applyloop.db.models import Event
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.pipeline import run_discovery, run_scoring
from applyloop.settings import get_settings

logger = logging.getLogger(__name__)


def pipeline_tick(session_factory, http_client, llm_client) -> tuple[int, int]:
    session = session_factory()
    try:
        new = run_discovery(session, http_client)
        if llm_client is None or not get_settings().anthropic_api_key:
            session.add(
                Event(stage="scoring", message="skipped: no ANTHROPIC_API_KEY")
            )
            session.commit()
            return new, 0
        scored = run_scoring(session, llm_client)
        return new, scored
    finally:
        session.close()


def build_scheduler(
    session_factory, http_client, llm_client, *, interval_hours: int = 3
) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(
        pipeline_tick,
        IntervalTrigger(hours=interval_hours),
        args=[session_factory, http_client, llm_client],
        id="pipeline_tick",
        next_run_time=datetime.now(UTC),
    )
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    llm_client = None
    if settings.anthropic_api_key:
        import anthropic

        llm_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    build_scheduler(
        make_session_factory(engine), httpx.Client(timeout=30), llm_client
    ).start()
