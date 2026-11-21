"""Settings > Data and About actions: open folders, export a backup, run the checks."""

from pathlib import Path

import shiboken6
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QWidget

from tea import backup, config, doctor, workers
from tea.clock import Clock
from tea.ui import strings
from tea.ui.theme import Theme
from tea.ui.widgets.report_dialog import ReportDialog


class SettingsActions(QObject):
    """Talks back through `status` (a short line for the Data panel) and `busy`."""

    status = Signal(str)
    busy = Signal(bool)

    def __init__(self, theme: Theme, clock: Clock, owner: QWidget) -> None:
        super().__init__(owner)
        self.theme = theme
        self.clock = clock
        self.owner = owner
        self.checks_dialog: ReportDialog | None = None

    @staticmethod
    def _open_folder(folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_data(self) -> None:
        self._open_folder(config.data_dir())

    def open_logs(self) -> None:
        self._open_folder(config.log_path().parent)

    def export(self) -> None:
        start = str(Path.home() / backup.default_name(self.clock))
        chosen, _ = QFileDialog.getSaveFileName(
            self.owner, strings.EXPORT_TITLE, start, strings.EXPORT_FILTER
        )
        if not chosen:
            return
        dest = Path(chosen)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_name(dest.name + ".zip")
        self.status.emit(strings.BACKUP_WORKING)
        self.busy.emit(True)
        workers.run(
            backup.export_backup,
            dest,
            on_done=lambda _r: self._finished(strings.BACKUP_DONE.format(name=dest.name)),
            on_error=self._failed,
        )

    def _finished(self, text: str) -> None:
        if shiboken6.isValid(self):
            self.busy.emit(False)
            self.status.emit(text)

    def _failed(self, exc: BaseException) -> None:
        known = isinstance(exc, backup.BackupError)
        self._finished(str(exc) if known else strings.BACKUP_FAILED)

    def run_checks(self) -> None:
        text = doctor.report(doctor.run_checks())
        dialog = ReportDialog(self.theme, strings.SETTINGS_CHECKS_TITLE, text)
        self.checks_dialog = dialog
        dialog.show()
        dialog.raise_()
