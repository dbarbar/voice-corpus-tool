#!/bin/bash
# ===========================================================================
#  Voice Corpus Builder — double-click launcher (macOS)
#  Double-click this file. A window will open and walk you through everything.
# ===========================================================================

# Work from the folder this file lives in, so your export zips (which you put
# in the same folder) are found automatically.
cd "$(dirname "$0")" || exit 1

echo "==========================================================="
echo "  Voice Corpus Builder"
echo "==========================================================="
echo

# --- Find a working Python 3. Prefer python.org / Homebrew installs, then fall
#     back to whatever `python3` is on PATH. On macOS, /usr/bin/python3 can be a
#     stub that pops an Xcode installer when run, so we only trust it there if the
#     Command Line Tools are actually present. On Linux it's the real thing. -----
OS="$(uname -s)"

is_good_python() {
  [ -x "$1" ] && "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' 2>/dev/null
}

PYTHON=""
CANDIDATES=(
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3
  /Library/Frameworks/Python.framework/Versions/3.*/bin/python3
  /usr/local/bin/python3
  /opt/homebrew/bin/python3
  "$(command -v python3 2>/dev/null)"
)
for c in "${CANDIDATES[@]}"; do
  if [ "$c" = "/usr/bin/python3" ] && [ "$OS" = "Darwin" ]; then
    # Only safe to invoke on macOS if the Command Line Tools exist.
    xcode-select -p >/dev/null 2>&1 || continue
  fi
  if is_good_python "$c"; then
    PYTHON="$c"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Python 3 (version 3.8 or newer) isn't available yet."
  echo
  if [ "$OS" = "Darwin" ]; then
    echo "It's a quick one-time setup:"
    echo "  1. I'll open the Python download page for you."
    echo "  2. Download the macOS installer and run it (just click through)."
    echo "  3. Come back and double-click \"Build Voice Corpus\" again."
    echo
    read -n 1 -s -r -p "Press any key to open the Python download page..."
    echo
    open "https://www.python.org/downloads/macos/"
  else
    echo "Please install Python 3.8+ using your system's package manager"
    echo "(for example:  sudo apt install python3   on Debian/Ubuntu),"
    echo "then run this again."
  fi
  echo
  read -n 1 -s -r -p "Press any key to close this window."
  exit 1
fi

# --- Run the tool, using THIS folder as the place to look for export zips. -----
"$PYTHON" voice_corpus_tool.py "$(pwd)"

echo
echo "==========================================================="
read -n 1 -s -r -p "All done. Press any key to close this window."
echo
