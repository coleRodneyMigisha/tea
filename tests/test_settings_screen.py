"""Settings screen (UI_DESIGN 3.4): every item, validation messages, data and about actions."""

import zipfile
from datetime import time
from pathlib import Path

import pytest
from PySide6.QtCore import QTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QLabel,
    QPlainTextEdit,
    QPushButton,
)
from pytestqt.qtbot import QtBot

from tea import config
from tea.clock import FakeClock
from tea.db.connection import open_db
from tea.settings import Settings
from tea.ui import strings
from tea.ui.screens.settings import SettingsScreen
from tea.ui.theme import Theme


@pytest.fixture
def theme(qapp: QApplication) -> Theme:
    t = Theme(qapp, appearance="light", scale=1.0)
    t.apply()
    return t


@pytest.fixture
def emitted() -> list[Settings]:
    return []


@pytest.fixture
def screen(qtbot: QtBot, theme: Theme, clock: FakeClock, emitted: list[Settings]) -> SettingsScreen:
    s = SettingsScreen(theme, Settings(), clock)
    s.changed.connect(emitted.append)
    qtbot.addWidget(s)
    s.show()
    return s


def _texts(widget: SettingsScreen) -> list[str]:
    return [lb.text() for lb in widget.findChildren(QLabel)]


def test_every_section_of_the_design_is_there_in_order(screen: SettingsScreen) -> None:
    assert screen.section_titles() == [
        "Schedule", "Topic", "Questions", "Carry-over", "Reminders", "Hand-off",
        "Writing", "Appearance", "Data", "Automation", "About",
    ]  # fmt: skip


def test_controls_show_the_defaults(screen: SettingsScreen) -> None:
    s = Settings()
    assert screen.focus_day.currentIndex() == 0 and screen.focus_time.time().toPython() == time(9)
    assert screen.pick_day.currentIndex() == 3 and screen.pick_time.time().toPython() == time(9)
    assert screen.prompt_day.currentIndex() == 4
    assert screen.prompt_time.time().toPython() == time(18)
    assert screen.pick_enabled.isChecked()
    assert screen.interests.items() == []
    assert screen.region.text() == ""
    assert screen.per_login.value() == 3
    assert screen.dismiss_pause.value() == 120
    assert not screen.on_unlock.isChecked()  # off by default
    assert screen.carry_weeks.value() == 1
    assert screen.reminders.isChecked()
    assert screen.claude_url.text() == "https://claude.ai/new"
    assert screen.include_notes.isChecked()
    assert screen.style_notes.toPlainText() == ""
    assert screen.max_words.value() == s.max_answer_words
    assert screen.length.currentData() == "standard"
    assert screen.appearance.currentData() == "system"
    assert not screen.reduce_motion.isChecked()
    assert not screen.pause.isChecked()


def test_there_is_no_api_key_model_or_disclosure_setting(screen: SettingsScreen) -> None:
    words = " ".join(_texts(screen) + [b.text() for b in screen.findChildren(QPushButton)])
    checks = " ".join(c.text() for c in screen.findChildren(QCheckBox))
    for banned in ("api", "key", "model", "disclosure"):
        assert banned not in (words + " " + checks).lower().split(), banned


def test_style_notes_hint_is_the_design_text(screen: SettingsScreen) -> None:
    assert screen.style_notes.placeholderText() == (
        "Anything about how you write that the questions don't cover"
    )


def _t(text: str) -> QTime:
    return QTime.fromString(text, "HH:mm")


def _set_combo(box: QComboBox, data: object) -> None:
    box.setCurrentIndex(box.findData(data))


@pytest.mark.parametrize(
    ("field", "act", "expected"),
    [
        ("focus_day", lambda s: s.focus_day.setCurrentIndex(1), 1),
        ("focus_time", lambda s: s.focus_time.setTime(_t("08:30")), time(8, 30)),
        ("pick_day", lambda s: s.pick_day.setCurrentIndex(2), 2),
        ("pick_time", lambda s: s.pick_time.setTime(_t("07:15")), time(7, 15)),
        ("prompt_day", lambda s: s.prompt_day.setCurrentIndex(5), 5),
        ("prompt_time", lambda s: s.prompt_time.setTime(_t("20:00")), time(20)),
        ("pick_enabled", lambda s: s.pick_enabled.setChecked(False), False),
        ("region", lambda s: s.region.setText("Uganda"), "Uganda"),
        ("questions_per_login", lambda s: s.per_login.setValue(5), 5),
        ("dismiss_pause_minutes", lambda s: s.dismiss_pause.setValue(30), 30),
        ("carry_over_weeks", lambda s: s.carry_weeks.setValue(3), 3),
        ("reminders_enabled", lambda s: s.reminders.setChecked(False), False),
        ("questions_on_unlock", lambda s: s.on_unlock.setChecked(True), True),
        ("include_style_notes", lambda s: s.include_notes.setChecked(False), False),
        ("max_answer_words", lambda s: s.max_words.setValue(900), 900),
        ("default_length", lambda s: _set_combo(s.length, "long"), "long"),
        ("appearance", lambda s: _set_combo(s.appearance, "dark"), "dark"),
        ("reduce_motion", lambda s: s.reduce_motion.setChecked(True), True),
        ("pause_automation", lambda s: s.pause.setChecked(True), True),
    ],
)  # fmt: skip
def test_changing_a_control_emits_the_new_settings(
    screen: SettingsScreen, emitted: list[Settings], field: str, act: object, expected: object
) -> None:
    if field == "region":
        screen.region.setFocus()
    act(screen)  # type: ignore[operator]
    if field == "region":
        screen.region.editingFinished.emit()
    assert emitted, field
    assert getattr(emitted[-1], field) == expected


def test_pick_day_and_time_are_disabled_while_pick_is_off(screen: SettingsScreen) -> None:
    screen.pick_enabled.setChecked(False)
    assert not screen.pick_day.isEnabled() and not screen.pick_time.isEnabled()
    screen.pick_enabled.setChecked(True)
    assert screen.pick_day.isEnabled() and screen.pick_time.isEnabled()


def test_set_settings_updates_controls_without_emitting(
    screen: SettingsScreen, emitted: list[Settings]
) -> None:
    screen.set_settings(Settings(pause_automation=True, interests=["a", "b"], region="x"))
    assert screen.pause.isChecked()
    assert screen.interests.items() == ["a", "b"]
    assert screen.region.text() == "x"
    assert emitted == []


# Validation messages


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("http://claude.ai/new", strings.SETTINGS_URL_HTTPS),
        ("claude.ai/new", strings.SETTINGS_URL_HTTPS),
        ("", strings.SETTINGS_URL_EMPTY),
        ("   ", strings.SETTINGS_URL_EMPTY),
        ("https://", strings.SETTINGS_URL_NO_SITE),
        ("https://claude ai", strings.SETTINGS_URL_NO_SITE),
    ],
)
def test_bad_claude_link_shows_a_message_and_is_not_saved(
    screen: SettingsScreen, emitted: list[Settings], text: str, message: str
) -> None:
    screen.claude_url.setText(text)
    screen.claude_url.editingFinished.emit()
    assert emitted == []
    assert screen.claude_url_error.isVisible()
    assert screen.claude_url_error.text() == message


def test_a_good_claude_link_clears_the_message_and_saves(
    screen: SettingsScreen, emitted: list[Settings]
) -> None:
    screen.claude_url.setText("http://nope")
    screen.claude_url.editingFinished.emit()
    assert screen.claude_url_error.isVisible()
    screen.claude_url.setText("  https://claude.ai/project/abc  ")
    screen.claude_url.editingFinished.emit()
    assert not screen.claude_url_error.isVisible()
    assert emitted[-1].claude_url == "https://claude.ai/project/abc"


def test_validation_messages_follow_the_voice_rules() -> None:
    for text in (
        strings.SETTINGS_URL_HTTPS, strings.SETTINGS_URL_EMPTY, strings.SETTINGS_URL_NO_SITE,
        strings.SETTINGS_INTEREST_DUPLICATE, strings.SETTINGS_INTEREST_LONG,
    ):  # fmt: skip
        assert text.endswith(".") and "!" not in text and "oops" not in text.lower()


def test_settings_model_rejects_a_link_without_a_site() -> None:
    with pytest.raises(ValueError, match="site"):
        Settings(claude_url="https://")


# Interests


def test_interests_are_added_with_enter_and_removed_with_a_click(
    screen: SettingsScreen, emitted: list[Settings]
) -> None:
    box = screen.interests
    box.entry.setText("  Open data ")
    box.entry.returnPressed.emit()
    box.entry.setText("Climate")
    box.entry.returnPressed.emit()
    assert emitted[-1].interests == ["Open data", "Climate"]
    assert box.entry.text() == ""
    box.chip_buttons()[0].click()
    assert emitted[-1].interests == ["Climate"]
    assert [b.text() for b in box.chip_buttons()] == ["Climate"]


def test_blank_interest_is_ignored_and_duplicate_is_explained(
    screen: SettingsScreen, emitted: list[Settings]
) -> None:
    box = screen.interests
    box.entry.setText("   ")
    box.entry.returnPressed.emit()
    assert emitted == [] and box.message.text() == ""
    box.entry.setText("Climate")
    box.entry.returnPressed.emit()
    box.entry.setText("climate")
    box.entry.returnPressed.emit()
    assert len(emitted) == 1
    assert box.message.text() == strings.SETTINGS_INTEREST_DUPLICATE
    assert box.message.isVisible()
    assert box.entry.text() == "climate"  # kept so the owner can fix it


def test_overlong_interest_is_explained(screen: SettingsScreen, emitted: list[Settings]) -> None:
    screen.interests.entry.setText("x" * 200)
    screen.interests.entry.returnPressed.emit()
    assert emitted == []
    assert screen.interests.message.text() == strings.SETTINGS_INTEREST_LONG


def test_interest_chips_wrap_inside_the_width(qtbot: QtBot, theme: Theme, clock: FakeClock) -> None:
    s = SettingsScreen(
        theme,
        Settings(interests=[f"interest number {i}" for i in range(20)]),
        clock,
    )
    qtbot.addWidget(s)
    s.resize(900, 700)
    s.show()
    box = s.interests
    right = max(b.geometry().right() for b in box.chip_buttons())
    assert right <= box.width()
    tops = {b.geometry().top() for b in box.chip_buttons()}
    assert len(tops) > 1  # wrapped onto more than one row


# Style notes


def test_style_notes_save_after_a_pause_or_on_flush(
    qtbot: QtBot, screen: SettingsScreen, emitted: list[Settings]
) -> None:
    screen.style_notes.setPlainText("Short sentences. British spelling.")
    assert emitted == []
    screen.flush()
    assert emitted[-1].style_notes == "Short sentences. British spelling."
    emitted.clear()
    screen.style_notes.setPlainText("Changed")
    qtbot.waitUntil(lambda: bool(emitted), timeout=3000)
    assert emitted[-1].style_notes == "Changed"


def test_flush_without_changes_emits_nothing(
    screen: SettingsScreen, emitted: list[Settings]
) -> None:
    screen.flush()
    assert emitted == []


# Data and About


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> list[QUrl]:
    urls: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda u: urls.append(u)))
    return urls


def test_open_folders(screen: SettingsScreen, opened: list[QUrl]) -> None:
    screen.open_data_button.click()
    screen.open_logs_button.click()
    assert opened[0] == QUrl.fromLocalFile(str(config.data_dir()))
    assert opened[1] == QUrl.fromLocalFile(str(config.log_path().parent))
    assert config.data_dir().is_dir() and config.log_path().parent.is_dir()


def test_export_backup_writes_a_zip_and_says_so(
    qtbot: QtBot, screen: SettingsScreen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_db(config.db_path()).close()
    target = tmp_path / "out.zip"
    asked: list[str] = []

    def fake_dialog(*args: object, **_k: object) -> tuple[str, str]:
        asked.append(str(args[2]))
        return str(target), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_dialog))
    screen.export_button.click()
    qtbot.waitUntil(
        lambda: screen.data_status.text() == strings.BACKUP_DONE.format(name="out.zip"),
        timeout=5000,
    )
    assert asked[0].endswith("tea-backup-2026-11-13.zip")
    assert "tea.db" in zipfile.ZipFile(target).namelist()
    assert screen.data_status.text() == strings.BACKUP_DONE.format(name="out.zip")


def test_export_backup_cancelled_in_the_dialog_does_nothing(
    screen: SettingsScreen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    screen.export_button.click()
    assert screen.data_status.text() == ""


def test_export_backup_failure_is_explained(
    qtbot: QtBot, screen: SettingsScreen, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No database yet: nothing to back up.
    target = tmp_path / "out.zip"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), ""))
    )
    screen.export_button.click()
    qtbot.waitUntil(lambda: screen.data_status.text() == strings.BACKUP_NO_DB, timeout=5000)
    assert screen.data_status.text() == strings.BACKUP_NO_DB
    assert not target.exists()


def test_about_shows_the_version_and_run_checks_shows_the_report(
    qtbot: QtBot, screen: SettingsScreen
) -> None:
    assert "0.1.0" in screen.version_label.text()
    screen.checks_button.click()
    dialog = screen.checks_dialog
    assert isinstance(dialog, QDialog) and dialog.isVisible()
    box = dialog.findChild(QPlainTextEdit)
    assert box is not None and box.isReadOnly()
    text = box.toPlainText()
    assert "UI font:" in text and "Tray:" in text and "Prompts:" in text
    dialog.close()
