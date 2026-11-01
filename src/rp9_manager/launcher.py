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
from .errors import EmulatorNotFoundError, LaunchError
from .manifest import C64_EXTENSIONS, Platform


class EmulatorLauncher:
    """Start Amiberry (Amiga) of VICE ``x64sc`` (C64)."""

    def __init__(self, amiberry: str = "amiberry", vice: str = "x64sc") -> None:
        """Configureer de namen of paden van de emulators."""
        self.amiberry = amiberry
        self.vice = vice

    AMIBERRY_FLATPAK = "com.blitterstudio.amiberry"

    @staticmethod
    def _flatpak_installed(app_id: str) -> bool:
        """Controleer of een Flatpak-app geïnstalleerd is."""
        flatpak = shutil.which("flatpak")
        if not flatpak:
            return False
        result = subprocess.run([flatpak, "info", app_id], capture_output=True, check=False)
        return result.returncode == 0

    def _resolve(self, command: str, flatpak_id: str | None = None) -> list[str]:
        """Bepaal het uit te voeren commando (pad, eigen commando met argumenten of Flatpak).

        Raises:
            EmulatorNotFoundError: als de emulator nergens gevonden wordt.
        """
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            raise EmulatorNotFoundError(f"Ongeldig emulatorcommando '{command}': {exc}") from exc
        if parts and shutil.which(parts[0]):
            return [shutil.which(parts[0]) or parts[0], *parts[1:]]
        if flatpak_id and self._flatpak_installed(flatpak_id):
            return [shutil.which("flatpak") or "flatpak", "run", flatpak_id]
        raise EmulatorNotFoundError(
            f"Emulator '{command}' is niet gevonden. "
            "Installeer deze of stel het pad in via Instellingen."
        )

    def launch(self, entry: RP9Entry) -> subprocess.Popen[bytes]:
        """Start de passende emulator voor ``entry`` en geef het proces terug."""
        if entry.platform is Platform.AMIGA:
            return self._spawn([*self._resolve(self.amiberry, self.AMIBERRY_FLATPAK), str(entry.path.resolve())])
        if entry.platform is Platform.C64:
            return self._launch_c64(entry)
        raise LaunchError("Onbekend platform; stel het platform in via de editor.")

    def _launch_c64(self, entry: RP9Entry) -> subprocess.Popen[bytes]:
        """Pak de images uit naar een privé-map in /tmp en start VICE.

        De map (mode 0700, via ``mkdtemp``) wordt opgeruimd zodra VICE stopt.
        """
        exe = self._resolve(self.vice)
        images = [n for n in entry.disk_images if Path(n).suffix.lower() in C64_EXTENSIONS]
        if not images:
            raise LaunchError("Geen C64-disk-images in dit archief.")
        tmpdir = Path(tempfile.mkdtemp(prefix="rp9-", dir="/tmp"))
        try:
            files = RP9Archive(entry.path).extract(images, tmpdir)
            # Eerste image als -autostart; overige als extra drives.
            cmd = [*exe, "-autostart", str(files[0])]
            for drive, extra in enumerate(files[1:3], start=9):
                cmd += [f"-{drive}", str(extra)]
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
        for d in Path("/tmp").glob("rp9-*"):
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
            raise LaunchError(f"Starten mislukt: {exc}") from exc
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
            raise LaunchError(f"Emulator stopte direct (code {code}).\n{detail}")
        err.close()
        return proc
