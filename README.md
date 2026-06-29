# Voice Corpus Tool

Builds a single, chronologically-ordered text file of your **written voice** from
Facebook + Instagram data exports — for feeding to an AI you're calibrating to
write like you.

Works on **any** FB/IG "Download Your Information" export (not a specific account),
needs only Python 3.8+, and has **no dependencies**.

## Usage

```bash
python3 voice_corpus_tool.py [folder-with-your-export-zips]
```

If you omit the folder it asks for one (default: current directory). It prints
how to request the exports, then asks what to include.

## Getting your data (do this first)

Request both exports in **JSON** format (HTML will not parse), "All time":

- **Facebook**: Settings → Accounts Center → Your information and permissions →
  Download your information → pick profile → Format **JSON** → include Posts,
  Comments, Stories.
- **Instagram**: Settings → Accounts Center → Your information and permissions →
  Download your information → pick profile → Format **JSON** → include Content
  (posts/stories/reels) and Comments.

Drop the downloaded `.zip` file(s) into one folder (zips are fine — no need to
unzip). The Facebook zip, the Instagram zip, or both.

## What it asks you

- **Content types** — Facebook posts, Instagram captions (posts/reels/IGTV),
  Instagram stories, comments & replies.
- **Date range** — from / to (`YYYY` or `YYYY-MM-DD`), blank for no limit.
- **Minimum text length** — drops one-word / emoji-only fragments.
- **Visibility** — *only* offered if the export actually contains audience data.
  Standard Meta exports do **not** include per-post visibility, so normally
  everything is tagged `visibility=unknown` and no privacy filter is applied.
  See [Limitation: visibility/privacy data](#limitation-visibilityprivacy-data).
- **De-dupe** identical cross-posts (same text on both platforms).
- **One combined file** or **one file per content type**.

## Output

Each entry is tagged so you (or the downstream AI) can filter further:

```
[#00001] 2023-01-14 20:12:06 | IG | caption | era=recent | media=yes | shared_link=no | visibility=unknown | chars=132

The full text of your post or caption appears here, exactly as written ...
```

- **source** FB/IG · **type** post/caption/story/comment
- **era** early (<2020) / mid (2020–22) / recent (2023+)
- **media**, **shared_link**, **visibility**, **chars**

Emoji/accents are repaired automatically (Meta exports mangle them).

> Tip for voice calibration: weight `recent` posts + captions most heavily —
> that's where your current, composed voice lives.

## Limitation: visibility/privacy data

**Meta's data exports do not include per-post visibility/audience information.**
This was verified against real Facebook and Instagram exports:

- **Facebook posts** carry no audience/privacy field — only `post`, `timestamp`,
  `attachments`, `title`. (The `your_post_audiences.json` file is just your
  custom friend-list definitions, e.g. "Restricted", *not* a per-post mapping.)
- **Instagram** posts and stories carry no visibility field either; Instagram
  privacy is account-wide, not per-post.

**What this means:** the tool *cannot* exclude friends-only, private, or
custom-audience posts based on the export alone — that distinction isn't present
in the data Meta provides. Every item is tagged `visibility=unknown` and no
privacy filter is applied.

The tool still checks each item for audience/privacy values across known schema
variants, so if a future export format (or a different locale/account) *does*
include them, the visibility filter activates automatically.

If you specifically need to filter by visibility, the only reliable options are:

- **Manual review** — use the date/type tags to locate items and prune by hand.
- **Graph API (Facebook)** — fetch posts live with the `privacy` field via the
  API, which does expose per-post audience. This requires app credentials and is
  outside the scope of this tool.

## Sharing this with non-technical Mac users

`VoiceCorpusBuilder/` is a ready-to-share package so someone can run this without
touching a terminal command themselves:

- **`Build Voice Corpus.command`** — they double-click it; a window opens and the
  guided prompts run. It finds Python automatically (and, on macOS, points them to
  the python.org installer if Python isn't installed yet).
- **`READ ME FIRST.txt`** — plain-language steps: get the exports, drop the zips in
  the folder, double-click, and the first-launch right-click→Open security step.

Point people at the [**Releases**](../../releases) page to download
`VoiceCorpusBuilder.zip` — it's built and attached automatically by CI for every
version tag (see below). `./package.sh` produces the same zip locally if you need
to test the package by hand.

> Distribution note: this is the "install Python from python.org" approach — no
> app bundling/signing yet. A future step could bundle Python with PyInstaller so
> users install nothing, and notarize it to remove the macOS security prompt.

## Development / tests

```bash
./package.sh                               # assemble the shippable package first
python3 -m unittest discover -s tests -v   # unit tests (synthetic exports, no real data)
bash tests/test_launcher.sh                # launcher integration test
```

Run `./package.sh` before the tests: the launcher and drift-guard tests check the
assembled `VoiceCorpusBuilder/voice_corpus_tool.py`, which is **generated** (a copy
of the root tool) and not committed.

CI (`.github/workflows/ci.yml`) runs the same steps on **Linux and macOS** for every
push and PR.

## Cutting a release

Releases are built and published by CI — nothing is uploaded from a laptop:

```bash
git tag v1.2.0
git push origin v1.2.0
```

The [release workflow](.github/workflows/release.yml) runs the full test matrix, and
only if it passes does it build `VoiceCorpusBuilder.zip` and create the GitHub release
with the zip attached. Use [semantic version](https://semver.org/) tags (`vMAJOR.MINOR.PATCH`).

## Files in this repo

- `voice_corpus_tool.py` — the reusable tool (the single source of truth).
- `VoiceCorpusBuilder/` — the shareable Mac package: launcher (`Build Voice Corpus.command`)
  + `READ ME FIRST.txt`. The tool copy and the `.zip` are **build outputs**, not committed.
- `package.sh` — assembles the package and builds `VoiceCorpusBuilder.zip` locally.
- `tests/` — unit + launcher integration tests.
- `.github/workflows/` — `ci.yml` (test on push/PR) and `release.yml` (test + build +
  publish on a version tag).

Your real exports (`*.zip`) and the generated corpora (`voice_*.txt`) are **git-ignored
on purpose** — they contain your personal posts and never get committed.

## License

[MIT](LICENSE) — free to use, modify, and share with attribution.
