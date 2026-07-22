from applyloop.db.models import Company, Job
from applyloop.db.session import init_db, make_engine, make_session_factory


def make_test_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_job_company_roundtrip():
    session = make_test_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    job = Job(
        company_id=company.id, external_id="123", title="Data Scientist",
        location="Remote", url="https://boards.greenhouse.io/acme/jobs/123",
        description_text="Do data science.", content_hash="abc",
    )
    session.add(job)
    session.commit()
    fetched = session.query(Job).one()
    assert fetched.company.name == "Acme"
    assert fetched.status == "new"
    assert fetched.discovered_at is not None
