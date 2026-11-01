"""Parser en datamodel voor de ``rp9-manifest.xml`` in een .rp9-archief.

Het echte Cloanto-formaat (namespace ``http://www.retroplatform.com``) heeft de
structuur ``rp9/application/{description,configuration,media,extras}``. De
beschrijvende tekst staat niet in het manifest maar in een ingesloten helpdocument
(``rp9-help-en.txt``), dat via ``extras/document[@type=help]`` wordt aangewezen.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum

from .errors import ManifestError

NS_URI = "http://www.retroplatform.com"
NS = f"{{{NS_URI}}}"
XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"
DEFAULT_HELP_NAME = "rp9-help-en.txt"

DISK_EXTENSIONS: frozenset[str] = frozenset(
    {".adf", ".adz", ".dms", ".ipf", ".hdf", ".d64", ".d71", ".d81", ".g64", ".t64", ".prg", ".tap", ".crt"}
)
C64_EXTENSIONS: frozenset[str] = frozenset({".d64", ".d71", ".d81", ".g64", ".t64", ".prg", ".tap", ".crt"})
AMIGA_EXTENSIONS: frozenset[str] = frozenset({".adf", ".adz", ".dms", ".ipf", ".hdf"})


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
            raise ManifestError("DOCTYPE/ENTITY in het manifest is niet toegestaan.")
        try:
            return ET.ElementTree(ET.fromstring(data))
        except ET.ParseError as exc:
            raise ManifestError(f"Ongeldig manifest: {exc}") from exc

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
            raise ManifestError("Geen geldig rp9-manifest (rootelement is niet 'rp9').")
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
        for e in root.iter():
            if _tag(e) == "document" and e.get("type") == "help":
                m.help_file = (e.text or "").strip()
                break
        return m

    @classmethod
    def apply(cls, data: bytes | None, m: Manifest, help_name: str | None = None) -> bytes:
        """Verwerk ``m`` in bestaande XML (of maak een nieuw manifest) en geef bytes terug.

        Alleen bekende velden worden aangepast; al het andere blijft behouden.
        ``help_name`` is de bestandsnaam van het helpdocument dat in ``extras`` moet staan.
        """
        ET.register_namespace("", NS_URI)
        ET.register_namespace("xsi", XSI_URI)
        if data:
            root = cls.parse_tree(data).getroot()
        else:
            root = ET.Element(f"{NS}rp9")
        tree = ET.ElementTree(root)

        def child(parent: ET.Element, tag: str) -> ET.Element:
            """Haal een kindelement op of maak het aan."""
            for el in parent:
                if _tag(el) == tag:
                    return el
            return ET.SubElement(parent, f"{NS}{tag}")

        app = child(root, "application")
        desc = child(app, "description")
        if not len(desc) or _tag(desc[0]) != "type":
            child(desc, "type").text = "game"
        for tag, value in (("title", m.title), ("year", m.year), ("genre", m.genre)):
            if value or any(_tag(e) == tag for e in desc):
                child(desc, tag).text = value
        pub = next((e for e in desc if _tag(e) == "entity" and e.get("type") == "publisher"), None)
        if m.publisher and pub is None:
            pub = ET.SubElement(desc, f"{NS}entity", {"type": "publisher", "priority": "1"})
        if pub is not None:
            pub.text = m.publisher

        conf = child(app, "configuration")
        system = child(conf, "system")
        if Platform.from_text(system.text) is not m.platform and m.platform is not Platform.UNKNOWN:
            system.text = "c64" if m.platform is Platform.C64 else "a-500"
        elif not system.text:
            system.text = m.system or ("c64" if m.platform is Platform.C64 else "a-500")

        if help_name:
            extras = child(app, "extras")
            if not any(_tag(e) == "document" and e.get("type") == "help" for e in extras):
                doc = ET.SubElement(extras, f"{NS}document", {"root": "embedded", "type": "help", "priority": "1"})
                doc.text = help_name

        if not data:
            media = child(app, "media")
            for name in m.media:
                kind = "harddrive" if name.lower().endswith(".hdf") else "floppy"
                ET.SubElement(media, f"{NS}{kind}", {"priority": str(len(media) + 1)}).text = name
        ET.indent(tree, space="\t")
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
