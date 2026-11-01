"""RP9 Manager: beheer, bewerk, maak en start Cloanto .rp9-bestanden."""


def main() -> None:
    """Start de grafische applicatie (PyQt6 wordt pas hier geïmporteerd)."""
    from .ui import main as run

    run()
