"""PyQt6-interface; delegeert alle logica aan :class:`RP9Manager`."""

from __future__ import annotations

import html
import sys
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView,
)

from .archive import RP9Entry
from .errors import RP9Error
from .launcher import EmulatorLauncher
from .manager import RP9Manager
from .manifest import Manifest, Platform


class ManifestDialog(QDialog):
    """Dialoog om titel, beschrijving en platform te bewerken."""

    def __init__(self, manifest: Manifest, parent: QWidget | None = None) -> None:
        """Bouw het formulier met de waarden van ``manifest``."""
        super().__init__(parent)
        self.setWindowTitle("Manifest bewerken")
        self.title_edit = QLineEdit(manifest.title)
        self.desc_edit = QPlainTextEdit(manifest.description)
        self.publisher_edit = QLineEdit(manifest.publisher)
        self.year_edit = QLineEdit(manifest.year)
        self.genre_edit = QLineEdit(manifest.genre)
        self._original = manifest
        self.platform_box = QComboBox()
        for p in Platform:
            self.platform_box.addItem(p.value, p)
        self.platform_box.setCurrentIndex(self.platform_box.findData(manifest.platform))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Titel", self.title_edit)
        form.addRow("Uitgever", self.publisher_edit)
        form.addRow("Jaar", self.year_edit)
        form.addRow("Genre", self.genre_edit)
        form.addRow("Beschrijving", self.desc_edit)
        form.addRow("Platform", self.platform_box)
        form.addRow(buttons)

    def result_manifest(self) -> Manifest:
        """Geef het ingevulde manifest terug."""
        return replace(
            self._original,
            title=self.title_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip(),
            platform=self.platform_box.currentData(),
            publisher=self.publisher_edit.text().strip(),
            year=self.year_edit.text().strip(),
            genre=self.genre_edit.text().strip(),
        )


class SettingsDialog(QDialog):
    """Dialoog voor bibliotheekmap en emulatorcommando's."""

    def __init__(self, manager: RP9Manager, parent: QWidget | None = None) -> None:
        """Toon de huidige instellingen van ``manager``."""
        super().__init__(parent)
        self.setWindowTitle("Instellingen")
        self.setMinimumWidth(480)
        self.dir_edit = QLineEdit(str(manager.library_dir))
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit)
        row.addWidget(browse)
        self.amiberry_edit = QLineEdit(manager.launcher.amiberry)
        self.vice_edit = QLineEdit(manager.launcher.vice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow("Bibliotheekmap", row)
        form.addRow("Amiberry-commando", self.amiberry_edit)
        form.addRow("VICE-commando (x64sc)", self.vice_edit)
        form.addRow(buttons)

    def _browse(self) -> None:
        """Kies een map via de bestandsdialoog."""
        d = QFileDialog.getExistingDirectory(self, "Bibliotheekmap", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def apply_to(self, manager: RP9Manager) -> None:
        """Schrijf de ingevulde waarden naar ``manager`` en bewaar ze."""
        manager.library_dir = Path(self.dir_edit.text()).expanduser()
        manager.launcher.amiberry = self.amiberry_edit.text().strip() or "amiberry"
        manager.launcher.vice = self.vice_edit.text().strip() or "x64sc"
        manager.save_config()


class MainApplicationWindow(QMainWindow):
    """Hoofdvenster met bibliotheeklijst, preview en acties."""

    def __init__(self, manager: RP9Manager) -> None:
        """Bouw de UI en laad de bibliotheek."""
        super().__init__()
        self.manager = manager
        self.all_entries: list[RP9Entry] = []
        self.entries: list[RP9Entry] = []
        self.setWindowTitle("RP9 Manager")
        self.resize(900, 520)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Titel", "Platform", "Uitgever", "Jaar", "Genre"])
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 260)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.doubleClicked.connect(self._launch)

        self.preview = QLabel("Geen preview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(280, 200)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Zoeken op titel, uitgever, genre…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.platform_filter = QComboBox()
        self.platform_filter.addItem("Alle platforms", None)
        for p in (Platform.AMIGA, Platform.C64, Platform.UNKNOWN):
            self.platform_filter.addItem(p.value, p)
        self.platform_filter.currentIndexChanged.connect(self._apply_filter)
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.platform_filter)

        buttons = QHBoxLayout()
        for text, slot in [("Instellingen…", self._settings), ("Verversen", self.refresh), ("Starten", self._launch),
                           ("Bewerken…", self._edit), ("Nieuw .rp9…", self._create)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)

        side = QVBoxLayout()
        side.addWidget(self.preview)
        side.addWidget(self.details, 1)
        body = QHBoxLayout()
        left = QVBoxLayout()
        left.addLayout(filters)
        left.addWidget(self.table)
        body.addLayout(left, 2)
        body.addLayout(side, 1)
        root = QVBoxLayout()
        root.addLayout(body)
        root.addLayout(buttons)
        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)
        self.refresh()

    def _error(self, exc: Exception) -> None:
        """Toon een foutmelding."""
        QMessageBox.critical(self, "Fout", str(exc))

    def _current(self) -> RP9Entry | None:
        """Geef de geselecteerde entry, of None."""
        row = self.table.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def refresh(self) -> None:
        """Scan de map opnieuw en pas het huidige filter toe."""
        self.all_entries = self.manager.scan()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Vul de tabel met entries die aan zoekterm en platformfilter voldoen."""
        self.entries = self.manager.filter(self.all_entries, self.search.text(), self.platform_filter.currentData())
        self.table.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            m = e.manifest
            for c, text in enumerate((e.title, e.platform.value, m.publisher, m.year, m.genre)):
                item = QTableWidgetItem(text)
                item.setToolTip(e.error or str(e.path))
                self.table.setItem(r, c, item)
        self.statusBar().showMessage(
            f"{len(self.entries)} van {len(self.all_entries)} bestand(en) in {self.manager.library_dir}")
        if self.entries:
            self.table.selectRow(0)
        self._show_details()

    def _show_details(self) -> None:
        """Toon preview en metadata van de selectie."""
        e = self._current()
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Geen preview")
        if e is None:
            self.details.setText("")
            return
        try:
            data = self.manager.preview(e)
            pix = QPixmap()
            if data and pix.loadFromData(data):
                self.preview.setPixmap(pix.scaled(280, 200, Qt.AspectRatioMode.KeepAspectRatio))
        except RP9Error:
            pass
        if e.error:
            self.details.setText(f"⚠ {html.escape(e.error)}")
            return
        m = e.manifest
        meta = " · ".join(x for x in (m.publisher, m.year, m.genre, m.system) if x)
        self.details.setText(
            f"<b>{html.escape(e.title)}</b><br><i>{html.escape(meta)}</i><br><br>"
            f"{html.escape(m.description).replace(chr(10), '<br>')}<br><br>"
            f"Images: {html.escape(', '.join(e.disk_images) or '-')}<br>Grootte: {e.size / 1024:.0f} KiB"
        )

    def _settings(self) -> None:
        """Open de instellingen en ververs de bibliotheek."""
        dlg = SettingsDialog(self.manager, self)
        if dlg.exec():
            try:
                dlg.apply_to(self.manager)
            except OSError as exc:
                self._error(exc)
            self.refresh()

    def _launch(self) -> None:
        """Start de geselecteerde game."""
        if (e := self._current()) is None:
            return
        try:
            self.manager.launch(e)
            self.statusBar().showMessage(f"'{e.title}' gestart", 5000)
        except RP9Error as exc:
            self._error(exc)

    def _edit(self) -> None:
        """Bewerk het manifest van de selectie."""
        if (e := self._current()) is None:
            return
        dlg = ManifestDialog(e.manifest, self)
        if dlg.exec():
            try:
                self.manager.update_manifest(e, dlg.result_manifest())
            except RP9Error as exc:
                self._error(exc)
            self.refresh()

    def _create(self) -> None:
        """Maak een nieuw .rp9 uit een gekozen map."""
        src = QFileDialog.getExistingDirectory(self, "Map met games/disks")
        if not src:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, "Opslaan als", str(self.manager.library_dir / f"{Path(src).name}.rp9"), "RP9 (*.rp9)")
        if not out:
            return
        dlg = ManifestDialog(Manifest(title=Path(src).name), self)
        if dlg.exec():
            try:
                self.manager.create(Path(src), Path(out), dlg.result_manifest())
            except RP9Error as exc:
                self._error(exc)
            self.refresh()


def main() -> None:
    """Startpunt van de applicatie."""
    app = QApplication(sys.argv)
    EmulatorLauncher.purge_stale_temp()
    window = MainApplicationWindow(RP9Manager())
    window.show()
    sys.exit(app.exec())
