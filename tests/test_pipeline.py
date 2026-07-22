import httpx
import respx

from applyloop.db.models import Company, Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.pipeline import run_discovery, run_scoring
from tests.test_scorer import FakeClient


def make_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def write_configs(tmp_path):
    (tmp_path / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\n    token: acme\n"
    )
    (tmp_path / "profile.yaml").write_text("name: Jane\nskills: [python]\n")
    (tmp_path / "preferences.yaml").write_text("titles: [Data Scientist]\n")


@respx.mock
def test_run_discovery_survives_poller_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    write_configs(tmp_path)
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").respond(
        status_code=500
    )
    session = make_session()
    assert run_discovery(session, httpx.Client()) == 0
    errors = session.query(Event).filter_by(level="error").all()
    assert len(errors) == 1


def test_run_scoring_updates_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    write_configs(tmp_path)
    session = make_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    session.add(
        Job(
            company_id=company.id, external_id="1", title="DS", location="Remote",
            url="https://x", description_text="d", content_hash="h1",
        )
    )
    session.commit()
    payload = {
        "score": 90, "rationale": "r", "matched_skills": [], "missing_skills": [],
    }
    assert run_scoring(session, FakeClient(payload)) == 1
    job = session.query(Job).one()
    assert job.score == 90
    assert job.status == "scored"
