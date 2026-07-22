from datetime import UTC, datetime

import httpx

from applyloop.discovery.html_text import html_to_text
from applyloop.discovery.types import JobPosting

BASE = "https://apply.workable.com/api/v1/widget/accounts/{account}"


def fetch_workable(client: httpx.Client, account: str) -> list[JobPosting]:
    resp = client.get(BASE.format(account=account), params={"details": "true"})
    resp.raise_for_status()
    postings = []
    for j in resp.json().get("jobs", []):
        parts = [p for p in [j.get("city"), j.get("country")] if p]
        published = j.get("published_on")
        postings.append(
            JobPosting(
                external_id=str(j["shortcode"]),
                title=j["title"],
                location=", ".join(parts) or j.get("location", "") or "",
                url=j["url"],
                description_text=html_to_text(j.get("description", "")),
                posted_at=(
                    datetime.strptime(published, "%Y-%m-%d").replace(tzinfo=UTC)
                    if published
                    else None
                ),
            )
        )
    return postings
