"""Veilige ZIP-afhandeling voor .rp9-bestanden (geen UI-code)."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .errors import CorruptArchiveError, ManifestError
from .manifest import AMIGA_EXTENSIONS, C64_EXTENSIONS, DEFAULT_HELP_NAME, DISK_EXTENSIONS, Manifest, ManifestParser, Platform

MANIFEST_NAME = "rp9-manifest.xml"
LEGACY_MANIFEST_NAME = "manifest.xml"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif")
MAX_MEMBER_SIZE = 512 * 1024 * 1024  # bescherming tegen zip-bommen


@dataclass(slots=True)
class RP9Entry:
    """Samenvatting van één .rp9-bestand voor de bibliotheek."""

    path: Path
    manifest: Manifest
    disk_images: list[str] = field(default_factory=list)
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
            raise CorruptArchiveError(f"Kan '{self.path.name}' niet openen: {exc}") from exc

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
                    raise CorruptArchiveError(f"'{name}' is verdacht groot.")
                return zf.read(info)
            except KeyError as exc:
                raise CorruptArchiveError(f"'{name}' ontbreekt in {self.path.name}") from exc
            except (zipfile.BadZipFile, RuntimeError, OSError, zlib.error) as exc:
                raise CorruptArchiveError(f"Beschadigd archief {self.path.name}: {exc}") from exc

    def manifest_name(self) -> str | None:
        """Naam van het manifest in het archief (``rp9-manifest.xml`` of oud ``manifest.xml``)."""
        names = self.names()
        return next((n for n in (MANIFEST_NAME, LEGACY_MANIFEST_NAME) if n in names), None)

    def disk_images(self) -> list[str]:
        """Namen van herkende disk-images (.adf, .d64, ...)."""
        return [n for n in self.names() if Path(n).suffix.lower() in DISK_EXTENSIONS]

    def preview_name(self) -> str | None:
        """Naam van de eerste ingesloten afbeelding, indien aanwezig."""
        return next((n for n in self.names() if n.lower().endswith(IMAGE_EXTENSIONS)), None)

    def read_manifest(self) -> Manifest:
        """Lees het manifest en de beschrijving uit het helpdocument.

        Raises:
            ManifestError: als het manifest ontbreekt of ongeldig is.
        """
        name = self.manifest_name()
        if name is None:
            raise ManifestError(f"{MANIFEST_NAME} ontbreekt in {self.path.name}")
        manifest = ManifestParser.parse(self.read(name))
        help_name = manifest.help_file or DEFAULT_HELP_NAME
        if help_name in self.names():
            manifest.description = self.read(help_name).decode("utf-8", errors="replace").strip()
        return manifest

    def summarize(self) -> RP9Entry:
        """Maak een :class:`RP9Entry`; fouten worden vastgelegd i.p.v. opgegooid."""
        entry = RP9Entry(self.path, Manifest())
        try:
            entry.size = self.path.stat().st_size
            entry.disk_images = self.disk_images()
            entry.preview_name = self.preview_name()
            entry.manifest = self.read_manifest()
        except (CorruptArchiveError, ManifestError, OSError) as exc:
            entry.error = str(exc)
        return entry

    def write_manifest(self, manifest: Manifest) -> None:
        """Schrijf manifest en beschrijving veilig terug.

        Er wordt een nieuw archief naast het origineel gebouwd en daarna atomair
        vervangen, zodat een fout het origineel nooit beschadigt.
        """
        old_name = self.manifest_name()
        old = self.read(old_name) if old_name else None
        help_name = manifest.help_file or DEFAULT_HELP_NAME
        new = ManifestParser.apply(old, manifest, help_name if manifest.description else None)
        skip = {MANIFEST_NAME, LEGACY_MANIFEST_NAME, help_name}
        fd, tmp_name = tempfile.mkstemp(suffix=".tmp", dir=self.path.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            with self._open() as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
                for info in src.infolist():
                    if info.filename not in skip:
                        dst.writestr(info, src.read(info))
                dst.writestr(MANIFEST_NAME, new)
                if manifest.description:
                    dst.writestr(help_name, manifest.description.encode("utf-8"))
            shutil.copymode(self.path, tmp)
            os.replace(tmp, self.path)
        except (OSError, zipfile.BadZipFile, zlib.error) as exc:
            tmp.unlink(missing_ok=True)
            raise CorruptArchiveError(f"Opslaan mislukt: {exc}") from exc
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def extract(self, names: list[str], target: Path) -> list[Path]:
        """Pak de opgegeven bestanden veilig uit naar ``target`` (platgeslagen namen)."""
        out: list[Path] = []
        for name in names:
            if not _safe_name(name):
                raise CorruptArchiveError(f"Onveilig pad in archief: {name}")
            dest = target / Path(name).name
            dest.write_bytes(self.read(name))
            out.append(dest)
        return out

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
            raise ManifestError("De map bevat geen herkenbare disk-images.")
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
                for p in files:
                    if p != preview:
                        zf.write(p, p.relative_to(src).as_posix())
                if preview:
                    zf.write(preview, "rp9-preview" + preview.suffix.lower())
        except OSError as exc:
            out.unlink(missing_ok=True)
            raise CorruptArchiveError(f"Aanmaken mislukt: {exc}") from exc
        return cls(out)
