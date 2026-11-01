#!/usr/bin/env bash
# Bouwt dist/rp9-manager en een release-tarball met PyInstaller.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .build-venv
.build-venv/bin/pip install -q PyQt6 pyinstaller .
.build-venv/bin/pyinstaller --noconfirm --clean --onefile --windowed --name rp9-manager \
    --paths src packaging/entry.py
rel="release/rp9-manager-linux-x86_64"
rm -rf release && mkdir -p "$rel"
cp dist/rp9-manager packaging/install.sh packaging/rp9-manager.desktop README.md "$rel/"
tar -C release -czf release/rp9-manager-linux-x86_64.tar.gz rp9-manager-linux-x86_64
echo "Klaar: release/rp9-manager-linux-x86_64.tar.gz"
