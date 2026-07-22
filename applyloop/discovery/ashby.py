from datetime import datetime

import httpx

from applyloop.discovery.html_text import html_to_text
from applyloop.discovery.types import JobPosting

BASE = "https://api.ashbyhq.com/posting-api/job-board/{board}"


def fetch_ashby(client: httpx.Client, board_name: str) -> list[JobPosting]:
    resp = client.get(BASE.format(board=board_name))
    resp.raise_for_status()
    postings = []
    for j in resp.json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        published = j.get("publishedAt")
        postings.append(
            JobPosting(
                external_id=str(j["id"]),
                title=j["title"],
                location=j.get("location", "") or "",
                url=j["jobUrl"],
                description_text=html_to_text(j.get("descriptionHtml", "")),
                posted_at=(
                    datetime.fromisoformat(published.replace("Z", "+00:00"))
                    if published
                    else None
                ),
            )
        )
    return postings
