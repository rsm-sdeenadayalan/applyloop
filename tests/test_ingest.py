from applyloop.config import CompanyEntry
from applyloop.db.models import Company, Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.discovery.ingest import content_hash, ingest_postings, sync_companies
from applyloop.discovery.types import JobPosting


def make_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def _posting(eid="1", title="Data Scientist"):
    return JobPosting(
        external_id=eid, title=title, location="Remote",
        url=f"https://x.example/{eid}", description_text="desc",
    )


def test_ingest_dedupes():
    session = make_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.commit()
    assert ingest_postings(session, company, [_posting()]) == 1
    assert ingest_postings(session, company, [_posting()]) == 0
    assert session.query(Job).count() == 1
    assert session.query(Event).filter_by(stage="discovery").count() == 2


def test_content_hash_stable():
    assert content_hash("Acme", "DS", "Remote") == content_hash("acme", "ds", "remote")


def test_sync_companies_upserts():
    session = make_session()
    entries = [CompanyEntry(name="Acme", ats="greenhouse", token="acme")]
    first = sync_companies(session, entries)
    second = sync_companies(session, entries)
    assert len(first) == len(second) == 1
    assert session.query(Company).count() == 1
