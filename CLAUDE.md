# CLAUDE.md

Guidance for Claude Code (and any agent) working in this repo. Auto-loaded each
session — keep it short and current.

## What this is

`voice-corpus-tool`: a standalone, dependency-free **Python 3.8+** tool that turns
Facebook + Instagram "Download Your Information" exports into a single,
chronologically-ordered corpus of the user's written voice — for calibrating an
AI to write like them. Public repo: <https://github.com/dbarbar/voice-corpus-tool>.

## Critical rules

- 🔒 **NEVER commit personal data.** The user's real FB/IG export `*.zip` files and
  the generated `voice_*.txt` corpora sit in this working folder but are
  **git-ignored**. Always check `git status` / `git ls-files` before staging;
  never `git add -A` without confirming no exports or corpora are included.
- **Privacy warnings are intentional and load-bearing.** They appear in the tool
  startup banner, the output file header, the README, and `READ ME FIRST.txt`.
  Don't trim or soften them unless asked.
- **Stdlib only — do not add third-party dependencies.**

## Source layout

- `voice_corpus_tool.py` (repo root) is the **single source of truth**.
- `VoiceCorpusBuilder/voice_corpus_tool.py` is a **generated copy** (git-ignored),
  produced by `./package.sh`. Never edit it directly.
- `build_corpus.py` was the original one-off (git-ignored); don't revive it.

## Dev workflow

- Run `./package.sh` **before** the tests — the launcher and drift-guard tests
  check the assembled `VoiceCorpusBuilder/` copy.
- Tests: `python3 -m unittest discover -s tests -v` and `bash tests/test_launcher.sh`.

## Releases (CI builds them — never upload from local)

- Tag-driven: `git tag vX.Y.Z && git push origin vX.Y.Z`.
- `.github/workflows/release.yml` runs the Linux+macOS test matrix, then builds
  `VoiceCorpusBuilder.zip` and publishes the GitHub release.
- `.github/workflows/ci.yml` tests every push to `main` and every PR.

## Cost / model

- Prefer **Sonnet** (`/model sonnet`) for routine work here — edits, running
  tests, doc tweaks, mechanical refactors. Reserve **Opus** for genuinely hard
  design or debugging. This project is small and well-structured; most tasks are
  Sonnet-tier.

## Notes

- `TODO.md` (git-ignored, local-only) holds approved-but-unbuilt future ideas:
  optional redaction pass, local-AI guidance, a canonical `PRIVACY.md`. **Don't
  implement these unless asked.**
- FB/IG exports contain **no per-post visibility data**; every item is tagged
  `visibility=unknown`. This is a documented limitation, not a bug to "fix."
