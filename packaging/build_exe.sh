#!/usr/bin/env bash
# Build the standalone executable into out/ with PyInstaller. CI runs this on the runner, or
# inside a manylinux_2_28 container so the Linux executables run on glibc 2.28 and newer.
set -euo pipefail
: "${PYINSTALLER_VERSION:?set PYINSTALLER_VERSION}"
python -m pip install ".[api]" "pyinstaller==${PYINSTALLER_VERSION}"
work="$(mktemp -d)"
pyinstaller --onefile --name invoice-agent --noconfirm \
  --collect-data invoice_agent --collect-data pdfminer --collect-submodules uvicorn \
  --distpath out --workpath "$work" --specpath "$work" \
  packaging/entry.py
