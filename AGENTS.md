# Projectvoorkeuren (RP9 Manager)

Deze voorkeuren gelden voor alle vervolgopdrachten.

- Doel: Linux-app (Linux Mint / Zorin OS) als manager, creator en launcher voor Cloanto `.rp9`-bestanden (Amiga/C64).
- Taal: Python ≥ 3.12, idiomatisch en efficiënt; GUI met PyQt6.
- Code: object-georiënteerd, uitgebreide type hints, docstrings bij alle klassen en methoden, beknopt inline-commentaar waar verduidelijking nodig is.
- Architectuur: logica (ZIP, XML, subprocess) strikt gescheiden van UI. UI (`ui.py`) praat alleen met `RP9Manager`.
  Kernklassen: `RP9Manager`, `ManifestParser`, `RP9Archive`, `EmulatorLauncher`, `MainApplicationWindow`.
- Functionaliteit: bibliotheek scannen (titel, platform, metadata, preview); manifest.xml lezen/bewerken en veilig terugschrijven;
  disk-images (`.adf`, `.d64`, …) herkennen; nieuw `.rp9` maken uit een map.
- Launcher: Amiga → `amiberry <bestand.rp9>`; C64 → images uitpakken in een privé-map onder `/tmp/` en `x64sc` (VICE) starten.
- Veiligheid/robuustheid: ZIP behandelen als onbetrouwbaar (zip-slip, groottelimiet), atomair opslaan, eigen exceptions
  (`errors.py`) voor corrupte archieven en ontbrekende emulators.
- Documentatie: Nederlandstalige `README.md` met installatie, afhankelijkheden (PyQt6) en PyInstaller-instructies. Houd deze actueel.
- Communicatie met de gebruiker: Nederlands.
