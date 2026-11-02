# RP9 Manager

Grafische manager, creator en launcher voor Cloanto `.rp9`-bestanden (Amiga en C64) op Linux (Linux Mint, Zorin OS).

## Functies
- Bibliotheek: scant een map op `.rp9`, toont titel, platform, beschrijving en preview-afbeelding.
- Sorteren: klik op een kolomkop om te sorteren; nogmaals klikken keert de richting om. Via rechtermuisknop op de kop kies je expliciet oplopend of aflopend.
- Taal: Nederlands of Engels, te kiezen onder **Instellingen > Taal** (wordt direct toegepast en opgeslagen als `language` in de config; standaard de systeemtaal). Nieuwe teksten voeg je toe in `src/rp9_manager/i18n.py`.
- Bewerken in zes tabbladen, naar het voorbeeld van de Cloanto RP9 Title Editor (Amiga/C64 Forever): **Informatie**, **Details** (type, genre, kwaliteitsbeoordeling, versie, taal, homepage, TOSEC), **Media**, **Configuratie** (model, Kickstart-ROM, Fast RAM, turbo floppy, stille drives, automatische drive; bij C64 turbo start en automatisch laden/starten), **Invoer** (joystick, muis, toetsenbord, multiplayer, joystickpoort) en **Emulatie** (per-game Amiberry- of VICE-opties). Alles behalve Emulatie wordt in `rp9-manifest.xml` opgeslagen en geldt dus ook voor Cloanto's Player; atomair opgeslagen.
- Compatibiliteit met Cloanto's Player (volgens de RP9-documentatie op retroplatform.com): bij een wijziging krijgt `<application>` het attribuut `user-edited="true"` (anders negeert de Player onze aanpassingen en gebruikt hij de bibliotheekdata); een gewijzigde titel of uitgever wist de bijbehorende OID's; kiest u een model dat Player 3.0.0.0 vereist (A500+/A2000/A3000/A4000), dan wordt `playerversion` verhoogd. Opslaan zonder wijzigingen laat het manifest ongewijzigd.
- Tabblad **Media** (volgens het officiële `rp9.xsd`): screenshots (`.png/.jpg/.gif`) per type: tijdens het spel (`screen-running`, de bovenste is het voorbeeld in de bibliotheek), titelscherm (`screen-title`) en scorescherm (`screen-score`), met ▲/▼ om de prioriteit te wijzigen, documenten (`.pdf/.txt`, als `document type="help"`) en extra disk-, harddisk-, CD- of tape-images (`floppy`, `harddrive`, `cd`, `tape`) toevoegen of verwijderen. Bestanden met een bestaande naam of een niet-ondersteund type worden geweigerd; nieuwe images zijn direct kiesbaar onder Emulatie. Snapshots en `startup` worden niet ondersteund.
- Nieuw `.rp9` maken uit een map met disk-images (`.adf`, `.d64`, …).
- Starten: Amiga via `amiberry`, C64 via VICE `x64sc` (native of Flatpak `net.sf.VICE`; images tijdelijk uitgepakt in `/tmp`, bij de Flatpak in `~/.cache/rp9-manager/tmp`, daarna opgeruimd).

## Snelle start (release, Zorin OS / Linux Mint)
```bash
./packaging/build.sh                      # bouwt release/rp9-manager-linux-x86_64.tar.gz
tar xzf release/rp9-manager-linux-x86_64.tar.gz && cd rp9-manager-linux-x86_64
./install.sh                              # installeert in ~/.local/bin + menu-item
```
Start daarna via het menu (RP9 Manager) of met `rp9-manager`. Kies bij **Instellingen…** je bibliotheekmap
(standaard `~/Games/rp9`; bijv. de map `rp9-examples`).

## Emulators installeren
```bash
sudo apt install vice                     # levert x64sc
flatpak install flathub net.sf.VICE       # alternatief: wordt automatisch gevonden
flatpak install flathub com.blitterstudio.amiberry   # of installeer amiberry zelf; wordt automatisch gevonden
```
VICE: de standaardinstelling `vice` gebruikt eerst de Flatpak `net.sf.VICE` en valt terug op een native `x64sc`;
vul bij Instellingen een eigen commando in om dat te overrulen.
Zonder emulator toont de app een duidelijke melding. Eigen paden/commando's stel je in bij Instellingen
(config: `~/.config/rp9-manager/config.json`). C64-launch pakt images uit in `/tmp/rp9-*` en ruimt daarna op.
Per-game opties stel je in via **Bewerken… > Emulatie**; alleen het paneel van het gekozen platform wordt getoond.
Beide emulators hebben een vinkje **Starten in volledig scherm** (Amiberry: `-s gfx_fullscreen_amiga=true`, na het RP9-pad omdat Amiberry eerdere `-s`-opties overschrijft;
VICE (`x64sc`): `-VICIIfull`). Amiberry biedt model-, UAE-configuratie-, DF0–DF3-, HDF- en CD-imagekeuzes. VICE biedt configuratie, autostart,
datasette en stations 8–11. Geselecteerde images komen uit het RP9-archief. Extra opdrachtregelopties
worden als losse argumenten verwerkt (zonder shell); quotes en spaties worden ondersteund. De velden volgen
de gangbare opties uit de
[Amiberry CLI-documentatie](https://github.com/BlitterStudio/amiberry/wiki/Command-line-reference) en
[VICE-handleiding](https://vice-emu.sourceforge.io/vice_2.html).
Let op: Amiberry als Flatpak heeft mogelijk toegang tot je bibliotheekmap nodig
(`flatpak override --user --filesystem=<map> com.blitterstudio.amiberry`).

## Ontwikkelen
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install PyQt6 pytest -e .
python -m rp9_manager     # starten
pytest                    # tests (gebruikt ook rp9-examples/)
```
Afhankelijkheden: Python ≥ 3.12, PyQt6. Manifestformaat: `rp9-manifest.xml` (Cloanto-schema); de beschrijving wordt
bewaard in het ingesloten helpdocument `rp9-help-en.txt`.

## Executable bouwen met PyInstaller
`packaging/build.sh` doet dit automatisch; handmatig:
```bash
pip install pyinstaller PyQt6 .
pyinstaller --onefile --windowed --name rp9-manager --paths src packaging/entry.py
```
Resultaat: `dist/rp9-manager`. Bouw op het oudste doelsysteem voor de beste glibc-compatibiliteit.

## Architectuur
`manifest.py` (XML) · `archive.py` (ZIP) · `launcher.py` (subprocess) · `manager.py` (façade) · `ui.py` (PyQt6).

> Let op: de manifestparser is tolerant (zoekt `title`/`name`, `description`/`info`, `platform`); pas
> `ManifestParser` aan als jouw archieven afwijkende tags gebruiken.

## Voorbeeldbestanden
De map `rp9-examples/` staat bewust niet in deze repository (auteursrechtelijk materiaal). Plaats er zelf `.rp9`-bestanden
in om de extra tests te draaien; zonder deze map worden die tests overgeslagen.

## Meehelpen
Dit project is nog jong en hulp is zeer welkom! Zie [CONTRIBUTING.md](CONTRIBUTING.md). Vooral gezocht:
- **Testers** op andere distributies en met Flatpak-, AppImage- of native Amiberry/VICE-installaties.
- **Kennis van het RP9-formaat**: ontbrekende manifestvelden (content rating, multitap, virtuele knoppen, CPU/JIT, extra geheugen, audio) en de exacte modelnamen (a-500, a-1000, a-600, a-4000, c-128, …).
- **Vertalingen** naar meer talen (`src/rp9_manager/i18n.py`).
- **VICE-integratie**: configuratie en invoer vertalen naar VICE-opdrachtregels.
- **Packaging**: AppImage, Flatpak, `.deb`.

Open gerust een issue of pull request.
