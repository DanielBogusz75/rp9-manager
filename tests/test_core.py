import shutil
import zipfile
from pathlib import Path

import pytest

from rp9_manager.archive import RP9Archive
from rp9_manager.errors import CorruptArchiveError, EmulatorNotFoundError, LaunchError
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
    e = RP9Archive.create(
        s,
        tmp_path / "g.rp9",
        Manifest(title="T", description="D", vice_options="-pal"),
    ).summarize()
    assert e.error is None and e.platform is Platform.C64 and e.title == "T"
    assert e.manifest.description == "D" and e.manifest.media == ("game.d64",)
    assert e.manifest.vice_options == "-pal"


def test_emulator_options_roundtrip(tmp_path: Path) -> None:
    from rp9_manager.manifest import Manifest

    source = tmp_path / "source"
    source.mkdir()
    (source / "game.d64").write_bytes(b"x")
    (source / "game.iso").write_bytes(b"cd")
    archive = RP9Archive.create(source, tmp_path / "game.rp9", Manifest(title="Game"))
    manifest = archive.read_manifest()
    manifest.amiberry_options = "--fullscreen --config '/path with spaces/config.uae'"
    manifest.vice_options = '-joydev1 "My Joystick"'
    manifest.amiberry_model = "A1200"
    manifest.amiberry_config = "/configs/amiga.uae"
    manifest.amiberry_floppies = ("disk1.adf", "", "disk2.adf", "")
    manifest.amiberry_hardfile = "drive.hdf"
    manifest.amiberry_cdimage = "game.iso"
    manifest.vice_config = "/configs/vice"
    manifest.vice_autostart = "game.d64"
    manifest.vice_tape = "game.tap"
    manifest.vice_drives = ("disk1.d64", "", "disk2.d64", "")

    archive.write_manifest(manifest)

    saved = archive.read_manifest()
    assert saved.amiberry_options == manifest.amiberry_options
    assert saved.vice_options == manifest.vice_options
    assert saved.amiberry_model == manifest.amiberry_model
    assert saved.amiberry_config == manifest.amiberry_config
    assert saved.amiberry_floppies == manifest.amiberry_floppies
    assert saved.amiberry_hardfile == manifest.amiberry_hardfile
    assert saved.amiberry_cdimage == manifest.amiberry_cdimage
    assert saved.vice_config == manifest.vice_config
    assert saved.vice_autostart == manifest.vice_autostart
    assert saved.vice_tape == manifest.vice_tape
    assert saved.vice_drives == manifest.vice_drives


def test_amiberry_launch_uses_game_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rp9_manager.archive import RP9Entry
    from rp9_manager.manifest import Manifest

    game = tmp_path / "game.rp9"
    game.touch()
    entry = RP9Entry(
        game,
        Manifest(platform=Platform.AMIGA, amiberry_options='--config "/path with spaces/game.uae"'),
    )
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))

    EmulatorLauncher(amiberry="/bin/true").launch(entry)

    assert seen[0] == [
        "/bin/true",
        str(game.resolve()),
        "--config",
        "/path with spaces/game.uae",
    ]


def test_amiberry_fullscreen_comes_after_rp9_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rp9_manager.archive import RP9Entry
    from rp9_manager.manifest import Manifest

    game = tmp_path / "game.rp9"
    game.touch()
    entry = RP9Entry(game, Manifest(platform=Platform.AMIGA, fullscreen=True))
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))

    EmulatorLauncher(amiberry="/bin/true").launch(entry)

    assert seen[0] == ["/bin/true", str(game.resolve()), "-s", "gfx_fullscreen_amiga=true"]


def test_vice_launch_uses_game_options(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rp9_manager.archive import RP9Entry
    from rp9_manager.manifest import Manifest

    source = tmp_path / "source"
    source.mkdir()
    (source / "game.d64").write_bytes(b"x")
    archive = RP9Archive.create(source, tmp_path / "game.rp9", Manifest(title="Game"))
    entry = archive.summarize()
    entry.manifest.vice_options = '-joydev1 "My Joystick"'
    entry.manifest.fullscreen = True
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))
    monkeypatch.setattr(
        EmulatorLauncher,
        "_reap",
        staticmethod(lambda proc, cleanup=None: shutil.rmtree(cleanup) if cleanup else None),
    )

    EmulatorLauncher(vice="/bin/true").launch(entry)

    assert seen[0][:3] == ["/bin/true", "-VICIIfull", "-autostart"]
    assert Path(seen[0][3]).name == "game.d64"
    assert seen[0][-2:] == ["-joydev1", "My Joystick"]


def test_vice_flatpak_fallback_uses_home_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rp9_manager.manifest import Manifest

    source = tmp_path / "source"
    source.mkdir()
    (source / "game.d64").write_bytes(b"x")
    entry = RP9Archive.create(source, tmp_path / "game.rp9", Manifest(title="Game")).summarize()
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "FLATPAK_TMP", tmp_path / "cache")
    monkeypatch.setattr(EmulatorLauncher, "_flatpak_installed", staticmethod(lambda app_id: app_id == "net.sf.VICE"))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/flatpak" if name == "flatpak" else None)
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))
    monkeypatch.setattr(
        EmulatorLauncher,
        "_reap",
        staticmethod(lambda proc, cleanup=None: shutil.rmtree(cleanup) if cleanup else None),
    )

    EmulatorLauncher().launch(entry)

    assert seen[0][:4] == ["/usr/bin/flatpak", "run", "--command=x64sc", "net.sf.VICE"]
    assert seen[0][4] == "-autostart"
    assert Path(seen[0][5]).is_relative_to(tmp_path / "cache")


def test_amiberry_launch_uses_selected_media_and_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rp9_manager.manifest import Manifest

    source = tmp_path / "source"
    source.mkdir()
    (source / "first.adf").write_bytes(b"disk 1")
    (source / "second.adf").write_bytes(b"disk 2")
    (source / "drive.hdf").write_bytes(b"hard disk")
    (source / "game.iso").write_bytes(b"CD image")
    manifest = Manifest(
        platform=Platform.AMIGA,
        amiberry_floppies=("first.adf", "", "second.adf", ""),
        amiberry_hardfile="drive.hdf",
        amiberry_cdimage="game.iso",
        amiberry_model="A1200",
        amiberry_options="-G",
    )
    archive = RP9Archive.create(
        source,
        tmp_path / "amiga.rp9",
        manifest,
    )
    archive.write_manifest(manifest)
    entry = archive.summarize()
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))
    monkeypatch.setattr(
        EmulatorLauncher,
        "_reap",
        staticmethod(lambda proc, cleanup=None: shutil.rmtree(cleanup) if cleanup else None),
    )

    EmulatorLauncher(amiberry="/bin/true").launch(entry)

    command = seen[0]
    assert command[:3] == ["/bin/true", "--model", "A1200"]
    assert "-0" in command and "-2" in command and "-W" in command and "--cdimage" in command
    assert "-G" in command
    assert command[command.index("-G") - 1] == str(archive.path.resolve())
    assert Path(command[command.index("-0") + 1]).name == "first.adf"
    assert Path(command[command.index("-2") + 1]).name == "second.adf"
    assert command[command.index("-W") + 1].startswith("DH0:")
    assert Path(command[command.index("--cdimage") + 1]).name == "game.iso"


def test_vice_launch_uses_selected_drives_and_tape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rp9_manager.manifest import Manifest

    source = tmp_path / "source"
    source.mkdir()
    for name in ("first.d64", "second.d64", "game.tap"):
        (source / name).write_bytes(name.encode())
    manifest = Manifest(
        platform=Platform.C64,
        vice_autostart="first.d64",
        vice_tape="game.tap",
        vice_drives=("first.d64", "", "second.d64", ""),
        vice_config="/configs/vice",
    )
    archive = RP9Archive.create(
        source,
        tmp_path / "c64.rp9",
        manifest,
    )
    archive.write_manifest(manifest)
    entry = archive.summarize()
    seen: list[list[str]] = []
    monkeypatch.setattr(EmulatorLauncher, "_spawn", staticmethod(lambda cmd, reap=True: seen.append(cmd)))
    monkeypatch.setattr(
        EmulatorLauncher,
        "_reap",
        staticmethod(lambda proc, cleanup=None: shutil.rmtree(cleanup) if cleanup else None),
    )

    EmulatorLauncher(vice="/bin/true").launch(entry)

    command = seen[0]
    assert command[:3] == ["/bin/true", "-config", "/configs/vice"]
    assert "-autostart" in command and "-1" in command and "-8" in command and "-10" in command
    assert Path(command[command.index("-autostart") + 1]).name == "first.d64"
    assert Path(command[command.index("-1") + 1]).name == "game.tap"
    assert Path(command[command.index("-10") + 1]).name == "second.d64"


def test_invalid_emulator_options_raise_launch_error() -> None:
    from rp9_manager.archive import RP9Entry
    from rp9_manager.manifest import Manifest

    entry = RP9Entry(Path("game.rp9"), Manifest(platform=Platform.AMIGA, amiberry_options="'unterminated"))
    with pytest.raises(LaunchError, match="Ongeldige Amiberry-opties"):
        EmulatorLauncher(amiberry="/bin/true").launch(entry)


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


def test_extract_duplicate_basenames_remain_distinct(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicate.rp9"
    with zipfile.ZipFile(archive_path, "w") as archive_file:
        archive_file.writestr("disk1/game.adf", b"first")
        archive_file.writestr("disk2/game.adf", b"second")
    target = tmp_path / "extracted"
    target.mkdir()

    extracted = RP9Archive(archive_path).extract(["disk1/game.adf", "disk2/game.adf"], target)

    assert [path.name for path in extracted] == ["game.adf", "game_2.adf"]
    assert [path.read_bytes() for path in extracted] == [b"first", b"second"]


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


def test_translation_switches_language() -> None:
    from rp9_manager import i18n

    try:
        i18n.set_language("en")
        assert i18n.tr("Starten") == "Launch"
        assert i18n.tr("'{title}' gestart", title="X") == "'X' started"
        assert i18n.tr("Onbekende tekst") == "Onbekende tekst"
        i18n.set_language("nl")
        assert i18n.tr("Starten") == "Starten"
        i18n.set_language("xx")
        assert i18n.get_language() == "nl"
    finally:
        i18n.set_language("nl")


def test_core_errors_are_translated() -> None:
    from rp9_manager import i18n

    try:
        i18n.set_language("en")
        with pytest.raises(EmulatorNotFoundError, match="was not found"):
            EmulatorLauncher(amiberry="/nonexistent/amiberry")._resolve("/nonexistent/amiberry")
    finally:
        i18n.set_language("nl")


def test_language_is_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rp9_manager import i18n, manager as manager_module

    monkeypatch.setattr(manager_module, "CONFIG_PATH", tmp_path / "config.json")
    try:
        RP9Manager(library_dir=tmp_path).set_language("en")
        assert RP9Manager(library_dir=tmp_path).language == "en"
    finally:
        i18n.set_language("nl")


def _make_game(tmp_path: Path, name: str = "game.rp9") -> RP9Archive:
    from rp9_manager.manifest import Manifest

    source = tmp_path / "src"
    source.mkdir(exist_ok=True)
    (source / "disk1.adf").write_bytes(b"d1")
    return RP9Archive.create(source, tmp_path / name, Manifest(title="Game", platform=Platform.AMIGA))


def test_add_media_updates_archive_and_manifest(tmp_path: Path) -> None:
    from rp9_manager.media import MediaChanges, MediaItem, MediaKind

    archive = _make_game(tmp_path)
    shot, doc, disk = tmp_path / "shot.png", tmp_path / "manual.pdf", tmp_path / "disk2.adf"
    for f in (shot, doc, disk):
        f.write_bytes(b"x")
    entry = archive.summarize()
    changes = MediaChanges(add=[MediaItem(MediaKind.IMAGE, shot), MediaItem(MediaKind.DOCUMENT, doc),
                                MediaItem(MediaKind.DISK, disk)])

    archive.write_manifest(entry.manifest, changes)

    names = archive.names()
    assert {"shot.png", "manual.pdf", "disk2.adf"} <= set(names)
    xml = archive.read("rp9-manifest.xml").decode()
    assert 'type="screen-running"' in xml and ">shot.png<" in xml and ">manual.pdf<" in xml
    assert xml.index("<floppy") < xml.index(">disk2.adf<")
    again = archive.summarize()
    assert "shot.png" in again.images and "manual.pdf" in again.documents and "disk2.adf" in again.disk_images


def test_remove_media_clears_manifest_and_emulator_settings(tmp_path: Path) -> None:
    from dataclasses import replace

    from rp9_manager.media import MediaChanges

    archive = _make_game(tmp_path)
    entry = archive.summarize()
    manifest = replace(entry.manifest, amiberry_floppies=("disk1.adf", "", "", ""))
    archive.write_manifest(manifest)
    assert archive.summarize().manifest.amiberry_floppies[0] == "disk1.adf"

    archive.write_manifest(manifest, MediaChanges(remove=["disk1.adf"]))

    assert "disk1.adf" not in archive.names()
    assert ">disk1.adf<" not in archive.read("rp9-manifest.xml").decode()
    assert not any(archive.summarize().manifest.amiberry_floppies)


def test_media_rejects_duplicates_bad_types_and_protected_files(tmp_path: Path) -> None:
    from rp9_manager.errors import MediaError
    from rp9_manager.media import MediaChanges, MediaItem, MediaKind

    archive = _make_game(tmp_path)
    manifest = archive.summarize().manifest
    dup, bad = tmp_path / "disk1.adf", tmp_path / "virus.exe"
    dup.write_bytes(b"x")
    bad.write_bytes(b"x")
    before = archive.path.read_bytes()
    for changes in (
        MediaChanges(add=[MediaItem(MediaKind.DISK, dup)]),
        MediaChanges(add=[MediaItem(MediaKind.DOCUMENT, bad)]),
        MediaChanges(add=[MediaItem(MediaKind.IMAGE, tmp_path / "missing.png")]),
        MediaChanges(remove=["rp9-manifest.xml"]),
    ):
        with pytest.raises(MediaError):
            archive.write_manifest(manifest, changes)
    assert archive.path.read_bytes() == before


def test_create_with_media_changes(tmp_path: Path) -> None:
    from rp9_manager.manifest import Manifest
    from rp9_manager.media import MediaChanges, MediaItem, MediaKind

    source = tmp_path / "src"
    source.mkdir()
    (source / "a.d64").write_bytes(b"x")
    (source / "first.png").write_bytes(b"x")
    (source / "notes.txt").write_bytes(b"x")
    shot = tmp_path / "extra.png"
    shot.write_bytes(b"x")
    manager = RP9Manager(library_dir=tmp_path)
    assert manager.inspect_folder(source) == (["a.d64"], ["rp9-preview.png"], ["notes.txt"])

    entry = manager.create(
        source, tmp_path / "c64.rp9", Manifest(title="C"),
        MediaChanges(add=[MediaItem(MediaKind.IMAGE, shot)], remove=["notes.txt"]),
    )

    assert "extra.png" in entry.images and "rp9-preview.png" in entry.images
    assert "notes.txt" not in RP9Archive(entry.path).names()
    assert entry.preview_name == "rp9-preview.png"


def test_added_text_document_is_not_mistaken_for_description(tmp_path: Path) -> None:
    from rp9_manager.media import MediaChanges, MediaItem, MediaKind

    archive = _make_game(tmp_path)
    notes = tmp_path / "notes.txt"
    notes.write_text("niet de beschrijving")
    manifest = archive.summarize().manifest
    assert manifest.description == ""

    archive.write_manifest(manifest, MediaChanges(add=[MediaItem(MediaKind.DOCUMENT, notes)]))
    reread = archive.summarize()

    assert reread.manifest.description == ""
    assert archive.read("notes.txt") == "niet de beschrijving".encode()
    assert "notes.txt" in reread.documents


def _example(tmp_path: Path, pattern: str) -> RP9Archive:
    source = sorted(Path(__file__).parent.parent.glob(f"rp9-examples/{pattern}"))[0]
    target = tmp_path / source.name
    target.write_bytes(source.read_bytes())
    return RP9Archive(target)


def _tags(archive: RP9Archive) -> str:
    return archive.read("rp9-manifest.xml").decode()


def test_unchanged_save_keeps_manifest_identical_and_not_user_edited(tmp_path: Path) -> None:
    archive = _example(tmp_path, "*Amiga*.rp9")
    before = _tags(archive)
    archive.write_manifest(archive.summarize().manifest)
    after = _tags(archive)
    assert "user-edited" not in after
    import xml.etree.ElementTree as ET

    canonical = lambda text: ET.canonicalize(text.lstrip("\ufeff"), strip_text=True)  # noqa: E731
    assert canonical(after) == canonical(before)


def test_editing_sets_user_edited_and_clears_oid_on_title_change(tmp_path: Path) -> None:
    from dataclasses import replace

    archive = _example(tmp_path, "*Amiga*.rp9")
    manifest = archive.summarize().manifest
    archive.write_manifest(replace(manifest, year="1999"))
    xml = _tags(archive)
    assert 'user-edited="true"' in xml and 'oid="1.3.6.1.4.1.23153.1000.9.' in xml

    archive.write_manifest(replace(archive.summarize().manifest, title="Nieuwe titel"))
    xml = _tags(archive)
    assert 'libraryversion' not in xml and 'score=' not in xml
    assert 'oid="1.3.6.1.4.1.23153.1000.9.' not in xml
    assert 'oid="1.3.6.1.4.1.23153.1000.1.' in xml  # uitgever-OID blijft staan

    archive.write_manifest(replace(archive.summarize().manifest, publisher="Iemand anders"))
    assert 'oid="1.3.6.1.4.1.23153.1000.1.' not in _tags(archive)


def test_configuration_fields_roundtrip_amiga(tmp_path: Path) -> None:
    from dataclasses import replace

    archive = _example(tmp_path, "*Amiga*.rp9")
    manifest = archive.summarize().manifest
    archive.write_manifest(replace(
        manifest, system="a-4000", rom="310", fast_ram=2097152, rating="5", version="1.1", homepage="http://x.test",
        language="nl", tosec="x", mouse=True, joystick=False, joystick_port="2", turbo_floppy=True,
        silent_drives=False, autodrive=True, content_type="demo", genre="sports",
    ))
    got = archive.summarize().manifest
    assert (got.system, got.rom, got.fast_ram, got.rating, got.version) == ("a-4000", "310", 2097152, "5", "1.1")
    assert (got.homepage, got.language, got.tosec, got.content_type, got.genre) == ("http://x.test", "nl", "x", "demo", "sports")
    assert got.mouse and not got.joystick and got.joystick_port == "2"
    assert got.turbo_floppy and got.autodrive and not got.silent_drives
    xml = _tags(archive)
    assert "<playerversion>3.0.0.0</playerversion>" in xml and 'requiredversion="3.0.0.0"' in xml
    assert xml.count("input-joystick") == 1


def test_configuration_fields_roundtrip_c64_startup(tmp_path: Path) -> None:
    from dataclasses import replace

    archive = _example(tmp_path, "*C64*.rp9")
    manifest = archive.summarize().manifest
    assert manifest.auto_load and manifest.auto_run and manifest.turbo_start
    archive.write_manifest(replace(manifest, auto_run=False, turbo_start=False))
    got = archive.summarize().manifest
    assert got.auto_load and not got.auto_run and not got.turbo_start
    assert "<playerversion>2.2.0.0</playerversion>" in _tags(archive)


def test_image_types_priority_and_order(tmp_path: Path) -> None:
    from rp9_manager.media import MediaChanges, MediaItem, MediaKind

    archive = _example(tmp_path, "*Amiga*.rp9")
    a, b, c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    for f in (a, b, c):
        f.write_bytes(b"x")
    manifest = archive.summarize().manifest
    archive.write_manifest(manifest, MediaChanges(add=[
        MediaItem(MediaKind.IMAGE, a, "screen-title"),
        MediaItem(MediaKind.IMAGE, b, "screen-score"),
        MediaItem(MediaKind.IMAGE, c, "screen-running"),
    ]))
    entry = archive.summarize()
    assert entry.manifest.image_types["a.png"] == "screen-title"
    assert entry.manifest.image_types["b.png"] == "screen-score"
    assert entry.preview_name == "rp9-preview.png"
    xml = _tags(archive)
    assert xml.count('type="screen-running"') == 2 and 'priority="2">c.png<' in xml
    assert 'type="screen-title" priority="1">a.png<' in xml

    # Herordenen: c.png wordt de standaard "running"-afbeelding.
    archive.write_manifest(entry.manifest, MediaChanges(order=["c.png", "rp9-preview.png"]))
    assert archive.summarize().preview_name == "c.png"
