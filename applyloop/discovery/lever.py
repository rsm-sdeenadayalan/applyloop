from datetime import UTC, datetime

import httpx

from applyloop.discovery.types import JobPosting

BASE = "https://api.lever.co/v0/postings/{company}"


def fetch_lever(client: httpx.Client, company: str) -> list[JobPosting]:
    resp = client.get(BASE.format(company=company), params={"mode": "json"})
    resp.raise_for_status()
    postings = []
    for j in resp.json():
        created_ms = j.get("createdAt")
        postings.append(
            JobPosting(
                external_id=str(j["id"]),
                title=j["text"],
                location=(j.get("categories") or {}).get("location", "") or "",
                url=j["hostedUrl"],
                description_text=j.get("descriptionPlain", ""),
                posted_at=(
                    datetime.fromtimestamp(created_ms / 1000, tz=UTC) if created_ms else None
                ),
            )
        )
    return postings
