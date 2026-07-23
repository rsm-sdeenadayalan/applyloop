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
