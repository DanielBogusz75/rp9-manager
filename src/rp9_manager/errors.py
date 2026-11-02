"""Gedeelde uitzonderingen van RP9 Manager."""


class RP9Error(Exception):
    """Basisklasse voor alle applicatiefouten."""


class CorruptArchiveError(RP9Error):
    """Het .rp9-bestand is geen geldig of veilig ZIP-archief."""


class ManifestError(RP9Error):
    """De manifest.xml ontbreekt of is ongeldig."""


class MediaError(RP9Error):
    """Een media-bestand (afbeelding, document of disk-image) kan niet worden toegevoegd of verwijderd."""


class EmulatorNotFoundError(RP9Error):
    """De benodigde emulator is niet geïnstalleerd of niet uitvoerbaar."""


class LaunchError(RP9Error):
    """De emulator kon niet worden gestart."""
