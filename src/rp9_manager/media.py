"""Media die aan een .rp9 kunnen worden toegevoegd (geen UI-code).

Volgens het RP9-schema (``rp9.xsd``) staat in ``application/media`` per image één element
(``floppy``, ``harddrive``, ``cd``, ``tape``, ``snapshot``), en in ``application/extras``
staan ``image``- en ``document``-elementen met ``root="embedded"`` voor ingesloten bestanden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .errors import MediaError
from .i18n import tr

IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".gif")
DOCUMENT_EXTENSIONS: tuple[str, ...] = (".pdf", ".txt")
MAX_MEDIA_SIZE = 512 * 1024 * 1024  # gelijk aan de leeslimiet van het archief
# Volgorde van de kind-elementen in ``application/media`` volgens het schema.
MEDIA_ELEMENT_ORDER: tuple[str, ...] = ("floppy", "harddrive", "cd", "tape", "snapshot")


class MediaKind(str, Enum):
    """Soort media dat via het tabblad Media wordt beheerd."""

    IMAGE = "image"
    DOCUMENT = "document"
    DISK = "disk"


def media_element(name: str) -> str:
    """Geef het manifest-element (``floppy``, ``harddrive``, ``cd`` of ``tape``) voor een image."""
    suffix = Path(name).suffix.lower()
    if suffix == ".hdf":
        return "harddrive"
    if suffix in {".iso", ".chd"}:
        return "cd"
    if suffix in {".tap", ".t64"}:
        return "tape"
    return "floppy"


def archive_name(source: Path | str) -> str:
    """Bestandsnaam waaronder ``source`` in het archief komt (alleen de naam, zonder map)."""
    name = Path(source).name.replace("\\", "_").strip()
    return name or "bestand"


@dataclass(frozen=True, slots=True)
class MediaItem:
    """Een toe te voegen bestand."""

    kind: MediaKind
    source: Path
    image_type: str = "screen-running"

    @property
    def name(self) -> str:
        """Naam in het archief."""
        return archive_name(self.source)

    def validate(self, allowed_disk_extensions: frozenset[str]) -> None:
        """Controleer type, bestaan en grootte.

        Raises:
            MediaError: als het bestand niet toegevoegd mag worden.
        """
        suffix = self.source.suffix.lower()
        allowed: tuple[str, ...] | frozenset[str] = {
            MediaKind.IMAGE: IMAGE_EXTENSIONS,
            MediaKind.DOCUMENT: DOCUMENT_EXTENSIONS,
            MediaKind.DISK: allowed_disk_extensions,
        }[self.kind]
        if suffix not in allowed:
            raise MediaError(tr("Bestandstype niet ondersteund: {name}", name=self.name))
        try:
            if not self.source.is_file():
                raise MediaError(tr("Bestand niet gevonden: {name}", name=self.name))
            if self.source.stat().st_size > MAX_MEDIA_SIZE:
                raise MediaError(tr("'{name}' is te groot.", name=self.name))
        except OSError as exc:
            raise MediaError(tr("Bestand niet leesbaar: {name} ({exc})", name=self.name, exc=exc)) from exc


@dataclass(slots=True)
class MediaChanges:
    """Gewenste wijzigingen in de media van een archief."""

    add: list[MediaItem] = field(default_factory=list)
    remove: list[str] = field(default_factory=list)
    order: list[str] = field(default_factory=list)  # gewenste volgorde (= prioriteit) van extra's

    def __bool__(self) -> bool:
        """Waar als er iets toegevoegd, verwijderd of herordend moet worden."""
        return bool(self.add or self.remove or self.order)
