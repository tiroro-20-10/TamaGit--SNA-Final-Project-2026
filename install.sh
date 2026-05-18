#!/bin/bash
# TamaGit installer — creates an isolated venv and a global symlink.
# This avoids touching the system Python (PEP 668 / Debian 12+).
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="/opt/tamagit-venv"
SYMLINK="/usr/local/bin/tamagit"

echo "TamaGit — Install"
echo "─────────────────"

echo "Creating virtual environment at $VENV_DIR ..."
python3 -m venv "$VENV_DIR"

echo "Installing TamaGit and dependencies ..."
"$VENV_DIR/bin/pip" install -e "$PROJECT_DIR" --quiet

echo "Creating symlink at $SYMLINK ..."
ln -sf "$VENV_DIR/bin/tamagit" "$SYMLINK"

echo ""
echo "Done!  Test with:  tamagit help"
