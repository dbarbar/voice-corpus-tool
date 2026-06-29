#!/usr/bin/env python3
"""
voice_corpus_tool.py — Build a "written voice" corpus from Facebook + Instagram
data exports.

Standalone, no third-party dependencies (Python 3.8+). Works on ANY Facebook /
Instagram "Download Your Information" export, not a specific account. It:

  1. Tells you how to request the two exports and where to put them.
  2. Discovers the export(s) — zipped or already extracted.
  3. Asks what to include (content types, date range, min length, visibility, ...).
  4. Parses every relevant file across known schema variants, repairs Meta's
     emoji mojibake, dedupes cross-posts, and writes a chronologically-ordered
     text file with per-entry metadata tags for downstream filtering.

Usage:
    python3 voice_corpus_tool.py [EXPORT_DIR]

If EXPORT_DIR is omitted you'll be prompted for it (default: current directory).
"""

import sys, os, re, json, glob, zipfile, fnmatch, datetime, io, textwrap

# ----------------------------------------------------------------------------
# 0. Instructions
# ----------------------------------------------------------------------------
INSTRUCTIONS = """\
============================================================================
  SOCIAL VOICE CORPUS BUILDER
============================================================================
This tool turns your Facebook + Instagram posts into a single text file you can
feed to an AI you're calibrating to write in your voice.

STEP 1 — Request your data exports (choose JSON format!)

  Facebook:
    Settings & privacy > Settings > Accounts Center >
      Your information and permissions > Download your information
    - Pick your Facebook profile
    - Format: JSON   (REQUIRED — HTML will not parse)
    - Date range: All time
    - Include at least: Posts, Comments, Stories
    - Submit, wait for the email, download the .zip

  Instagram:
    Settings > Accounts Center >
      Your information and permissions > Download your information
    - Pick your Instagram profile
    - Format: JSON   (REQUIRED)
    - Date range: All time
    - Include at least: Content (posts/stories/reels) and Comments
    - Submit, wait for the email, download the .zip

STEP 2 — Put the files in one folder
  Drop the downloaded .zip file(s) into a single folder. You can include the
  Facebook zip, the Instagram zip, or both. Already-unzipped folders work too.
  You do NOT need to unzip anything yourself.

STEP 3 — Run this tool and answer the questions.
============================================================================
"""

# ----------------------------------------------------------------------------
# 1. Small interactive helpers
# ----------------------------------------------------------------------------
def ask(prompt, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    try:
        ans = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        ans = ""
    return ans if ans else (default if default is not None else "")

def ask_yes_no(prompt, default=True):
    d = "Y/n" if default else "y/N"
    ans = ask(f"{prompt} ({d})", "").lower()
    if not ans:
        return default
    return ans.startswith("y")

def ask_multi(prompt, options, default_all=True):
    """options: list of (key, label). Returns set of chosen keys."""
    print(f"\n{prompt}")
    for i, (k, label) in enumerate(options, 1):
        print(f"  {i}. {label}")
    dflt = "all" if default_all else ""
    raw = ask("Choose numbers (comma-separated) or 'all'", dflt).lower()
    if raw in ("all", ""):
        return {k for k, _ in options}
    chosen = set()
    for tok in re.split(r"[,\s]+", raw):
        if tok.isdigit() and 1 <= int(tok) <= len(options):
            chosen.add(options[int(tok) - 1][0])
    return chosen or {k for k, _ in options}

def parse_date(s, end=False):
    s = s.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            if fmt == "%Y" and end:
                d = d.replace(month=12, day=31)
            if end:
                d = d.replace(hour=23, minute=59, second=59)
            return d.timestamp()
        except ValueError:
            continue
    print(f"  (couldn't read date '{s}', ignoring)")
    return None

# ----------------------------------------------------------------------------
# 2. Export discovery + file access (zip or extracted dir)
# ----------------------------------------------------------------------------
FB_MARKER = "your_facebook_activity/"
IG_MARKER = "your_instagram_activity/"

class Source:
    """Abstracts reading JSON members from a zip OR an extracted directory."""
    def __init__(self, kind, zip_path=None, dir_path=None):
        self.kind = kind            # 'FB' or 'IG'
        self.zip_path = zip_path
        self.dir_path = dir_path

    def _names(self):
        if self.zip_path:
            with zipfile.ZipFile(self.zip_path) as z:
                return z.namelist()
        names = []
        for root, _, files in os.walk(self.dir_path):
            for f in files:
                names.append(os.path.relpath(os.path.join(root, f), self.dir_path))
        return names

    def read_matching(self, pattern):
        """Yield parsed JSON for every member whose path matches *pattern*."""
        results = []
        if self.zip_path:
            with zipfile.ZipFile(self.zip_path) as z:
                for n in z.namelist():
                    if fnmatch.fnmatch(n, pattern):
                        try:
                            results.append(json.loads(z.read(n).decode("utf-8")))
                        except Exception:
                            pass
        else:
            for n in self._names():
                if fnmatch.fnmatch(n.replace(os.sep, "/"), pattern):
                    try:
                        with open(os.path.join(self.dir_path, n), encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception:
                        pass
        return results

def discover_sources(export_dir):
    """Find FB and IG exports (zip or extracted) inside export_dir."""
    sources = []
    # zips
    for zp in glob.glob(os.path.join(export_dir, "*.zip")):
        try:
            with zipfile.ZipFile(zp) as z:
                names = z.namelist()
        except zipfile.BadZipFile:
            continue
        if any(FB_MARKER in n for n in names):
            sources.append(Source("FB", zip_path=zp))
        elif any(IG_MARKER in n for n in names):
            sources.append(Source("IG", zip_path=zp))
    # extracted directories (look for marker folders anywhere a few levels down)
    for root, dirs, _ in os.walk(export_dir):
        rootslash = root.replace(os.sep, "/") + "/"
        if rootslash.endswith(FB_MARKER) or os.path.isdir(os.path.join(root, "your_facebook_activity")):
            base = root if os.path.isdir(os.path.join(root, "your_facebook_activity")) else os.path.dirname(root)
            if not any(s.dir_path == base and s.kind == "FB" for s in sources) \
               and not any(s.kind == "FB" for s in sources):
                sources.append(Source("FB", dir_path=base))
        if os.path.isdir(os.path.join(root, "your_instagram_activity")):
            if not any(s.kind == "IG" for s in sources):
                sources.append(Source("IG", dir_path=root))
        # don't descend too deep
        if root[len(export_dir):].count(os.sep) >= 4:
            dirs[:] = []
    return sources

# ----------------------------------------------------------------------------
# 3. Text repair (Meta mojibake) + helpers
# ----------------------------------------------------------------------------
_MOJIBAKE_HINT = re.compile(r"Ã.|Â.|â€|ð\x9f|ð\x9f|[\x80-\x9f]")

def fix_text(s):
    """Repair Meta's latin-1/UTF-8 double-encoding (e.g. restores emoji)."""
    if not isinstance(s, str):
        return ""
    if not _MOJIBAKE_HINT.search(s):
        return s
    try:
        repaired = s.encode("latin-1").decode("utf-8")
        # only accept if it didn't introduce replacement chars
        if "�" not in repaired:
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return s

def era_of(year):
    if year < 2020:
        return "early"
    if year < 2023:
        return "mid"
    return "recent"

def label_lookup(record, *names):
    """Pull a value from Meta's label_values list format (case-insensitive)."""
    wanted = {n.lower() for n in names}
    for lv in record.get("label_values", []) or []:
        if lv.get("label", "").lower() in wanted and lv.get("value"):
            return lv["value"]
    return ""

def detect_visibility(record):
    """Best-effort per-item visibility/audience extraction across schemas."""
    # newer label_values schema
    v = label_lookup(record, "Audience", "Privacy", "Visibility", "Shared with")
    if v:
        return v.strip()
    # nested privacy/audience keys some exports use
    for key in ("privacy", "audience", "visibility"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            for sub in ("value", "name", "description"):
                if val.get(sub):
                    return str(val[sub]).strip()
    return ""

# ----------------------------------------------------------------------------
# 4. Parsers (return list of entry dicts)
# ----------------------------------------------------------------------------
def entry(ts, source, ctype, text, media=False, shared_link=False, visibility=""):
    text = fix_text(text).strip()
    if not text or not ts:
        return None
    return dict(ts=int(ts), source=source, type=ctype, text=text,
                media=bool(media), shared_link=bool(shared_link),
                visibility=visibility or "unknown")

def fb_owner_name(src):
    """Find the account owner's display name (to filter their own comments)."""
    for doc in src.read_matching("*profile_information*.json"):
        try:
            for k in ("profile_v2", "profile"):
                if isinstance(doc, dict) and k in doc:
                    name = doc[k].get("name", {})
                    full = name.get("full_name") if isinstance(name, dict) else name
                    if full:
                        return fix_text(full)
        except Exception:
            pass
    return None

def parse_fb(src):
    out = []
    # --- Posts (handles both classic and label_values schemas) ---
    for doc in src.read_matching("*your_facebook_activity/posts/your_posts*.json"):
        for rec in (doc if isinstance(doc, list) else doc.get("data", [])):
            text = ""
            for d in rec.get("data", []) or []:
                if isinstance(d, dict) and d.get("post"):
                    text = d["post"]; break
            if not text:
                text = label_lookup(rec, "Post", "Text", "Message")
            atts = rec.get("attachments", []) or []
            shared = any("external_context" in a2
                         for a in atts for a2 in (a.get("data", []) or []))
            e = entry(rec.get("timestamp"), "FB", "post", text,
                      media=bool(atts) and not shared, shared_link=shared,
                      visibility=detect_visibility(rec))
            if e: out.append(e)
    # --- Posts on other pages/profiles ---
    for doc in src.read_matching("*posts_on_other_pages_and_profiles.json"):
        for rec in (doc if isinstance(doc, list) else []):
            e = entry(rec.get("timestamp"), "FB", "post",
                      label_lookup(rec, "Message", "Post", "Text"),
                      visibility=detect_visibility(rec))
            if e: out.append(e)
    # --- Comments (owner's only) ---
    owner = fb_owner_name(src)
    for doc in src.read_matching("*comments_and_reactions/comments.json"):
        rows = doc.get("comments_v2", doc) if isinstance(doc, dict) else doc
        for rec in rows:
            for d in rec.get("data", []) or []:
                cm = d.get("comment", {})
                if not isinstance(cm, dict):
                    continue
                author = fix_text(cm.get("author", ""))
                if owner and author and author != owner:
                    continue
                e = entry(cm.get("timestamp") or rec.get("timestamp"),
                          "FB", "comment", cm.get("comment", ""))
                if e: out.append(e)
    return out

def _ig_caption(rec):
    """Caption text + timestamp from an IG media record."""
    if rec.get("title", "").strip():
        return rec["title"], rec.get("creation_timestamp") or rec.get("timestamp")
    for m in rec.get("media", []) or []:
        if m.get("title", "").strip():
            return m["title"], m.get("creation_timestamp") or rec.get("creation_timestamp")
    ts = rec.get("creation_timestamp") or rec.get("timestamp")
    if not ts and rec.get("media"):
        ts = rec["media"][0].get("creation_timestamp")
    return "", ts

def _rows(doc):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for v in doc.values():
            if isinstance(v, list):
                return v
    return []

def parse_ig(src):
    out = []
    # --- Captions: posts (possibly multi-part), reels, igtv ---
    for pat in ("*your_instagram_activity/media/posts_[0-9]*.json",
                "*your_instagram_activity/media/reels.json",
                "*your_instagram_activity/media/igtv_videos.json"):
        for doc in src.read_matching(pat):
            for rec in _rows(doc):
                text, ts = _ig_caption(rec)
                e = entry(ts, "IG", "caption", text, media=True,
                          visibility=detect_visibility(rec))
                if e: out.append(e)
    # --- Stories ---
    for doc in src.read_matching("*your_instagram_activity/media/stories.json"):
        for rec in _rows(doc):
            e = entry(rec.get("creation_timestamp"), "IG", "story",
                      rec.get("title", ""), media=True,
                      visibility=detect_visibility(rec))
            if e: out.append(e)
    # --- Comments: posts (multi-part), reels, story/hype ---
    for pat in ("*your_instagram_activity/comments/post_comments_[0-9]*.json",
                "*your_instagram_activity/comments/reels_comments.json",
                "*your_instagram_activity/comments/hype.json"):
        for doc in src.read_matching(pat):
            for rec in _rows(doc):
                smd = rec.get("string_map_data", {}) if isinstance(rec, dict) else {}
                e = entry(smd.get("Time", {}).get("timestamp"),
                          "IG", "comment", smd.get("Comment", {}).get("value", ""))
                if e: out.append(e)
    return out

# ----------------------------------------------------------------------------
# 5. Filtering + output (importable / testable)
# ----------------------------------------------------------------------------
def apply_filters(entries, types, ts_from=None, ts_to=None, min_len=0,
                  excluded_vis=frozenset(), dedupe=True):
    """Filter, chronologically sort, and (optionally) de-dupe entries."""
    def keep(e):
        if e["type"] not in types: return False
        if ts_from and e["ts"] < ts_from: return False
        if ts_to and e["ts"] > ts_to: return False
        if len(e["text"]) < min_len: return False
        if e["visibility"] in excluded_vis: return False
        return True

    sel = [e for e in entries if keep(e)]
    sel.sort(key=lambda e: e["ts"])
    if dedupe:
        seen, deduped = set(), []
        for e in sel:
            norm = e["text"].lower().strip()
            if len(norm) > 12 and norm in seen:
                continue
            seen.add(norm); deduped.append(e)
        sel = deduped
    return sel

def write_corpus(path, entries):
    """Write the tagged, chronologically-ordered corpus file."""
    by_type = {}
    for e in entries:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    header = textwrap.dedent(f"""\
        # Written-voice corpus — Facebook + Instagram exports
        # Ordered chronologically (oldest first).
        # Entry format: [#id] datetime | source | type | era | media | shared_link | visibility | chars
        #   source: FB / IG     type: post | caption | story | comment
        #   era: early=<2020, mid=2020-2022, recent=2023+
        # Entries: {len(entries)} — {', '.join(f'{k}:{v}' for k,v in sorted(by_type.items()))}
        """)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for i, e in enumerate(entries, 1):
            dt = datetime.datetime.fromtimestamp(e["ts"])
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"[#{i:05d}] {dt.isoformat(sep=' ', timespec='seconds')} | "
                    f"{e['source']} | {e['type']} | era={era_of(dt.year)} | "
                    f"media={'yes' if e['media'] else 'no'} | "
                    f"shared_link={'yes' if e['shared_link'] else 'no'} | "
                    f"visibility={e['visibility']} | chars={len(e['text'])}\n\n")
            f.write(e["text"] + "\n")

def collect_entries(sources):
    """Parse every source into a flat list of entries."""
    all_entries = []
    for s in sources:
        all_entries += parse_fb(s) if s.kind == "FB" else parse_ig(s)
    return all_entries

# ----------------------------------------------------------------------------
# 6. Main
# ----------------------------------------------------------------------------
def main():
    print(INSTRUCTIONS)
    export_dir = sys.argv[1] if len(sys.argv) > 1 else ask(
        "Folder containing your export zip(s)", os.getcwd())
    export_dir = os.path.abspath(os.path.expanduser(export_dir))
    if not os.path.isdir(export_dir):
        print(f"Not a folder: {export_dir}"); sys.exit(1)

    print(f"\nScanning {export_dir} ...")
    sources = discover_sources(export_dir)
    if not sources:
        print("No Facebook or Instagram exports found here.\n"
              "Make sure the .zip (or extracted folder) is in this directory.")
        sys.exit(1)
    for s in sources:
        where = s.zip_path or s.dir_path
        print(f"  found {s.kind}: {os.path.basename(where)}")

    # ---- Parse everything up front (so we can offer real filter choices) ----
    print("\nParsing exports (this can take a moment for large archives)...")
    all_entries = collect_entries(sources)
    if not all_entries:
        print("Parsed 0 entries — the export may be HTML instead of JSON.")
        sys.exit(1)

    types_present = sorted({e["type"] for e in all_entries})
    yrs = [datetime.datetime.fromtimestamp(e["ts"]).year for e in all_entries]
    vis_values = sorted({e["visibility"] for e in all_entries} - {"unknown"})
    type_counts = {t: sum(1 for e in all_entries if e["type"] == t) for t in types_present}
    counts_str = ", ".join(f"{t}:{n}" for t, n in type_counts.items())
    print(f"\nParsed {len(all_entries)} items ({counts_str})")
    print(f"Date range: {min(yrs)}-{max(yrs)}")

    # ---- Questions ----
    type_labels = {"post": "Facebook posts", "caption": "Instagram captions (posts/reels/IGTV)",
                   "story": "Instagram stories", "comment": "Comments & replies"}
    opts = [(t, type_labels.get(t, t)) for t in ["post", "caption", "story", "comment"]
            if t in types_present]
    chosen_types = ask_multi("Which content types should be included?", opts)

    print("\nDate range (blank = no limit). Formats: YYYY or YYYY-MM-DD")
    ts_from = parse_date(ask("  Include content FROM date", ""))
    ts_to = parse_date(ask("  Include content TO date", ""), end=True)

    min_len = ask("\nMinimum text length in characters (filters out one-word/emoji-only)", "0")
    min_len = int(min_len) if min_len.isdigit() else 0

    # ---- Visibility (only offer if the export actually contains it) ----
    excluded_vis = set()
    if vis_values:
        print(f"\nVisibility/audience values found in your export: {', '.join(vis_values)}")
        keep_vis = ask_multi(
            "Which visibilities should be INCLUDED?",
            [(v, v) for v in vis_values] + [("unknown", "unknown (no visibility recorded)")])
        excluded_vis = ({v for v in vis_values} | {"unknown"}) - keep_vis
    else:
        print("\nNOTE: These exports contain NO per-item visibility/audience data.")
        print("      (Meta omits it from posts/captions/stories; IG privacy is account-wide.)")
        print("      Every item will be tagged visibility=unknown; no privacy filter applied.")

    dedupe = ask_yes_no("\nDe-duplicate identical cross-posts (same text on FB & IG)?", True)
    split = ask_yes_no("Write a separate file per content type (vs one combined file)?", False)
    out_name = ask("Output base filename", "voice_corpus")

    # ---- Apply filters ----
    sel = apply_filters(all_entries, chosen_types, ts_from, ts_to,
                        min_len, excluded_vis, dedupe)
    if not sel:
        print("\nNo entries matched your filters. Nothing written.")
        sys.exit(0)

    # ---- Write ----
    written = []
    if split:
        for t in sorted({e["type"] for e in sel}):
            sub = [e for e in sel if e["type"] == t]
            path = os.path.join(export_dir, f"{out_name}_{t}.txt")
            write_corpus(path, sub); written.append((path, len(sub)))
    else:
        path = os.path.join(export_dir, f"{out_name}.txt")
        write_corpus(path, sel); written.append((path, len(sel)))

    print("\nDone:")
    for path, n in written:
        print(f"  {path}  ({n} entries)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
