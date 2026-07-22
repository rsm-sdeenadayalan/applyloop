import httpx

from applyloop.db.models import Event
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.worker import build_scheduler, pipeline_tick


def test_pipeline_tick_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    (tmp_path / "companies.yaml").write_text("companies: []\n")
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    new, scored = pipeline_tick(factory, httpx.Client(), llm_client=None)
    assert (new, scored) == (0, 0)
    session = factory()
    assert session.query(Event).filter_by(stage="scoring").count() == 1


def test_build_scheduler_has_job():
    sched = build_scheduler(lambda: None, None, None)
    assert len(sched.get_jobs()) == 1
