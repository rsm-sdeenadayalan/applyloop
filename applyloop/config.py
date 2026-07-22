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
