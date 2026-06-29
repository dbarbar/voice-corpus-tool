#!/bin/bash
# Integration test for the double-click launcher (Build Voice Corpus.command).
# Builds a tiny synthetic Instagram export, runs the SHIPPED launcher exactly as
# a double-click would, and checks it produced the expected corpus file.
# Runs on Linux and macOS (CI matrix).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$REPO_ROOT/VoiceCorpusBuilder"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/vcb-launcher.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

# Stage the shipped package into a throwaway folder.
cp "$PKG/voice_corpus_tool.py" "$SCRATCH/"
cp "$PKG/Build Voice Corpus.command" "$SCRATCH/"
chmod +x "$SCRATCH/Build Voice Corpus.command"

# Build a minimal but valid Instagram export zip (no real data, no `zip` binary needed).
python3 - "$SCRATCH/instagram-export.zip" <<'PY'
import sys, json, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("your_instagram_activity/media/posts_1.json",
               json.dumps([{"creation_timestamp": 1717243200,
                            "title": "A test caption that is long enough",
                            "media": [{"uri": "a.jpg", "creation_timestamp": 1717243200}]}]))
PY

# Drive the launcher non-interactively. Answers:
#   types=all, from=blank, to=blank, min_len=0, dedupe=Y, split=N, name=ci_corpus
# Trailing newlines satisfy the two "press any key" reads.
printf 'all\n\n\n0\n\n\nci_corpus\n\n\n' | bash "$SCRATCH/Build Voice Corpus.command" >/dev/null 2>&1 || true

OUT="$SCRATCH/ci_corpus.txt"
if [ ! -f "$OUT" ]; then
  echo "FAIL: launcher did not produce $OUT"; exit 1
fi
if ! grep -q "A test caption that is long enough" "$OUT"; then
  echo "FAIL: expected caption text missing from output"; exit 1
fi
echo "PASS: launcher produced a valid corpus file"
