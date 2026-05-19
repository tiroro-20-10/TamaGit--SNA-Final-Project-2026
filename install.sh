#!/bin/bash
# TamaGit installer — creates an isolated venv and a global symlink.
# Uses a virtual environment to avoid touching the system Python (PEP 668 / Debian 12+).
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
echo "✅  Done!  Test with:  tamagit help"
echo ""
echo "Next steps:"
echo "  1.  tamagit server-setup   (configure GitHub webhook, start Docker)"
echo "  2.  tamagit init           (hatch the team pet)"
echo "  3.  Share the VPS URL with teammates so they can run 'tamagit setup'"
