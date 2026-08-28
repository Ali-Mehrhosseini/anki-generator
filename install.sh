#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Anki Generator — macOS Installer
# Run this once to set everything up on a new Mac.
#
# Usage:
#   chmod +x install.sh && ./install.sh
# ──────────────────────────────────────────────────────────────

set -e

# ── Colors and formatting ────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_ok()   { echo -e "  ${GREEN}✅  $1${NC}"; }
print_warn() { echo -e "  ${YELLOW}⚠️   $1${NC}"; }
print_err()  { echo -e "  ${RED}❌  $1${NC}"; }
print_info() { echo -e "  ${CYAN}ℹ️   $1${NC}"; }

# ── Resolve script directory ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Welcome banner ───────────────────────────────────────────
clear
echo ""
echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║                                                  ║"
echo "  ║     🎴  Anki Generator — macOS Installer         ║"
echo "  ║                                                  ║"
echo "  ║     This will set up everything you need.        ║"
echo "  ║     It only needs to run once.                   ║"
echo "  ║                                                  ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ══════════════════════════════════════════════════════════════
# Step 1: Check for Python 3
# ══════════════════════════════════════════════════════════════
print_step "Step 1/6: Checking for Python 3…"

PYTHON_CMD=""

# Check for python3 first, then python
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    # Make sure it's Python 3
    PY_VER=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    if [ "$PY_MAJOR" = "3" ]; then
        PYTHON_CMD="python"
    fi
fi

if [ -z "$PYTHON_CMD" ]; then
    print_err "Python 3 is not installed."
    echo ""
    echo "  To install Python 3, you have two options:"
    echo ""
    echo "  Option A — Install Xcode Command Line Tools (easiest):"
    echo "    xcode-select --install"
    echo ""
    echo "  Option B — Install via Homebrew:"
    echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo "    brew install python"
    echo ""
    echo "  After installing Python, run this script again."
    echo ""
    echo "  Press any key to close…"
    read -n 1 -s
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1)
print_ok "Found $PY_VERSION"

# Check minimum version (3.9+)
PY_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    print_err "Python 3.9 or higher is required. You have $PY_VERSION."
    echo "  Please upgrade Python and run this script again."
    echo ""
    echo "  Press any key to close…"
    read -n 1 -s
    exit 1
fi

# ══════════════════════════════════════════════════════════════
# Step 2: Create virtual environment
# ══════════════════════════════════════════════════════════════
print_step "Step 2/6: Setting up Python environment…"

if [ -d "venv" ]; then
    print_info "Virtual environment already exists — reusing it."
else
    print_info "Creating virtual environment…"
    $PYTHON_CMD -m venv venv
    print_ok "Virtual environment created."
fi

source venv/bin/activate

# ══════════════════════════════════════════════════════════════
# Step 3: Install Python dependencies
# ══════════════════════════════════════════════════════════════
print_step "Step 3/6: Installing Python dependencies…"
print_info "This may take a minute or two on first install."

pip install --upgrade pip --quiet 2>&1 | tail -1
pip install -r requirements.txt --quiet 2>&1 | tail -1

# Also install the CLI entry point
pip install -e . --quiet 2>&1 | tail -1

print_ok "All dependencies installed."

# ══════════════════════════════════════════════════════════════
# Step 4: Verify required files
# ══════════════════════════════════════════════════════════════
print_step "Step 4/6: Verifying required files…"

# Check all required untracked files are present
MISSING_FILES=()
[ ! -f "learning_lab.py" ]         && MISSING_FILES+=("learning_lab.py")
[ ! -f "static/speaking.html" ]    && MISSING_FILES+=("static/speaking.html")
[ ! -f "static/speaking.js" ]      && MISSING_FILES+=("static/speaking.js")

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    print_err "The following required files are missing from the project folder:"
    for f in "${MISSING_FILES[@]}"; do
        echo "    • $f"
    done
    echo ""
    echo "  These files are required but were not included in the download."
    echo "  Please make sure you have the complete project folder and try again."
    echo ""
    echo "  Press any key to close…"
    read -n 1 -s
    exit 1
fi
print_ok "learning_lab.py found."
print_ok "static/speaking.html found."
print_ok "static/speaking.js found."

# Check app.py has an entry point (app.run)
if ! grep -q "app.run" app.py; then
    print_warn "app.py is missing its entry point — adding it now."
    echo "" >> app.py
    echo "if __name__ == '__main__':" >> app.py
    echo "    app.run(debug=True, port=5001)" >> app.py
    print_ok "Entry point added to app.py."
else
    print_ok "app.py entry point OK."
fi

# ══════════════════════════════════════════════════════════════
# Step 4: Make the launcher executable
# ══════════════════════════════════════════════════════════════
print_step "Step 5/6: Setting up the launcher…"

chmod +x AnkiGenerator.command
print_ok "AnkiGenerator.command is ready."

# ══════════════════════════════════════════════════════════════
# Step 5: Create a macOS .app bundle
# ══════════════════════════════════════════════════════════════
print_step "Step 6/6: Creating desktop app…"

APP_NAME="Anki Generator"
APP_DIR="$HOME/Desktop/${APP_NAME}.app"

# Clean up any old version
rm -rf "$APP_DIR"

# Create the .app bundle structure
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Create the executable script inside the .app
cat > "$APP_DIR/Contents/MacOS/AnkiGenerator" << LAUNCHER
#!/bin/bash
# This is the internal launcher for the Anki Generator .app bundle.
# It opens Terminal.app and runs the main launcher script.

ANKI_DIR="$SCRIPT_DIR"

osascript -e "
tell application \"Terminal\"
    activate
    do script \"cd '\$ANKI_DIR' && bash AnkiGenerator.command\"
end tell
"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/AnkiGenerator"

# Create Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Anki Generator</string>
    <key>CFBundleDisplayName</key>
    <string>Anki Generator</string>
    <key>CFBundleIdentifier</key>
    <string>com.ankigenerator.app</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>AnkiGenerator</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.15</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

# ── Generate a simple app icon using Python ──────────────────
# Creates a colorful icon with a card emoji-style design
$PYTHON_CMD << 'ICONSCRIPT'
import subprocess, tempfile, os, sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    # Skip icon generation if Pillow fails — app still works fine
    print("  ℹ️   Skipping custom icon (Pillow not available for icon generation)")
    sys.exit(0)

size = 1024
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Rounded rectangle background — gradient-like with two-tone
# Main card shape
card_margin = 80
card_rect = [card_margin, card_margin, size - card_margin, size - card_margin]

# Draw rounded rectangle (solid color — we layer effects)
# Background: deep purple-blue gradient effect via layered rectangles
for i in range(20):
    offset = i * 2
    r = int(88 + i * 3)
    g = int(28 + i * 4)
    b = int(200 - i * 2)
    draw.rounded_rectangle(
        [card_margin + offset, card_margin + offset,
         size - card_margin - offset, size - card_margin - offset],
        radius=80 - offset,
        fill=(r, g, b, 255)
    )

# Draw a stylized "A" letter for Anki
# Use a large system font if available, otherwise draw manually
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 500)
except (OSError, IOError):
    try:
        font = ImageFont.truetype("/System/Library/Fonts/SFNSDisplay.ttf", 500)
    except (OSError, IOError):
        font = ImageFont.load_default()

# Draw "A" with slight shadow
shadow_offset = 6
draw.text((size//2 + shadow_offset, size//2 - 200 + shadow_offset), "A",
          fill=(0, 0, 0, 80), font=font, anchor="mt")
draw.text((size//2, size//2 - 200), "A",
          fill=(255, 255, 255, 255), font=font, anchor="mt")

# Small sparkle/star decorations
for (x, y, s) in [(200, 200, 40), (824, 200, 30), (824, 824, 35), (200, 750, 25)]:
    draw.ellipse([x-s, y-s, x+s, y+s], fill=(255, 255, 255, 120))

# Save as PNG
png_path = os.path.expanduser("~/Desktop/Anki Generator.app/Contents/Resources/AppIcon.png")
img.save(png_path, "PNG")

# Convert PNG to ICNS using macOS sips
iconset_dir = tempfile.mkdtemp(suffix=".iconset")
for sz in [16, 32, 64, 128, 256, 512, 1024]:
    resized = img.resize((sz, sz), Image.LANCZOS)
    resized.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}.png"))
    if sz <= 512:
        resized2x = img.resize((sz*2, sz*2), Image.LANCZOS)
        resized2x.save(os.path.join(iconset_dir, f"icon_{sz}x{sz}@2x.png"))

os.rename(iconset_dir, iconset_dir.replace(".iconset", "") + ".iconset")
iconset_dir = iconset_dir.replace(".iconset", "") + ".iconset"

icns_path = os.path.expanduser("~/Desktop/Anki Generator.app/Contents/Resources/AppIcon.icns")
subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", icns_path],
               capture_output=True)

print("  ✅  App icon created.")
ICONSCRIPT

print_ok "Desktop app created: ~/Desktop/Anki Generator.app"

# ══════════════════════════════════════════════════════════════
# Check for Anki Desktop
# ══════════════════════════════════════════════════════════════
echo ""
if [ -d "/Applications/Anki.app" ]; then
    print_ok "Anki Desktop is installed."
else
    print_warn "Anki Desktop not found in /Applications."
    echo ""
    echo "  To use this app, you need:"
    echo "  1. Anki Desktop — download from https://apps.ankiweb.net"
    echo "  2. AnkiConnect add-on — install code: 2055492159"
    echo "     (In Anki: Tools → Add-ons → Get Add-ons → paste the code)"
    echo ""
fi

# ══════════════════════════════════════════════════════════════
# Done!
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║                                                  ║"
echo "  ║     ✅  Installation Complete!                   ║"
echo "  ║                                                  ║"
echo "  ║     To start the app:                            ║"
echo "  ║     → Double-click 'Anki Generator' on Desktop   ║"
echo "  ║                                                  ║"
echo "  ║     First time? Click ⚙️ Settings to enter       ║"
echo "  ║     your Gemini and AWS API keys.                ║"
echo "  ║                                                  ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "  Press any key to close…"
read -n 1 -s
