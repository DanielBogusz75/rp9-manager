"""Veilige ZIP-afhandeling voor .rp9-bestanden (geen UI-code)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath

from .i18n import tr
from .errors import CorruptArchiveError, ManifestError, MediaError
from .media import DOCUMENT_EXTENSIONS, IMAGE_EXTENSIONS, MediaChanges, MediaKind
from .manifest import AMIGA_EXTENSIONS, C64_EXTENSIONS, DEFAULT_HELP_NAME, DISK_EXTENSIONS, Manifest, ManifestParser, Platform

MANIFEST_NAME = "rp9-manifest.xml"
LEGACY_MANIFEST_NAME = "manifest.xml"
EMULATOR_OPTIONS_NAME = "rp9-manager/emulator-options.json"
MAX_MEMBER_SIZE = 512 * 1024 * 1024  # bescherming tegen zip-bommen


@dataclass(slots=True)
class RP9Entry:
    """Samenvatting van één .rp9-bestand voor de bibliotheek."""

    path: Path
    manifest: Manifest
    disk_images: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    preview_name: str | None = None
    size: int = 0
    error: str | None = None

    @property
    def title(self) -> str:
        """Titel uit het manifest, anders de bestandsnaam."""
        return self.manifest.title or self.path.stem

    @property
    def platform(self) -> Platform:
        """Platform uit manifest; zo nodig afgeleid uit de disk-extensies."""
        if self.manifest.platform is not Platform.UNKNOWN:
            return self.manifest.platform
        return detect_platform(self.disk_images)


def detect_platform(names: list[str]) -> Platform:
    """Leid het platform af uit bestandsextensies."""
    exts = {Path(n).suffix.lower() for n in names}
    if exts & C64_EXTENSIONS:
        return Platform.C64
    if exts & AMIGA_EXTENSIONS:
        return Platform.AMIGA
    return Platform.UNKNOWN


def _safe_name(name: str) -> bool:
    """Controleer dat een archiefpad relatief is en niet uit de doelmap ontsnapt (zip-slip)."""
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in name


def _emulator_options(manifest: Manifest) -> dict[str, str | bool | tuple[str, ...]]:
    """Verzamel de per-game emulatorinstellingen voor opslag in het archief."""
    return {
        "amiberry": manifest.amiberry_options,
        "vice": manifest.vice_options,
        "amiberry_model": manifest.amiberry_model,
        "amiberry_config": manifest.amiberry_config,
        "amiberry_floppies": manifest.amiberry_floppies,
        "amiberry_hardfile": manifest.amiberry_hardfile,
        "amiberry_cdimage": manifest.amiberry_cdimage,
        "vice_config": manifest.vice_config,
        "vice_autostart": manifest.vice_autostart,
        "vice_tape": manifest.vice_tape,
        "vice_drives": manifest.vice_drives,
        "fullscreen": manifest.fullscreen,
    }


def _has_emulator_options(options: dict[str, str | tuple[str, ...]]) -> bool:
    """Controleer of minstens één emulatorinstelling ingevuld is."""
    scalar_values = (
        value for key, value in options.items()
        if key not in {"amiberry_floppies", "vice_drives"}
    )
    return any(scalar_values) or any(
        any(options[key]) for key in ("amiberry_floppies", "vice_drives")
    )


def _without_media(manifest: Manifest, removed: set[str]) -> Manifest:
    """Wis verwijzingen naar verwijderde bestanden uit de emulatorinstellingen."""
    def clean(value: str) -> str:
        """Maak een verwijzing leeg als het bestand verwijderd wordt."""
        return "" if value in removed else value

    return replace(
        manifest,
        amiberry_floppies=tuple(clean(n) for n in manifest.amiberry_floppies),
        amiberry_hardfile=clean(manifest.amiberry_hardfile),
        amiberry_cdimage=clean(manifest.amiberry_cdimage),
        vice_autostart=clean(manifest.vice_autostart),
        vice_tape=clean(manifest.vice_tape),
        vice_drives=tuple(clean(n) for n in manifest.vice_drives),
    )


class RP9Archive:
    """Wrapper rond één .rp9-bestand."""

    def __init__(self, path: Path | str) -> None:
        """Sla het pad op; het archief wordt pas bij gebruik geopend."""
        self.path = Path(path)

    def _open(self, mode: str = "r") -> zipfile.ZipFile:
        """Open als ZIP en vertaal fouten naar :class:`CorruptArchiveError`."""
        try:
            return zipfile.ZipFile(self.path, mode)  # type: ignore[arg-type]
        except (zipfile.BadZipFile, OSError) as exc:
            raise CorruptArchiveError(tr("Kan '{name}' niet openen: {exc}", name=self.path.name, exc=exc)) from exc

    def names(self) -> list[str]:
        """Alle (veilige) bestandsnamen in het archief."""
        with self._open() as zf:
            return [n for n in zf.namelist() if not n.endswith("/") and _safe_name(n)]

    def read(self, name: str) -> bytes:
        """Lees één bestand uit het archief (met groottelimiet)."""
        with self._open() as zf:
            try:
                info = zf.getinfo(name)
                if info.file_size > MAX_MEMBER_SIZE:
                    raise CorruptArchiveError(tr("'{name}' is verdacht groot.", name=name))
                return zf.read(info)
            except KeyError as exc:
                raise CorruptArchiveError(tr("'{name}' ontbreekt in {archive}", name=name, archive=self.path.name)) from exc
            except (zipfile.BadZipFile, RuntimeError, OSError, zlib.error) as exc:
                raise CorruptArchiveError(tr("Beschadigd archief {archive}: {exc}", archive=self.path.name, exc=exc)) from exc

    def manifest_name(self) -> str | None:
        """Naam van het manifest in het archief (``rp9-manifest.xml`` of oud ``manifest.xml``)."""
        names = self.names()
        return next((n for n in (MANIFEST_NAME, LEGACY_MANIFEST_NAME) if n in names), None)

    def disk_images(self) -> list[str]:
        """Namen van herkende disk-images (.adf, .d64, ...)."""
        return [n for n in self.names() if Path(n).suffix.lower() in DISK_EXTENSIONS]

    def preview_name(self) -> str | None:
        """Naam van de eerste ingesloten afbeelding, indien aanwezig."""
        images = self.images()
        return next((n for n in images if Path(n).name.lower().startswith("rp9-preview")), images[0] if images else None)

    def images(self) -> list[str]:
        """Namen van ingesloten afbeeldingen (png, jpg, gif)."""
        return [n for n in self.names() if n.lower().endswith(IMAGE_EXTENSIONS)]

    def documents(self, help_name: str = DEFAULT_HELP_NAME) -> list[str]:
        """Namen van ingesloten documenten (pdf, txt), zonder het helpdocument met de beschrijving."""
        return [n for n in self.names() if n.lower().endswith(DOCUMENT_EXTENSIONS) and n != help_name]

    def read_manifest(self) -> Manifest:
        """Lees het manifest en de beschrijving uit het helpdocument.

        Raises:
            ManifestError: als het manifest ontbreekt of ongeldig is.
        """
        name = self.manifest_name()
        if name is None:
            raise ManifestError(tr("{name} ontbreekt in {archive}", name=MANIFEST_NAME, archive=self.path.name))
        manifest = ManifestParser.parse(self.read(name))
        help_name = manifest.help_file or DEFAULT_HELP_NAME
        if help_name in self.names():
            manifest.description = self.read(help_name).decode("utf-8", errors="replace").strip()
        names = self.names()
        if EMULATOR_OPTIONS_NAME in names:
            try:
                options = json.loads(self.read(EMULATOR_OPTIONS_NAME))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CorruptArchiveError(
                    tr("Ongeldige emulatorinstellingen in {archive}: {exc}", archive=self.path.name, exc=exc)
                ) from exc
            string_fields = (
                "amiberry", "vice", "amiberry_model", "amiberry_config",
                "amiberry_hardfile", "amiberry_cdimage", "vice_config", "vice_autostart", "vice_tape",
            )
            list_fields = ("amiberry_floppies", "vice_drives")
            if (
                not isinstance(options, dict)
                or any(not isinstance(options.get(key, ""), str) for key in string_fields)
                or not isinstance(options.get("fullscreen", False), bool)
                or any(
                    not isinstance(options.get(key, []), list)
                    or any(not isinstance(item, str) for item in options.get(key, []))
                    for key in list_fields
                )
                or any(len(options.get(key, [])) > 4 for key in list_fields)
            ):
                raise CorruptArchiveError(tr("Ongeldige emulatorinstellingen in {archive}.", archive=self.path.name))
            manifest.amiberry_options = options.get("amiberry", "")
            manifest.vice_options = options.get("vice", "")
            manifest.amiberry_model = options.get("amiberry_model", "")
            manifest.amiberry_config = options.get("amiberry_config", "")
            manifest.amiberry_floppies = tuple(options.get("amiberry_floppies", []))
            manifest.amiberry_hardfile = options.get("amiberry_hardfile", "")
            manifest.amiberry_cdimage = options.get("amiberry_cdimage", "")
            manifest.vice_config = options.get("vice_config", "")
            manifest.vice_autostart = options.get("vice_autostart", "")
            manifest.vice_tape = options.get("vice_tape", "")
            manifest.vice_drives = tuple(options.get("vice_drives", []))
            manifest.fullscreen = options.get("fullscreen", False)
        return manifest

    def summarize(self) -> RP9Entry:
        """Maak een :class:`RP9Entry`; fouten worden vastgelegd i.p.v. opgegooid."""
        entry = RP9Entry(self.path, Manifest())
        try:
            entry.size = self.path.stat().st_size
            entry.disk_images = self.disk_images()
            entry.preview_name = self.preview_name()
            entry.images = self.images()
            entry.manifest = self.read_manifest()
            entry.documents = self.documents(entry.manifest.help_file or DEFAULT_HELP_NAME)
            # Volgorde en voorbeeld volgen de prioriteiten in het manifest.
            order = {name: index for index, name in enumerate(entry.manifest.extras_order)}
            entry.images.sort(key=lambda n: order.get(n, len(order)))
            entry.documents.sort(key=lambda n: order.get(n, len(order)))
            running = [n for n in entry.images if entry.manifest.image_types.get(n) == "screen-running"]
            if running:
                entry.preview_name = running[0]
        except (CorruptArchiveError, ManifestError, OSError) as exc:
            entry.error = str(exc)
        return entry

    def write_manifest(self, manifest: Manifest, changes: MediaChanges | None = None) -> None:
        """Schrijf manifest, beschrijving en media-wijzigingen veilig terug.

        Er wordt een nieuw archief naast het origineel gebouwd en daarna atomair
        vervangen, zodat een fout het origineel nooit beschadigt.

        Raises:
            MediaError: als een toe te voegen bestand ongeldig is of de naam al bestaat,
                of als een beschermd bestand verwijderd wordt.
        """
        old_name = self.manifest_name()
        old = self.read(old_name) if old_name else None
        help_name = manifest.help_file or DEFAULT_HELP_NAME
        protected = {MANIFEST_NAME, LEGACY_MANIFEST_NAME, help_name, EMULATOR_OPTIONS_NAME}
        add = list(changes.add) if changes else []
        remove = set(changes.remove) if changes else set()
        existing = set(self.names())
        if remove & protected:
            raise MediaError(tr("Dit bestand kan niet verwijderd worden: {name}", name=sorted(remove & protected)[0]))
        taken = (existing - remove) | protected
        for item in add:
            item.validate(DISK_EXTENSIONS)
            if item.name in taken:
                raise MediaError(tr("Er bestaat al een bestand met de naam '{name}'.", name=item.name))
            taken.add(item.name)
        if remove:
            manifest = _without_media(manifest, remove)
        # Bij toegevoegde documenten bestaat altijd een eigen helpbestand, zodat een toegevoegd
        # .txt-bestand nooit voor de beschrijving wordt aangezien.
        write_help = bool(manifest.description) or any(item.kind is MediaKind.DOCUMENT for item in add)
        new = ManifestParser.apply(old, manifest, help_name if write_help else None)
        if add or remove or (changes and changes.order):
            referenced = ManifestParser.parse(new).image_types
            # Afbeeldingen in het archief die het manifest nog niet noemt (bijv. bij een nieuwe map).
            loose = [
                (MediaKind.IMAGE, name, "screen-title" if name.lower().startswith("rp9-title") else "screen-running")
                for name in self.images() if name not in remove and name not in referenced
            ]
            new = ManifestParser.update_media(
                new, loose + [(item.kind, item.name, item.image_type) for item in add], remove,
                changes.order if changes else None,
            )
        skip = protected | remove
        options = _emulator_options(manifest)
        fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with self._open() as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
                for info in src.infolist():
                    if info.filename not in skip:
                        dst.writestr(info, src.read(info))
                dst.writestr(MANIFEST_NAME, new)
                if write_help:
                    dst.writestr(help_name, manifest.description.encode("utf-8"))
                if _has_emulator_options(options):
                    dst.writestr(
                        EMULATOR_OPTIONS_NAME,
                        json.dumps(options, ensure_ascii=False, indent=2).encode("utf-8"),
                    )
                for item in add:
                    dst.write(item.source, item.name)
            shutil.copymode(self.path, tmp)
            os.replace(tmp, self.path)
        except (OSError, zipfile.BadZipFile, zlib.error) as exc:
            tmp.unlink(missing_ok=True)
            raise CorruptArchiveError(tr("Opslaan mislukt: {exc}", exc=exc)) from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def extract(self, names: list[str], target: Path) -> list[Path]:
        """Pak de opgegeven bestanden veilig uit naar ``target`` (platgeslagen namen)."""
        out: list[Path] = []
        used_names: set[str] = set()
        for name in names:
            if not _safe_name(name):
                raise CorruptArchiveError(tr("Onveilig pad in archief: {name}", name=name))
            source_name = Path(name).name
            stem, suffix = Path(source_name).stem, Path(source_name).suffix
            dest_name = source_name
            duplicate = 2
            while dest_name in used_names:
                dest_name = f"{stem}_{duplicate}{suffix}"
                duplicate += 1
            used_names.add(dest_name)
            dest = target / dest_name
            dest.write_bytes(self.read(name))
            out.append(dest)
        return out

    @staticmethod
    def folder_contents(source_dir: Path | str) -> tuple[list[str], list[str], list[str]]:
        """Geef (disk-images, afbeeldingen, documenten) van een bronmap als archiefnamen.

        De eerste afbeelding krijgt de naam ``rp9-preview.<ext>``, zoals :meth:`create` die opslaat.
        """
        src = Path(source_dir)
        files = sorted(p for p in src.rglob("*") if p.is_file() and not p.is_symlink())
        images = [p for p in files if p.suffix.lower() in IMAGE_EXTENSIONS]
        names = lambda found: [p.relative_to(src).as_posix() for p in found]  # noqa: E731
        return (
            names(p for p in files if p.suffix.lower() in DISK_EXTENSIONS),
            ["rp9-preview" + images[0].suffix.lower(), *names(images[1:])] if images else [],
            names(p for p in files if p.suffix.lower() in DOCUMENT_EXTENSIONS),
        )

    @classmethod
    def create(cls, source_dir: Path | str, output: Path | str, manifest: Manifest) -> "RP9Archive":
        """Maak een nieuw .rp9 van de bestanden in ``source_dir``.

        Raises:
            ManifestError: als de map geen disk-images bevat.
            CorruptArchiveError: als schrijven mislukt.
        """
        src, out = Path(source_dir), Path(output)
        files = sorted(p for p in src.rglob("*") if p.is_file() and not p.is_symlink())
        disks = [p.relative_to(src).as_posix() for p in files if p.suffix.lower() in DISK_EXTENSIONS]
        if not disks:
            raise ManifestError(tr("De map bevat geen herkenbare disk-images."))
        if manifest.platform is Platform.UNKNOWN:
            manifest.platform = detect_platform(disks)
        manifest.title = manifest.title or out.stem
        manifest.media = tuple(disks)
        manifest.help_file = manifest.help_file or DEFAULT_HELP_NAME
        # Een bestaande preview in de bronmap wordt als rp9-preview.* meegenomen.
        preview = next((p for p in files if p.suffix.lower() in IMAGE_EXTENSIONS), None)
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(MANIFEST_NAME, ManifestParser.apply(None, manifest, manifest.help_file))
                if manifest.description:
                    zf.writestr(manifest.help_file, manifest.description.encode("utf-8"))
                options = _emulator_options(manifest)
                if _has_emulator_options(options):
                    zf.writestr(
                        EMULATOR_OPTIONS_NAME,
                        json.dumps(options, ensure_ascii=False, indent=2).encode("utf-8"),
                    )
                for p in files:
                    if p != preview:
                        zf.write(p, p.relative_to(src).as_posix())
                if preview:
                    zf.write(preview, "rp9-preview" + preview.suffix.lower())
        except OSError as exc:
            out.unlink(missing_ok=True)
            raise CorruptArchiveError(tr("Aanmaken mislukt: {exc}", exc=exc)) from exc
        return cls(out)
