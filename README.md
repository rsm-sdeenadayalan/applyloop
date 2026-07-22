# applyloop

Self-hosted, single-user AI job application system: discovers new postings from
public ATS job APIs (Greenhouse, Lever, Ashby, Workable), scores them against
your résumé with an LLM, tailors application materials, queues them for your
one-tap approval, submits, and tracks everything.

**Status:** Milestone 1 (discover + score + feed) under construction.

## Quickstart

1. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`.
2. `cp config/profile.yaml.example config/profile.yaml` (repeat for
   `preferences.yaml`, `companies.yaml`) and edit with your details.
3. `docker compose up --build` — dashboard at http://localhost:8000.

Local dev without Docker: `uv sync`, then `uv run applyloop-worker` in one
terminal and `uv run applyloop-web` in another (uses SQLite by default).

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
