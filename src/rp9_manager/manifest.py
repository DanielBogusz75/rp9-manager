"""Parser en datamodel voor de ``rp9-manifest.xml`` in een .rp9-archief.

Het echte Cloanto-formaat (namespace ``http://www.retroplatform.com``) heeft de
structuur ``rp9/application/{description,configuration,media,extras}``. De
beschrijvende tekst staat niet in het manifest maar in een ingesloten helpdocument
(``rp9-help-en.txt``), dat via ``extras/document[@type=help]`` wordt aangewezen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields
from enum import Enum

from .errors import ManifestError
from .i18n import tr
from .media import MEDIA_ELEMENT_ORDER, MediaKind, media_element

NS_URI = "http://www.retroplatform.com"
NS = f"{{{NS_URI}}}"
XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"
DEFAULT_HELP_NAME = "rp9-help-en.txt"

DISK_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".adf", ".adz", ".dms", ".ipf", ".hdf", ".iso", ".chd",
        ".d64", ".d71", ".d81", ".g64", ".t64", ".prg", ".tap", ".crt",
    }
)
C64_EXTENSIONS: frozenset[str] = frozenset({".d64", ".d71", ".d81", ".g64", ".t64", ".prg", ".tap", ".crt"})
C64_DISK_EXTENSIONS: frozenset[str] = frozenset({".d64", ".d71", ".d81", ".g64"})
C64_TAPE_EXTENSIONS: frozenset[str] = frozenset({".tap", ".t64"})
C64_AUTOSTART_EXTENSIONS: frozenset[str] = C64_EXTENSIONS - {".crt"}
AMIGA_FLOPPY_EXTENSIONS: frozenset[str] = frozenset({".adf", ".adz", ".dms", ".ipf"})
AMIGA_CD_EXTENSIONS: frozenset[str] = frozenset({".iso", ".chd"})
AMIGA_EXTENSIONS: frozenset[str] = AMIGA_FLOPPY_EXTENSIONS | AMIGA_CD_EXTENSIONS | {".hdf"}

# Waarden zoals ze in echte RP9-bestanden van Cloanto voorkomen.
IMAGE_TYPES: tuple[str, ...] = ("screen-running", "screen-title", "screen-score")
SYSTEMS: dict[Platform, tuple[str, ...]] = {}  # gevuld na de definitie van Platform
KICKSTART_ROMS: tuple[tuple[str, str], ...] = (("120", "Kickstart 1.2"), ("130", "Kickstart 1.3"), ("310", "Kickstart 3.1"))
# Systemen die RetroPlatform Player 3.0.0.0 of nieuwer vereisen.
NEWER_PLAYER_SYSTEMS: frozenset[str] = frozenset({"a-500plus", "a-2000", "a-3000", "a-4000"})
NEWER_PLAYER_VERSION = (3, 0, 0, 0)
# Volgorde van de elementen, zoals in echte RP9-bestanden.
DESCRIPTION_ORDER: tuple[str, ...] = (
    "type", "entity", "title", "year", "rating", "version", "homepage", "tosec-extended",
    "joystick", "mouse", "keyboard", "multiplayer", "systemrom", "genre", "distribution", "language",
)
APPLICATION_ORDER: tuple[str, ...] = ("description", "startup", "configuration", "media", "extras")


class Platform(str, Enum):
    """Ondersteunde platformen."""

    AMIGA = "Amiga"
    C64 = "C64"
    UNKNOWN = "Onbekend"

    @classmethod
    def from_text(cls, text: str | None) -> "Platform":
        """Zet een systeemnaam (``a-500``, ``c64``, ``Amiga``) om naar een platform."""
        value = (text or "").strip().lower()
        if value.startswith("a-") or "amiga" in value:
            return cls.AMIGA
        if "c64" in value or "c-64" in value or "commodore" in value:
            return cls.C64
        return cls.UNKNOWN


SYSTEMS.update({
    Platform.AMIGA: ("a-500", "a-500plus", "a-1200"),
    Platform.C64: ("c-64",),
    Platform.UNKNOWN: (),
})


@dataclass(slots=True)
class Manifest:
    """Bewerkbare weergave van de manifestgegevens."""

    title: str = ""
    description: str = ""
    platform: Platform = Platform.UNKNOWN
    publisher: str = ""
    year: str = ""
    genre: str = ""
    system: str = ""
    help_file: str = ""
    media: tuple[str, ...] = ()
    amiberry_options: str = ""
    vice_options: str = ""
    amiberry_model: str = ""
    amiberry_config: str = ""
    amiberry_floppies: tuple[str, ...] = ()
    amiberry_hardfile: str = ""
    amiberry_cdimage: str = ""
    vice_config: str = ""
    vice_autostart: str = ""
    vice_tape: str = ""
    vice_drives: tuple[str, ...] = ()
    fullscreen: bool = False
    content_type: str = ""
    rating: str = ""
    version: str = ""
    homepage: str = ""
    language: str = ""
    tosec: str = ""
    joystick: bool = False
    mouse: bool = False
    keyboard: bool = False
    multiplayer: bool = False
    joystick_port: str = ""
    rom: str = ""
    fast_ram: int = 0
    turbo_floppy: bool = False
    turbo_start: bool = False
    silent_drives: bool = False
    autodrive: bool = False
    auto_load: bool = False
    auto_run: bool = False
    image_types: dict[str, str] = field(default_factory=dict)
    extras_order: tuple[str, ...] = ()


# Velden die de beschrijving en configuratie in het RP9 zelf bepalen; hiervoor zet de editor ``user-edited``.
RP9_FIELDS: tuple[str, ...] = (
    "title", "publisher", "year", "genre", "system", "platform", "content_type", "rating", "version",
    "homepage", "language", "tosec", "joystick", "mouse", "keyboard", "multiplayer", "joystick_port", "rom",
    "fast_ram", "turbo_floppy", "turbo_start", "silent_drives", "autodrive", "auto_load", "auto_run",
)


def _tag(el: ET.Element) -> str:
    """Geef de tagnaam zonder namespace."""
    return el.tag.rsplit("}", 1)[-1]


class ManifestParser:
    """Leest, wijzigt en serialiseert manifest-XML."""

    @staticmethod
    def parse_tree(data: bytes) -> ET.ElementTree:
        """Parseer XML-bytes (BOM toegestaan) tot een ElementTree.

        Raises:
            ManifestError: bij ongeldige XML of een DOCTYPE/ENTITY-declaratie.
        """
        data = data.lstrip(b"\xef\xbb\xbf")
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ManifestError(tr("DOCTYPE/ENTITY in het manifest is niet toegestaan."))
        try:
            return ET.ElementTree(ET.fromstring(data))
        except ET.ParseError as exc:
            raise ManifestError(tr("Ongeldig manifest: {exc}", exc=exc)) from exc

    @staticmethod
    def _desc(root: ET.Element) -> ET.Element | None:
        """Zoek ``application/description``."""
        for el in root.iter():
            if _tag(el) == "description" and len(el):
                return el
        return None

    @classmethod
    def parse(cls, data: bytes) -> Manifest:
        """Zet manifest-bytes om naar een :class:`Manifest`."""
        root = cls.parse_tree(data).getroot()
        if _tag(root) != "rp9":
            raise ManifestError(tr("Geen geldig rp9-manifest (rootelement is niet 'rp9')."))
        m = Manifest()
        desc = cls._desc(root)
        if desc is not None:
            for el in desc:
                text = (el.text or "").strip()
                tag = _tag(el)
                if tag == "title":
                    m.title = text
                elif tag == "year":
                    m.year = text
                elif tag == "genre":
                    m.genre = text
                elif tag == "type":
                    m.content_type = text
                elif tag in ("rating", "version", "homepage", "language"):
                    setattr(m, tag, text)
                elif tag == "tosec-extended":
                    m.tosec = text
                elif tag in ("joystick", "mouse", "keyboard", "multiplayer"):
                    setattr(m, tag, text.lower() == "true")
                elif tag == "systemrom" and not m.rom:
                    m.rom = text
                elif tag == "entity" and el.get("type") == "publisher" and not m.publisher:
                    m.publisher = text
        system = next((e for e in root.iter() if _tag(e) == "system"), None)
        m.system = (system.text or "").strip() if system is not None else ""
        m.platform = Platform.from_text(m.system)
        media = [
            (e.text or "").strip()
            for media_el in root.iter() if _tag(media_el) == "media"
            for e in media_el if (e.text or "").strip()
        ]
        m.media = tuple(media)
        cls._parse_configuration(root, m)
        m.extras_order = tuple(
            (e.text or "").strip()
            for extras in root.iter() if _tag(extras) == "extras"
            for e in extras if (e.text or "").strip()
        )
        m.image_types = {
            (e.text or "").strip(): e.get("type", "")
            for e in root.iter() if _tag(e) == "image" and (e.text or "").strip()
        }
        for e in root.iter():
            if _tag(e) == "document" and e.get("type") == "help" and (e.text or "").strip().lower().endswith(".txt"):
                m.help_file = (e.text or "").strip()
                break
        return m

    @staticmethod
    def _parse_configuration(root: ET.Element, m: Manifest) -> None:
        """Lees ``configuration`` en ``startup`` in ``m``."""
        for e in root.iter():
            tag, text = _tag(e), (e.text or "").strip()
            if tag == "rom" and e.get("type") == "system" and text:
                m.rom = text
            elif tag == "ram" and e.get("type") == "fast" and text.isdigit():
                m.fast_ram = int(text)
            elif tag == "compatibility":
                if text == "turbo-floppy":
                    m.turbo_floppy = True
                elif text == "turbo-start":
                    m.turbo_start = True
            elif tag == "peripheral":
                if text == "silent-drives":
                    m.silent_drives = True
                elif text == "autodrive":
                    m.autodrive = True
                elif text == "input-joystick" and not m.joystick_port:
                    m.joystick_port = e.get("unit", "")
            elif tag == "load" and e.get("auto") == "true":
                m.auto_load = True
            elif tag == "run" and e.get("auto") == "true":
                m.auto_run = True

    @classmethod
    def update_media(
        cls,
        data: bytes,
        added: list[tuple[MediaKind, str, str]],
        removed: set[str],
        order: list[str] | None = None,
    ) -> bytes:
        """Registreer toegevoegde en verwijderde bestanden in ``media`` en ``extras``.

        ``added`` bevat (soort, bestandsnaam, afbeeldingstype). Afbeeldingen worden
        ``image[@type=...]`` en documenten ``document[@type=help]`` (beide ``root="embedded"``),
        zoals in bestaande RP9-bestanden. ``order`` bepaalt de volgorde van de extra's. Prioriteiten
        worden per elementsoort en type opnieuw genummerd (vanaf 1); de volgorde in ``media``
        volgt het schema (floppy, harddrive, cd, tape, snapshot). Zet ``user-edited="true"``.
        """
        ET.register_namespace("", NS_URI)
        ET.register_namespace("xsi", XSI_URI)
        tree = cls.parse_tree(data)
        root = tree.getroot()
        app = next((e for e in root.iter() if _tag(e) == "application"), None)
        if app is None:
            app = ET.SubElement(root, f"{NS}application")

        def container(tag: str) -> ET.Element:
            """Haal ``media`` of ``extras`` op of maak het aan."""
            found = next((e for e in app if _tag(e) == tag), None)
            return found if found is not None else ET.SubElement(app, f"{NS}{tag}")

        media, extras = container("media"), container("extras")
        for parent in (media, extras):
            for el in list(parent):
                if (el.text or "").strip() in removed:
                    parent.remove(el)
        for kind, name, image_type in added:
            if kind is MediaKind.DISK:
                ET.SubElement(media, f"{NS}{media_element(name)}").text = name
            elif kind is MediaKind.IMAGE:
                ET.SubElement(extras, f"{NS}image", {"root": "embedded", "type": image_type}).text = name
            else:
                ET.SubElement(extras, f"{NS}document", {"root": "embedded", "type": "help"}).text = name
        rank = {tag: index for index, tag in enumerate(MEDIA_ELEMENT_ORDER)}
        media[:] = sorted(media, key=lambda el: rank.get(_tag(el), len(rank)))
        if order:
            position = {name: index for index, name in enumerate(order)}
            extras[:] = sorted(extras, key=lambda el: position.get((el.text or "").strip(), len(position)))
        for parent in (media, extras):
            counters: dict[tuple[str, str], int] = {}
            for el in parent:
                key = (_tag(el), el.get("type", "") if parent is extras else "")
                counters[key] = counters.get(key, 0) + 1
                el.set("priority", str(counters[key]))
        app.set("user-edited", "true")
        if not len(media):
            app.remove(media)
        if not len(extras):
            app.remove(extras)
        ET.indent(tree, space="\t")
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @classmethod
    def apply(cls, data: bytes | None, m: Manifest, help_name: str | None = None) -> bytes:
        """Verwerk ``m`` in bestaande XML (of maak een nieuw manifest) en geef bytes terug.

        Alleen bekende velden worden aangepast; al het andere blijft behouden. ``help_name`` is de
        bestandsnaam van het helpdocument dat in ``extras`` moet staan. Volgens de RP9-richtlijnen
        voor editors krijgt ``application`` het attribuut ``user-edited="true"`` zodra gegevens
        wijzigen, en worden de OID's gewist als titel of uitgever wijzigen.
        """
        ET.register_namespace("", NS_URI)
        ET.register_namespace("xsi", XSI_URI)
        old = cls.parse(data) if data else None
        root = cls.parse_tree(data).getroot() if data else ET.Element(f"{NS}rp9")
        tree = ET.ElementTree(root)

        def child(parent: ET.Element, tag: str) -> ET.Element:
            """Haal een kindelement op of maak het aan."""
            for el in parent:
                if _tag(el) == tag:
                    return el
            return ET.SubElement(parent, f"{NS}{tag}")

        def set_text(parent: ET.Element, tag: str, value: str, keep_empty: bool = False) -> None:
            """Zet de tekst van ``tag``; een lege waarde verwijdert het element (tenzij ``keep_empty``)."""
            existing = next((e for e in parent if _tag(e) == tag), None)
            if value or (keep_empty and existing is not None):
                child(parent, tag).text = value
            elif existing is not None:
                parent.remove(existing)

        def set_flag(parent: ET.Element, tag: str, text: str, on: bool, **attrs: str) -> None:
            """Zorg dat ``<tag>text</tag>`` wel (``on``) of niet in ``parent`` staat."""
            found = [e for e in parent if _tag(e) == tag and (e.text or "").strip() == text]
            if on and not found:
                ET.SubElement(parent, f"{NS}{tag}", attrs).text = text
            elif not on:
                for el in found:
                    parent.remove(el)

        app = child(root, "application")
        desc = child(app, "description")
        if not len(desc) or _tag(desc[0]) != "type":
            child(desc, "type").text = "game"
        set_text(desc, "type", m.content_type or "game")
        for tag, value in (("title", m.title), ("year", m.year), ("genre", m.genre)):
            set_text(desc, tag, value, keep_empty=True)
        for tag, value in (("rating", m.rating), ("version", m.version), ("homepage", m.homepage),
                           ("language", m.language), ("tosec-extended", m.tosec)):
            set_text(desc, tag, value)
        for tag in ("joystick", "mouse", "keyboard", "multiplayer"):
            set_text(desc, tag, "true" if getattr(m, tag) else "")
        if any(_tag(e) == "systemrom" for e in desc):
            set_text(desc, "systemrom", m.rom)
        pub = next((e for e in desc if _tag(e) == "entity" and e.get("type") == "publisher"), None)
        if m.publisher and pub is None:
            pub = ET.SubElement(desc, f"{NS}entity", {"type": "publisher", "priority": "1"})
        if pub is not None:
            pub.text = m.publisher
        rank = {tag: index for index, tag in enumerate(DESCRIPTION_ORDER)}
        desc[:] = sorted(desc, key=lambda el: rank.get(_tag(el), len(rank)))

        conf = child(app, "configuration")
        system = child(conf, "system")
        default_system = "c-64" if m.platform is Platform.C64 else "a-500"
        if m.platform is not Platform.UNKNOWN and Platform.from_text(m.system or system.text) is not m.platform:
            system.text = default_system
        elif m.system:
            system.text = m.system
        elif not system.text:
            system.text = default_system
        rom = next((e for e in conf if _tag(e) == "rom" and e.get("type") == "system"), None)
        listed = next((e for e in desc if _tag(e) == "systemrom"), None)
        if not m.rom and rom is not None:
            conf.remove(rom)
        elif m.rom and (rom is not None or listed is None or (listed.text or "").strip() != m.rom):
            (rom if rom is not None else ET.SubElement(conf, f"{NS}rom", {"type": "system"})).text = m.rom
        fast = next((e for e in conf if _tag(e) == "ram" and e.get("type") == "fast"), None)
        if fast is not None and not m.fast_ram:
            conf.remove(fast)
        elif m.fast_ram:
            (fast if fast is not None else ET.SubElement(conf, f"{NS}ram", {"type": "fast"})).text = str(m.fast_ram)
        set_flag(conf, "compatibility", "turbo-floppy", m.turbo_floppy)
        set_flag(conf, "compatibility", "turbo-start", m.turbo_start)
        set_flag(conf, "peripheral", "silent-drives", m.silent_drives)
        set_flag(conf, "peripheral", "autodrive", m.autodrive)
        sticks = [e for e in conf if _tag(e) == "peripheral" and (e.text or "").strip() == "input-joystick"]
        if not m.joystick_port:
            for el in sticks:
                conf.remove(el)
        elif sticks:
            sticks[0].set("unit", m.joystick_port)
        else:
            ET.SubElement(conf, f"{NS}peripheral", {"unit": m.joystick_port}).text = "input-joystick"

        startup = next((e for e in app if _tag(e) == "startup"), None)
        if m.auto_load or m.auto_run or startup is not None:
            startup = startup if startup is not None else ET.SubElement(app, f"{NS}startup")
            for tag, on in (("load", m.auto_load), ("run", m.auto_run)):
                for el in [e for e in startup if _tag(e) == tag]:
                    startup.remove(el)
                if on:
                    ET.SubElement(startup, f"{NS}{tag}", {"auto": "true"})

        if help_name:
            extras = child(app, "extras")
            if not any(
                _tag(e) == "document" and e.get("type") == "help" and (e.text or "").strip().lower().endswith(".txt")
                for e in extras
            ):
                doc = ET.SubElement(extras, f"{NS}document", {"root": "embedded", "type": "help", "priority": "1"})
                doc.text = help_name

        if not data:
            media = child(app, "media")
            for name in m.media:
                ET.SubElement(media, f"{NS}{media_element(name)}", {"priority": str(len(media) + 1)}).text = name
        app_rank = {tag: index for index, tag in enumerate(APPLICATION_ORDER)}
        app[:] = sorted(app, key=lambda el: app_rank.get(_tag(el), len(app_rank)))

        if old is not None:
            cls._mark_edited(root, app, old, m)
        cls._require_player_version(root, conf)
        ET.indent(tree, space="\t")
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _mark_edited(root: ET.Element, app: ET.Element, old: Manifest, new: Manifest) -> None:
        """Zet ``user-edited`` bij gewijzigde gegevens en wis de OID's bij een andere titel of uitgever."""
        if any(getattr(old, f.name) != getattr(new, f.name) for f in fields(Manifest) if f.name in RP9_FIELDS):
            app.set("user-edited", "true")
        if old.title != new.title or old.publisher != new.publisher:
            for key in ("oid", "libraryversion", "score"):
                app.attrib.pop(key, None)
            if old.publisher != new.publisher:
                for el in root.iter():
                    if _tag(el) == "entity" and el.get("type") == "publisher":
                        el.attrib.pop("oid", None)

    @staticmethod
    def _require_player_version(root: ET.Element, conf: ET.Element) -> None:
        """Verhoog ``playerversion`` als het gekozen systeem een nieuwere RetroPlatform Player vereist."""
        system = next((e for e in conf if _tag(e) == "system"), None)
        if system is None or (system.text or "").strip() not in NEWER_PLAYER_SYSTEMS:
            return
        for el in root.iter():
            if _tag(el) in ("playerversion", "features"):
                attr = el.get("requiredversion") if _tag(el) == "features" else el.text
                try:
                    current = tuple(int(part) for part in (attr or "").split("."))
                except ValueError:
                    current = ()
                if current < NEWER_PLAYER_VERSION:
                    text = ".".join(str(part) for part in NEWER_PLAYER_VERSION)
                    if _tag(el) == "features":
                        el.set("requiredversion", text)
                    else:
                        el.text = text
