import httpx
import respx

from applyloop.db.models import Company, Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.pipeline import run_discovery, run_scoring
from tests.test_scorer import FakeBlock, FakeClient


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


class FlakyClient:
    """Client that fails on first call, succeeds on second."""
    def __init__(self, payload):
        self.messages = FlakyMessages(payload)


class FlakyMessages:
    def __init__(self, payload):
        self.payload = payload
        self.call_count = 0
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        self.call_count += 1
        
        if self.call_count == 1:
            raise RuntimeError("First call fails")
        
        # Create response with FakeBlock
        resp_obj = type('Resp', (), {})()
        resp_obj.content = [FakeBlock(self.payload)]
        return resp_obj


@respx.mock
def test_run_discovery_continues_past_failing_company(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    
    # Write configs with TWO companies
    (tmp_path / "companies.yaml").write_text(
        "companies:\n"
        "  - name: Acme\n    ats: greenhouse\n    token: acme\n"
        "  - name: Beta\n    ats: lever\n    token: beta\n"
    )
    (tmp_path / "profile.yaml").write_text("name: Jane\nskills: [python]\n")
    (tmp_path / "preferences.yaml").write_text("titles: [Data Scientist]\n")
    
    # Mock Greenhouse (Acme) to return 500
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").respond(
        status_code=500
    )
    
    # Mock Lever (Beta) to return a posting
    respx.get("https://api.lever.co/v0/postings/beta").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "L1",
                    "text": "ML Engineer",
                    "createdAt": 1752969600000,
                    "categories": {"location": "Remote"},
                    "hostedUrl": "https://jobs.lever.co/beta/L1",
                    "descriptionPlain": "x",
                }
            ],
        )
    )
    
    session = make_session()
    assert run_discovery(session, httpx.Client()) == 1
    
    # Assert one error event exists
    errors = session.query(Event).filter_by(level="error").all()
    assert len(errors) == 1


@respx.mock
def test_run_scoring_isolates_per_job_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    write_configs(tmp_path)
    
    session = make_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    
    # Create two jobs
    job1 = Job(
        company_id=company.id, external_id="1", title="DS", location="Remote",
        url="https://x", description_text="d", content_hash="h1",
    )
    job2 = Job(
        company_id=company.id, external_id="2", title="ML", location="Remote",
        url="https://y", description_text="e", content_hash="h2",
    )
    session.add(job1)
    session.add(job2)
    session.commit()
    
    # Create a FlakyClient that fails on first job, succeeds on second
    payload = {
        "score": 85, "rationale": "Good fit", "matched_skills": ["python"], "missing_skills": [],
    }
    flaky_client = FlakyClient(payload)
    
    assert run_scoring(session, flaky_client) == 1
    
    # Check job statuses
    jobs = session.query(Job).order_by(Job.id).all()
    assert jobs[0].status == "new"  # Failed job stays "new"
    assert jobs[1].status == "scored"  # Successful job is "scored"
    
    # Check error event
    errors = session.query(Event).filter_by(stage="scoring", level="error").all()
    assert len(errors) == 1
