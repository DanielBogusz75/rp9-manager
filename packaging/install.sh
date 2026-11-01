#!/usr/bin/env bash
# Installeert de gebouwde executable voor de huidige gebruiker (geen root nodig).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
bin="${here}/rp9-manager"
[ -x "$bin" ] || bin="${here}/../dist/rp9-manager"
[ -x "$bin" ] || { echo "Executable niet gevonden; bouw eerst met packaging/build.sh" >&2; exit 1; }
install -Dm755 "$bin" "${HOME}/.local/bin/rp9-manager"
install -Dm644 "${here}/rp9-manager.desktop" "${HOME}/.local/share/applications/rp9-manager.desktop"
update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
echo "Geïnstalleerd. Start via het menu (Spellen → RP9 Manager) of met: rp9-manager"
