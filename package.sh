#!/bin/bash
# Assemble the distributable Mac package from the canonical sources.
# Keeps VoiceCorpusBuilder/voice_corpus_tool.py in sync with the repo root copy,
# then zips the folder for sharing. Run from anywhere.
set -euo pipefail
cd "$(dirname "$0")"

cp voice_corpus_tool.py VoiceCorpusBuilder/voice_corpus_tool.py
chmod +x "VoiceCorpusBuilder/Build Voice Corpus.command"

rm -f VoiceCorpusBuilder.zip
if command -v zip >/dev/null 2>&1; then
  zip -r -X VoiceCorpusBuilder.zip VoiceCorpusBuilder -x '*.DS_Store' >/dev/null
  echo "Built VoiceCorpusBuilder.zip"
else
  echo "Synced VoiceCorpusBuilder/ (install 'zip' to also produce VoiceCorpusBuilder.zip)"
fi
