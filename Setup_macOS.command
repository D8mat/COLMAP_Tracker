#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
  echo 'Run on Apple Silicon macOS in a native terminal (without Rosetta).'; exit 1
fi
export PATH="/opt/homebrew/bin:$PATH"
command -v brew >/dev/null || { echo 'Install Homebrew from https://brew.sh first.'; exit 1; }
brew install python@3.11 ffmpeg colmap
"$(brew --prefix python@3.11)/bin/python3.11" -m venv .venv-macos
.venv-macos/bin/python -m pip install --upgrade pip
.venv-macos/bin/python -m pip install --only-binary=:all: -r requirements.txt
if [[ ! -f config.macos.json ]]; then cp config.macos.example.json config.macos.json; fi
echo 'Ready. Run: bash Start_Tracker_macOS.command'
