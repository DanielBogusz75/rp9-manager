"""Emulator-launcher op basis van ``subprocess`` (geen UI-code)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .archive import RP9Entry, RP9Archive
from .i18n import tr
from .errors import EmulatorNotFoundError, LaunchError
from .manifest import (
    AMIGA_CD_EXTENSIONS, AMIGA_FLOPPY_EXTENSIONS, C64_AUTOSTART_EXTENSIONS,
    C64_DISK_EXTENSIONS, C64_EXTENSIONS, C64_TAPE_EXTENSIONS, Platform,
)


class EmulatorLauncher:
    """Start Amiberry (Amiga) of VICE ``x64sc`` (C64)."""

    def __init__(self, amiberry: str = "amiberry", vice: str = "vice") -> None:
        """Configureer de namen of paden van de emulators."""
        self.amiberry = amiberry
        self.vice = vice

    AMIBERRY_FLATPAK = "com.blitterstudio.amiberry"
    VICE_FLATPAK = "net.sf.VICE"
    # "vice" (of de oude standaard "x64sc") = automatisch: eerst de Flatpak, daarna een native x64sc.
    VICE_AUTO = ("", "vice", "x64sc")
    # De VICE-Flatpak ziet /tmp niet (eigen sandbox, wel $HOME), dus pakken we daar uit.
    FLATPAK_TMP = Path.home() / ".cache" / "rp9-manager" / "tmp"

    @staticmethod
    def _flatpak_installed(app_id: str) -> bool:
        """Controleer of een Flatpak-app geïnstalleerd is."""
        flatpak = shutil.which("flatpak")
        if not flatpak:
            return False
        result = subprocess.run([flatpak, "info", app_id], capture_output=True, check=False)
        return result.returncode == 0

    def _resolve(
        self, command: str, flatpak_id: str | None = None, flatpak_command: str | None = None
    ) -> list[str]:
        """Bepaal het uit te voeren commando (pad, eigen commando met argumenten of Flatpak).

        Raises:
            EmulatorNotFoundError: als de emulator nergens gevonden wordt.
        """
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            raise EmulatorNotFoundError(tr("Ongeldig emulatorcommando '{command}': {exc}", command=command, exc=exc)) from exc
        if parts and shutil.which(parts[0]):
            return [shutil.which(parts[0]) or parts[0], *parts[1:]]
        if flatpak_id and self._flatpak_installed(flatpak_id):
            cmd = [shutil.which("flatpak") or "flatpak", "run"]
            if flatpak_command:
                cmd.append(f"--command={flatpak_command}")
            return [*cmd, flatpak_id]
        raise EmulatorNotFoundError(
            tr(
                "Emulator '{command}' is niet gevonden. Installeer deze of stel het pad in via Instellingen.",
                command=command,
            )
        )

    def _resolve_vice(self) -> list[str]:
        """Bepaal het VICE-commando: standaard de Flatpak, anders een native ``x64sc``.

        Raises:
            EmulatorNotFoundError: als VICE nergens gevonden wordt.
        """
        if self.vice.strip() in self.VICE_AUTO:
            if self._flatpak_installed(self.VICE_FLATPAK):
                return [shutil.which("flatpak") or "flatpak", "run", "--command=x64sc", self.VICE_FLATPAK]
            return self._resolve("x64sc")
        return self._resolve(self.vice)

    def launch(self, entry: RP9Entry) -> subprocess.Popen[bytes]:
        """Start de passende emulator voor ``entry`` en geef het proces terug."""
        if entry.platform is Platform.AMIGA:
            return self._launch_amiga(entry)
        if entry.platform is Platform.C64:
            return self._launch_c64(entry)
        raise LaunchError(tr("Onbekend platform; stel het platform in via de editor."))

    def _launch_amiga(self, entry: RP9Entry) -> subprocess.Popen[bytes]:
        """Start Amiberry met geselecteerde configuratie en media."""
        manifest = entry.manifest
        selected_floppies = [
            name for name in manifest.amiberry_floppies
            if name and Path(name).suffix.lower() in AMIGA_FLOPPY_EXTENSIONS
        ][:4]
        selected_hardfile = manifest.amiberry_hardfile
        if selected_hardfile and Path(selected_hardfile).suffix.lower() != ".hdf":
            raise LaunchError(tr("De geselecteerde Amiberry-harddisk-image moet een HDF-bestand zijn."))
        selected_cdimage = manifest.amiberry_cdimage
        if selected_cdimage and Path(selected_cdimage).suffix.lower() not in AMIGA_CD_EXTENSIONS:
            raise LaunchError(tr("De geselecteerde Amiberry-CD-image moet een ISO- of CHD-bestand zijn."))
        media = list(dict.fromkeys([
            *selected_floppies,
            *([selected_hardfile] if selected_hardfile else []),
            *([selected_cdimage] if selected_cdimage else []),
        ]))
        tmpdir = Path(tempfile.mkdtemp(prefix="rp9-", dir="/tmp")) if media else None
        try:
            extracted = RP9Archive(entry.path).extract(media, tmpdir) if tmpdir else []
            extracted_by_name = dict(zip(media, extracted))
            cmd = self._resolve(self.amiberry, self.AMIBERRY_FLATPAK)
            if manifest.amiberry_model:
                cmd += ["--model", manifest.amiberry_model]
            if manifest.amiberry_config:
                cmd += ["--config", manifest.amiberry_config]
            if selected_hardfile:
                cmd += ["-W", f"DH0:{extracted_by_name[selected_hardfile]}"]
            if selected_cdimage:
                cmd += ["--cdimage", str(extracted_by_name[selected_cdimage])]
            for drive, name in enumerate(manifest.amiberry_floppies[:4]):
                if name:
                    if name not in extracted_by_name:
                        raise LaunchError(tr("Amiberry-media ontbreekt in het archief: {name}", name=name))
                    cmd += [f"-{drive}", str(extracted_by_name[name])]
            cmd.append(str(entry.path.resolve()))
            # Amiberry laadt de RP9-configuratie bij het verwerken van het bestand en overschrijft
            # eerdere -s-opties; daarom komen deze opties pas ná het RP9-pad.
            if manifest.fullscreen:
                cmd += ["-s", "gfx_fullscreen_amiga=true"]
            cmd += self._split_options(manifest.amiberry_options, "Amiberry")
            proc = self._spawn(cmd, reap=tmpdir is None)
        except BaseException:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
            raise
        if tmpdir:
            self._reap(proc, tmpdir)
        return proc

    @staticmethod
    def _split_options(options: str, emulator: str) -> list[str]:
        """Parseer emulatoropties zonder shell-uitvoering."""
        try:
            return shlex.split(options)
        except ValueError as exc:
            raise LaunchError(tr("Ongeldige {emulator}-opties: {exc}", emulator=emulator, exc=exc)) from exc

    def _launch_c64(self, entry: RP9Entry) -> subprocess.Popen[bytes]:
        """Pak de images uit naar een privé-map in /tmp en start VICE.

        De map (mode 0700, via ``mkdtemp``) wordt opgeruimd zodra VICE stopt.
        """
        exe = self._resolve_vice()
        via_flatpak = exe[1:2] == ["run"]
        manifest = entry.manifest
        configured_media = bool(
            manifest.vice_autostart or manifest.vice_tape or any(manifest.vice_drives)
        )
        if configured_media:
            auto = manifest.vice_autostart
            tape = manifest.vice_tape
            drives = manifest.vice_drives[:4]
            if auto and Path(auto).suffix.lower() not in C64_AUTOSTART_EXTENSIONS:
                raise LaunchError(tr("De geselecteerde VICE-autostart-image is geen C64-image."))
            if tape and Path(tape).suffix.lower() not in C64_TAPE_EXTENSIONS:
                raise LaunchError(tr("Een VICE-datasette-image moet .tap of .t64 zijn."))
            if any(
                name and Path(name).suffix.lower() not in C64_DISK_EXTENSIONS
                for name in drives
            ):
                raise LaunchError(tr("VICE-diskstations vereisen .d64, .d71, .d81 of .g64-images."))
            media = list(dict.fromkeys([*([auto] if auto else []), *([tape] if tape else []),
                                        *(name for name in drives if name)]))
        else:
            images = [n for n in entry.disk_images if Path(n).suffix.lower() in C64_EXTENSIONS]
            if not images:
                raise LaunchError(tr("Geen C64-disk-images in dit archief."))
            auto, tape, drives = images[0], "", tuple(images[1:3])
            media = list(dict.fromkeys([auto, *drives]))
        if not media:
            raise LaunchError(tr("Geen C64-disk-images in dit archief."))
        base = self.FLATPAK_TMP if via_flatpak else Path("/tmp")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmpdir = Path(tempfile.mkdtemp(prefix="rp9-", dir=base))
        try:
            files = RP9Archive(entry.path).extract(media, tmpdir)
            extracted_by_name = dict(zip(media, files))
            cmd = list(exe)
            if manifest.vice_config:
                cmd += ["-config", manifest.vice_config]
            if manifest.fullscreen:
                cmd.append("-VICIIfull")
            if auto:
                cmd += ["-autostart", str(extracted_by_name[auto])]
            if tape:
                cmd += ["-1", str(extracted_by_name[tape])]
            if configured_media:
                for drive, name in enumerate(drives, start=8):
                    if name:
                        cmd += [f"-{drive}", str(extracted_by_name[name])]
            else:
                for drive, name in enumerate(drives, start=9):
                    cmd += [f"-{drive}", str(extracted_by_name[name])]
            cmd += self._split_options(manifest.vice_options, "VICE")
            proc = self._spawn(cmd, reap=False)
        except BaseException:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise
        self._reap(proc, tmpdir)
        return proc

    @staticmethod
    def _reap(proc: subprocess.Popen[bytes], cleanup: Path | None = None) -> None:
        """Wacht in een achtergrondthread op ``proc`` (geen zombie) en verwijder daarna ``cleanup``."""
        def worker() -> None:
            proc.wait()
            if cleanup:
                shutil.rmtree(cleanup, ignore_errors=True)

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def purge_stale_temp(max_age_s: float = 86400) -> None:
        """Verwijder eigen, verlopen ``/tmp/rp9-*``-mappen van eerdere (afgebroken) sessies."""
        for d in [*Path("/tmp").glob("rp9-*"), *EmulatorLauncher.FLATPAK_TMP.glob("rp9-*")]:
            try:
                st = d.lstat()
                if d.is_dir() and not d.is_symlink() and st.st_uid == os.getuid() and time.time() - st.st_mtime > max_age_s:
                    shutil.rmtree(d, ignore_errors=True)
            except OSError:
                continue

    @staticmethod
    def _spawn(cmd: list[str], reap: bool = True) -> subprocess.Popen[bytes]:
        """Start een proces zonder shell en meld directe crashes.

        Raises:
            LaunchError: als starten mislukt of de emulator binnen 1,5 s met een fout stopt.
        """
        err = tempfile.TemporaryFile()
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=err, start_new_session=True)
        except OSError as exc:
            err.close()
            raise LaunchError(tr("Starten mislukt: {exc}", exc=exc)) from exc
        try:
            code = proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            err.close()
            if reap:
                EmulatorLauncher._reap(proc)
            return proc
        if code != 0:
            err.seek(0)
            detail = err.read().decode(errors="replace").strip()[-500:]
            err.close()
            raise LaunchError(tr("Emulator stopte direct (code {code}).\n{detail}", code=code, detail=detail))
        err.close()
        return proc
