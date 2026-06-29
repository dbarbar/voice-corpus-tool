"""
Unit + integration tests for voice_corpus_tool.

Uses only the standard library (unittest) so it runs in CI with no pip install.
Builds tiny synthetic Facebook/Instagram export zips on the fly — no real
personal data required.

Run from the repo root:   python -m unittest discover -s tests -v
"""
import os, sys, json, zipfile, tempfile, shutil, datetime, unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
import voice_corpus_tool as vct

# Fixed, timezone-safe timestamps (midday avoids date-boundary flip across TZs).
def ts(year):
    return int(datetime.datetime(year, 6, 1, 12, 0, 0).timestamp())

TS_2018, TS_2021, TS_2024 = ts(2018), ts(2021), ts(2024)

# A string mangled exactly the way Meta's exports mangle UTF-8 (emoji + accent).
CLEAN = "Grateful today 🤣 café"
MOJIBAKE = CLEAN.encode("utf-8").decode("latin-1")


def make_fb_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("personal_information/profile_information/profile_information.json",
                   json.dumps({"profile_v2": {"name": {"full_name": "Test User"}}}))
        z.writestr("your_facebook_activity/posts/your_posts__check_ins__photos_and_videos_1.json",
                   json.dumps([
                       {"timestamp": TS_2018, "data": [{"post": "Old gaming post"}], "title": "t"},
                       {"timestamp": TS_2024, "data": [{"post": "Recent shared thought"}],
                        "attachments": [{"data": [{"external_context": {"url": "http://x"}}]}]},
                       {"timestamp": TS_2024,
                        "label_values": [{"label": "Post", "value": "New-schema post"}]},
                   ]))
        z.writestr("your_facebook_activity/comments_and_reactions/comments.json",
                   json.dumps({"comments_v2": [
                       {"timestamp": TS_2021, "data": [{"comment": {
                           "timestamp": TS_2021, "comment": "My own comment", "author": "Test User"}}]},
                       {"timestamp": TS_2021, "data": [{"comment": {
                           "timestamp": TS_2021, "comment": "Not mine", "author": "Other Person"}}]},
                   ]}))


def make_ig_zip(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("your_instagram_activity/media/posts_1.json",
                   json.dumps([
                       {"creation_timestamp": TS_2021, "title": "Caption " + MOJIBAKE,
                        "media": [{"uri": "a.jpg", "creation_timestamp": TS_2021}]},
                       {"media": [{"uri": "b.jpg", "creation_timestamp": TS_2024,
                                   "title": "Caption on media level"}]},
                   ]))
        z.writestr("your_instagram_activity/media/stories.json",
                   json.dumps({"ig_stories": [
                       {"creation_timestamp": TS_2024, "title": "Story text here"},
                       {"creation_timestamp": TS_2024, "title": ""},  # empty -> dropped
                   ]}))
        z.writestr("your_instagram_activity/comments/post_comments_1.json",
                   json.dumps([
                       {"string_map_data": {"Comment": {"value": "An IG comment"},
                                            "Time": {"timestamp": TS_2021}}},
                   ]))


class TestTextRepair(unittest.TestCase):
    def test_repairs_mojibake(self):
        self.assertEqual(vct.fix_text(MOJIBAKE), CLEAN)

    def test_leaves_clean_text_unchanged(self):
        self.assertEqual(vct.fix_text("plain ascii text"), "plain ascii text")
        self.assertEqual(vct.fix_text(CLEAN), CLEAN)  # already-correct emoji preserved

    def test_non_string(self):
        self.assertEqual(vct.fix_text(None), "")


class TestEntry(unittest.TestCase):
    def test_drops_empty_and_missing_ts(self):
        self.assertIsNone(vct.entry(TS_2021, "FB", "post", "   "))
        self.assertIsNone(vct.entry(None, "FB", "post", "hello"))

    def test_builds_and_defaults_visibility(self):
        e = vct.entry(TS_2021, "IG", "caption", "  hi  ", media=True)
        self.assertEqual(e["text"], "hi")
        self.assertEqual(e["visibility"], "unknown")
        self.assertTrue(e["media"])


class TestVisibilityDetection(unittest.TestCase):
    def test_label_values_audience(self):
        rec = {"label_values": [{"label": "Audience", "value": "Friends"}]}
        self.assertEqual(vct.detect_visibility(rec), "Friends")

    def test_none_present(self):
        self.assertEqual(vct.detect_visibility({"data": []}), "")


class TestParsing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        make_fb_zip(os.path.join(self.tmp, "facebook-export.zip"))
        make_ig_zip(os.path.join(self.tmp, "instagram-export.zip"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_discovery(self):
        kinds = sorted(s.kind for s in vct.discover_sources(self.tmp))
        self.assertEqual(kinds, ["FB", "IG"])

    def test_fb_parsing_and_owner_filter(self):
        src = [s for s in vct.discover_sources(self.tmp) if s.kind == "FB"][0]
        ents = vct.parse_fb(src)
        posts = [e for e in ents if e["type"] == "post"]
        comments = [e for e in ents if e["type"] == "comment"]
        self.assertEqual(len(posts), 3)                       # classic x2 + label_values
        self.assertEqual(len(comments), 1)                    # only owner's comment kept
        self.assertEqual(comments[0]["text"], "My own comment")
        self.assertTrue(any(e["shared_link"] for e in posts)) # link post flagged

    def test_ig_parsing_and_encoding(self):
        src = [s for s in vct.discover_sources(self.tmp) if s.kind == "IG"][0]
        ents = vct.parse_ig(src)
        captions = [e for e in ents if e["type"] == "caption"]
        stories = [e for e in ents if e["type"] == "story"]
        comments = [e for e in ents if e["type"] == "comment"]
        self.assertEqual(len(captions), 2)
        self.assertEqual(len(stories), 1)                     # empty story dropped
        self.assertEqual(len(comments), 1)
        self.assertTrue(any("🤣" in e["text"] and "café" in e["text"] for e in captions))


class TestFilters(unittest.TestCase):
    def _entries(self):
        return [
            vct.entry(TS_2018, "FB", "post", "old post here"),
            vct.entry(TS_2024, "FB", "post", "recent post here"),
            vct.entry(TS_2024, "IG", "caption", "a recent caption"),
            vct.entry(TS_2024, "IG", "story", "x"),                 # short
            vct.entry(TS_2024, "IG", "comment", "duplicate text content"),
            vct.entry(TS_2021, "FB", "comment", "duplicate text content"),
        ]

    def test_type_filter(self):
        sel = vct.apply_filters(self._entries(), {"post"})
        self.assertTrue(all(e["type"] == "post" for e in sel))
        self.assertEqual(len(sel), 2)

    def test_date_range(self):
        sel = vct.apply_filters(self._entries(), {"post", "caption", "story", "comment"},
                                ts_from=ts(2020))
        self.assertTrue(all(e["ts"] >= ts(2020) for e in sel))

    def test_min_length(self):
        sel = vct.apply_filters(self._entries(), {"story", "caption"}, min_len=5)
        self.assertNotIn("x", [e["text"] for e in sel])         # short story removed

    def test_dedupe_keeps_earliest(self):
        sel = vct.apply_filters(self._entries(), {"comment"}, dedupe=True)
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["ts"], TS_2021)                 # earliest kept

    def test_sorted_chronologically(self):
        sel = vct.apply_filters(self._entries(), {"post", "caption", "story", "comment"},
                                dedupe=False)
        self.assertEqual([e["ts"] for e in sel], sorted(e["ts"] for e in sel))


class TestWrite(unittest.TestCase):
    def test_write_corpus(self):
        tmp = tempfile.mkdtemp()
        try:
            ents = [
                vct.entry(TS_2018, "FB", "post", "first " + CLEAN),
                vct.entry(TS_2024, "IG", "caption", "second one"),
            ]
            out = os.path.join(tmp, "corpus.txt")
            vct.write_corpus(out, ents)
            with open(out, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("# Entries: 2", text)
            self.assertIn("🤣", text)                            # encoding survives write
            self.assertIn("[#00001]", text)
            self.assertIn("| FB | post |", text)
            self.assertIn("PRIVACY", text)                       # privacy warning in header
            self.assertIn("visibility=unknown", text)            # visibility caveat surfaced
        finally:
            shutil.rmtree(tmp)


class TestPackageInSync(unittest.TestCase):
    """Guard against the shipped copy drifting from the canonical tool."""
    def test_copies_identical(self):
        root = os.path.join(REPO_ROOT, "voice_corpus_tool.py")
        shipped = os.path.join(REPO_ROOT, "VoiceCorpusBuilder", "voice_corpus_tool.py")
        if not os.path.exists(shipped):
            self.skipTest("VoiceCorpusBuilder copy not present")
        with open(root, "rb") as a, open(shipped, "rb") as b:
            self.assertEqual(a.read(), b.read(),
                             "VoiceCorpusBuilder/voice_corpus_tool.py is out of sync — run package.sh")


if __name__ == "__main__":
    unittest.main(verbosity=2)
