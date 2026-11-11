import json
from datetime import time
from pathlib import Path

import pytest

from tea import config
from tea.settings import Settings, SettingsError, load, save


def test_defaults() -> None:
    s = Settings()
    assert (s.focus_day, s.focus_time) == (0, time(9, 0))
    assert (s.pick_enabled, s.pick_day, s.pick_time) == (True, 3, time(9, 0))
    assert (s.prompt_day, s.prompt_time) == (4, time(18, 0))
    assert s.questions_per_login == 3
    assert s.dismiss_pause_minutes == 120
    assert s.carry_over_weeks == 1
    assert s.reminders_enabled is True
    assert s.claude_url == "https://claude.ai/new"
    assert s.include_style_notes is True
    assert s.style_notes == ""
    assert s.max_answer_words == 1500
    assert s.default_length == "standard"
    assert s.appearance == "system"
    assert s.reduce_motion is False
    assert s.pause_automation is False


def test_no_api_key_model_or_disclosure_fields() -> None:
    names = set(Settings.model_fields)
    assert not {n for n in names if "api" in n or "model" in n or "disclosure" in n}


def test_first_run_seeds_interests_and_writes_file() -> None:
    seed = json.loads((config.resource_dir("data") / "interests.json").read_text())
    s = load()
    assert s.interests == seed["interests"]
    assert s.region == seed["region"]
    assert config.settings_path().is_file()


def test_round_trip() -> None:
    s = Settings(
        focus_day=1,
        focus_time=time(7, 30),
        interests=["tea"],
        region="",
        style_notes="Short sentences.\nNo jargon.",
        carry_over_weeks=3,
        appearance="dark",
    )
    save(s)
    assert load() == s


def test_round_trip_to_explicit_path(tmp_path: Path) -> None:
    path = tmp_path / "elsewhere" / "s.json"
    s = Settings(questions_per_login=0)
    save(s, path)
    assert load(path) == s


def test_unknown_keys_ignored() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"carry_over_weeks": 2, "api_key": "x", "future_thing": [1]}))
    s = load()
    assert s.carry_over_weeks == 2
    assert not hasattr(s, "api_key")


def test_missing_keys_take_defaults_without_reseeding() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    assert load().interests == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("questions_per_login", 6),
        ("questions_per_login", -1),
        ("carry_over_weeks", 4),
        ("focus_day", 7),
        ("focus_time", "25:00"),
        ("default_length", "huge"),
        ("appearance", "neon"),
        ("claude_url", "ftp://claude.ai"),
        ("max_answer_words", 10),
        ("reminders_enabled", "maybe"),
    ],
)
def test_bad_value_rejected_with_clear_message(key: str, value: object) -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({key: value}))
    with pytest.raises(SettingsError) as err:
        load()
    assert key in str(err.value)


def test_bad_value_rejected_on_assignment() -> None:
    s = Settings()
    with pytest.raises(ValueError):
        s.questions_per_login = 9


def test_broken_json_rejected() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    with pytest.raises(SettingsError) as err:
        load()
    assert "settings.json" in str(err.value)


def test_top_level_must_be_object() -> None:
    path = config.settings_path()
    path.parent.mkdir(parents=True)
    path.write_text("[]")
    with pytest.raises(SettingsError):
        load()


def test_save_leaves_no_temp_files() -> None:
    save(Settings())
    assert [p.name for p in config.config_dir().iterdir()] == ["settings.json"]
