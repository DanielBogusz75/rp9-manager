import shutil
import zipfile
from pathlib import Path

import pytest

from rp9_manager.archive import RP9Archive
from rp9_manager.errors import CorruptArchiveError, EmulatorNotFoundError
from rp9_manager.launcher import EmulatorLauncher
from rp9_manager.manager import RP9Manager
from rp9_manager.manifest import Platform

EXAMPLES = Path(__file__).parent.parent / "rp9-examples"
needs_examples = pytest.mark.skipif(not EXAMPLES.is_dir(), reason="rp9-examples ontbreekt")


@needs_examples
def test_scan_examples(tmp_path: Path) -> None:
    entries = RP9Manager(EXAMPLES).scan()
    assert entries and all(e.error is None for e in entries)
    assert all(e.platform is Platform.AMIGA and e.title and e.preview_name for e in entries)
    astro = next(e for e in entries if e.title == "Astro Marine Corps")
    assert astro.manifest.publisher == "Dinamic" and astro.manifest.year == "1990"
    assert astro.disk_images == ["amc1.adf", "amc2.adf"]
    assert "joystick" in astro.manifest.description
    assert RP9Manager(EXAMPLES).preview(astro)[:4] == b"\x89PNG"


@needs_examples
def test_edit_roundtrip_on_copy(tmp_path: Path) -> None:
    src = next(EXAMPLES.glob("Arkanoid*.rp9"))
    dst = tmp_path / "a.rp9"
    shutil.copy(src, dst)
    arc = RP9Archive(dst)
    m = arc.read_manifest()
    m.title, m.description, m.platform = "Nieuw", "Omschrijving", Platform.C64
    arc.write_manifest(m)
    e = arc.summarize()
    assert (e.title, e.manifest.description, e.platform) == ("Nieuw", "Omschrijving", Platform.C64)
    assert e.manifest.publisher == "Discovery Software"
    assert arc.read("arkanoid.adf") == RP9Archive(src).read("arkanoid.adf")
    assert not list(tmp_path.glob("*.tmp"))


def test_create_roundtrip(tmp_path: Path) -> None:
    from rp9_manager.manifest import Manifest

    s = tmp_path / "src"
    s.mkdir()
    (s / "game.d64").write_bytes(b"x")
    e = RP9Archive.create(s, tmp_path / "g.rp9", Manifest(title="T", description="D")).summarize()
    assert e.error is None and e.platform is Platform.C64 and e.title == "T"
    assert e.manifest.description == "D" and e.manifest.media == ("game.d64",)


def test_corrupt_and_zip_slip(tmp_path: Path) -> None:
    bad = tmp_path / "bad.rp9"
    bad.write_text("nope")
    assert RP9Archive(bad).summarize().error
    with pytest.raises(CorruptArchiveError):
        RP9Archive(bad).names()
    p = tmp_path / "e.rp9"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("../evil.d64", b"x")
    assert RP9Archive(p).disk_images() == []


def test_missing_emulator() -> None:
    with pytest.raises(EmulatorNotFoundError):
        EmulatorLauncher(amiberry="/nonexistent/amiberry")._resolve("/nonexistent/amiberry")


@needs_examples
def test_amiga_launch_uses_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))
    monkeypatch.chdir(EXAMPLES.parent)
    entry = RP9Manager(Path("rp9-examples")).scan()[0]
    EmulatorLauncher(amiberry="/bin/true").launch(entry)
    assert Path(seen[0][-1]).is_absolute() and seen[0][-1].endswith(".rp9")
