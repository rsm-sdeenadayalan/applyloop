import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from applyloop.config import (
    load_companies,
    load_preferences,
    load_profile,
    preferences_as_text,
    profile_as_text,
)
from applyloop.db.models import Event, Job
from applyloop.discovery.ashby import fetch_ashby
from applyloop.discovery.greenhouse import fetch_greenhouse
from applyloop.discovery.ingest import ingest_postings, sync_companies
from applyloop.discovery.lever import fetch_lever
from applyloop.discovery.workable import fetch_workable
from applyloop.scoring.scorer import score_job
from applyloop.settings import get_settings

logger = logging.getLogger(__name__)

POLLERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "workable": fetch_workable,
}


def run_discovery(session: Session, http_client: httpx.Client) -> int:
    settings = get_settings()
    entries = load_companies(settings.config_dir / "companies.yaml")
    companies = sync_companies(session, entries)
    total_new = 0
    for company in companies:
        try:
            postings = POLLERS[company.ats_type](http_client, company.board_token)
        except Exception as exc:  # noqa: BLE001 - per-company isolation is the point
            logger.exception("discovery failed for %s", company.name)
            session.add(
                Event(stage="discovery", level="error", message=f"{company.name}: {exc}")
            )
            session.commit()
            continue
        total_new += ingest_postings(session, company, postings)
    return total_new


def run_scoring(session: Session, llm_client, *, limit: int = 50) -> int:
    settings = get_settings()
    profile_text = profile_as_text(load_profile(settings.config_dir / "profile.yaml"))
    prefs_text = preferences_as_text(
        load_preferences(settings.config_dir / "preferences.yaml")
    )
    jobs = list(
        session.scalars(
            select(Job).where(Job.status == "new").order_by(Job.id).limit(limit)
        )
    )
    scored = 0
    for job in jobs:
        try:
            result = score_job(
                llm_client,
                title=job.title,
                company=job.company.name,
                location=job.location,
                description=job.description_text,
                profile_text=profile_text,
                preferences_text=prefs_text,
            )
        except Exception as exc:  # noqa: BLE001 - per-job isolation is the point
            logger.exception("scoring failed for job %s", job.id)
            session.add(
                Event(job_id=job.id, stage="scoring", level="error", message=str(exc))
            )
            session.commit()
            continue
        job.score = result.score
        job.score_rationale = result.rationale
        job.matched_skills = result.matched_skills
        job.missing_skills = result.missing_skills
        job.status = "scored"
        session.commit()
        scored += 1
    return scored
