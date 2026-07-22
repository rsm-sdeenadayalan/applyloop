# Milestone 1: Smart Job Feed — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A running system that polls public ATS job APIs for a company watchlist, dedupes new postings into Postgres, scores each against the user's résumé with Claude Haiku, and shows a ranked feed in a web dashboard.

**Architecture:** Python monorepo `applyloop/` package. Sync SQLAlchemy 2.0 + Postgres (SQLite in tests). Per-ATS poller modules returning a shared `JobPosting` DTO, an ingest service that dedupes by content hash, an LLM scorer using a forced tool call for structured output, an APScheduler worker running discover→score, and a FastAPI+Jinja2 dashboard. Docker Compose for deploy, GitHub Actions CI.

**Tech Stack:** Python ≥3.12, uv, FastAPI, Jinja2, SQLAlchemy 2.0, Alembic, psycopg, httpx, pydantic v2, pydantic-settings, PyYAML, APScheduler, anthropic SDK, pytest, respx, ruff.

## Global Constraints

- License MIT; dependencies must be permissively licensed (MIT/Apache-2.0/BSD/PSF) or weak-copyleft (LGPL/MPL, e.g. psycopg, certifi) used unmodified as installed packages. No GPL/AGPL dependencies.
- No personal data in the repo: `config/*.yaml`, `.env`, `*.pdf`, `*.db` are gitignored; only `*.example` templates are committed.
- No code copied from other job-application projects (AIHawk, ApplyPilot, etc.).
- Python ≥3.12. Line length 100 (ruff). All timestamps stored UTC.
- LLM scoring uses model id `claude-haiku-4-5-20251001`; scorer must never run without `ANTHROPIC_API_KEY` set (skip gracefully with a logged event).
- Tests must not hit the network (respx-mock httpx; fake Anthropic client) and must not require Postgres (SQLite in-memory).

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`, `.env.example`, `ruff.toml`, `applyloop/__init__.py`, `tests/__init__.py`, `tests/test_scaffold.py`

**Interfaces:**
- Produces: installable `applyloop` package; `uv run pytest` and `uv run ruff check .` work.

- [ ] **Step 1: Write pyproject.toml**

```toml
[project]
name = "applyloop"
version = "0.1.0"
description = "Self-hosted AI job application system: discover, score, tailor, approve, apply, track."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "jinja2>=3.1",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg[binary]>=3.2",
    "httpx>=0.27",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "pyyaml>=6.0",
    "apscheduler>=3.10,<4",
    "anthropic>=0.34",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6", "respx>=0.21"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["applyloop"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write ruff.toml**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 3: Write .gitignore**

```
__pycache__/
*.pyc
.venv/
.env
config/*.yaml
!config/*.yaml.example
*.db
*.pdf
data/
.pytest_cache/
.ruff_cache/
uv.lock
```

Note: `uv.lock` stays ignored for now (library-style repo; revisit at deploy milestone).

- [ ] **Step 4: Write LICENSE**

Standard MIT license text, copyright line: `Copyright (c) 2026 applyloop contributors`.

- [ ] **Step 5: Write README.md**

```markdown
# applyloop

Self-hosted, single-user AI job application system: discovers new postings from
public ATS job APIs (Greenhouse, Lever, Ashby, Workable), scores them against
your résumé with an LLM, tailors application materials, queues them for your
one-tap approval, submits, and tracks everything.

**Status:** Milestone 1 (discover + score + feed) under construction.

## Honest constraints

- Auto-submission can conflict with some job sites' terms of service, and bot
  defenses change; applyloop always degrades to "manual needed, with everything
  prepped" rather than fighting CAPTCHAs. No CAPTCHA-solving services, ever.
- The LLM tailors by reordering and rephrasing your real profile. It never
  fabricates experience, dates, or skills.
- Aggregator scraping (LinkedIn/Indeed via JobSpy) is optional and off by default.
- This repo ships no personal data and no scraped job content.

## License

MIT
```

- [ ] **Step 6: Write .env.example**

```
DATABASE_URL=postgresql+psycopg://applyloop:applyloop@localhost:5432/applyloop
ANTHROPIC_API_KEY=
```

- [ ] **Step 7: Create package + failing smoke test**

`applyloop/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/test_scaffold.py`:
```python
import applyloop


def test_package_importable():
    assert applyloop.__version__ == "0.1.0"
```

- [ ] **Step 8: Run tests and lint**

Run: `uv sync && uv run pytest -v && uv run ruff check .`
Expected: 1 test PASS, no lint errors.

- [ ] **Step 9: Commit**

```bash
git add -A && git commit -m "feat: project scaffold (pyproject, ruff, MIT license, README)"
```

---

### Task 2: Settings and YAML config loading

**Files:**
- Create: `applyloop/settings.py`, `applyloop/config.py`, `config/profile.yaml.example`, `config/preferences.yaml.example`, `config/companies.yaml.example`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `applyloop.settings.Settings` (pydantic-settings): fields `database_url: str` (default `sqlite:///applyloop.db`), `anthropic_api_key: str = ""`, `config_dir: Path` (default `Path("config")`), `score_threshold: int = 70`. `get_settings() -> Settings` cached accessor.
  - `applyloop.config.load_profile(path: Path) -> dict`, `load_preferences(path: Path) -> dict`, `load_companies(path: Path) -> list[CompanyEntry]` where `CompanyEntry` is a pydantic model: `name: str`, `ats: Literal["greenhouse", "lever", "ashby", "workable"]`, `token: str`.
  - `profile_as_text(profile: dict) -> str` and `preferences_as_text(prefs: dict) -> str` — YAML-dumped stable text for LLM prompts.

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
from pathlib import Path

from applyloop.config import CompanyEntry, load_companies, load_profile, profile_as_text
from applyloop.settings import Settings


def test_settings_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    assert s.database_url.startswith("sqlite")
    assert s.score_threshold == 70


def test_load_companies(tmp_path: Path):
    f = tmp_path / "companies.yaml"
    f.write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\n    token: acme\n"
    )
    companies = load_companies(f)
    assert companies == [CompanyEntry(name="Acme", ats="greenhouse", token="acme")]


def test_profile_roundtrip(tmp_path: Path):
    f = tmp_path / "profile.yaml"
    f.write_text("name: Jane Doe\nskills: [python, sql]\n")
    profile = load_profile(f)
    text = profile_as_text(profile)
    assert "Jane Doe" in text and "python" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v` — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

`applyloop/settings.py`:
```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///applyloop.db"
    anthropic_api_key: str = ""
    config_dir: Path = Path("config")
    score_threshold: int = 70


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`applyloop/config.py`:
```python
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel


class CompanyEntry(BaseModel):
    name: str
    ats: Literal["greenhouse", "lever", "ashby", "workable"]
    token: str


def _load_yaml(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def load_profile(path: Path) -> dict:
    return _load_yaml(path)


def load_preferences(path: Path) -> dict:
    return _load_yaml(path)


def load_companies(path: Path) -> list[CompanyEntry]:
    data = _load_yaml(path)
    return [CompanyEntry(**c) for c in data.get("companies", [])]


def profile_as_text(profile: dict) -> str:
    return yaml.safe_dump(profile, sort_keys=False)


def preferences_as_text(prefs: dict) -> str:
    return yaml.safe_dump(prefs, sort_keys=False)
```

- [ ] **Step 4: Write the three example configs**

`config/companies.yaml.example`:
```yaml
# Copy to companies.yaml and edit. token = the company's board slug in its ATS URL,
# e.g. https://boards.greenhouse.io/<token>, https://jobs.lever.co/<token>,
# https://jobs.ashbyhq.com/<token>, https://apply.workable.com/<token>
companies:
  - name: Example Corp
    ats: greenhouse
    token: examplecorp
  - name: Sample Startup
    ats: lever
    token: samplestartup
```

`config/profile.yaml.example`:
```yaml
# Copy to profile.yaml. This is your master résumé as data. The tailor may
# reorder/rephrase but never invent anything not present here.
name: Jane Doe
email: jane@example.com
phone: "+1 555 000 0000"
location: San Francisco, CA
links:
  - https://github.com/janedoe
  - https://linkedin.com/in/janedoe
work_authorization: US citizen            # or: needs H-1B sponsorship, F-1 OPT, etc.
summary: >
  Data scientist with 3 years of experience in ML pipelines and analytics.
experience:
  - company: Acme Analytics
    title: Data Scientist
    start: 2023-07
    end: present
    location: Remote
    bullets:
      - Built churn prediction model (XGBoost) reducing churn 12%
      - Deployed feature pipelines on Airflow + dbt serving 40 models
education:
  - school: UC San Diego
    degree: MS Business Analytics
    year: 2023
skills: [python, sql, pytorch, airflow, dbt, aws]
```

`config/preferences.yaml.example`:
```yaml
# Copy to preferences.yaml. Used to gate and score jobs.
titles: [Data Scientist, Machine Learning Engineer, Analytics Engineer]
seniority: [entry, mid]            # entry | mid | senior | staff
locations: [United States, Remote]
remote_ok: true
salary_floor_usd: 110000
dealbreakers:
  - security clearance required
search_terms: [data scientist, machine learning engineer]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_config.py -v` — Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: settings and YAML config loading with example templates"
```

---

### Task 3: Database models and session

**Files:**
- Create: `applyloop/db/__init__.py`, `applyloop/db/models.py`, `applyloop/db/session.py`, `tests/test_models.py`

**Interfaces:**
- Produces:
  - `applyloop.db.models.Base` (DeclarativeBase)
  - `Company`: `id int pk`, `name str unique`, `ats_type str`, `board_token str`, `active bool default True`, `created_at datetime`
  - `Job`: `id int pk`, `company_id fk`, `external_id str`, `title str`, `location str`, `url str`, `description_text Text`, `posted_at datetime|None`, `discovered_at datetime`, `content_hash str unique`, `score int|None`, `score_rationale Text|None`, `matched_skills JSON|None`, `missing_skills JSON|None`, `status str default "new"` (new→scored; ignored), relationship `company`
  - `Application`: `id int pk`, `job_id fk`, `status str default "queued"`, `resume_pdf_path str|None`, `cover_letter Text|None`, `answers JSON|None`, `receipt JSON|None`, `created_at`, `updated_at`
  - `Event`: `id int pk`, `job_id int|None`, `application_id int|None`, `stage str`, `level str default "info"`, `message Text`, `created_at`
  - `applyloop.db.session.make_engine(url: str)`, `make_session_factory(engine) -> sessionmaker[Session]`, `init_db(engine)` (create_all — Alembic arrives in the deploy milestone)
  - `utcnow() -> datetime` helper in `models.py` (timezone-aware UTC).

- [ ] **Step 1: Write failing test**

`tests/test_models.py`:
```python
from applyloop.db.models import Company, Job
from applyloop.db.session import init_db, make_engine, make_session_factory


def make_test_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_job_company_roundtrip():
    session = make_test_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    job = Job(
        company_id=company.id, external_id="123", title="Data Scientist",
        location="Remote", url="https://boards.greenhouse.io/acme/jobs/123",
        description_text="Do data science.", content_hash="abc",
    )
    session.add(job)
    session.commit()
    fetched = session.query(Job).one()
    assert fetched.company.name == "Acme"
    assert fetched.status == "new"
    assert fetched.discovered_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v` — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement models**

`applyloop/db/__init__.py` empty. `applyloop/db/models.py`:
```python
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    ats_type: Mapped[str]
    board_token: Mapped[str]
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    jobs: Mapped[list["Job"]] = relationship(back_populates="company")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    external_id: Mapped[str]
    title: Mapped[str]
    location: Mapped[str] = mapped_column(default="")
    url: Mapped[str]
    description_text: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    content_hash: Mapped[str] = mapped_column(unique=True)
    score: Mapped[int | None] = mapped_column(nullable=True)
    score_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missing_skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(default="new")
    company: Mapped[Company] = relationship(back_populates="jobs")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    status: Mapped[str] = mapped_column(default="queued")
    resume_pdf_path: Mapped[str | None] = mapped_column(nullable=True)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    job: Mapped[Job] = relationship()


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("applications.id"), nullable=True
    )
    stage: Mapped[str]
    level: Mapped[str] = mapped_column(default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

`applyloop/db/session.py`:
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from applyloop.db.models import Base


def make_engine(url: str):
    return create_engine(url)


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_models.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: SQLAlchemy models for companies, jobs, applications, events"
```

---

### Task 4: JobPosting DTO + HTML-to-text helper

**Files:**
- Create: `applyloop/discovery/__init__.py`, `applyloop/discovery/types.py`, `applyloop/discovery/html_text.py`, `tests/test_html_text.py`

**Interfaces:**
- Produces:
  - `applyloop.discovery.types.JobPosting` (pydantic): `external_id: str`, `title: str`, `location: str = ""`, `url: str`, `description_text: str = ""`, `posted_at: datetime | None = None`
  - `applyloop.discovery.html_text.html_to_text(html: str) -> str` — unescapes entities, strips tags, collapses whitespace.

- [ ] **Step 1: Write failing test**

`tests/test_html_text.py`:
```python
from applyloop.discovery.html_text import html_to_text


def test_strips_tags_and_entities():
    html = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;"
    assert html_to_text(html) == "Hello & welcome"


def test_plain_html():
    assert html_to_text("<ul><li>Python</li><li>SQL</li></ul>") == "Python SQL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_html_text.py -v` — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/discovery/types.py`:
```python
from datetime import datetime

from pydantic import BaseModel


class JobPosting(BaseModel):
    external_id: str
    title: str
    location: str = ""
    url: str
    description_text: str = ""
    posted_at: datetime | None = None
```

`applyloop/discovery/html_text.py`:
```python
import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    text = raw
    # Greenhouse double-escapes entities; unescape until stable (max 3 rounds).
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_html_text.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: JobPosting DTO and HTML-to-text helper"
```

---

### Task 5: Greenhouse and Lever pollers

**Files:**
- Create: `applyloop/discovery/greenhouse.py`, `applyloop/discovery/lever.py`, `tests/test_pollers_greenhouse_lever.py`

**Interfaces:**
- Consumes: `JobPosting`, `html_to_text` (Task 4).
- Produces:
  - `fetch_greenhouse(client: httpx.Client, board_token: str) -> list[JobPosting]` — GET `https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
  - `fetch_lever(client: httpx.Client, company: str) -> list[JobPosting]` — GET `https://api.lever.co/v0/postings/{company}?mode=json`

- [ ] **Step 1: Write failing tests (respx-mocked)**

`tests/test_pollers_greenhouse_lever.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail** — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

`applyloop/discovery/greenhouse.py`:
```python
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
```

`applyloop/discovery/lever.py`:
```python
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
```

- [ ] **Step 4: Run tests** — Expected: PASS. (Note: the Lever fixture timestamp 1752969600000 is 2025-07-20 UTC; assert accordingly.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Greenhouse and Lever pollers over public board APIs"
```

---

### Task 6: Ashby and Workable pollers

**Files:**
- Create: `applyloop/discovery/ashby.py`, `applyloop/discovery/workable.py`, `tests/test_pollers_ashby_workable.py`

**Interfaces:**
- Consumes: `JobPosting`, `html_to_text`.
- Produces:
  - `fetch_ashby(client: httpx.Client, board_name: str) -> list[JobPosting]` — GET `https://api.ashbyhq.com/posting-api/job-board/{board_name}` (JSON key `jobs`; fields `id`, `title`, `location`, `jobUrl`, `descriptionHtml`, `publishedAt`, plus `isListed` filter)
  - `fetch_workable(client: httpx.Client, account: str) -> list[JobPosting]` — GET `https://apply.workable.com/api/v1/widget/accounts/{account}?details=true` (JSON key `jobs`; fields `shortcode`, `title`, `city`/`country` or `location`, `url`, `description`, `published_on`)

- [ ] **Step 1: Write failing tests**

`tests/test_pollers_ashby_workable.py`:
```python
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
            "publishedAt": "2026-07-19T00:00:00.000Z",
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
```

- [ ] **Step 2: Run tests to verify they fail** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/discovery/ashby.py`:
```python
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
```

`applyloop/discovery/workable.py`:
```python
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
```

- [ ] **Step 4: Run tests** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Ashby and Workable pollers"
```

---

### Task 7: Ingest service (dedup + upsert)

**Files:**
- Create: `applyloop/discovery/ingest.py`, `tests/test_ingest.py`

**Interfaces:**
- Consumes: `JobPosting`, models `Company`/`Job`/`Event`, `make_test_session` pattern from Task 3.
- Produces:
  - `content_hash(company_name: str, title: str, location: str) -> str` — sha256 hex of `f"{company_name}|{title}|{location}".lower()`
  - `ingest_postings(session: Session, company: Company, postings: list[JobPosting]) -> int` — inserts unseen postings as `Job(status="new")`, skips known hashes, logs one `Event(stage="discovery")` per run with counts; returns number of new jobs. Commits.
  - `sync_companies(session: Session, entries: list[CompanyEntry]) -> list[Company]` — upserts watchlist entries into `companies` by name; returns active companies.

- [ ] **Step 1: Write failing tests**

`tests/test_ingest.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/discovery/ingest.py`:
```python
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
        session.scalars(select(Job.content_hash).where(Job.company_id == company.id))
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
```

- [ ] **Step 4: Run tests** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: ingest service with content-hash dedup and watchlist sync"
```

---

### Task 8: LLM scorer (Claude Haiku, forced tool call)

**Files:**
- Create: `applyloop/scoring/__init__.py`, `applyloop/scoring/scorer.py`, `tests/test_scorer.py`

**Interfaces:**
- Consumes: `Job` model; `profile_as_text`/`preferences_as_text` output strings.
- Produces:
  - `ScoreResult` (pydantic): `score: int` (0–100), `rationale: str`, `matched_skills: list[str]`, `missing_skills: list[str]`
  - `score_job(client, *, title: str, company: str, location: str, description: str, profile_text: str, preferences_text: str, model: str = "claude-haiku-4-5-20251001") -> ScoreResult` — `client` is an `anthropic.Anthropic` (or fake with same `.messages.create` shape). Uses a single tool `report_match` with `tool_choice={"type": "tool", "name": "report_match"}` and parses `content[0].input` into `ScoreResult`. Description truncated to 6000 chars.

- [ ] **Step 1: Write failing test with a fake client**

`tests/test_scorer.py`:
```python
from applyloop.scoring.scorer import ScoreResult, score_job


class FakeBlock:
    type = "tool_use"

    def __init__(self, payload):
        self.input = payload


class FakeMessages:
    def __init__(self, payload):
        self.payload = payload
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs

        class Resp:
            content = [FakeBlock(self.payload)]

        return Resp()


class FakeClient:
    def __init__(self, payload):
        self.messages = FakeMessages(payload)


def test_score_job_parses_tool_output():
    payload = {
        "score": 82, "rationale": "Strong skills overlap.",
        "matched_skills": ["python"], "missing_skills": ["golang"],
    }
    client = FakeClient(payload)
    result = score_job(
        client, title="DS", company="Acme", location="Remote",
        description="x" * 10000, profile_text="skills: python",
        preferences_text="titles: [DS]",
    )
    assert result == ScoreResult(**payload)
    sent = client.messages.last_kwargs
    assert sent["tool_choice"] == {"type": "tool", "name": "report_match"}
    # description truncated
    assert "x" * 6001 not in str(sent["messages"])
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/scoring/scorer.py`:
```python
from pydantic import BaseModel, Field

MATCH_TOOL = {
    "name": "report_match",
    "description": "Report how well this job matches the candidate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "rationale": {"type": "string", "description": "Two sentences max."},
            "matched_skills": {"type": "array", "items": {"type": "string"}},
            "missing_skills": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["score", "rationale", "matched_skills", "missing_skills"],
    },
}

SYSTEM = (
    "You score job postings for one specific candidate. Score 0-100 for how well "
    "the candidate matches the role AND how well the role matches their stated "
    "preferences. Score below 40 if a dealbreaker applies or required experience "
    "far exceeds the candidate's. Be strict: 70+ means genuinely worth applying."
)


class ScoreResult(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: str
    matched_skills: list[str]
    missing_skills: list[str]


def score_job(
    client,
    *,
    title: str,
    company: str,
    location: str,
    description: str,
    profile_text: str,
    preferences_text: str,
    model: str = "claude-haiku-4-5-20251001",
) -> ScoreResult:
    prompt = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"CANDIDATE PREFERENCES:\n{preferences_text}\n\n"
        f"JOB: {title} at {company} ({location})\n"
        f"DESCRIPTION:\n{description[:6000]}"
    )
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM,
        tools=[MATCH_TOOL],
        tool_choice={"type": "tool", "name": "report_match"},
        messages=[{"role": "user", "content": prompt}],
    )
    block = next(b for b in resp.content if getattr(b, "type", "") == "tool_use")
    return ScoreResult(**block.input)
```

`applyloop/scoring/__init__.py` empty.

- [ ] **Step 4: Run tests** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Haiku job scorer with forced tool call"
```

---

### Task 9: Pipeline runner (discover → score)

**Files:**
- Create: `applyloop/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `POLLERS: dict[str, Callable[[httpx.Client, str], list[JobPosting]]]` mapping `"greenhouse"|"lever"|"ashby"|"workable"` to fetchers.
  - `run_discovery(session: Session, http_client: httpx.Client) -> int` — loads `companies.yaml` via settings config_dir, `sync_companies`, polls each active company (errors per company logged as `Event(stage="discovery", level="error")`, do not abort the loop), ingests; returns total new jobs.
  - `run_scoring(session: Session, llm_client, *, limit: int = 50) -> int` — loads profile/preferences, scores jobs with `status == "new"` oldest-first up to `limit`, writes score fields, sets `status="scored"`; per-job errors logged as `Event(stage="scoring", level="error")` and job left `new`; returns count scored.

- [ ] **Step 1: Write failing tests**

`tests/test_pipeline.py`:
```python
import httpx
import respx

from applyloop.db.models import Company, Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.pipeline import run_discovery, run_scoring
from tests.test_scorer import FakeClient


def make_session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def write_configs(tmp_path):
    (tmp_path / "companies.yaml").write_text(
        "companies:\n  - name: Acme\n    ats: greenhouse\n    token: acme\n"
    )
    (tmp_path / "profile.yaml").write_text("name: Jane\nskills: [python]\n")
    (tmp_path / "preferences.yaml").write_text("titles: [Data Scientist]\n")


@respx.mock
def test_run_discovery_survives_poller_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    write_configs(tmp_path)
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").respond(
        status_code=500
    )
    session = make_session()
    assert run_discovery(session, httpx.Client()) == 0
    errors = session.query(Event).filter_by(level="error").all()
    assert len(errors) == 1


def test_run_scoring_updates_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    write_configs(tmp_path)
    session = make_session()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    session.add(
        Job(
            company_id=company.id, external_id="1", title="DS", location="Remote",
            url="https://x", description_text="d", content_hash="h1",
        )
    )
    session.commit()
    payload = {
        "score": 90, "rationale": "r", "matched_skills": [], "missing_skills": [],
    }
    assert run_scoring(session, FakeClient(payload)) == 1
    job = session.query(Job).one()
    assert job.score == 90
    assert job.status == "scored"
```

- [ ] **Step 2: Run tests to verify they fail** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/pipeline.py`:
```python
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
```

Also add to `applyloop/settings.py` (Settings class): the `config_dir` field must read env var `CONFIG_DIR` — pydantic-settings does this automatically from the field name.

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_pipeline.py -v` — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: discover-and-score pipeline with per-item error isolation"
```

---

### Task 10: Worker entrypoint (APScheduler)

**Files:**
- Create: `applyloop/worker.py`, `tests/test_worker.py`

**Interfaces:**
- Consumes: `run_discovery`, `run_scoring`, settings, session factory.
- Produces:
  - `build_scheduler(session_factory, http_client, llm_client, *, interval_hours: int = 3) -> BlockingScheduler` — one job `pipeline_tick` on an `IntervalTrigger`, plus an immediate first run (`next_run_time=now`).
  - `pipeline_tick(session_factory, http_client, llm_client) -> tuple[int, int]` — opens a session, runs discovery then scoring (scoring skipped with an info `Event` if `settings.anthropic_api_key` empty), closes session, returns `(new, scored)`.
  - `main()` — wires real engine (init_db), `httpx.Client`, `anthropic.Anthropic`, starts scheduler. Registered as script: add to `pyproject.toml` `[project.scripts] applyloop-worker = "applyloop.worker:main"`.

- [ ] **Step 1: Write failing test**

`tests/test_worker.py`:
```python
import httpx

from applyloop.db.models import Event
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.worker import build_scheduler, pipeline_tick


def test_pipeline_tick_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from applyloop.settings import get_settings

    get_settings.cache_clear()
    (tmp_path / "companies.yaml").write_text("companies: []\n")
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    new, scored = pipeline_tick(factory, httpx.Client(), llm_client=None)
    assert (new, scored) == (0, 0)
    session = factory()
    assert session.query(Event).filter_by(stage="scoring").count() == 1


def test_build_scheduler_has_job():
    sched = build_scheduler(lambda: None, None, None)
    assert len(sched.get_jobs()) == 1
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/worker.py`:
```python
import logging
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from applyloop.db.models import Event
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.pipeline import run_discovery, run_scoring
from applyloop.settings import get_settings

logger = logging.getLogger(__name__)


def pipeline_tick(session_factory, http_client, llm_client) -> tuple[int, int]:
    session = session_factory()
    try:
        new = run_discovery(session, http_client)
        if llm_client is None or not get_settings().anthropic_api_key:
            session.add(
                Event(stage="scoring", message="skipped: no ANTHROPIC_API_KEY")
            )
            session.commit()
            return new, 0
        scored = run_scoring(session, llm_client)
        return new, scored
    finally:
        session.close()


def build_scheduler(
    session_factory, http_client, llm_client, *, interval_hours: int = 3
) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(
        pipeline_tick,
        IntervalTrigger(hours=interval_hours),
        args=[session_factory, http_client, llm_client],
        id="pipeline_tick",
        next_run_time=datetime.now(UTC),
    )
    return sched


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    llm_client = None
    if settings.anthropic_api_key:
        import anthropic

        llm_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    build_scheduler(
        make_session_factory(engine), httpx.Client(timeout=30), llm_client
    ).start()
```

And in `pyproject.toml` add:
```toml
[project.scripts]
applyloop-worker = "applyloop.worker:main"
applyloop-web = "applyloop.web.app:main"
```
(the web script lands in Task 11).

- [ ] **Step 4: Run tests** — Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: APScheduler worker entrypoint"
```

---

### Task 11: Dashboard (FastAPI + Jinja2 feed)

**Files:**
- Create: `applyloop/web/__init__.py`, `applyloop/web/app.py`, `applyloop/web/templates/base.html`, `applyloop/web/templates/feed.html`, `tests/test_web.py`

**Interfaces:**
- Consumes: models, session factory, settings.
- Produces:
  - `create_app(session_factory) -> FastAPI` with routes:
    - `GET /` — jobs with `status == "scored"` ordered `score` desc (top 200), template `feed.html`; query param `min_score: int = 0` filters.
    - `GET /healthz` — `{"ok": true, "last_discovery": <iso or null>}` (latest discovery Event timestamp).
  - `main()` — builds real engine/factory, `uvicorn.run` on `0.0.0.0:8000`.

- [ ] **Step 1: Write failing test**

`tests/test_web.py`:
```python
from fastapi.testclient import TestClient

from applyloop.db.models import Company, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.web.app import create_app


def make_client():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)
    session = factory()
    company = Company(name="Acme", ats_type="greenhouse", board_token="acme")
    session.add(company)
    session.flush()
    session.add(
        Job(
            company_id=company.id, external_id="1", title="Data Scientist",
            location="Remote", url="https://x/1", content_hash="h1",
            status="scored", score=88, score_rationale="Good fit",
        )
    )
    session.add(
        Job(
            company_id=company.id, external_id="2", title="Chef",
            location="NYC", url="https://x/2", content_hash="h2",
            status="scored", score=10, score_rationale="Bad fit",
        )
    )
    session.commit()
    return TestClient(create_app(factory))


def test_feed_sorted_and_filtered():
    client = make_client()
    page = client.get("/").text
    assert page.index("Data Scientist") < page.index("Chef")
    filtered = client.get("/?min_score=50").text
    assert "Chef" not in filtered


def test_healthz():
    client = make_client()
    body = client.get("/healthz").json()
    assert body["ok"] is True
```

- [ ] **Step 2: Run test to verify it fails** — Expected: FAIL.

- [ ] **Step 3: Implement**

`applyloop/web/app.py`:
```python
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from applyloop.db.models import Event, Job
from applyloop.db.session import init_db, make_engine, make_session_factory
from applyloop.settings import get_settings

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="applyloop")

    @app.get("/")
    def feed(request: Request, min_score: int = 0):
        session = session_factory()
        try:
            jobs = list(
                session.scalars(
                    select(Job)
                    .where(Job.status == "scored", Job.score >= min_score)
                    .order_by(Job.score.desc())
                    .limit(200)
                )
            )
            return TEMPLATES.TemplateResponse(
                request, "feed.html", {"jobs": jobs, "min_score": min_score}
            )
        finally:
            session.close()

    @app.get("/healthz")
    def healthz():
        session = session_factory()
        try:
            last = session.scalar(
                select(Event.created_at)
                .where(Event.stage == "discovery")
                .order_by(Event.created_at.desc())
                .limit(1)
            )
            return {"ok": True, "last_discovery": last.isoformat() if last else None}
        finally:
            session.close()

    return app


def main() -> None:
    import uvicorn

    settings = get_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    uvicorn.run(create_app(make_session_factory(engine)), host="0.0.0.0", port=8000)
```

`applyloop/web/templates/base.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>applyloop</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { text-align: left; padding: .5rem; border-bottom: 1px solid #ddd; }
    .score { font-weight: 700; }
    .rationale { color: #555; font-size: .9em; }
  </style>
</head>
<body>
  <h1>applyloop</h1>
  {% block content %}{% endblock %}
</body>
</html>
```

`applyloop/web/templates/feed.html`:
```html
{% extends "base.html" %}
{% block content %}
<form method="get">
  Min score: <input type="number" name="min_score" value="{{ min_score }}" min="0" max="100">
  <button type="submit">Filter</button>
</form>
<table>
  <tr><th>Score</th><th>Title</th><th>Company</th><th>Location</th><th>Why</th></tr>
  {% for job in jobs %}
  <tr>
    <td class="score">{{ job.score }}</td>
    <td><a href="{{ job.url }}" target="_blank" rel="noopener">{{ job.title }}</a></td>
    <td>{{ job.company.name }}</td>
    <td>{{ job.location }}</td>
    <td class="rationale">{{ job.score_rationale }}</td>
  </tr>
  {% endfor %}
</table>
{% endblock %}
```

- [ ] **Step 4: Run tests** — Expected: PASS. Full suite: `uv run pytest -v` all green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: FastAPI dashboard with ranked job feed"
```

---

### Task 12: Docker Compose + CI

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `applyloop-worker` and `applyloop-web` scripts (Tasks 10–11).
- Produces: `docker compose up` runs postgres + web + worker; CI runs ruff + pytest on push/PR.

- [ ] **Step 1: Write Dockerfile**

```dockerfile
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY applyloop ./applyloop
RUN uv pip install --system .
COPY config ./config
CMD ["applyloop-web"]
```

- [ ] **Step 2: Write docker-compose.yml**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: applyloop
      POSTGRES_PASSWORD: applyloop
      POSTGRES_DB: applyloop
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U applyloop"]
      interval: 5s
      timeout: 3s
      retries: 10

  web:
    build: .
    command: applyloop-web
    environment:
      DATABASE_URL: postgresql+psycopg://applyloop:applyloop@db:5432/applyloop
      CONFIG_DIR: /app/config
    env_file: [.env]
    ports: ["8000:8000"]
    volumes: ["./config:/app/config:ro"]
    depends_on:
      db: { condition: service_healthy }

  worker:
    build: .
    command: applyloop-worker
    environment:
      DATABASE_URL: postgresql+psycopg://applyloop:applyloop@db:5432/applyloop
      CONFIG_DIR: /app/config
    env_file: [.env]
    volumes: ["./config:/app/config:ro"]
    depends_on:
      db: { condition: service_healthy }

volumes:
  pgdata:
```

- [ ] **Step 3: Write .dockerignore**

```
.git
.venv
.env
*.db
__pycache__
tests
docs
```

- [ ] **Step 4: Write CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -v
```

- [ ] **Step 5: Verify locally**

Run: `uv run pytest -v && uv run ruff check .` — Expected: all green.
If Docker is available: `docker compose build` succeeds (don't require `up` in CI).

- [ ] **Step 6: Update README quickstart**

Add to `README.md` after Status:
```markdown
## Quickstart

1. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`.
2. `cp config/profile.yaml.example config/profile.yaml` (repeat for
   `preferences.yaml`, `companies.yaml`) and edit with your details.
3. `docker compose up --build` — dashboard at http://localhost:8000.

Local dev without Docker: `uv sync`, then `uv run applyloop-worker` in one
terminal and `uv run applyloop-web` in another (uses SQLite by default).
```

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: Docker Compose deploy and GitHub Actions CI"
```

---

## Milestone 1 acceptance check (manual, after all tasks)

1. Copy real config files with 3–5 real companies (e.g. find any Greenhouse/Lever/Ashby company you like), real profile.
2. `uv run applyloop-worker` — first tick discovers jobs; with API key set, scoring runs.
3. `uv run applyloop-web` — feed shows ranked jobs with rationales; `min_score` filter works.
4. `git push` — CI green on GitHub.

## Future milestone plans (separate documents, in order)

2. **Tailoring** — profile→Sonnet→resume JSON→PDF (WeasyPrint), cover letter, anti-fabrication validator.
3. **Approval queue** — Telegram bot + dashboard queue, Application records, approval events.
4. **Apply-bot** — Playwright per-ATS fillers (Greenhouse→Lever→Ashby), dry-run default, HTML fixtures.
5. **Tracker & polish** — receipts, reminders, issues panel, retries/backoff.
6. **Cloud deploy** — VPS, Caddy+basic-auth, Alembic migrations, pg_dump backups, heartbeat alerting.
