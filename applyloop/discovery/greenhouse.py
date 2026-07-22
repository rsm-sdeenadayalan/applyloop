from datetime import datetime

import httpx

from applyloop.discovery.html_text import html_to_text
from applyloop.discovery.types import JobPosting

BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch_greenhouse(client: httpx.Client, board_token: str) -> list[JobPosting]:
    resp = client.get(BASE.format(token=board_token), params={"content": "true"})
    resp.raise_for_status()
    postings = []
    for j in resp.json().get("jobs", []):
        posted = j.get("updated_at") or j.get("first_published")
        postings.append(
            JobPosting(
                external_id=str(j["id"]),
                title=j["title"],
                location=(j.get("location") or {}).get("name", ""),
                url=j["absolute_url"],
                description_text=html_to_text(j.get("content", "")),
                posted_at=datetime.fromisoformat(posted) if posted else None,
            )
        )
    return postings
