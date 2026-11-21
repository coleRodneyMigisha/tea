"""Main window: left rail with four destinations and one content area (UI_DESIGN 2)."""

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import QSettings, QSize, Qt, Signal
from PySide6.QtGui import QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from tea import config
from tea.clock import Clock, SystemClock
from tea.settings import Settings
from tea.ui import strings
from tea.ui.screens.drafts import DraftsScreen
from tea.ui.screens.new_blog import NewBlogScreen
from tea.ui.screens.settings import SettingsScreen
from tea.ui.screens.this_week import ThisWeekScreen
from tea.ui.theme import Theme

SCREEN_NAMES = ("this_week", "new_blog", "drafts", "settings")
_NAV = (
    ("this_week", strings.NAV_WEEK, "week"),
    ("new_blog", strings.NAV_NEW, "new-blog"),
    ("drafts", strings.NAV_DRAFTS, "drafts"),
    ("settings", strings.NAV_SETTINGS, "settings"),
)


class MainWindow(QMainWindow):
    pause_changed = Signal(bool)

    def __init__(
        self,
        theme: Theme,
        settings: Settings,
        save_settings: Callable[[Settings], None],
        remember_geometry: bool = True,
        clock: Clock | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme
        self.settings = settings
        self._save_settings = save_settings
        self._remember = remember_geometry
        self._hide_on_close = False
        self.closed_for_real = False
        self.setWindowTitle(strings.APP_NAME)
        self.setWindowIcon(theme.app_icon())
        self.setMinimumSize(QSize(theme.size("min_width"), theme.size("min_height")))

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.rail = self._build_rail()
        row.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        self.week_screen = ThisWeekScreen(theme, reduce_motion=settings.reduce_motion)
        self.drafts_screen = DraftsScreen(theme)
        self.new_blog_screen = NewBlogScreen(theme)
        self.settings_screen = SettingsScreen(theme, settings, clock or SystemClock())
        self.settings_screen.changed.connect(self._on_settings_screen)
        self.screens: dict[str, QWidget] = {
            "this_week": self.week_screen,
            "new_blog": self.new_blog_screen,
            "drafts": self.drafts_screen,
            "settings": self.settings_screen,
        }
        for name in SCREEN_NAMES:
            self.stack.addWidget(self.screens[name])
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._shortcuts: dict[str, QShortcut] = {}
        for index, name in enumerate(SCREEN_NAMES, start=1):
            self._add_shortcut(f"Ctrl+{index}", partial(self.show_screen, name))
        self._add_shortcut("Ctrl+N", lambda: self.show_screen("new_blog"))

        self._restore_geometry()
        self.show_screen("this_week")
        self._refresh_footer()
        theme.changed.connect(self._refresh_icons)

    # Rail

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rail.setFixedWidth(self.theme.size("rail_width"))
        col = QVBoxLayout(rail)
        t = self.theme
        col.setContentsMargins(t.space(2), t.space(4), t.space(2), t.space(3))
        col.setSpacing(t.space(0))

        brand = QHBoxLayout()
        brand.setSpacing(t.space(1))
        brand.setContentsMargins(t.space(1), 0, 0, t.space(4))
        self._brand_icon = QLabel()
        side = t.size("wordmark_icon")
        self._brand_icon.setPixmap(t.app_icon().pixmap(QSize(side, side)))
        brand.addWidget(self._brand_icon)
        wordmark = QLabel(strings.WORDMARK)
        wordmark.setObjectName("Wordmark")
        brand.addWidget(wordmark)
        brand.addStretch(1)
        col.addLayout(brand)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for name, label, _icon in _NAV:
            button = QPushButton(label)
            button.setProperty("nav", True)
            button.setCheckable(True)
            button.setIconSize(t.icon_size())
            button.setMinimumHeight(t.space(5))
            button.setAccessibleName(label)
            button.clicked.connect(lambda _=False, n=name: self.show_screen(n))
            self._group.addButton(button)
            self.nav_buttons.append(button)
            col.addWidget(button)
        self._refresh_icons()

        col.addStretch(1)
        self.footer = QPushButton()
        self.footer.setObjectName("RailFooter")
        self.footer.setToolTip(strings.AUTOMATION_TOOLTIP)
        self.footer.setMinimumHeight(t.space(5))
        self.footer.clicked.connect(lambda: self.set_paused(not self.settings.pause_automation))
        col.addWidget(self.footer)
        return rail

    def _refresh_icons(self) -> None:
        for button, (_name, _label, icon) in zip(self.nav_buttons, _NAV, strict=True):
            button.setIcon(self.theme.icon(icon, "muted", on_role="ink"))
        if hasattr(self, "footer"):
            self._refresh_footer()

    def _refresh_footer(self) -> None:
        paused = self.settings.pause_automation
        self.footer.setText(strings.AUTOMATION_PAUSED if paused else strings.AUTOMATION_ON)
        # Status is text plus color plus an icon (UI_DESIGN 1, principle 3).
        self.footer.setProperty("state", "paused" if paused else "on")
        self.footer.setIcon(self.theme.icon("pause", "amber") if paused else QIcon())
        self.footer.setIconSize(self.theme.icon_size())
        self.footer.style().unpolish(self.footer)
        self.footer.style().polish(self.footer)
        self.footer.setAccessibleName(self.footer.text())

    def set_paused(self, paused: bool) -> None:
        self.settings_screen.flush()  # notes typed a moment ago reach self.settings first
        if paused == self.settings.pause_automation:
            return
        self.settings = self.settings.model_copy(update={"pause_automation": paused})
        self._save_settings(self.settings)
        self._refresh_footer()
        self.settings_screen.set_settings(self.settings)
        self.pause_changed.emit(paused)

    def _on_settings_screen(self, new: object) -> None:
        assert isinstance(new, Settings)
        was_paused = self.settings.pause_automation
        self.settings = new
        self._save_settings(new)
        self._refresh_footer()
        if new.pause_automation != was_paused:
            self.pause_changed.emit(new.pause_automation)

    # Screens and shortcuts

    def show_screen(self, name: str) -> None:
        index = SCREEN_NAMES.index(name)
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    def current_screen(self) -> str:
        return SCREEN_NAMES[self.stack.currentIndex()]

    def _add_shortcut(self, keys: str, action: Callable[[], None]) -> None:
        shortcut = QShortcut(QKeySequence(keys), self)
        shortcut.activated.connect(action)
        self._shortcuts[keys] = shortcut

    def trigger_shortcut(self, keys: str) -> bool:
        """Activate a shortcut by its key text (used by tests and the snapshot tool)."""
        shortcut = self._shortcuts.get(keys)
        if shortcut is None:
            return False
        shortcut.activated.emit()
        return True

    # Window lifecycle

    def set_hide_on_close(self, hide: bool) -> None:
        self._hide_on_close = hide

    def bring_to_front(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _store(self) -> QSettings:
        return QSettings(str(config.window_state_path()), QSettings.Format.IniFormat)

    def _restore_geometry(self) -> None:
        self.resize(self.theme.size("default_width"), self.theme.size("default_height"))
        if not self._remember:
            return
        value = self._store().value("geometry")
        if value is not None:
            self.restoreGeometry(value)  # type: ignore[arg-type]

    def save_geometry(self) -> None:
        if not self._remember:
            return
        config.window_state_path().parent.mkdir(parents=True, exist_ok=True)
        store = self._store()
        store.setValue("geometry", self.saveGeometry())
        store.sync()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        self.save_geometry()
        if self._hide_on_close:
            event.ignore()
            self.hide()
            return
        self.closed_for_real = True
        event.accept()
