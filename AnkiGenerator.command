#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Anki Generator — Launcher
# Double-click this file to start the app.
# Close this Terminal window to stop the server.
# ──────────────────────────────────────────────────────────────

# Resolve the directory this script lives in (handles symlinks)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Pretty banner ────────────────────────────────────────────
clear
echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║                                          ║"
echo "  ║      🎴  Anki Generator is starting…     ║"
echo "  ║                                          ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── Activate virtual environment ─────────────────────────────
if [ ! -d "venv" ]; then
    echo "❌  Virtual environment not found."
    echo "    Please run install.sh first."
    echo ""
    echo "    Press any key to close…"
    read -n 1 -s
    exit 1
fi

source venv/bin/activate

# ── Check if port 5001 is already in use ─────────────────────
if lsof -i :5001 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  ✅  Anki Generator is already running!"
    echo ""
    echo "  Opening browser…"
    open "http://localhost:5001"
    echo ""
    echo "  Press any key to close this window…"
    read -n 1 -s
    exit 0
fi

# ── Check if Anki Desktop is running ─────────────────────────
if ! pgrep -x "Anki" >/dev/null 2>&1; then
    echo "  ⚠️   Anki Desktop is not running."
    echo "      Cards will generate but won't sync to Anki"
    echo "      until you open the Anki app."
    echo ""
fi

# ── Start the Flask server ───────────────────────────────────
echo "  🚀  Starting server on http://localhost:5001"
echo ""

# Open browser after a short delay (server needs a moment to boot)
(sleep 2 && open "http://localhost:5001") &

# Run the server — this blocks until you close the terminal window
python3 app.py 2>&1

# ── Cleanup on exit ──────────────────────────────────────────
echo ""
echo "  Server stopped. You can close this window."
echo "  Press any key to close…"
read -n 1 -s
