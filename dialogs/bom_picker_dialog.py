from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from bom_finder import find_recent_boms

# Scanned once per process, not once per dialog. verify_main reopens the picker
# after every run, and paying the share walk again each time would make the
# fix-and-recheck loop feel broken.
_SHORTLIST_CACHE: list[tuple[str, float]] | None = None


class _ScanThread(QThread):
    """Walks the share off the UI thread.

    Warm it is about a second, but this is a network drive: cold, busy, or with
    W: not mapped it can block for much longer, and a frozen window on startup
    is precisely the "nothing happens" failure this app has already worn once.
    """

    finished_scan = Signal(list)

    def __init__(self, scan: dict, parent=None):
        super().__init__(parent)
        self._scan = dict(scan)

    def run(self) -> None:
        try:
            hits = find_recent_boms(**self._scan)
        except Exception:
            hits = []
        self.finished_scan.emit(hits)


class BomPickerDialog(QDialog):
    """Front door for the frozen verification build.

    The .bat launcher takes its BOM by drag-and-drop, but an exe opened from a
    shortcut gets no argument at all, so it has to ask. The shortlist is there
    because the answer is nearly always one of the last few BOMs exported to
    the share, and navigating to it by hand is the slow part.
    """

    def __init__(self, data_dir: str, scan: dict, parent=None):
        super().__init__(parent)
        self.selected_path: str | None = None
        self._scan_settings = dict(scan)
        self._scan: _ScanThread | None = None
        self._search_root = self._scan_settings.get("root", "")

        self.setWindowTitle("Verify Inventor BOM")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Check an Inventor BOM for missing DXFs and unknown descriptions.\n"
            "Writes a report next to the BOM. No RADAN CSV is produced."
        ))

        self.list_label = QLabel()
        layout.addWidget(self.list_label)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(self._accept_item)
        self.list.itemSelectionChanged.connect(self._sync_verify_button)
        layout.addWidget(self.list)

        self.status = QLabel("No BOM selected.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        rules = QLabel(f"Rule tables: {data_dir}")
        rules.setWordWrap(True)
        layout.addWidget(rules)

        buttons = QHBoxLayout()
        self.verify_button = QPushButton("Verify Selected")
        self.verify_button.setDefault(True)
        self.verify_button.setEnabled(False)
        self.verify_button.clicked.connect(self._accept_selected)
        buttons.addWidget(self.verify_button)

        browse = QPushButton("Select BOM...")
        browse.clicked.connect(self.choose_bom)
        buttons.addWidget(browse)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(lambda: self.start_scan(force=True))
        buttons.addWidget(self.refresh_button)

        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.start_scan()

    # ---- shortlist

    def start_scan(self, *, force: bool = False) -> None:
        global _SHORTLIST_CACHE

        if not self._search_root:
            self.list_label.setText("Recent BOMs: shortlist disabled.")
            return
        if _SHORTLIST_CACHE is not None and not force:
            self._populate(_SHORTLIST_CACHE)
            return

        self.list_label.setText(f"Recent BOMs in {self._search_root} - scanning...")
        self.refresh_button.setEnabled(False)
        self._scan = _ScanThread(self._scan_settings, self)
        self._scan.finished_scan.connect(self._scan_done)
        self._scan.start()

    def _scan_done(self, hits: list) -> None:
        global _SHORTLIST_CACHE
        _SHORTLIST_CACHE = hits
        self.refresh_button.setEnabled(True)
        self._populate(hits)

    def _populate(self, hits: list[tuple[str, float]]) -> None:
        self.list.clear()
        if not hits:
            self.list_label.setText(
                f"Recent BOMs in {self._search_root} - none found (drive not mapped?)."
            )
            self._sync_verify_button()
            return

        self.list_label.setText(f"Recent BOMs in {self._search_root}:")
        for path, mtime in hits:
            when = time.strftime("%Y-%m-%d", time.localtime(mtime))
            job = os.path.basename(os.path.dirname(path))
            item = QListWidgetItem(f"{when}   {os.path.basename(path)}   [{job}]")
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
        self._sync_verify_button()

    def _sync_verify_button(self) -> None:
        self.verify_button.setEnabled(self.list.currentItem() is not None)

    # ---- selection

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected_path = item.data(Qt.UserRole)
        self.accept()

    def _accept_selected(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self._accept_item(item)

    def choose_bom(self) -> None:
        start_dir = self._search_root if os.path.isdir(self._search_root) else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select an Inventor BOM",
            start_dir,
            "BOM files (*.csv *.xlsx);;All files (*)",
        )
        if not path:
            return
        self.selected_path = path
        self.accept()


def pick_bom(data_dir: str, scan: dict, last_message: str = "") -> str | None:
    """Show the picker and return the chosen BOM, or None if they closed it.

    `scan` is passed straight to `bom_finder.find_recent_boms`, so settings can
    be added there without threading another argument through this call.
    """
    dialog = BomPickerDialog(data_dir, scan)
    if last_message:
        dialog.status.setText(last_message)
    if dialog.exec() != QDialog.Accepted:
        return None
    return dialog.selected_path
