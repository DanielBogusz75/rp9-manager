"""Applicatielogica: bibliotheek, bewerken, aanmaken en starten (geen UI-code)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .archive import RP9Archive, RP9Entry
from .launcher import EmulatorLauncher
from .manifest import Manifest, Platform

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rp9-manager" / "config.json"


class RP9Manager:
    """Façade die de UI gebruikt; bevat alle bedrijfslogica."""

    def __init__(self, library_dir: Path | None = None, launcher: EmulatorLauncher | None = None) -> None:
        """Laad de configuratie en stel map en launcher in."""
        cfg = self._load_config()
        self.library_dir = library_dir or Path(cfg.get("library_dir", Path.home() / "Games" / "rp9"))
        self.launcher = launcher or EmulatorLauncher(cfg.get("amiberry", "amiberry"), cfg.get("vice", "x64sc"))

    @staticmethod
    def _load_config() -> dict[str, str]:
        """Lees de JSON-configuratie; ontbrekend of kapot bestand geeft defaults."""
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_config(self) -> None:
        """Sla de huidige instellingen op."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(
                {"library_dir": str(self.library_dir), "amiberry": self.launcher.amiberry, "vice": self.launcher.vice},
                indent=2,
            ),
            encoding="utf-8",
        )

    def scan(self) -> list[RP9Entry]:
        """Scan de bibliotheekmap (recursief) en geef entries gesorteerd op titel."""
        if not self.library_dir.is_dir():
            return []
        paths = (p for p in self.library_dir.rglob("*") if p.suffix.lower() == ".rp9" and p.is_file())
        return sorted((RP9Archive(p).summarize() for p in paths), key=lambda e: e.title.lower())

    @staticmethod
    def filter(entries: list[RP9Entry], text: str = "", platform: Platform | None = None) -> list[RP9Entry]:
        """Filter entries op zoektekst (titel, uitgever, genre, bestandsnaam) en platform."""
        needle = text.strip().lower()
        return [
            e for e in entries
            if (platform is None or e.platform is platform)
            and (not needle or needle in " ".join(
                (e.title, e.manifest.publisher, e.manifest.genre, e.manifest.year, e.path.name)).lower())
        ]

    def preview(self, entry: RP9Entry) -> bytes | None:
        """Geef de bytes van de preview-afbeelding, of None."""
        return RP9Archive(entry.path).read(entry.preview_name) if entry.preview_name else None

    def update_manifest(self, entry: RP9Entry, manifest: Manifest) -> RP9Entry:
        """Sla een gewijzigd manifest op en geef de ververste entry terug."""
        archive = RP9Archive(entry.path)
        archive.write_manifest(manifest)
        return archive.summarize()

    def create(self, source_dir: Path, output: Path, manifest: Manifest) -> RP9Entry:
        """Maak een nieuw .rp9 uit een map."""
        return RP9Archive.create(source_dir, output, manifest).summarize()

    def launch(self, entry: RP9Entry) -> None:
        """Start de emulator voor ``entry``."""
        self.launcher.launch(entry)
