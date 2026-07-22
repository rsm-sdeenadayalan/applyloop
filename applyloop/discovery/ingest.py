import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from applyloop.config import CompanyEntry
from applyloop.db.models import Company, Event, Job
from applyloop.discovery.types import JobPosting


def content_hash(company_name: str, title: str, location: str) -> str:
    key = f"{company_name}|{title}|{location}".lower()
    return hashlib.sha256(key.encode()).hexdigest()


def ingest_postings(session: Session, company: Company, postings: list[JobPosting]) -> int:
    existing = set(
        session.scalars(select(Job.content_hash))
    )
    new_count = 0
    for p in postings:
        h = content_hash(company.name, p.title, p.location)
        if h in existing:
            continue
        existing.add(h)
        session.add(
            Job(
                company_id=company.id, external_id=p.external_id, title=p.title,
                location=p.location, url=p.url, description_text=p.description_text,
                posted_at=p.posted_at, content_hash=h,
            )
        )
        new_count += 1
    session.add(
        Event(
            stage="discovery",
            message=f"{company.name}: {len(postings)} postings, {new_count} new",
        )
    )
    session.commit()
    return new_count


def sync_companies(session: Session, entries: list[CompanyEntry]) -> list[Company]:
    for e in entries:
        row = session.scalar(select(Company).where(Company.name == e.name))
        if row is None:
            session.add(Company(name=e.name, ats_type=e.ats, board_token=e.token))
        else:
            row.ats_type, row.board_token = e.ats, e.token
    session.commit()
    return list(session.scalars(select(Company).where(Company.active.is_(True))))
