# applyloop — design spec

**Date:** 2026-07-22 · **Status:** approved

## What this is

A single-user, self-hosted AI job-application system (in the spirit of commercial tools like Tsenta, implemented entirely from scratch): it discovers new US tech job postings, scores them against the user's résumé, tailors a résumé + cover letter per job, queues each application for one-tap approval, then auto-submits via browser automation and tracks everything with receipts.

## Product decisions

- **Single-user personal tool.** No auth beyond dashboard basic-auth, no billing, no multi-tenancy.
- **Approve-then-apply.** Nothing is ever submitted without explicit user approval (Telegram button or dashboard).
- **US tech roles.** Greenhouse/Lever/Ashby/Workable dominate this market and all expose free, no-auth public JSON job APIs — discovery is API polling, not scraping.
- **Cost target:** ~$6–12/mo VPS + ~$5–15/mo LLM API (Claude Haiku for bulk scoring, Claude Sonnet for the few tailorings/day that matter).
- **Open source, MIT.** Distinct name ("applyloop"), no code copied from any existing project (AIHawk/ApplyPilot studied for ideas only), all dependencies permissively licensed, personal data (résumé, keys, DB, generated PDFs) gitignored — the repo ships no personal data and no scraped job content.

## Architecture

One VPS running Docker Compose: **Postgres** + **FastAPI web app** (dashboard/approval queue) + **worker** (APScheduler pipeline with Playwright inside).

```
ATS public APIs (Greenhouse/Lever/Ashby/Workable) + JobSpy (LinkedIn/Indeed, optional, off by default)
  → poll every 2–4h → jobs table (dedup by hash(company,title,location))
  → LLM scorer (Claude Haiku): 0–100 vs master résumé + preferences.yaml
  → LLM tailor (Claude Sonnet, jobs ≥ threshold ~70): tailored résumé JSON → ATS-friendly PDF + short cover letter
     · hard rule: reorder/rephrase/emphasize only — NEVER fabricate experience, dates, skills
  → approval queue: Telegram message (score, rationale, PDF link, ✅/❌ buttons) + dashboard with PDF preview/edit
  → on approve: Playwright apply-bot, deterministic per-ATS form fillers (Greenhouse, Lever, Ashby);
     LLM fallback only for unknown free-text questions (flagged in receipt)
     · CAPTCHA/login-wall → status "manual needed", prefilled answers + PDF attached; no CAPTCHA solvers
  → tracker: queued/approved/submitted/manual-needed/rejected/interview,
     receipts (submission screenshot + timestamp + PDF hash), follow-up reminders
```

**Self-growing watchlist:** seed `companies.yaml` + harvesting `boards.greenhouse.io` / `jobs.lever.co` / `jobs.ashbyhq.com` apply-URLs from JobSpy sweeps to extract new board tokens.

## Components

| Component | Responsibility | Key deps |
|---|---|---|
| `db` | SQLAlchemy models + Alembic migrations: companies, jobs, applications, events | SQLAlchemy, Alembic, Postgres |
| `discovery` | Per-ATS pollers (public JSON APIs), dedup, optional JobSpy sweep + token harvest | httpx, python-jobspy |
| `scoring` | Haiku structured scoring: score, 2-line rationale, matched/missing skills | anthropic |
| `tailoring` | profile.yaml → Sonnet → resume_schema JSON → PDF template + cover letter; anti-fabrication validation (employers/titles/dates must exact-match profile) | anthropic, WeasyPrint |
| `apply` | Playwright per-ATS fillers; dry-run default; LLM fallback for unknown questions | playwright |
| `notify` | Telegram approvals + alerts | python-telegram-bot |
| `web` | FastAPI + Jinja2/HTMX dashboard: feed, approval queue, tracker, issues panel | FastAPI, Jinja2 |
| `worker` | APScheduler: discover → score → tailor → notify; consumes approval events → apply | APScheduler |

## Error handling

Every pipeline stage is idempotent and logged per-job (events table); failures retry with backoff and surface in a dashboard "issues" panel. Worker heartbeat is visible in the dashboard; a stalled worker triggers a Telegram alert.

## Testing

- Per-ATS fillers: replay tests against saved HTML fixtures of real forms + live `--dry-run` (fills, screenshots, never submits). Dry-run is the default until a config flag flips.
- Scorer/tailor: golden-file prompt tests; manual fabrication review of first tailored PDFs.
- Pollers: unit tests on saved API JSON fixtures; smoke test against 2–3 real public boards (read-only).
- End-to-end: 2 days full-pipeline dry-run locally, then one supervised real submission before normal operation.

## Deployment

Small VPS (Hetzner CX22 / DO $6): Docker Compose, Caddy HTTPS + basic-auth on dashboard, nightly `pg_dump` to object storage, healthcheck alerting.

## Honest constraints (go in README)

Auto-submission can conflict with some sites' ToS and bot defenses change; the system always degrades to "manual needed with everything prepped." JobSpy scraping is optional and off by default.
