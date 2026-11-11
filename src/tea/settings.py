"""Pydantic Settings model, load and save (JSON in the config dir).

Fields follow ARCHITECTURE section 9, minus the disclosure fields (owner decision, see DEVIATIONS).
"""

import json
import os
import tempfile
from datetime import time
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator

from tea import config

Weekday = Annotated[int, Field(ge=0, le=6, description="0 = Monday ... 6 = Sunday")]


class SettingsError(ValueError):
    """settings.json could not be read or holds an invalid value."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    # Schedule (DECISIONS D8)
    focus_day: Weekday = 0
    focus_time: time = time(9, 0)
    pick_enabled: StrictBool = True
    pick_day: Weekday = 3
    pick_time: time = time(9, 0)
    prompt_day: Weekday = 4
    prompt_time: time = time(18, 0)

    # Topic (D13)
    interests: list[str] = Field(default_factory=list)
    region: str = ""

    # Questions
    questions_per_login: Annotated[int, Field(ge=0, le=5)] = 3
    dismiss_pause_minutes: Annotated[int, Field(ge=0, le=24 * 60)] = 120

    # Carry-over (D3)
    carry_over_weeks: Annotated[int, Field(ge=0, le=3)] = 1

    # Reminders (D6)
    reminders_enabled: StrictBool = True

    # Hand-off
    claude_url: str = "https://claude.ai/new"
    include_style_notes: StrictBool = True
    style_notes: str = ""
    max_answer_words: Annotated[int, Field(ge=200, le=5000)] = 1500

    # Writing (D11)
    default_length: Literal["short", "standard", "long"] = "standard"

    # Appearance
    appearance: Literal["system", "light", "dark"] = "system"
    reduce_motion: StrictBool = False

    pause_automation: StrictBool = False

    @field_validator("claude_url")
    @classmethod
    def _https_only(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("must start with https://")
        return value

    @field_validator("focus_time", "pick_time", "prompt_time")
    @classmethod
    def _whole_minutes(cls, value: time) -> time:
        return value.replace(second=0, microsecond=0)


def _describe(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        field = ".".join(str(p) for p in e["loc"]) or "settings"
        parts.append(f"{field}: {e['msg']} (got {e.get('input')!r})")
    return "; ".join(parts)


def _seed() -> Settings:
    path = config.resource_dir("data") / "interests.json"
    try:
        seed: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"{path.name} could not be read: {exc}") from exc
    if not isinstance(seed, dict):
        raise SettingsError(f"{path.name} must hold a JSON object")
    return Settings(interests=list(seed.get("interests", [])), region=seed.get("region", ""))


def load(path: Path | None = None) -> Settings:
    """Read settings. On first run, seed interests and region and write the file."""
    path = path or config.settings_path()
    if not path.exists():
        settings = _seed()
        try:
            save(settings, path)
        except OSError as exc:
            raise SettingsError(f"{path.name} could not be written: {exc}") from exc
        return settings
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"{path.name} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"{path.name} must hold a JSON object")
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise SettingsError(f"{path.name} has an invalid value. {_describe(exc)}") from exc


def save(settings: Settings, path: Path | None = None) -> None:
    """Write atomically, so a crash never leaves a half-written file."""
    path = path or config.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(settings.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
