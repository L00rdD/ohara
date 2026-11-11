"""Tests of Chopper's examinations of the downloads, without Prowlarr or Transmission:
python3 -m unittest test_ailments_downloads.py"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = sys.modules.get("ohara")  # one copy for every test module, as there is one when Ohara runs
if ohara is None:
    ohara = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ohara)
    sys.modules["ohara"] = ohara  # Chopper's remedies are given it

import ailments_downloads as dl  # noqa: E402

NOW = 1_000_000_000
HOUR = 3600


def info(h, state="downloading", pct=0, kind="volumes", title=None, series="Jujutsu Kaisen", error=""):
    return {"hash": h, "series": series, "title": title or f"Pack {h}", "range": None, "kind": kind, "pct": pct, "state": state, "eta": -1, "error": error}


def entry(at, folder="f", series="Jujutsu Kaisen", rng=None, kind=None, **more):
    e = {"series": series, "title": "t", "folder": folder, "range": rng, "at": NOW - at, **more}
    if kind:
        e["kind"] = kind
    return e


def snap(downloads=(), entries=None, incoming=()):
    return {"series": [], "downloads": list(downloads), "state": {"downloads": entries or {}}, "files": {}, "incoming": list(incoming), "now": NOW}


def ids(found):
    return [a["id"] for a in found]


class Exams(unittest.TestCase):
    """The examinations only read the snapshot."""

    def test_durations(self):
        self.assertEqual(dl.ago(14.4 * HOUR), {"fr": "14 h", "en": "14 h"})
        self.assertEqual(dl.ago(60), {"fr": "1 h", "en": "1 h"})
        self.assertEqual(dl.ago(75 * HOUR), {"fr": "3 jours", "en": "3 days"})

    def test_a_pack_that_never_starts_or_stays_in_error(self):
        s = snap([info("A", title="Jujutsu Kaisen - T01 à T17"), info("B"), info("C", kind="ost"), info("D", pct=3),
                  info("E", state="error", kind="ost", error="no space"), info("F", state="error")],
                 {"A": entry(14 * HOUR), "B": entry(2 * HOUR), "C": entry(20 * HOUR, kind="ost"), "D": entry(20 * HOUR),
                  "E": entry(0, kind="ost"), "F": entry(0)})
        found = dl.stuck(s)
        self.assertEqual(ids(found), ["dl-stuck:A", "dl-stuck:E", "dl-stuck:F"])
        a = found[0]
        self.assertEqual(a["text"]["fr"], "« Jujutsu Kaisen - T01 à T17 » n'a pas commencé depuis 14 h : personne ne le partage peut-être plus.")
        self.assertEqual((a["series"], a["severity"]), ("Jujutsu Kaisen", "trouble"))
        self.assertEqual(a["remedies"], [{"kind": "dl-cancel", "label": {"fr": "L'annuler", "en": "Cancel it"}, "risky": True, "args": {"hash": "A"}}])
        self.assertEqual(found[1]["text"]["fr"], "« Pack E » est en erreur : no space.")
        self.assertIn("?", found[2]["text"]["en"])
        self.assertEqual(ids(dl.stuck(s)), ids(found))  # the same ids, examination after examination

    def test_a_download_transmission_no_longer_knows(self):
        s = snap([info("A", state="unknown"), info("B", state="unknown"), info("C")],
                 {"A": entry(2 * HOUR), "B": entry(HOUR / 2), "C": entry(0)})
        found = dl.lost(s)
        self.assertEqual(ids(found), ["dl-lost:A"])
        self.assertEqual([(r["risky"], r["args"]) for r in found[0]["remedies"]], [(False, {"hash": "A"}), (True, {"hash": "A", "wipe": True})])
        self.assertIn("retiré hors d'Ohara", found[0]["text"]["fr"])
        # nothing known at all: Transmission is away, not every download gone
        away = snap([info("A", state="unknown"), info("B", state="unknown")], {"A": entry(9 * HOUR), "B": entry(9 * HOUR)})
        self.assertEqual(dl.lost(away), [])
        alone = snap([info("A", state="unknown")], {"A": entry(9 * HOUR)})
        self.assertEqual(ids(dl.lost(alone)), ["dl-lost:A"])

    def test_a_download_finished_but_never_filed(self):
        s = snap([info("A", state="done", pct=100), info("B", state="done", pct=100), info("C", pct=100, state="error"),
                  info("D", state="done", pct=100), info("E", pct=50)],
                 {"A": entry(2 * HOUR), "B": entry(5 * 60), "C": entry(HOUR), "D": entry(5 * HOUR, done_at=NOW - 60), "E": entry(5 * HOUR)})
        found = dl.unfiled(s)
        self.assertEqual(ids(found), ["dl-unfiled:A", "dl-unfiled:C"])
        self.assertEqual([(r["kind"], r["risky"]) for r in found[0]["remedies"]], [("dl-file", False), ("dl-cancel", True)])
        self.assertIn("n'a pas été rangé", found[0]["text"]["fr"])

    def test_leftovers_in_incoming(self):
        s = snap([], {"A": entry(0, folder="abc"), "B": {"series": "x", "title": "t"}}, incoming=["abc", "old one", "ost-9"])
        found = dl.leftovers(s)
        self.assertEqual(ids(found), ["dl-leftover:old one", "dl-leftover:ost-9"])
        self.assertEqual((found[0]["severity"], found[0]["series"]), ("advice", None))
        self.assertEqual(found[0]["remedies"][0]["args"], {"name": "old one"})
        self.assertTrue(found[0]["remedies"][0]["risky"])

    def test_the_same_tomes_coming_twice(self):
        entries = {"OLD": entry(5 * HOUR, rng=[1, 17]), "NEW": entry(HOUR, rng=[15, 20]), "FAR": entry(HOUR, rng=[30, 31]),
                   "ONE": entry(0, rng=[17, 17]), "ELSE": entry(HOUR, series="Naruto", rng=[1, 72]),
                   "OST": entry(HOUR, kind="ost"), "NONE": entry(HOUR)}
        found = dl.twice(snap([], entries))
        self.assertEqual(ids(found), ["dl-twice:OLD+NEW", "dl-twice:OLD+ONE", "dl-twice:NEW+ONE"])
        self.assertIn("T15–T17", found[0]["text"]["fr"])
        self.assertIn("both bring T17.", found[1]["text"]["en"])
        self.assertEqual(found[0]["remedies"][0]["args"], {"hash": "NEW"})
        self.assertEqual(found[0]["severity"], "advice")

    def test_chopper_finds_them_all(self):
        s = snap([info("A")], {"A": entry(13 * HOUR)}, incoming=["f", "junk"])
        with mock.patch.object(ohara.chopper, "_loaded", False):
            found = ohara.chopper.examine(s)
        self.assertEqual(sorted(ids(found)), ["dl-leftover:junk", "dl-stuck:A"])


class Cures(unittest.TestCase):
    """The cures, on a temporary library, Transmission mocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = {"MANGA": root, "STATE_DIR": root / ".ohara", "INCOMING": root / ".incoming", "MUSIC": root / ".ost"}
        for name, value in patches.items():
            p = mock.patch.object(ohara, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.root = root
        self.incoming = root / ".incoming"
        self.incoming.mkdir()
        self.calls = []
        self.known = []  # the torrents Transmission has

        def rpc(method, arguments):
            self.calls.append((method, arguments))
            return {"torrents": [{"hashString": h} for h in self.known]} if method == "torrent-get" else {}
        p = mock.patch.object(ohara, "rpc", side_effect=rpc)
        p.start()
        self.addCleanup(p.stop)
        for net in ("find_releases", "http_json", "lookup"):
            p = mock.patch.object(ohara, net, side_effect=AssertionError("no network"))
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def cure(self, kind, **args):
        return dl.chopper.CURES[kind](ohara, **args)

    def folder(self, name, files=("a.cbz",)):
        f = self.incoming / name
        f.mkdir()
        for n in files:
            (f / n).write_bytes(b"x")
        return f

    def removed(self):
        return [a["ids"] for m, a in self.calls if m == "torrent-remove"]

    def test_cancel_drops_the_download_and_its_folder_twice_safely(self):
        self.folder("abc")
        ohara.save_state({"downloads": {"H": {"series": "S", "title": "t", "folder": "abc", "range": [1, 2], "at": 1}}})
        self.cure("dl-cancel", hash="H")
        self.assertFalse((self.incoming / "abc").exists())
        self.assertEqual(ohara.load_state()["downloads"], {})
        self.cure("dl-cancel", hash="H")  # gone meanwhile: nothing more
        self.assertEqual(self.removed(), [["H"], ["H"]])
        self.assertTrue(self.root.exists())

    def test_cancelling_a_soundtrack_lets_brook_take_another(self):
        self.folder("ost-1", ["a.mp3"])
        ohara.save_state({"downloads": {"H": {"series": "S", "title": "OST", "folder": "ost-1", "range": None, "kind": "ost", "at": 1}}})
        self.cure("dl-cancel", hash="H")
        state = ohara.load_state()
        self.assertEqual((state["downloads"], state["music"]["S"]["skipped"]), ({}, ["OST"]))
        self.assertFalse((self.incoming / "ost-1").exists())

    def test_a_folder_outside_incoming_is_never_touched(self):
        (self.root / "Naruto").mkdir()
        for bad in ("..", ".", "", "../Naruto", "a/b", "a\\b", "a\0b"):
            ohara.save_state({"downloads": {"H": {"series": "S", "title": "t", "folder": bad, "range": None, "at": 1}}})
            with self.assertRaises(KeyError, msg=bad):
                self.cure("dl-delete", name=bad)
            with self.assertRaises(KeyError, msg=bad):
                self.cure("dl-cancel", hash="H")
            with self.assertRaises(KeyError, msg=bad):
                self.cure("dl-file", hash="H")
        self.assertTrue((self.root / "Naruto").exists())
        self.assertTrue(self.incoming.exists())
        self.assertEqual(self.removed(), [])  # nor any download dropped

    def test_delete_takes_a_leftover_away_and_a_link_but_not_its_target(self):
        self.folder("old", ["x.cbz", "y.part"])
        (self.incoming / "loose.cbz").write_bytes(b"x")
        target = self.root / "Naruto"
        target.mkdir()
        (self.incoming / "link").symlink_to(target)
        for name in ("old", "loose.cbz", "link", "old"):
            self.cure("dl-delete", name=name)
        self.assertEqual(list(self.incoming.iterdir()), [])
        self.assertTrue(target.exists())

    def test_delete_spares_a_folder_a_download_has_taken_meanwhile(self):
        self.folder("abc")
        ohara.save_state({"downloads": {"H": {"series": "S", "title": "t", "folder": "abc", "range": None, "at": 1}}})
        with self.assertRaises(KeyError):
            self.cure("dl-delete", name="abc")
        self.assertTrue((self.incoming / "abc").exists())

    def test_forget_drops_what_transmission_lost(self):
        self.folder("empty", [])
        self.folder("full")
        self.folder("wiped")
        ohara.save_state({"downloads": {h: {"series": "S", "title": "t", "folder": f, "range": None, "at": 1}
                                        for h, f in (("E", "empty"), ("F", "full"), ("W", "wiped"))}})
        self.cure("dl-forget", hash="E")
        self.cure("dl-forget", hash="F")
        self.cure("dl-forget", hash="W", wipe=True)
        self.cure("dl-forget", hash="W", wipe=True)  # twice: nothing more
        self.assertEqual(ohara.load_state()["downloads"], {})
        self.assertEqual(sorted(p.name for p in self.incoming.iterdir()), ["full"])
        self.assertEqual(self.removed(), [])

    def test_forget_is_refused_while_transmission_has_it(self):
        self.folder("abc")
        ohara.save_state({"downloads": {"H": {"series": "S", "title": "t", "folder": "abc", "range": None, "at": 1}}})
        self.known = ["H"]
        with self.assertRaises(RuntimeError):
            self.cure("dl-forget", hash="H", wipe=True)
        self.assertIn("H", ohara.load_state()["downloads"])
        self.assertTrue((self.incoming / "abc").exists())

    def test_filing_again(self):
        src = self.folder("abc", ["Naruto T01.cbz"])
        ohara.save_state({"downloads": {"H": {"series": "Naruto", "title": "t", "folder": "abc", "range": [1, 1], "at": 1}}})
        self.cure("dl-file", hash="H")
        self.assertTrue((self.root / "Naruto" / "Naruto T01.cbz").exists())
        self.assertFalse(src.exists())
        self.assertEqual(ohara.load_state()["downloads"], {})
        self.assertEqual(self.cure("dl-file", hash="H"), {"gone": True})
        self.assertEqual(self.removed(), [["H"]])

    def test_dropping_an_unfiled_download(self):
        self.folder("abc", ["Naruto T01.cbz"])
        ohara.save_state({"downloads": {"H": {"series": "Naruto", "title": "t", "folder": "abc", "range": [1, 1], "at": 1}}})
        aid = "dl-unfiled:H"
        found = [dl.ailment("dl-unfiled", "H", dl.words("a", "a"), dl.unfiled(snap([info("H", state="done", pct=100)], {"H": entry(HOUR)}))[0]["remedies"])]
        self.assertEqual(dl.chopper.apply(found, aid, 1, ohara), {"ok": True})
        self.assertEqual(list(self.incoming.iterdir()), [])
        self.assertFalse((self.root / "Naruto").exists())


if __name__ == "__main__":
    unittest.main()
