from fastapi.testclient import TestClient

from applyloop.db.models import Company, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.web.app import create_app


def make_client():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    session = factory()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    session.add(
        Job(
            company_id=company.id, external_id="1", title="Data Scientist",
            location="Remote", url="https://x/1", content_hash="h1",
            status="scored", score=88, score_rationale="Good fit",
        )
    )
    session.add(
        Job(
            company_id=company.id, external_id="2", title="Chef",
            location="NYC", url="https://x/2", content_hash="h2",
            status="scored", score=10, score_rationale="Bad fit",
        )
    )
    session.commit()
    return TestClient(create_app(factory))


def test_feed_sorted_and_filtered():
    client = make_client()
    page = client.get("/").text
    assert page.index("Data Scientist") < page.index("Chef")
    filtered = client.get("/?min_score=50").text
    assert "Chef" not in filtered


def test_healthz():
    client = make_client()
    body = client.get("/healthz").json()
    assert body["ok"] is True
