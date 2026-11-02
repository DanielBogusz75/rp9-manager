# Bijdragen aan RP9 Manager

Bedankt voor je interesse! Issues, vragen en pull requests zijn welkom, in het Nederlands of Engels.

## Ontwikkelomgeving
```bash
uv run --with pytest pytest -q        # tests (rp9-examples/ is optioneel)
uv run python -m rp9_manager          # app starten
```
Voor GUI-tests zonder scherm: `QT_QPA_PLATFORM=offscreen`.

## Richtlijnen
- Python ≥ 3.12, type hints en docstrings bij klassen en methoden.
- Logica (ZIP, XML, subprocess) staat los van de UI; `ui.py` praat alleen met `RP9Manager`.
- Behandel ZIP-bestanden als onbetrouwbaar (zip-slip, groottelimiet) en sla atomair op.
- Nieuwe UI-teksten: Nederlandse tekst in `tr(...)` plus Engelse vertaling in `i18n.py`.
- Voeg tests toe en houd de README actueel.
- Voeg geen auteursrechtelijk beschermde games of ROMs toe aan de repository.

## Manifestvelden
Voeg alleen velden toe die je kunt verifiëren met de Cloanto-documentatie (retroplatform.com), het officiële `rp9.xsd` of echte RP9-bestanden. Vermeld de bron in je pull request.
