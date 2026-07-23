import json
import stat
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
