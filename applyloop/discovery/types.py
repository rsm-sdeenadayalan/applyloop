from datetime import datetime

from pydantic import BaseModel


class JobPosting(BaseModel):
    external_id: str
    title: str
    location: str = ""
    url: str
    description_text: str = ""
    posted_at: datetime | None = None
