# RP9 Manager

Grafische manager, creator en launcher voor Cloanto `.rp9`-bestanden (Amiga en C64) op Linux (Linux Mint, Zorin OS).

## Functies
- Bibliotheek: scant een map op `.rp9`, toont titel, platform, beschrijving en preview-afbeelding.
- Bewerken van `manifest.xml` (titel, beschrijving, platform); atomair opgeslagen.
- Nieuw `.rp9` maken uit een map met disk-images (`.adf`, `.d64`, …).
- Starten: Amiga via `amiberry`, C64 via VICE `x64sc` (images tijdelijk in `/tmp`, daarna opgeruimd).

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
flatpak install flathub com.blitterstudio.amiberry   # of installeer amiberry zelf; wordt automatisch gevonden
```
Zonder emulator toont de app een duidelijke melding. Eigen paden/commando's stel je in bij Instellingen
(config: `~/.config/rp9-manager/config.json`). C64-launch pakt images uit in `/tmp/rp9-*` en ruimt daarna op.
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
