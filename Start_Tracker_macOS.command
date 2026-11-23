#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:$PATH"
if [[ ! -x .venv-macos/bin/python ]]; then echo 'Run bash Setup_macOS.command first.'; exit 1; fi
exec .venv-macos/bin/python app/desktop.py
