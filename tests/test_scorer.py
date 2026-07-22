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
