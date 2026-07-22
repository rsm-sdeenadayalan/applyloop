from datetime import UTC

import httpx
import respx

from applyloop.discovery.ashby import fetch_ashby
from applyloop.discovery.workable import fetch_workable

ASHBY_PAYLOAD = {
    "jobs": [
        {
            "id": "b1e2",
            "title": "Analytics Engineer",
            "location": "Remote",
            "jobUrl": "https://jobs.ashbyhq.com/acme/b1e2",
            "descriptionHtml": "<p>Own dbt models</p>",
            "publishedAt": "2026-07-19T05:00:00+05:00",
            "isListed": True,
        },
        {"id": "hidden", "title": "Ghost", "jobUrl": "x", "isListed": False},
    ]
}

WORKABLE_PAYLOAD = {
    "jobs": [
        {
            "shortcode": "AB12",
            "title": "Data Engineer",
            "city": "Austin",
            "country": "United States",
            "url": "https://apply.workable.com/sample/j/AB12/",
            "description": "<p>Build pipelines</p>",
            "published_on": "2026-07-18",
        }
    ]
}


@respx.mock
def test_fetch_ashby_filters_unlisted():
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").respond(
        json=ASHBY_PAYLOAD
    )
    postings = fetch_ashby(httpx.Client(), "acme")
    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "b1e2"
    assert p.description_text == "Own dbt models"
    assert p.posted_at.tzinfo == UTC
    assert p.posted_at.hour == 0


@respx.mock
def test_fetch_workable():
    respx.get(
        "https://apply.workable.com/api/v1/widget/accounts/sample"
    ).respond(json=WORKABLE_PAYLOAD)
    postings = fetch_workable(httpx.Client(), "sample")
    p = postings[0]
    assert p.external_id == "AB12"
    assert p.location == "Austin, United States"
    assert p.description_text == "Build pipelines"
    assert postings[0].posted_at.tzinfo == UTC
