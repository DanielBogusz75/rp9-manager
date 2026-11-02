"""PyQt6-interface; delegeert alle logica aan :class:`RP9Manager`."""

from __future__ import annotations

import html
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget,
    QScrollArea, QSizePolicy, QStackedWidget, QTabWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QAbstractItemView, QGroupBox, QListWidget, QListWidgetItem, QMenu,
)

from .archive import EMULATOR_OPTIONS_NAME, LEGACY_MANIFEST_NAME, MANIFEST_NAME, RP9Entry
from .errors import RP9Error
from .i18n import LANGUAGES, get_language, tr
from .media import (
    MediaChanges, MediaItem, MediaKind, archive_name,
)
from .launcher import EmulatorLauncher
from .manager import RP9Manager
from .manifest import (
    AMIGA_CD_EXTENSIONS, AMIGA_FLOPPY_EXTENSIONS, C64_AUTOSTART_EXTENSIONS, C64_DISK_EXTENSIONS,
    C64_TAPE_EXTENSIONS, DISK_EXTENSIONS, IMAGE_TYPES, KICKSTART_ROMS, Manifest, Platform, SYSTEMS,
)

KNOWN_GENRES = ("action-shooting", "driving-simulation", "mind-puzzle", "platform", "sports")
KNOWN_TYPES = ("game", "demo", "gallery")
FAST_RAM_SIZES = (524288, 1048576, 2097152, 4194304, 8388608)


class MediaList(QWidget):
    """Lijst met archiefbestanden van één soort, met knoppen om bestanden toe te voegen of te verwijderen."""

    added = pyqtSignal(str)
    removed = pyqtSignal(str)

    def __init__(
        self,
        kind: MediaKind,
        title: str,
        names: tuple[str, ...],
        file_filter: str,
        is_taken: Callable[[str], bool],
        parent: QWidget | None = None,
        *,
        image_type: str = "screen-running",
    ) -> None:
        """Toon ``names`` (bestanden in het archief) onder ``title``.

        ``image_type`` is het manifesttype dat nieuwe afbeeldingen in deze lijst krijgen.
        """
        super().__init__(parent)
        self.kind = kind
        self.image_type = image_type
        self.moved = False
        self._file_filter = file_filter
        self._is_taken = is_taken
        self._removed: list[str] = []
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setMaximumHeight(110)
        for name in names:
            self._append(name, None)
        add_button = QPushButton(tr("Toevoegen…"))
        add_button.clicked.connect(self._add)
        remove_button = QPushButton(tr("Verwijderen"))
        remove_button.clicked.connect(self._remove)
        row = QHBoxLayout()
        row.addWidget(add_button)
        row.addWidget(remove_button)
        row.addStretch()
        if kind is not MediaKind.DISK:
            for text, step in (("▲", -1), ("▼", 1)):
                button = QPushButton(text)
                button.setFixedWidth(36)
                button.setToolTip(tr("Prioriteit wijzigen (bovenste = standaard)"))
                button.clicked.connect(lambda _checked=False, step=step: self._move(step))
                row.addWidget(button)
        box = QGroupBox(title)
        inner = QVBoxLayout(box)
        inner.addWidget(self.list)
        inner.addLayout(row)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)

    def _append(self, name: str, source: Path | None) -> None:
        """Voeg een regel toe; ``source`` is gezet voor nog niet opgeslagen bestanden."""
        item = QListWidgetItem(name if source is None else f"{name} {tr('(nieuw)')}")
        item.setData(Qt.ItemDataRole.UserRole, name)
        item.setData(Qt.ItemDataRole.UserRole + 1, str(source) if source else None)
        self.list.addItem(item)

    def names(self) -> list[str]:
        """Namen van alle bestanden die na opslaan in het archief zitten."""
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

    def pending(self) -> list[MediaItem]:
        """Bestanden die nog aan het archief moeten worden toegevoegd."""
        found = []
        for i in range(self.list.count()):
            source = self.list.item(i).data(Qt.ItemDataRole.UserRole + 1)
            if source:
                found.append(MediaItem(self.kind, Path(source), self.image_type))
        return found

    def removed_names(self) -> list[str]:
        """Namen van archiefbestanden die verwijderd moeten worden."""
        return list(self._removed)

    def _move(self, step: int) -> None:
        """Verplaats de geselecteerde regel omhoog (-1) of omlaag (+1)."""
        row = self.list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.list.count():
            return
        self.list.insertItem(target, self.list.takeItem(row))
        self.list.setCurrentRow(target)
        self.moved = True

    def _add(self) -> None:
        """Kies bestanden en voeg ze toe (bestaande namen worden geweigerd)."""
        files, _ = QFileDialog.getOpenFileNames(self, tr("Toevoegen…"), "", self._file_filter)
        for file in files:
            name = archive_name(file)
            if self._is_taken(name):
                QMessageBox.warning(self, tr("Bestand bestaat al"), tr("Er bestaat al een bestand met de naam '{name}'.", name=name))
                continue
            self._append(name, Path(file))
            self.added.emit(name)

    def _remove(self) -> None:
        """Verwijder de geselecteerde regels."""
        for item in self.list.selectedItems():
            name = item.data(Qt.ItemDataRole.UserRole)
            if not item.data(Qt.ItemDataRole.UserRole + 1):
                self._removed.append(name)
            self.list.takeItem(self.list.row(item))
            self.removed.emit(name)


class ManifestDialog(QDialog):
    """Dialoog om metadata en emulatoropties per game te bewerken."""

    def __init__(
        self,
        manifest: Manifest,
        media: tuple[str, ...] = (),
        parent: QWidget | None = None,
        *,
        images: tuple[str, ...] = (),
        documents: tuple[str, ...] = (),
    ) -> None:
        """Bouw het formulier met de waarden van ``manifest``.

        ``media``, ``images`` en ``documents`` zijn de bestanden die al in het archief zitten.
        """
        super().__init__(parent)
        self._media_boxes: list[tuple[QComboBox, frozenset[str]]] = []
        self._reserved = {MANIFEST_NAME, LEGACY_MANIFEST_NAME, EMULATOR_OPTIONS_NAME,
                          manifest.help_file or "rp9-help-en.txt"}
        self.setWindowTitle(tr("Manifest Bewerken"))
        self.title_edit = QLineEdit(manifest.title)
        self.desc_edit = QPlainTextEdit(manifest.description)
        self.publisher_edit = QLineEdit(manifest.publisher)
        self.year_edit = QLineEdit(manifest.year)
        self.genre_edit = self._editable_combo(KNOWN_GENRES, manifest.genre)
        self._original = manifest
        self.platform_box = QComboBox()
        for p in Platform:
            self.platform_box.addItem(tr(p.value), p)
        self.platform_box.setCurrentIndex(self.platform_box.findData(manifest.platform))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.setMinimumSize(580, 480)

        title_form = QFormLayout()
        title_form.addRow(tr("Titel"), self.title_edit)
        self.tabs = QTabWidget()
        information = QWidget()
        information_form = QFormLayout(information)
        information_form.addRow(tr("Uitgever"), self.publisher_edit)
        information_form.addRow(tr("Jaar"), self.year_edit)
        information_form.addRow("Genre", self.genre_edit)
        information_form.addRow(tr("Beschrijving"), self.desc_edit)
        information_form.addRow("Platform", self.platform_box)
        self.tabs.addTab(information, tr("Informatie"))
        self._build_details_tab(manifest)

        self.emulation_pages = QStackedWidget()
        amiga_page = QWidget()
        amiga_form = QFormLayout(amiga_page)
        self.amiberry_model_box = QComboBox()
        self.amiberry_model_box.addItem(tr("Standaard (volgens RP9)"), "")
        for model in ("A500", "A500P", "A600", "A1000", "A2000", "A3000", "A1200", "A4000", "CD32", "CDTV"):
            self.amiberry_model_box.addItem(model, model)
        self.amiberry_model_box.setCurrentIndex(
            max(0, self.amiberry_model_box.findData(manifest.amiberry_model))
        )
        self.amiberry_config_edit = QLineEdit(manifest.amiberry_config)
        self.amiberry_config_edit.setPlaceholderText(tr("Optioneel .uae-configuratiebestand"))
        self.amiberry_fullscreen_box = QCheckBox(tr("Starten in volledig scherm"))
        self.amiberry_fullscreen_box.setChecked(manifest.fullscreen)
        amiga_form.addRow(tr("Amiga-model"), self.amiberry_model_box)
        amiga_form.addRow(tr("Scherm"), self.amiberry_fullscreen_box)
        amiga_form.addRow(tr("Configuratiebestand"), self.amiberry_config_edit)
        self.amiberry_floppy_boxes = [
            self._media_box(
                media,
                manifest.amiberry_floppies[index] if index < len(manifest.amiberry_floppies) else "",
                AMIGA_FLOPPY_EXTENSIONS,
            )
            for index in range(4)
        ]
        for index, box in enumerate(self.amiberry_floppy_boxes):
            amiga_form.addRow(tr("Diskette-station DF{index}", index=index), box)
        self.amiberry_hardfile_box = self._media_box(media, manifest.amiberry_hardfile, frozenset({".hdf"}))
        amiga_form.addRow(tr("Harddisk-image (HDF)"), self.amiberry_hardfile_box)
        self.amiberry_cdimage_box = self._media_box(media, manifest.amiberry_cdimage, AMIGA_CD_EXTENSIONS)
        amiga_form.addRow(tr("CD-image (ISO/CHD)"), self.amiberry_cdimage_box)
        self.amiberry_options_edit = QLineEdit(manifest.amiberry_options)
        self.amiberry_options_edit.setPlaceholderText(tr("Extra opties, bijvoorbeeld -G of -s use_gui=no"))
        amiga_form.addRow(tr("Extra opdrachtregelopties"), self.amiberry_options_edit)

        c64_page = QWidget()
        c64_form = QFormLayout(c64_page)
        self.vice_config_edit = QLineEdit(manifest.vice_config)
        self.vice_config_edit.setPlaceholderText(tr("Optioneel VICE-configuratiebestand"))
        c64_form.addRow(tr("Configuratiebestand"), self.vice_config_edit)
        self.vice_fullscreen_box = QCheckBox(tr("Starten in volledig scherm"))
        self.vice_fullscreen_box.setChecked(manifest.fullscreen)
        c64_form.addRow(tr("Scherm"), self.vice_fullscreen_box)
        self.vice_autostart_box = self._media_box(media, manifest.vice_autostart, C64_AUTOSTART_EXTENSIONS)
        c64_form.addRow(tr("Autostart-image (disk/tape/PRG)"), self.vice_autostart_box)
        self.vice_tape_box = self._media_box(media, manifest.vice_tape, C64_TAPE_EXTENSIONS)
        c64_form.addRow(tr("Datasette-image (TAP/T64)"), self.vice_tape_box)
        self.vice_drive_boxes = [
            self._media_box(
                media,
                manifest.vice_drives[index] if index < len(manifest.vice_drives) else "",
                C64_DISK_EXTENSIONS,
            )
            for index in range(4)
        ]
        for drive, box in enumerate(self.vice_drive_boxes, start=8):
            c64_form.addRow(tr("Diskstation {drive}", drive=drive), box)
        self.vice_options_edit = QLineEdit(manifest.vice_options)
        self.vice_options_edit.setPlaceholderText(tr("Extra VICE-opties"))
        c64_form.addRow(tr("Extra opdrachtregelopties"), self.vice_options_edit)

        unknown_page = QWidget()
        unknown_layout = QVBoxLayout(unknown_page)
        unknown_layout.addWidget(QLabel(tr("Kies eerst Amiga of C64 onder Informatie.")))
        unknown_layout.addStretch()
        self.emulation_pages.addWidget(amiga_page)
        self.emulation_pages.addWidget(c64_page)
        self.emulation_pages.addWidget(unknown_page)
        self.tabs.addTab(self.emulation_pages, tr("Emulatie"))
        self.platform_box.currentIndexChanged.connect(self._update_emulation_page)
        self._update_emulation_page()

        self._build_media_tab(manifest, media, images, documents)
        self._build_configuration_tab(manifest)
        self._build_input_tab(manifest)
        self.tabs.tabBar().moveTab(self.tabs.indexOf(self.emulation_pages), self.tabs.count() - 1)

        layout = QVBoxLayout(self)
        layout.addLayout(title_form)
        layout.addWidget(self.tabs)
        layout.addWidget(buttons)

    @staticmethod
    def _editable_combo(values: tuple[str, ...], current: str) -> QComboBox:
        """Maak een bewerkbare keuzelijst met voorgestelde ``values``; ``current`` blijft behouden."""
        box = QComboBox()
        box.setEditable(True)
        box.addItems(values)
        box.setCurrentText(current)
        return box

    def _build_details_tab(self, manifest: Manifest) -> None:
        """Tabblad Details: type, beoordeling en catalogusgegevens (zoals in de Cloanto Title Editor)."""
        self.type_box = self._editable_combo(KNOWN_TYPES, manifest.content_type or "game")
        self.rating_box = QComboBox()
        self.rating_box.addItem(tr("Niet beoordeeld"), "")
        for stars in range(1, 6):
            self.rating_box.addItem("★" * stars, str(stars))
        index = self.rating_box.findData(manifest.rating)
        if index < 0 and manifest.rating:
            self.rating_box.addItem(manifest.rating, manifest.rating)
            index = self.rating_box.count() - 1
        self.rating_box.setCurrentIndex(max(0, index))
        self.version_edit = QLineEdit(manifest.version)
        self.language_edit = QLineEdit(manifest.language)
        self.language_edit.setPlaceholderText("en")
        self.homepage_edit = QLineEdit(manifest.homepage)
        self.tosec_edit = QLineEdit(manifest.tosec)
        page = QWidget()
        form = QFormLayout(page)
        form.addRow(tr("Type"), self.type_box)
        form.addRow(tr("Kwaliteitsbeoordeling"), self.rating_box)
        form.addRow(tr("Versie"), self.version_edit)
        form.addRow(tr("Taal (code)"), self.language_edit)
        form.addRow(tr("Homepage"), self.homepage_edit)
        form.addRow("TOSEC extended", self.tosec_edit)
        self.tabs.addTab(page, tr("Details"))

    def _build_media_tab(
        self, manifest: Manifest, media: tuple[str, ...], images: tuple[str, ...], documents: tuple[str, ...]
    ) -> None:
        """Tabblad Media: afbeeldingen per type, documenten en disk-/CD-/tape-images."""
        grouped: dict[str, list[str]] = {kind: [] for kind in IMAGE_TYPES}
        for name in images:
            kind = manifest.image_types.get(name, "screen-running")
            if kind in grouped:
                grouped[kind].append(name)
        shown = {name for names in grouped.values() for name in names}
        self._reserved |= set(images) - shown  # afbeeldingen van andere typen blijven ongemoeid
        image_filter = tr("Afbeeldingen (*.png *.jpg *.jpeg *.gif)") + ";;" + tr("Alle bestanden (*)")
        titles = {
            "screen-running": tr("Screenshots – tijdens het spel (standaardvoorbeeld)"),
            "screen-title": tr("Screenshots – titelscherm"),
            "screen-score": tr("Screenshots – scorescherm"),
        }
        self.image_lists = {
            kind: MediaList(MediaKind.IMAGE, titles[kind], tuple(grouped[kind]), image_filter, self._is_taken,
                            image_type=kind)
            for kind in IMAGE_TYPES
        }
        self.image_list = self.image_lists["screen-running"]
        self.document_list = MediaList(
            MediaKind.DOCUMENT, tr("Documentatie (PDF, TXT)"), documents,
            tr("Documenten (*.pdf *.txt)") + ";;" + tr("Alle bestanden (*)"), self._is_taken)
        patterns = " ".join(f"*{ext}" for ext in sorted(DISK_EXTENSIONS))
        self.disk_list = MediaList(
            MediaKind.DISK, tr("Disk-, harddisk-, CD- en tape-images"), media,
            tr("Images ({patterns})", patterns=patterns) + ";;" + tr("Alle bestanden (*)"), self._is_taken)
        self.disk_list.added.connect(self._disk_added)
        self.disk_list.removed.connect(self._disk_removed)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        for widget in (*self.image_lists.values(), self.document_list, self.disk_list):
            layout.addWidget(widget)
        hint = QLabel(
            tr("Het voorbeeld in de bibliotheek is de bovenste screenshot 'tijdens het spel'.")
            + "\n" + tr("Toegevoegde images verschijnen direct in de keuzelijsten onder Emulatie."))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        self.tabs.addTab(scroll, tr("Media"))

    def _build_configuration_tab(self, manifest: Manifest) -> None:
        """Tabblad Configuratie: hardware en compatibiliteit zoals Cloanto's Player ze uit het RP9 leest."""
        self.config_pages = QStackedWidget()
        amiga = QWidget()
        amiga_form = QFormLayout(amiga)
        self.amiga_system_box = self._editable_combo(SYSTEMS[Platform.AMIGA], manifest.system
                                                     if manifest.platform is Platform.AMIGA
                                                     else SYSTEMS[Platform.AMIGA][0])
        self.rom_box = QComboBox()
        self.rom_box.addItem(tr("Standaard (volgens model)"), "")
        for code, label in KICKSTART_ROMS:
            self.rom_box.addItem(f"{label} ({code})", code)
        self.rom_box.setCurrentIndex(max(0, self.rom_box.findData(manifest.rom)))
        self.fast_ram_box = QComboBox()
        self.fast_ram_box.addItem(tr("Geen"), 0)
        for size in sorted({*FAST_RAM_SIZES, manifest.fast_ram} - {0}):
            self.fast_ram_box.addItem(f"{size // 1024} KB" if size < 1048576 else f"{size // 1048576} MB", size)
        self.fast_ram_box.setCurrentIndex(max(0, self.fast_ram_box.findData(manifest.fast_ram)))
        amiga_form.addRow(tr("Model (systeem)"), self.amiga_system_box)
        amiga_form.addRow(tr("Kickstart-ROM"), self.rom_box)
        amiga_form.addRow(tr("Fast RAM"), self.fast_ram_box)
        c64 = QWidget()
        c64_form = QFormLayout(c64)
        self.c64_system_box = self._editable_combo(SYSTEMS[Platform.C64], manifest.system
                                                   if manifest.platform is Platform.C64
                                                   else SYSTEMS[Platform.C64][0])
        self.turbo_start_box = QCheckBox(tr("Turbo start"))
        self.turbo_start_box.setChecked(manifest.turbo_start)
        self.auto_load_box = QCheckBox(tr("Automatisch laden"))
        self.auto_load_box.setChecked(manifest.auto_load)
        self.auto_run_box = QCheckBox(tr("Automatisch starten (RUN)"))
        self.auto_run_box.setChecked(manifest.auto_run)
        c64_form.addRow(tr("Model (systeem)"), self.c64_system_box)
        c64_form.addRow(tr("Opstarten"), self.turbo_start_box)
        c64_form.addRow("", self.auto_load_box)
        c64_form.addRow("", self.auto_run_box)
        unknown = QWidget()
        QVBoxLayout(unknown).addWidget(QLabel(tr("Kies eerst Amiga of C64 onder Informatie.")))
        for page in (amiga, c64, unknown):
            self.config_pages.addWidget(page)
        self.turbo_floppy_box = QCheckBox(tr("Turbo floppy"))
        self.turbo_floppy_box.setChecked(manifest.turbo_floppy)
        self.silent_drives_box = QCheckBox(tr("Stille drives"))
        self.silent_drives_box.setChecked(manifest.silent_drives)
        self.autodrive_box = QCheckBox(tr("Automatische drive"))
        self.autodrive_box.setChecked(manifest.autodrive)
        compat = QGroupBox(tr("Compatibiliteit"))
        compat_layout = QVBoxLayout(compat)
        for box in (self.turbo_floppy_box, self.silent_drives_box, self.autodrive_box):
            compat_layout.addWidget(box)
        page = QWidget()
        layout = QVBoxLayout(page)
        self.config_pages.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addWidget(self.config_pages)
        layout.addWidget(compat)
        note = QLabel(tr("Deze instellingen worden in het RP9 zelf opgeslagen en zijn ook geldig voor Cloanto's Player."))
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.tabs.addTab(page, tr("Configuratie"))
        self.platform_box.currentIndexChanged.connect(self._update_config_page)
        self._update_config_page()

    def _build_input_tab(self, manifest: Manifest) -> None:
        """Tabblad Invoer: welke invoerapparaten de titel gebruikt."""
        self.joystick_box = QCheckBox(tr("Joystick"))
        self.joystick_box.setChecked(manifest.joystick)
        self.mouse_box = QCheckBox(tr("Muis"))
        self.mouse_box.setChecked(manifest.mouse)
        self.keyboard_box = QCheckBox(tr("Toetsenbord"))
        self.keyboard_box.setChecked(manifest.keyboard)
        self.multiplayer_box = QCheckBox(tr("Multiplayer"))
        self.multiplayer_box.setChecked(manifest.multiplayer)
        self.joystick_port_box = QComboBox()
        self.joystick_port_box.addItem(tr("Niet ingesteld / automatisch"), "")
        for port in ("1", "2"):
            self.joystick_port_box.addItem(tr("Poort {port}", port=port), port)
        if manifest.joystick_port not in ("", "1", "2"):
            self.joystick_port_box.addItem(tr("Poort {port}", port=manifest.joystick_port), manifest.joystick_port)
        self.joystick_port_box.setCurrentIndex(max(0, self.joystick_port_box.findData(manifest.joystick_port)))
        play = QGroupBox(tr("Speelopties"))
        play_layout = QVBoxLayout(play)
        for box in (self.joystick_box, self.mouse_box, self.keyboard_box, self.multiplayer_box):
            play_layout.addWidget(box)
        ports = QGroupBox(tr("Invoerpoorten"))
        ports_form = QFormLayout(ports)
        ports_form.addRow(tr("Joystick aangesloten op"), self.joystick_port_box)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(play)
        layout.addWidget(ports)
        layout.addStretch()
        self.tabs.addTab(page, tr("Invoer"))

    def _update_config_page(self) -> None:
        """Toon de configuratievelden die bij het gekozen platform horen."""
        self.config_pages.setCurrentIndex({Platform.AMIGA: 0, Platform.C64: 1}.get(self.platform_box.currentData(), 2))

    def _media_box(self, media: tuple[str, ...], current: str, accepts: frozenset[str]) -> QComboBox:
        """Maak een keuzelijst met de archiefbestanden waarvan de extensie in ``accepts`` zit.

        De lijst wordt bijgehouden, zodat in het tabblad Media toegevoegde of verwijderde
        images direct in alle keuzelijsten verschijnen of verdwijnen.
        """
        box = QComboBox()
        box.addItem(tr("Niet ingesteld / automatisch"), "")
        for name in media:
            if Path(name).suffix.lower() in accepts:
                box.addItem(name, name)
        self._media_boxes.append((box, accepts))
        index = box.findData(current)
        box.setCurrentIndex(index if index >= 0 else 0)
        return box

    def _is_taken(self, name: str) -> bool:
        """Geef aan of ``name`` al in het archief zit (of gereserveerd is)."""
        return name in self._reserved or any(name in widget.names() for widget in self._media_lists())

    def _disk_added(self, name: str) -> None:
        """Zet een nieuw image in de passende keuzelijsten onder Emulatie."""
        for box, accepts in self._media_boxes:
            if Path(name).suffix.lower() in accepts:
                box.addItem(name, name)

    def _disk_removed(self, name: str) -> None:
        """Haal een verwijderd image uit alle keuzelijsten; een gekozen waarde wordt 'automatisch'."""
        for box, _ in self._media_boxes:
            index = box.findData(name)
            if index >= 0:
                was_selected = box.currentIndex() == index
                box.removeItem(index)
                if was_selected:
                    box.setCurrentIndex(0)

    def _media_lists(self) -> tuple[MediaList, ...]:
        """Alle lijsten van het tabblad Media."""
        return (*self.image_lists.values(), self.document_list, self.disk_list)

    def result_media(self) -> MediaChanges:
        """Geef de gevraagde media-wijzigingen (toevoegen, verwijderen, herordenen) terug."""
        lists = self._media_lists()
        order: list[str] = []
        if any(widget.moved for widget in lists):
            order = [name for widget in lists if widget.kind is not MediaKind.DISK for name in widget.names()]
        return MediaChanges(
            add=[item for widget in lists for item in widget.pending()],
            remove=[name for widget in lists for name in widget.removed_names()],
            order=order,
        )

    def _update_emulation_page(self) -> None:
        """Toon alleen de velden die bij het gekozen platform horen."""
        platform = self.platform_box.currentData()
        page = {
            Platform.AMIGA: 0,
            Platform.C64: 1,
        }.get(platform, 2)
        self.emulation_pages.setCurrentIndex(page)

    def _configuration_values(self) -> dict[str, object]:
        """Waarden van de tabbladen Details, Configuratie en Invoer als velden van :class:`Manifest`."""
        platform = self.platform_box.currentData()
        values: dict[str, object] = {
            "content_type": self.type_box.currentText().strip(),
            "rating": self.rating_box.currentData() or "",
            "version": self.version_edit.text().strip(),
            "language": self.language_edit.text().strip(),
            "homepage": self.homepage_edit.text().strip(),
            "tosec": self.tosec_edit.text().strip(),
            "joystick": self.joystick_box.isChecked(),
            "mouse": self.mouse_box.isChecked(),
            "keyboard": self.keyboard_box.isChecked(),
            "multiplayer": self.multiplayer_box.isChecked(),
            "joystick_port": self.joystick_port_box.currentData() or "",
            "turbo_floppy": self.turbo_floppy_box.isChecked(),
            "silent_drives": self.silent_drives_box.isChecked(),
            "autodrive": self.autodrive_box.isChecked(),
        }
        if platform is Platform.AMIGA:
            values.update(
                system=self.amiga_system_box.currentText().strip(),
                rom=self.rom_box.currentData() or "",
                fast_ram=self.fast_ram_box.currentData() or 0,
            )
        elif platform is Platform.C64:
            values.update(
                system=self.c64_system_box.currentText().strip(),
                turbo_start=self.turbo_start_box.isChecked(),
                auto_load=self.auto_load_box.isChecked(),
                auto_run=self.auto_run_box.isChecked(),
            )
        return values

    def result_manifest(self) -> Manifest:
        """Geef het ingevulde manifest terug."""
        return replace(
            self._original,
            title=self.title_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip(),
            platform=self.platform_box.currentData(),
            publisher=self.publisher_edit.text().strip(),
            year=self.year_edit.text().strip(),
            genre=self.genre_edit.currentText().strip(),
            **self._configuration_values(),
            amiberry_options=self.amiberry_options_edit.text().strip(),
            vice_options=self.vice_options_edit.text().strip(),
            amiberry_model=self.amiberry_model_box.currentData(),
            amiberry_config=self.amiberry_config_edit.text().strip(),
            amiberry_floppies=tuple(box.currentData() or "" for box in self.amiberry_floppy_boxes),
            amiberry_hardfile=self.amiberry_hardfile_box.currentData() or "",
            amiberry_cdimage=self.amiberry_cdimage_box.currentData() or "",
            vice_config=self.vice_config_edit.text().strip(),
            vice_autostart=self.vice_autostart_box.currentData() or "",
            vice_tape=self.vice_tape_box.currentData() or "",
            vice_drives=tuple(box.currentData() or "" for box in self.vice_drive_boxes),
            fullscreen=(
                self.vice_fullscreen_box.isChecked()
                if self.platform_box.currentData() == Platform.C64
                else self.amiberry_fullscreen_box.isChecked()
            ),
        )


class SettingsDialog(QDialog):
    """Dialoog voor bibliotheekmap en emulatorcommando's."""

    def __init__(self, manager: RP9Manager, parent: QWidget | None = None) -> None:
        """Toon de huidige instellingen van ``manager``."""
        super().__init__(parent)
        self.setWindowTitle(tr("Instellingen"))
        self.setMinimumWidth(480)
        self.dir_edit = QLineEdit(str(manager.library_dir))
        browse = QPushButton("…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit)
        row.addWidget(browse)
        self.amiberry_edit = QLineEdit(manager.launcher.amiberry)
        self.language_box = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_box.addItem(name, code)
        self.language_box.setCurrentIndex(max(0, self.language_box.findData(get_language())))
        self.vice_edit = QLineEdit(manager.launcher.vice)
        self.vice_edit.setPlaceholderText(tr("vice = Flatpak net.sf.VICE, anders x64sc"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        form.addRow(tr("Bibliotheekmap"), row)
        form.addRow(tr("Amiberry-commando"), self.amiberry_edit)
        form.addRow(tr("VICE-commando"), self.vice_edit)
        form.addRow(tr("Taal"), self.language_box)
        form.addRow(buttons)

    def _browse(self) -> None:
        """Kies een map via de bestandsdialoog."""
        d = QFileDialog.getExistingDirectory(self, tr("Bibliotheekmap"), self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def apply_to(self, manager: RP9Manager) -> None:
        """Schrijf de ingevulde waarden naar ``manager`` en bewaar ze."""
        manager.library_dir = Path(self.dir_edit.text()).expanduser()
        manager.launcher.amiberry = self.amiberry_edit.text().strip() or "amiberry"
        manager.launcher.vice = self.vice_edit.text().strip() or "vice"
        manager.set_language(self.language_box.currentData())


class SortItem(QTableWidgetItem):
    """Tabelcel die hoofdletterongevoelig sorteert."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Vergelijk op tekst zonder rekening te houden met hoofdletters."""
        return self.text().casefold() < other.text().casefold()


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
        self.sort_column = 0
        self.sort_order = Qt.SortOrder.AscendingOrder
        self._build()
        self.refresh()

    def _build(self) -> None:
        """Bouw het hoofdscherm op in de actieve taal (ook gebruikt na een taalwissel)."""
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            [tr("Titel"), tr("Platform"), tr("Uitgever"), tr("Jaar"), tr("Genre")]
        )
        header = self.table.horizontalHeader()
        header.setSortIndicatorShown(True)
        header.setSortIndicator(self.sort_column, self.sort_order)
        header.setSectionsClickable(True)
        header.sortIndicatorChanged.connect(self._sort_changed)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 260)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_details)
        self.table.doubleClicked.connect(self._launch)

        self.preview = QLabel(tr("Geen preview"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(280, 200)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Zoeken op titel, uitgever, genre…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.platform_filter = QComboBox()
        self.platform_filter.addItem(tr("Alle platforms"), None)
        for p in (Platform.AMIGA, Platform.C64, Platform.UNKNOWN):
            self.platform_filter.addItem(tr(p.value), p)
        self.platform_filter.currentIndexChanged.connect(self._apply_filter)
        filters = QHBoxLayout()
        filters.addWidget(self.search, 1)
        filters.addWidget(self.platform_filter)

        buttons = QHBoxLayout()
        for text, slot in [(tr("Instellingen…"), self._settings), (tr("Verversen"), self.refresh), (tr("Starten"), self._launch),
                           (tr("Bewerken…"), self._edit), (tr("Nieuw .rp9…"), self._create)]:
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

    def _error(self, exc: Exception) -> None:
        """Toon een foutmelding."""
        QMessageBox.critical(self, tr("Fout"), str(exc))

    def _current(self) -> RP9Entry | None:
        """Geef de geselecteerde entry, of None."""
        item = self.table.item(self.table.currentRow(), 0)
        index = item.data(Qt.ItemDataRole.UserRole) if item else None
        return self.entries[index] if index is not None and 0 <= index < len(self.entries) else None

    def _sort_changed(self, column: int, order: Qt.SortOrder) -> None:
        """Onthoud de gekozen sorteerkolom en -richting."""
        self.sort_column, self.sort_order = column, order

    def _header_menu(self, pos) -> None:
        """Toon een menu om de kolom onder de cursor oplopend of aflopend te sorteren."""
        header = self.table.horizontalHeader()
        column = header.logicalIndexAt(pos)
        if column < 0:
            return
        menu = QMenu(self)
        for label, order in ((tr("Oplopend sorteren"), Qt.SortOrder.AscendingOrder),
                             (tr("Aflopend sorteren"), Qt.SortOrder.DescendingOrder)):
            action = QAction(label, menu)
            action.triggered.connect(lambda _=False, o=order: header.setSortIndicator(column, o))
            menu.addAction(action)
        menu.exec(header.mapToGlobal(pos))

    def refresh(self) -> None:
        """Scan de map opnieuw en pas het huidige filter toe."""
        self.all_entries = self.manager.scan()
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Vul de tabel met entries die aan zoekterm en platformfilter voldoen."""
        self.entries = self.manager.filter(self.all_entries, self.search.text(), self.platform_filter.currentData())
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.entries))
        for r, e in enumerate(self.entries):
            m = e.manifest
            for c, text in enumerate((e.title, tr(e.platform.value), m.publisher, m.year, m.genre)):
                item = SortItem(text)
                item.setToolTip(e.error or str(e.path))
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(self.sort_column, self.sort_order)
        self.statusBar().showMessage(
            tr("{shown} van {total} bestand(en) in {folder}", shown=len(self.entries),
               total=len(self.all_entries), folder=self.manager.library_dir))
        if self.entries:
            self.table.selectRow(0)
        self._show_details()

    def _show_details(self) -> None:
        """Toon preview en metadata van de selectie."""
        e = self._current()
        self.preview.setPixmap(QPixmap())
        self.preview.setText(tr("Geen preview"))
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
            f"Images: {html.escape(', '.join(e.disk_images) or '-')}<br>{tr('Grootte')}: {e.size / 1024:.0f} KiB"
        )

    def _settings(self) -> None:
        """Open de instellingen en ververs de bibliotheek."""
        dlg = SettingsDialog(self.manager, self)
        if dlg.exec():
            try:
                dlg.apply_to(self.manager)
            except OSError as exc:
                self._error(exc)
            self._build()
            self.refresh()

    def _launch(self) -> None:
        """Start de geselecteerde game."""
        if (e := self._current()) is None:
            return
        try:
            self.manager.launch(e)
            self.statusBar().showMessage(tr("'{title}' gestart", title=e.title), 5000)
        except RP9Error as exc:
            self._error(exc)

    def _edit(self) -> None:
        """Bewerk het manifest van de selectie."""
        if (e := self._current()) is None:
            return
        dlg = ManifestDialog(
            e.manifest, tuple(e.disk_images), self, images=tuple(e.images), documents=tuple(e.documents)
        )
        if dlg.exec():
            try:
                self.manager.update_manifest(e, dlg.result_manifest(), dlg.result_media())
            except RP9Error as exc:
                self._error(exc)
            self.refresh()

    def _create(self) -> None:
        """Maak een nieuw .rp9 uit een gekozen map."""
        src = QFileDialog.getExistingDirectory(self, tr("Map met games/disks"))
        if not src:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, tr("Opslaan als"), str(self.manager.library_dir / f"{Path(src).name}.rp9"), "RP9 (*.rp9)")
        if not out:
            return
        source = Path(src)
        disks, images, documents = self.manager.inspect_folder(source)
        dlg = ManifestDialog(
            Manifest(title=source.name), tuple(disks), self, images=tuple(images), documents=tuple(documents)
        )
        if dlg.exec():
            try:
                self.manager.create(source, Path(out), dlg.result_manifest(), dlg.result_media())
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
