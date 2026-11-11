from pathlib import Path

from tea import config


def test_paths_follow_env_overrides(tmp_dirs: Path) -> None:
    assert config.data_dir() == tmp_dirs / "data"
    assert config.config_dir() == tmp_dirs / "config"
    assert config.state_dir() == tmp_dirs / "state"
    assert config.uploads_dir() == tmp_dirs / "data" / "uploads"
    assert config.db_path() == tmp_dirs / "data" / "tea.db"
    assert config.settings_path() == tmp_dirs / "config" / "settings.json"
    assert config.log_path() == tmp_dirs / "state" / "tea.log"


def test_default_paths_use_app_name(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in ("DATA", "CONFIG", "STATE"):
        monkeypatch.delenv(f"TEA_{name}_DIR")
    assert config.data_dir().name == "tea"
    assert config.config_dir().name == "tea"
    assert config.state_dir().name == "tea"


def test_resource_dirs_exist() -> None:
    assert (config.resource_dir("data") / "interests.json").is_file()
    assert (config.resource_dir("prompts") / "packet_draft.md").is_file()


def test_limits() -> None:
    assert config.MAX_ATTACHMENT_BYTES == 50 * 1024 * 1024
    assert config.MAX_ATTACHMENTS_PER_BLOG == 20
