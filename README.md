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

## Using a Claude subscription instead of an API key

If you have a Claude Pro/Max subscription and [Claude Code](https://claude.com/claude-code)
installed, applyloop can route its LLM calls through `claude -p` (headless mode) so
scoring costs nothing beyond your subscription:

1. Install Claude Code and log in (`claude` → `/login`), or on a server run
   `claude setup-token` and export the printed token as `CLAUDE_CODE_OAUTH_TOKEN`.
2. Set `LLM_BACKEND=claude_code` in `.env`.
3. Run the worker directly on that machine: `uv run applyloop-worker`.

Notes: this path is for personal use of your own subscription; it shares your
subscription's rolling rate limits with your interactive Claude Code sessions, and
large first-run backfills may need to spread across a few hours. The Docker Compose
worker image does not include the Claude Code CLI — use the API backend there, or run
the worker on the host.

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
