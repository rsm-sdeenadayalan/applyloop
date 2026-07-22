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
