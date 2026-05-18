#!/bin/bash
# TamaGit installer — creates isolated venv and global symlink
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="/opt/tamagit-venv"
SYMLINK="/usr/local/bin/tamagit"

echo "TamaGit — Install"
echo "─────────────────"

# Create venv
echo "Creating virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

# Install project into venv
echo "Installing TamaGit and dependencies..."
"$VENV_DIR/bin/pip" install -e "$PROJECT_DIR" --quiet

# Create global symlink
echo "Creating symlink at $SYMLINK..."
ln -sf "$VENV_DIR/bin/tamagit" "$SYMLINK"

echo ""
echo "Done! Test with: tamagit help"