# Claude Code Subscription Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let applyloop's LLM calls run through the Claude Code CLI in headless mode (`claude -p`), so a user's Claude Pro/Max subscription powers scoring/tailoring at zero marginal cost, instead of a pay-per-token API key.

**Architecture:** A `ClaudeCodeClient` that mimics the exact anthropic-client surface the scorer already uses (`.messages.create(...)` returning a response whose first content block has `.type == "tool_use"` and `.input`), implemented by shelling out to `claude -p --output-format json --json-schema <tool schema>`. The scorer (`applyloop/scoring/scorer.py`) needs zero changes. Backend selection via `LLM_BACKEND` env var; `anthropic_api` stays the repo default.

**Tech Stack:** subprocess + json (stdlib only), pydantic settings, pytest with a fake `claude` executable.

## Global Constraints

- `anthropic_api` remains the default backend — the public repo must not steer users toward subscription workarounds; `claude_code` is opt-in and documented as personal-use.
- The scorer interface is frozen: `score_job(client, ...)` reads `resp.content` → first block with `type == "tool_use"` → `.input`. `ClaudeCodeClient` must satisfy it without scorer changes.
- Tests must not invoke the real `claude` binary and must not hit the network (use a fake executable on PATH/tmp).
- CLI envelope facts (verified live on claude CLI 2.1.218): success → JSON object with `"subtype": "success"`, `"is_error": false`, and `"structured_output": <object matching the schema>`; `--model` accepts aliases (`haiku`/`sonnet`/`opus`); `--system-prompt`, `--json-schema` are the flag names.
- Line length 100 (ruff); all timestamps UTC; no personal data committed.

---

### Task 1: ClaudeCodeClient backend + settings

**Files:**
- Create: `applyloop/llm.py`, `tests/test_llm.py`
- Modify: `applyloop/settings.py`

**Interfaces:**
- Consumes: `Settings` (existing pydantic-settings class).
- Produces:
  - New `Settings` fields: `llm_backend: str = "anthropic_api"` (values `anthropic_api` | `claude_code`), `claude_code_binary: str = "claude"`, `claude_code_timeout: int = 180`.
  - `applyloop.llm.ClaudeCodeError(RuntimeError)`
  - `applyloop.llm.ClaudeCodeClient(binary: str = "claude", timeout: int = 180)` with `.messages.create(*, model, max_tokens, system, tools, tool_choice, messages) -> resp` where `resp.content[0].type == "tool_use"` and `resp.content[0].input` is the parsed structured output dict.
  - `applyloop.llm._map_model(model: str) -> str` — `"haiku" in model` → `"haiku"`, `"sonnet"` → `"sonnet"`, `"opus"` → `"opus"`, else pass through unchanged.

- [ ] **Step 1: Write failing tests**

`tests/test_llm.py`:
```python
import json
import stat
import subprocess
from pathlib import Path

import pytest

from applyloop.llm import ClaudeCodeClient, ClaudeCodeError, _map_model

SCHEMA = {
    "type": "object",
    "properties": {"score": {"type": "integer"}},
    "required": ["score"],
}
TOOL = {"name": "report_match", "description": "d", "input_schema": SCHEMA}


def make_fake_claude(tmp_path: Path, body: str) -> str:
    """Write a fake `claude` executable that logs its argv and prints a canned envelope."""
    script = tmp_path / "claude"
    script.write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/argv.txt\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


SUCCESS_ENVELOPE = json.dumps(
    {"subtype": "success", "is_error": False, "structured_output": {"score": 88}}
)


def test_create_returns_tool_use_block(tmp_path):
    binary = make_fake_claude(tmp_path, f"cat <<'EOF'\n{SUCCESS_ENVELOPE}\nEOF")
    client = ClaudeCodeClient(binary=binary)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You score jobs.",
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "report_match"},
        messages=[{"role": "user", "content": "JOB: DS at Acme"}],
    )
    block = resp.content[0]
    assert block.type == "tool_use"
    assert block.input == {"score": 88}
    argv = (tmp_path / "argv.txt").read_text()
    assert "--model haiku" in argv
    assert "--json-schema" in argv
    assert "--output-format json" in argv
    assert "You score jobs." in argv
    assert "JOB: DS at Acme" in argv


def test_error_envelope_raises(tmp_path):
    envelope = json.dumps({"subtype": "error", "is_error": True, "result": "limit reached"})
    binary = make_fake_claude(tmp_path, f"cat <<'EOF'\n{envelope}\nEOF")
    client = ClaudeCodeClient(binary=binary)
    with pytest.raises(ClaudeCodeError, match="limit reached"):
        client.messages.create(
            model="haiku", max_tokens=10, system="s", tools=[TOOL],
            tool_choice={}, messages=[{"role": "user", "content": "x"}],
        )


def test_nonzero_exit_raises(tmp_path):
    binary = make_fake_claude(tmp_path, "echo boom >&2\nexit 1")
    client = ClaudeCodeClient(binary=binary)
    with pytest.raises(ClaudeCodeError, match="boom"):
        client.messages.create(
            model="haiku", max_tokens=10, system="s", tools=[TOOL],
            tool_choice={}, messages=[{"role": "user", "content": "x"}],
        )


def test_missing_structured_output_raises(tmp_path):
    envelope = json.dumps({"subtype": "success", "is_error": False, "result": "no json"})
    binary = make_fake_claude(tmp_path, f"cat <<'EOF'\n{envelope}\nEOF")
    client = ClaudeCodeClient(binary=binary)
    with pytest.raises(ClaudeCodeError, match="structured_output"):
        client.messages.create(
            model="haiku", max_tokens=10, system="s", tools=[TOOL],
            tool_choice={}, messages=[{"role": "user", "content": "x"}],
        )


def test_map_model():
    assert _map_model("claude-haiku-4-5-20251001") == "haiku"
    assert _map_model("claude-sonnet-5") == "sonnet"
    assert _map_model("claude-opus-4-8") == "opus"
    assert _map_model("weird-model") == "weird-model"


def test_timeout_raises(tmp_path):
    binary = make_fake_claude(tmp_path, "sleep 5")
    client = ClaudeCodeClient(binary=binary, timeout=1)
    with pytest.raises(ClaudeCodeError, match="timed out"):
        client.messages.create(
            model="haiku", max_tokens=10, system="s", tools=[TOOL],
            tool_choice={}, messages=[{"role": "user", "content": "x"}],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm.py -v` — Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

`applyloop/llm.py`:
```python
"""LLM backends. ClaudeCodeClient runs prompts through the Claude Code CLI in
headless mode so a Claude Pro/Max subscription can power scoring instead of an
API key. It mimics the small slice of the anthropic client surface that
applyloop.scoring.scorer uses: messages.create(...) -> resp.content[0].input.
"""

import json
import subprocess
from dataclasses import dataclass


class ClaudeCodeError(RuntimeError):
    pass


def _map_model(model: str) -> str:
    for alias in ("haiku", "sonnet", "opus"):
        if alias in model:
            return alias
    return model


@dataclass
class _ToolUseBlock:
    input: dict
    type: str = "tool_use"


@dataclass
class _Response:
    content: list


class _Messages:
    def __init__(self, binary: str, timeout: int):
        self._binary = binary
        self._timeout = timeout

    def create(self, *, model, max_tokens, system, tools, tool_choice, messages) -> _Response:
        del max_tokens, tool_choice  # CLI equivalents not needed; schema forces the shape
        schema = tools[0]["input_schema"]
        prompt = messages[0]["content"]
        cmd = [
            self._binary, "-p",
            "--model", _map_model(model),
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--system-prompt", system,
            prompt,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self._timeout, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCodeError(f"claude CLI timed out after {self._timeout}s") from exc
        if proc.returncode != 0:
            raise ClaudeCodeError(
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:500]}"
            )
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeError(f"unparseable CLI output: {proc.stdout[:500]}") from exc
        if envelope.get("is_error") or envelope.get("subtype") != "success":
            raise ClaudeCodeError(
                f"claude CLI error: {str(envelope.get('result', envelope))[:500]}"
            )
        structured = envelope.get("structured_output")
        if not isinstance(structured, dict):
            raise ClaudeCodeError("claude CLI response missing structured_output")
        return _Response(content=[_ToolUseBlock(input=structured)])


class ClaudeCodeClient:
    def __init__(self, binary: str = "claude", timeout: int = 180):
        self.messages = _Messages(binary, timeout)
```

`applyloop/settings.py` — add fields to `Settings`:
```python
    llm_backend: str = "anthropic_api"  # anthropic_api | claude_code
    claude_code_binary: str = "claude"
    claude_code_timeout: int = 180
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_llm.py -v` (7 PASS), full `uv run pytest -v`, `uv run ruff check .`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Claude Code CLI backend for subscription-powered scoring"
```

---

### Task 2: Backend wiring, env template, README

**Files:**
- Modify: `applyloop/worker.py`, `tests/test_worker.py`, `.env.example`, `README.md`

**Interfaces:**
- Consumes: `ClaudeCodeClient`, `Settings.llm_backend` (Task 1); existing `pipeline_tick`/`build_scheduler`/`main`.
- Produces:
  - `applyloop.worker.build_llm_client(settings) -> object | None` — `"claude_code"` → `ClaudeCodeClient(binary=settings.claude_code_binary, timeout=settings.claude_code_timeout)`; `"anthropic_api"` → `anthropic.Anthropic(api_key=...)` if `settings.anthropic_api_key` else `None`; unknown backend → raise `ValueError`.
  - `pipeline_tick` skip condition becomes `llm_client is None` (message: `"skipped: no LLM backend configured"`); it must no longer read `anthropic_api_key` directly.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_worker.py`:
```python
def test_build_llm_client_claude_code(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude_code")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from applyloop.llm import ClaudeCodeClient
    from applyloop.settings import Settings
    from applyloop.worker import build_llm_client

    client = build_llm_client(Settings(_env_file=None, llm_backend="claude_code"))
    assert isinstance(client, ClaudeCodeClient)


def test_build_llm_client_api_without_key_is_none():
    from applyloop.settings import Settings
    from applyloop.worker import build_llm_client

    assert build_llm_client(Settings(_env_file=None, anthropic_api_key="")) is None


def test_build_llm_client_unknown_backend():
    import pytest

    from applyloop.settings import Settings
    from applyloop.worker import build_llm_client

    with pytest.raises(ValueError):
        build_llm_client(Settings(_env_file=None, llm_backend="nope"))
```

Existing `test_pipeline_tick_without_api_key` keeps passing (llm_client=None still skips) — update its Event-message expectation only if it asserts the message text.

- [ ] **Step 2: Run tests to verify they fail** — `uv run pytest tests/test_worker.py -v`.

- [ ] **Step 3: Implement**

`applyloop/worker.py`:
```python
def build_llm_client(settings):
    if settings.llm_backend == "claude_code":
        from applyloop.llm import ClaudeCodeClient

        return ClaudeCodeClient(
            binary=settings.claude_code_binary, timeout=settings.claude_code_timeout
        )
    if settings.llm_backend == "anthropic_api":
        if not settings.anthropic_api_key:
            return None
        import anthropic

        return anthropic.Anthropic(api_key=settings.anthropic_api_key)
    raise ValueError(f"unknown LLM_BACKEND: {settings.llm_backend}")
```

In `pipeline_tick`, replace the skip condition:
```python
        if llm_client is None:
            session.add(Event(stage="scoring", message="skipped: no LLM backend configured"))
            session.commit()
            return new, 0
```
(remove the `get_settings().anthropic_api_key` check). In `main()`, replace the inline anthropic construction with `llm_client = build_llm_client(settings)`.

- [ ] **Step 4: Update .env.example**

```
# LLM backend: anthropic_api (default, needs ANTHROPIC_API_KEY)
# or claude_code (uses the Claude Code CLI + your Claude Pro/Max subscription)
LLM_BACKEND=anthropic_api
DATABASE_URL=postgresql+psycopg://applyloop:applyloop@localhost:5432/applyloop
ANTHROPIC_API_KEY=
```

- [ ] **Step 5: Add README section** (after Quickstart)

```markdown
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
```

- [ ] **Step 6: Run everything** — `uv run pytest -v` (all pass), `uv run ruff check .` (clean).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: select LLM backend via LLM_BACKEND; document subscription mode"
```

---

## Verification (manual, after tasks)

1. `LLM_BACKEND=claude_code` in local `.env`, seed a real `companies.yaml` with 1-2 Greenhouse/Lever boards.
2. Run one pipeline tick against a temp SQLite DB — confirm jobs discovered and scored via the CLI (events show no errors; scores/rationales look sane).
3. `git push` — CI stays green (CI never invokes the real CLI).
