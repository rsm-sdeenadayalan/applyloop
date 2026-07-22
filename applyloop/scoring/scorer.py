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
