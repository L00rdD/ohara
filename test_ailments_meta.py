"""Tests of ailments_meta.py, Chopper's examinations of what Ohara knows of each series,
without AniList, Prowlarr or Transmission: python3 -m unittest test_ailments_meta.py"""

import importlib.util
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = sys.modules.get("ohara") or importlib.util.module_from_spec(_spec)
if "ohara" not in sys.modules:
    _spec.loader.exec_module(ohara)
    sys.modules["ohara"] = ohara  # as it is when it runs: Chopper's remedies are given it

import ailments_meta as meta  # noqa: E402

chopper = meta.chopper

ERAGON = "Christopher Paolini Eragon"
FOUND = {"id": 7, "title": "Eragon", "names": ["Eragon"], "cover": "c", "color": "#000", "banner": "b", "status": "Terminé", "volumes": 3, "year": 2003}


def vol(series, file, number):
    return {"id": f"{series}/{file}", "label": file, "number": number, "file": file, "readable": True, "page": 0, "pages": 0,
            "done": False, "new": False, "at": 0, "spine": None, "chapters": None}


def series(name, files, meta=None, **more):
    vols = [vol(name, f, ohara.volume_number(f)) for f in files]
    info = {"name": name, "volumes": vols, "read": 0, "new": 0, "follow": False, "decor": "banner", "kept": None,
            "meta": meta or {}, "missing": [], "coming": []}
    return {**info, **more}


def snapshot(*infos, entries=None):
    return {"series": list(infos), "downloads": [], "state": {"series": entries or {}}, "files": {}, "incoming": [], "now": 0}


def eragon(**more):
    files = ["1 - Eragon - Christopher Paolini.epub", "1-Eragon-Christopher-Paolini.pdf", "2 - L'Aine - Christopher Paolini.epub"]
    return series(ERAGON, files, **more)


def naruto(meta=None, top=3, **more):
    files = [f"[Team] Naruto - Tome #{n:03} - [V2].cbz" for n in range(1, top + 1)]
    return series("Naruto", files, meta if meta is not None else {"id": 1, "title": "Naruto", "names": ["NARUTO"], "status": "Terminé", "volumes": 72}, **more)


def ids(found):
    return [a["id"] for a in found]


class Names(unittest.TestCase):
    """What else a series could be called."""

    def test_the_folder_name_without_brackets_or_years(self):
        self.assertEqual(meta.cleaned("Berserk (Miura) [2021] 1989"), "Berserk")
        s = series("Berserk (Miura) 1989", ["Berserk T01.cbz", "Berserk T02.cbz"])
        self.assertEqual(meta.other_names(s), ["Berserk"])

    def test_the_folder_name_without_its_author(self):
        self.assertEqual(meta.common_parts(meta.file_titles(eragon())), ["Christopher Paolini"])
        self.assertEqual(meta.other_names(eragon()), ["Eragon"])

    def test_the_title_every_file_name_has(self):
        s = series("JJK", ["Jujutsu Kaisen T01 (Akutami) [FR].cbz", "Jujutsu Kaisen T02 (Akutami) [FR].cbz"])
        self.assertEqual(meta.other_names(s), ["Jujutsu Kaisen"])

    def test_nothing_more_when_the_folder_is_the_title_of_every_file(self):
        files = ["Rowling J. K - Harry Potter [Tome 1] - Harry Potter à l_école des sorciers.epub",
                 "Rowling J. K - Harry Potter [Tome 2] - Harry Potter et la chambre des secrets.epub"]
        self.assertEqual(meta.other_names(series("Harry Potter", files)), [])

    def test_runs_of_tomes(self):
        self.assertEqual(meta.runs([9, 3, 7, 8]), [(3, 3), (7, 9)])
        self.assertEqual(meta.said_runs([3, 7, 8, 9, 12], "à"), "3, 7 à 9, 12")


class Unknown(unittest.TestCase):
    """A series AniList knows nothing of."""

    def test_asked_again_under_other_names_and_dressed_with_its_first_cover(self):
        [a] = meta.unknown(snapshot(eragon(), naruto()))
        self.assertEqual((a["id"], a["severity"], a["series"]), ("anilist-unknown:" + ERAGON, "advice", ERAGON))
        self.assertIn("AniList ne connaît pas « Christopher Paolini Eragon »", a["text"]["fr"])
        ask, decor = a["remedies"]
        self.assertEqual((ask["kind"], ask["args"]), ("anilist-ask", {"series": ERAGON, "query": "Eragon"}))
        self.assertEqual(ask["label"]["fr"], "Demander à AniList « Eragon »")
        self.assertEqual(decor["args"], {"series": ERAGON, "decor": "vol:" + ERAGON + "/1 - Eragon - Christopher Paolini.epub"})

    def test_not_a_name_already_asked_nor_a_decor_chosen(self):
        [a] = meta.unknown(snapshot(eragon(decor="none"), entries={ERAGON: {"query": "Eragon"}}))
        self.assertEqual(a["remedies"], [])

    def test_the_same_id_from_one_examination_to_the_next(self):
        self.assertEqual(ids(meta.unknown(snapshot(eragon()))), ids(meta.unknown(snapshot(eragon(read=2, decor="cover")))))


class Doubtful(unittest.TestCase):
    """A series AniList took for another one."""

    def test_tomes_well_past_anilists_count(self):
        s = naruto({"id": 2, "title": "Naruto Gaiden", "names": ["Naruto"], "volumes": 12}, top=40)
        [a] = meta.doubtful(snapshot(s))
        self.assertEqual((a["id"], a["severity"]), ("anilist-doubtful:Naruto", "trouble"))
        self.assertIn("AniList donne 12 tomes à « Naruto Gaiden », or tu as le tome 40", a["text"]["fr"])
        kinds = [(r["kind"], r["args"]) for r in a["remedies"]]
        self.assertEqual(kinds, [("anilist-ask", {"series": "Naruto", "query": "Naruto"}), ("anilist-forget", {"series": "Naruto"})])

    def test_names_that_share_nothing(self):
        s = eragon(meta={"id": 3, "title": "Dragon Quest", "names": ["Dragon Quest: Dai no Daibouken"]})
        [a] = meta.doubtful(snapshot(s))
        self.assertIn("AniList a pris « Christopher Paolini Eragon » pour « Dragon Quest »", a["text"]["fr"])
        self.assertEqual([r["args"].get("query") for r in a["remedies"]], [ERAGON, "Eragon", None])

    def test_a_good_match_is_left_alone(self):
        jjk = series("JJK", ["Jujutsu Kaisen T01.cbz"], {"id": 4, "title": "Jujutsu Kaisen", "names": ["呪術廻戦"], "volumes": 30})
        found = meta.doubtful(snapshot(naruto(top=75), eragon(meta=FOUND), jjk, series("Sorcery", ["S T01.cbz"], {"id": 5, "title": "Sorcery Fight"})))
        self.assertEqual(found, [])
        asked = series("Ikki", ["Ikki T01.cbz"], {"id": 6, "title": "Zetman"})
        self.assertEqual(meta.doubtful(snapshot(asked, entries={"Ikki": {"query": "Zetman"}})), [])
        self.assertEqual(ids(meta.doubtful(snapshot(asked))), ["anilist-doubtful:Ikki"])
        self.assertEqual(meta.doubtful(snapshot(series("Z", ["Z T01.cbz"], {"id": 6, "title": "Zetman"}))), [])  # too short to tell


class Missing(unittest.TestCase):
    """Holes among the tomes."""

    def test_said_as_runs_with_the_remedy(self):
        [a] = meta.missing(snapshot(naruto(missing=[3, 7, 8, 9]), naruto(missing=[]) | {"name": "Other"}))
        self.assertEqual((a["id"], a["severity"]), ("tomes-missing:Naruto", "advice"))
        self.assertEqual(a["text"], {"fr": "Il manque à « Naruto » les tomes 3, 7 à 9.", "en": "“Naruto” lacks volumes 3, 7 to 9."})
        self.assertEqual([(r["kind"], r["args"]) for r in a["remedies"]], [("tomes-fetch", {"series": "Naruto"})])
        [one] = meta.missing(snapshot(naruto(missing=[30])))
        self.assertEqual(one["text"]["fr"], "Il manque à « Naruto » le tome 30.")

    def test_not_while_tomes_are_coming_nor_when_anilists_count_is_doubtful(self):
        wrong = {"id": 2, "title": "Other", "names": [], "volumes": 2}
        self.assertEqual(meta.missing(snapshot(naruto(missing=[4], coming=[5]), naruto(wrong, top=9, missing=[4]))), [])


class FollowedOver(unittest.TestCase):
    """A followed series that is over."""

    def test_stop_following_it(self):
        [a] = meta.followed_over(snapshot(naruto(follow=True)))
        self.assertEqual((a["id"], a["severity"]), ("follow-over:Naruto", "advice"))
        self.assertIn("est terminé et tu as tous ses tomes", a["text"]["fr"])
        self.assertEqual([(r["kind"], r["args"]) for r in a["remedies"]], [("follow-stop", {"series": "Naruto"})])

    def test_not_while_something_is_left_to_come(self):
        going = naruto({"id": 1, "title": "Naruto", "names": [], "status": "En cours"}, follow=True)
        cases = [naruto(), naruto(follow=True, missing=[4]), naruto(follow=True, coming=[4]), going]
        self.assertEqual(meta.followed_over(snapshot(*cases)), [])


class LostDecor(unittest.TestCase):
    """A decor chosen that cannot be shown."""

    def test_a_volume_gone_or_an_image_not_kept(self):
        gone = naruto(decor="vol:Naruto/gone.cbz")
        own = eragon(decor="own:12")
        found = meta.lost_decor(snapshot(gone, own))
        self.assertEqual(ids(found), ["decor-gone:Naruto", "decor-gone:" + ERAGON])
        self.assertEqual(found[0]["severity"], "trouble")
        self.assertIn("Le décor choisi pour « Naruto » n'existe plus", found[0]["text"]["fr"])
        self.assertEqual([r["args"]["decor"] for r in found[0]["remedies"]], ["banner", "vol:Naruto/[Team] Naruto - Tome #001 - [V2].cbz"])
        self.assertEqual([r["args"]["decor"] for r in found[1]["remedies"]], ["banner", "vol:" + ERAGON + "/1 - Eragon - Christopher Paolini.epub"])

    def test_a_decor_that_can_be_shown(self):
        banner = {"id": 1, "title": "Naruto", "banner": "b"}
        fine = [naruto(decor="vol:Naruto/[Team] Naruto - Tome #001 - [V2].cbz"), eragon(decor="own:12", kept=12), naruto(decor="cover")]
        self.assertEqual(meta.lost_decor(snapshot(*fine)), [])
        [a] = meta.lost_decor(snapshot(naruto(banner, decor="vol:x")))
        self.assertEqual(len(a["remedies"]), 1)


class Examined(unittest.TestCase):
    def test_every_examination_through_chopper(self):
        with mock.patch.object(chopper, "_loaded", True):
            found = chopper.examine(snapshot(eragon(decor="vol:gone"), naruto(follow=True), naruto(missing=[2]) | {"name": "One Piece"}))
        self.assertEqual(ids(found), ["decor-gone:" + ERAGON, "anilist-unknown:" + ERAGON, "follow-over:Naruto", "tomes-missing:One Piece"])


def cbz(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("1.png", b"x")
    return path


class Cures(unittest.TestCase):
    """The remedies, on a temporary library, AniList and Prowlarr mocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = {"MANGA": root, "STATE_DIR": root / ".ohara", "INCOMING": root / ".incoming", "MUSIC": root / ".ost"}
        for p in [mock.patch.object(ohara, name, value) for name, value in patches.items()] + [mock.patch.dict(sys.modules, {"ohara": ohara})]:
            p.start()
            self.addCleanup(p.stop)
        self.root = root
        cbz(root / ERAGON / "1 - Eragon - Christopher Paolini.epub")
        cbz(root / ERAGON / "2 - L'Aine - Christopher Paolini.epub")
        ohara.ailments_seen.update(at=0, list=[])

    def tearDown(self):
        self.tmp.cleanup()

    def cure(self, kind, **args):
        return chopper.CURES[kind](ohara, **args)

    def test_asking_anilist_under_another_name_from_the_doctor(self):
        ohara.save_state({"lookups": {ohara.norm(ERAGON): {}}})
        with mock.patch.object(ohara, "anilist_fetch", return_value=FOUND) as fetch, mock.patch.object(ohara, "safe_torrents", return_value=[]):
            self.assertIn("anilist-unknown:" + ERAGON, ids(ohara.ailments(fresh=True)))
            done = ohara.treat("anilist-unknown:" + ERAGON, 0)
        fetch.assert_called_once_with("Eragon")
        self.assertEqual(done["done"], {"title": "Eragon"})
        state = ohara.load_state()
        self.assertEqual(state["lookups"][ohara.norm(ERAGON)], FOUND)
        self.assertEqual((state["series"][ERAGON]["query"], state["series"][ERAGON]["anilist"]), ("Eragon", 7))
        self.assertNotIn("anilist-unknown:" + ERAGON, ids(done["ailments"]))

    def test_asking_anilist_for_a_name_it_does_not_know(self):
        ohara.save_state({"series": {ERAGON: {"follow": True, "anilist": 3}}})
        with mock.patch.object(ohara, "anilist_fetch", return_value={}):
            self.assertEqual(self.cure("anilist-ask", series=ERAGON, query="Eragon"), {"title": None})
        state = ohara.load_state()
        self.assertEqual(state["series"][ERAGON], {"follow": True, "query": "Eragon"})
        self.assertEqual(state["lookups"][ohara.norm(ERAGON)], {})

    def test_forgetting_what_anilist_said(self):
        ohara.save_state({"lookups": {ohara.norm(ERAGON): {"id": 3}}, "series": {ERAGON: {"anilist": 3, "follow": True}}})
        self.cure("anilist-forget", series=ERAGON)
        self.cure("anilist-forget", series="Nobody")
        state = ohara.load_state()
        self.assertEqual((state["lookups"][ohara.norm(ERAGON)], state["series"][ERAGON]), ({}, {"follow": True}))
        with mock.patch.object(ohara, "anilist_fetch") as fetch:
            self.assertEqual(ohara.lookup(ERAGON), {})  # not asked again by itself
        fetch.assert_not_called()

    def test_fetching_the_missing_tomes(self):
        with mock.patch.object(ohara, "find_releases", return_value=[]) as find:
            self.assertEqual(self.cure("tomes-fetch", series=ERAGON), {"sent": [], "nowhere": []})
        find.assert_called_once_with(ERAGON)

    def test_following_no_more(self):
        ohara.save_state({"series": {ERAGON: {"follow": True, "query": ERAGON}}})
        self.cure("follow-stop", series=ERAGON)
        self.assertFalse(ohara.load_state()["series"][ERAGON]["follow"])

    def test_choosing_a_decor(self):
        vid = "vol:" + ERAGON + "/1 - Eragon - Christopher Paolini.epub"
        self.assertEqual(self.cure("decor-choose", series=ERAGON, decor=vid), {"ok": True, "decor": vid})
        self.assertEqual(self.cure("decor-choose", series=ERAGON, decor="banner")["decor"], "banner")
        self.assertEqual(ohara.load_state()["series"][ERAGON]["decor"], "banner")
        with self.assertRaises(KeyError):
            self.cure("decor-choose", series=ERAGON, decor="vol:" + ERAGON + "/gone.epub")


if __name__ == "__main__":
    unittest.main()
