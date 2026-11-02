"""Eenvoudige vertaallaag (Nederlands/Engels) zonder UI-afhankelijkheden.

De Nederlandse tekst is tevens de sleutel; ``tr`` zoekt de Engelse vertaling op en
vult eventuele ``{plaatshouders}`` in.
"""

from __future__ import annotations

import locale

LANGUAGES: dict[str, str] = {"nl": "Nederlands", "en": "English"}
DEFAULT_LANGUAGE = "nl"

_current = DEFAULT_LANGUAGE

_EN: dict[str, str] = {
    # Platformen
    "Onbekend": "Unknown",
    # Foutmeldingen: archief
    "Kan '{name}' niet openen: {exc}": "Cannot open '{name}': {exc}",
    "'{name}' is verdacht groot.": "'{name}' is suspiciously large.",
    "'{name}' ontbreekt in {archive}": "'{name}' is missing in {archive}",
    "Beschadigd archief {archive}: {exc}": "Corrupt archive {archive}: {exc}",
    "{name} ontbreekt in {archive}": "{name} is missing in {archive}",
    "Ongeldige emulatorinstellingen in {archive}: {exc}": "Invalid emulator settings in {archive}: {exc}",
    "Ongeldige emulatorinstellingen in {archive}.": "Invalid emulator settings in {archive}.",
    "Opslaan mislukt: {exc}": "Saving failed: {exc}",
    "Onveilig pad in archief: {name}": "Unsafe path in archive: {name}",
    "De map bevat geen herkenbare disk-images.": "The folder contains no recognisable disk images.",
    "Aanmaken mislukt: {exc}": "Creation failed: {exc}",
    # Foutmeldingen: manifest
    "DOCTYPE/ENTITY in het manifest is niet toegestaan.": "DOCTYPE/ENTITY in the manifest is not allowed.",
    "Ongeldig manifest: {exc}": "Invalid manifest: {exc}",
    "Geen geldig rp9-manifest (rootelement is niet 'rp9').": "Not a valid rp9 manifest (root element is not 'rp9').",
    # Foutmeldingen: launcher
    "Ongeldig emulatorcommando '{command}': {exc}": "Invalid emulator command '{command}': {exc}",
    "Emulator '{command}' is niet gevonden. Installeer deze of stel het pad in via Instellingen.":
        "Emulator '{command}' was not found. Install it or set the path in Settings.",
    "Onbekend platform; stel het platform in via de editor.": "Unknown platform; set the platform in the editor.",
    "De geselecteerde Amiberry-harddisk-image moet een HDF-bestand zijn.":
        "The selected Amiberry hard disk image must be an HDF file.",
    "De geselecteerde Amiberry-CD-image moet een ISO- of CHD-bestand zijn.":
        "The selected Amiberry CD image must be an ISO or CHD file.",
    "Amiberry-media ontbreekt in het archief: {name}": "Amiberry media is missing in the archive: {name}",
    "Ongeldige {emulator}-opties: {exc}": "Invalid {emulator} options: {exc}",
    "De geselecteerde VICE-autostart-image is geen C64-image.":
        "The selected VICE autostart image is not a C64 image.",
    "Een VICE-datasette-image moet .tap of .t64 zijn.": "A VICE datasette image must be .tap or .t64.",
    "VICE-diskstations vereisen .d64, .d71, .d81 of .g64-images.":
        "VICE disk drives require .d64, .d71, .d81 or .g64 images.",
    "Geen C64-disk-images in dit archief.": "No C64 disk images in this archive.",
    "Starten mislukt: {exc}": "Launch failed: {exc}",
    "Emulator stopte direct (code {code}).\n{detail}": "Emulator exited immediately (code {code}).\n{detail}",
    # Details, configuratie en invoer
    "Prioriteit wijzigen (bovenste = standaard)": "Change priority (top = default)",
    "Niet beoordeeld": "Not rated",
    "Type": "Type",
    "Kwaliteitsbeoordeling": "Quality rating",
    "Versie": "Version",
    "Taal (code)": "Language (code)",
    "Homepage": "Home page",
    "Details": "Details",
    "Screenshots – tijdens het spel (standaardvoorbeeld)": "Screenshots – running (default preview)",
    "Screenshots – titelscherm": "Screenshots – title screen",
    "Screenshots – scorescherm": "Screenshots – score screen",
    "Het voorbeeld in de bibliotheek is de bovenste screenshot 'tijdens het spel'.":
        "The library preview is the top 'running' screenshot.",
    "Standaard (volgens model)": "Default (per model)",
    "Geen": "None",
    "Model (systeem)": "Model (system)",
    "Kickstart-ROM": "Kickstart ROM",
    "Fast RAM": "Fast RAM",
    "Turbo start": "Turbo start",
    "Automatisch laden": "Automatic load",
    "Automatisch starten (RUN)": "Automatic run (RUN)",
    "Opstarten": "Startup",
    "Turbo floppy": "Turbo floppy",
    "Stille drives": "Silent drives",
    "Automatische drive": "Automatic drive",
    "Compatibiliteit": "Compatibility",
    "Deze instellingen worden in het RP9 zelf opgeslagen en zijn ook geldig voor Cloanto's Player.":
        "These settings are stored in the RP9 itself and are also used by Cloanto's Player.",
    "Configuratie": "Configuration",
    "Joystick": "Joystick",
    "Muis": "Mouse",
    "Toetsenbord": "Keyboard",
    "Multiplayer": "Multiplayer",
    "Poort {port}": "Port {port}",
    "Speelopties": "Play options",
    "Invoerpoorten": "Input ports",
    "Joystick aangesloten op": "Joystick connected to",
    "Invoer": "Input",
    # Media
    "Bestandstype niet ondersteund: {name}": "File type not supported: {name}",
    "Bestand niet gevonden: {name}": "File not found: {name}",
    "'{name}' is te groot.": "'{name}' is too large.",
    "Bestand niet leesbaar: {name} ({exc})": "File not readable: {name} ({exc})",
    "Dit bestand kan niet verwijderd worden: {name}": "This file cannot be removed: {name}",
    "Er bestaat al een bestand met de naam '{name}'.": "A file named '{name}' already exists.",
    "Media": "Media",
    "Screenshots en afbeeldingen (PNG, JPG, GIF)": "Screenshots and images (PNG, JPG, GIF)",
    "Documentatie (PDF, TXT)": "Documentation (PDF, TXT)",
    "Disk-, harddisk-, CD- en tape-images": "Disk, hard disk, CD and tape images",
    "Toevoegen…": "Add…",
    "Verwijderen": "Remove",
    "(nieuw)": "(new)",
    "Afbeelding kiezen": "Choose image",
    "Document kiezen": "Choose document",
    "Image kiezen": "Choose image file",
    "Afbeeldingen (*.png *.jpg *.jpeg *.gif)": "Images (*.png *.jpg *.jpeg *.gif)",
    "Documenten (*.pdf *.txt)": "Documents (*.pdf *.txt)",
    "Images ({patterns})": "Images ({patterns})",
    "Alle bestanden (*)": "All files (*)",
    "Toegevoegde images verschijnen direct in de keuzelijsten onder Emulatie.":
        "Added images appear immediately in the lists under Emulation.",
    "Bestand bestaat al": "File already exists",
    # Dialoog: manifest bewerken
    "Manifest Bewerken": "Edit Manifest",
    "Titel": "Title",
    "Uitgever": "Publisher",
    "Jaar": "Year",
    "Beschrijving": "Description",
    "Informatie": "Information",
    "Emulatie": "Emulation",
    "Standaard (volgens RP9)": "Default (as in RP9)",
    "Optioneel .uae-configuratiebestand": "Optional .uae configuration file",
    "Starten in volledig scherm": "Start in full screen",
    "Amiga-model": "Amiga model",
    "Scherm": "Screen",
    "Configuratiebestand": "Configuration file",
    "Diskette-station DF{index}": "Floppy drive DF{index}",
    "Harddisk-image (HDF)": "Hard disk image (HDF)",
    "CD-image (ISO/CHD)": "CD image (ISO/CHD)",
    "Extra opties, bijvoorbeeld -G of -s use_gui=no": "Extra options, for example -G or -s use_gui=no",
    "Extra opdrachtregelopties": "Extra command-line options",
    "Optioneel VICE-configuratiebestand": "Optional VICE configuration file",
    "Autostart-image (disk/tape/PRG)": "Autostart image (disk/tape/PRG)",
    "Datasette-image (TAP/T64)": "Datasette image (TAP/T64)",
    "Diskstation {drive}": "Disk drive {drive}",
    "Extra VICE-opties": "Extra VICE options",
    "Kies eerst Amiga of C64 onder Informatie.": "First choose Amiga or C64 under Information.",
    "Niet ingesteld / automatisch": "Not set / automatic",
    # Dialoog: instellingen
    "Instellingen": "Settings",
    "vice = Flatpak net.sf.VICE, anders x64sc": "vice = Flatpak net.sf.VICE, otherwise x64sc",
    "Bibliotheekmap": "Library folder",
    "Amiberry-commando": "Amiberry command",
    "VICE-commando": "VICE command",
    "Taal": "Language",
    # Hoofdvenster
    "Geen preview": "No preview",
    "Zoeken op titel, uitgever, genre…": "Search by title, publisher, genre…",
    "Alle platforms": "All platforms",
    "Instellingen…": "Settings…",
    "Verversen": "Refresh",
    "Starten": "Launch",
    "Bewerken…": "Edit…",
    "Nieuw .rp9…": "New .rp9…",
    "Fout": "Error",
    "{shown} van {total} bestand(en) in {folder}": "{shown} of {total} file(s) in {folder}",
    "Grootte": "Size",
    "'{title}' gestart": "'{title}' started",
    "Map met games/disks": "Folder with games/disks",
    "Opslaan als": "Save as",
    "Oplopend sorteren": "Sort ascending",
    "Aflopend sorteren": "Sort descending",
}


def detect_language() -> str:
    """Bepaal een standaardtaal uit de systeemtaal (``nl`` of anders ``en``)."""
    code = (locale.getlocale()[0] or "").lower()
    return "nl" if code.startswith("nl") else "en"


def set_language(code: str) -> None:
    """Stel de actieve taal in; onbekende codes vallen terug op de standaardtaal."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    """Geef de code van de actieve taal."""
    return _current


def tr(text: str, **values: object) -> str:
    """Vertaal ``text`` (Nederlandse bron) naar de actieve taal en vul ``values`` in."""
    result = _EN.get(text, text) if _current == "en" else text
    return result.format(**values) if values else result
