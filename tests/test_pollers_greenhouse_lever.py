import httpx
import respx

from applyloop.discovery.greenhouse import fetch_greenhouse
from applyloop.discovery.lever import fetch_lever

GH_PAYLOAD = {
    "jobs": [
        {
            "id": 4011,
            "title": "Data Scientist",
            "updated_at": "2026-07-20T12:00:00-04:00",
            "location": {"name": "Remote - US"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4011",
            "content": "&lt;p&gt;Build models&lt;/p&gt;",
        }
    ]
}

LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "ML Engineer",
        "createdAt": 1752969600000,
        "categories": {"location": "San Francisco, CA"},
        "hostedUrl": "https://jobs.lever.co/sample/abc-123",
        "descriptionPlain": "Train models.",
    }
]


@respx.mock
def test_fetch_greenhouse():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").respond(
        json=GH_PAYLOAD
    )
    postings = fetch_greenhouse(httpx.Client(), "acme")
    assert len(postings) == 1
    p = postings[0]
    assert p.external_id == "4011"
    assert p.title == "Data Scientist"
    assert p.location == "Remote - US"
    assert p.description_text == "Build models"
    assert p.posted_at is not None


@respx.mock
def test_fetch_lever():
    respx.get("https://api.lever.co/v0/postings/sample").respond(json=LEVER_PAYLOAD)
    postings = fetch_lever(httpx.Client(), "sample")
    p = postings[0]
    assert p.external_id == "abc-123"
    assert p.title == "ML Engineer"
    assert p.location == "San Francisco, CA"
    assert p.description_text == "Train models."
    assert p.posted_at.year == 2025
