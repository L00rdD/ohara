"""Tests of ohara.py, without Prowlarr, Transmission or a socket:
python3 -m unittest test_ohara.py"""

import base64
import importlib.util
import io
import json
import os
import sys
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = sys.modules.get("ohara")  # one copy for every test module, as there is one when Ohara runs
if ohara is None:
    ohara = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ohara)
    sys.modules["ohara"] = ohara  # Chopper's remedies are given it


def png(color=(200, 30, 30)):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(out, "PNG")
    return out.getvalue()


def cbz(path, names):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, png() if n.endswith(".png") else b"x")
    return path


def reading(state=None):
    """Where the first reader is in each volume."""
    return (state or ohara.load_state())["readers"]["1"]["progress"]


class Library(unittest.TestCase):
    """A temporary library folder for each test."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = {"MANGA": root, "STATE_DIR": root / ".ohara", "INCOMING": root / ".incoming"}
        for name, value in patches.items():
            p = mock.patch.object(ohara, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.root = root
        ohara.found_releases.clear()
        ohara.pages_cache.clear()
        ohara.page_memory.clear()
        ohara.shapes_memory.clear()
        ohara.translations.update(kept=None, failed=0)
        ohara.torrents_seen.clear()

    def tearDown(self):
        self.tmp.cleanup()


class Names(unittest.TestCase):
    def test_series_from_release_titles(self):
        cases = {
            "Naruto - T01 à T72 Intégrale + Gaiden [CBZ]  Fr": "Naruto",
            "Sousou no Frieren - Tomes 01 à 13 [CBZ/FR]": "Sousou no Frieren",
            "Berserk v42 (2025) (Digital) (LuCaZ)": "Berserk",
            "[SoM] Dragon Ball Manga Kanzenban v01-34": "Dragon Ball Manga Kanzenban",
            "One.Piece.Tome.105.FRENCH.CBZ": "One Piece",
            "Boruto - Naruto Next Generations Tomes 1 à 16 [FR] [CBZ]": "Boruto - Naruto Next Generations",
            "[Team]": "[Team]",
            "[lord_ne] Return of the Blossoming Blade (Return of the Mount Hua Sect) ch001-158 (Complete) [WEBTOON]": "Return of the Blossoming Blade",
            "[Dalte] Ashtarte S1-2 (2022) (Digital) (Tappytoon) | Ongoing": "Ashtarte",
            "[Dalte] Father, I Don't Want This Marriage (2021) (Digital) (Tappytoon) | Ongoing": "Father, I Don't Want This Marriage",
            "Solo Leveling Season 2 c045-060": "Solo Leveling",
            "Steins;Gate 0": "Steins;Gate 0",
        }
        for title, series in cases.items():
            self.assertEqual(ohara.guess_series(title), series, title)

    def test_safe_name(self):
        self.assertEqual(ohara.safe_name('a/b:c*  d. '), "a b c d")
        self.assertEqual(ohara.safe_name(" .. "), "Sans titre")

    def test_volume_label(self):
        self.assertEqual(ohara.volume_label("Naruto T05.cbz"), "Tome 5")
        self.assertEqual(ohara.volume_label("Berserk v042.cbz"), "Tome 42")
        self.assertEqual(ohara.volume_label("Frieren - Tome 12.5.cbz"), "Tome 12.5")
        self.assertEqual(ohara.volume_label("Volume 3.pdf"), "Tome 3")
        self.assertEqual(ohara.volume_label("Artbook.cbz"), "Artbook")

    def test_a_webtoons_chapters(self):
        cases = {
            "Ashtarte c001 (2022) (Digital) (Dalte).cbz": (1, "Chapitre 1", True),
            "Return of the Blossoming Blade - #012 - Episode 12.cbz": (12, "Chapitre 12", True),
            "My Life as an Internet Novel c000 (2019) (Digital) (Dalte).cbz": (0, "Chapitre 0", True),
            "Chainsaw Man ch. 12.5.cbz": (12.5, "Chapitre 12.5", True),
            "Mob Psycho 100 c045.cbz": (45, "Chapitre 45", True),
            "Naruto v01 c001.cbz": (1, "Tome 1", False),  # a tome that says its first chapter
            "Mob Psycho 100 - 045.cbz": (45, "Tome 45", False),
            "Epic 3.cbz": (3, "Tome 3", False),
        }
        for name, (number, label, chapter) in cases.items():
            self.assertEqual((ohara.volume_number(name), ohara.volume_label(name), ohara.is_chapter(name)), (number, label, chapter), name)
        for title in ("[Dalte] Ashtarte S1-2 (2022) (Digital) (Tappytoon) | Ongoing", "Return of the Blossoming Blade ch001-158"):
            self.assertIsNone(ohara.tome_range(title), title)  # neither seasons nor chapters are tomes

    def test_a_webtoons_packs(self):
        cases = {
            "[lord_ne] Return of the Blossoming Blade (Return of the Mount Hua Sect) ch001-158 (Complete) [WEBTOON]": ((1, 158), True),
            "[Dalte] Ashtarte S1-2 (2022) (Digital) (Tappytoon) | Ongoing": (None, True),
            "[Dalte] Father, I Don't Want This Marriage (2021) (Digital) (Tappytoon)": (None, True),
            "Spy x Family c045-060 (Digital)": ((45, 60), True),  # chapters in English
            "One Piece Chapitre 1100 VF": ((1100, 1100), False),  # a French chapter: a manga's
            "One Piece v105 c1050-1060": ((1050, 1060), False),  # chapters inside a tome
            "Naruto - T01 à T72 [CBZ] Fr": (None, False),
            "Season of Love v01 (Digital)": (None, False),
        }
        for title, (chapters, webtoon) in cases.items():
            self.assertEqual((ohara.chapter_range(title), ohara.webtoon_pack(title)), (chapters, webtoon), title)

    def test_language(self):
        self.assertEqual(ohara.language("Frieren [CBZ/FR]"), "FR")
        self.assertEqual(ohara.language("Naruto VF cbz"), "FR")
        self.assertEqual(ohara.language("Berserk v42 (Digital)"), "EN")
        self.assertEqual(ohara.language("Dragon Ball [PDF]"), "?")
        self.assertEqual(ohara.language("Naruto en couleurs - T01-72 CBZ"), "?")
        self.assertEqual(ohara.language("Naruto en couleurs - T01-72 CBZ", "YggReborn"), "FR")
        self.assertEqual(ohara.language("One Piece 1198 [JP]"), "JP")
        self.assertEqual(ohara.language("ONE PIECE カラー版 第001-106巻"), "JP")
        self.assertEqual(ohara.language("Naruto v01-72 [VIZ]", "YggReborn"), "EN")

    def test_natural_order(self):
        names = ["T10.cbz", "T2.cbz", "T1.cbz"]
        self.assertEqual(sorted(names, key=ohara.natural), ["T1.cbz", "T2.cbz", "T10.cbz"])

    def test_is_manga(self):
        cat = lambda *ids: [{"id": i} for i in ids]
        self.assertTrue(ohara.is_manga({"title": "Naruto Tome 1", "categories": cat(8000)}))
        self.assertTrue(ohara.is_manga({"title": "Something", "categories": cat(7030)}))
        self.assertTrue(ohara.is_manga({"title": "Frieren CBZ", "categories": []}))
        self.assertFalse(ohara.is_manga({"title": "Frieren S01E04 1080p", "categories": cat(5070)}))
        self.assertFalse(ohara.is_manga({"title": "Frieren S01E04 CBZ", "categories": []}))
        self.assertTrue(ohara.is_manga({"title": "[Dalte] Ashtarte S01 (2022) (Digital)", "categories": cat(7030)}))  # a webtoon's season
        self.assertFalse(ohara.is_manga({"title": "Naruto Tome 1", "categories": cat(2000)}))
        self.assertFalse(ohara.is_manga({"title": "Naruto", "categories": []}))
        self.assertFalse(ohara.is_manga({"title": "Kyonatix - Frieren.zip", "categories": cat(8000)}))
        self.assertFalse(ohara.is_manga({"title": "Frieren Fern Tome 1", "categories": cat(6000, 6070)}))
        self.assertFalse(ohara.is_manga({"title": "Frieren OST [FLAC]", "categories": cat(3000)}))
        self.assertTrue(ohara.is_manga({"title": "Naruto T01-72 [CBZ]", "categories": cat(8000)}))


class MoreNames(unittest.TestCase):
    def test_tome_ranges(self):
        cases = {
            "Naruto - T01 à T72 Intégrale + Gaiden [CBZ]  Fr": (1, 72),
            "Frieren T01 - T14 (scan officiel) [CBZ] Fr": (1, 14),
            "Sousou no Frieren - Tomes 01 à 13 [CBZ/FR]": (1, 13),
            "One Piece - Édition Originale - Tome 98 : Les neuf rônins": (98, 98),
            "[SoM] Dragon Ball Manga Kanzenban v01-34": (1, 34),
            "One Piece T106-114 Scan CBZ": (106, 114),
            "Frieren - Tomes 3 à 5 - Ki-oon": (3, 5),
            "Frieren - Tomes 1 et 2 - Yamada": (1, 2),
            "Boruto T17 & T18  [CBZ] Fr": (17, 18),
            "Berserk v42 (2025) (Digital)": (42, 42),
            "One Piece en couleurs - T001-104 CBZ": (1, 104),
            "Sousou no Frieren Tome 1 à Tome 13 VF": (1, 13),
            "Sousou no Frieren T01 à 6 +Ch.65 à 79 [Scantrad KSS]": (1, 6),
            "Naruto [VON] Manga Volumes 01-73 + Data Books": (1, 73),
            "Odd T09 - T03 [CBZ]": (9, 9),
            "Berserk (01-41+) (Miura)": None,
            "Naruto Intégrale [CBZ]": None,
        }
        for title, expected in cases.items():
            self.assertEqual(ohara.tome_range(title), expected, title)

    def test_norm_speed_and_numbers(self):
        self.assertEqual(ohara.norm("Shingeki no Kyojin : L'Attaque des Titans!"), "shingekinokyojinlattaquedestitans")
        self.assertEqual(ohara.norm("Élan"), "elan")
        self.assertEqual([ohara.speed(n) for n in (25, 4, 1, 0)], ["rapide", "correct", "lent", "bloqué"])
        self.assertEqual(ohara.volume_number("Naruto T05.cbz"), 5.0)
        self.assertIsNone(ohara.volume_number("ScanTrad bonus.cbz"))
        cases = {
            "[Compressé] Naruto [Team Chromatique] - Tome #001 - [V2].cbz": 1,
            "[Compressé] Naruto [Team Chromatique] - Tome #072 - [V1].cbz": 72,
            "One Piece 105 (2023).cbz": 105,
            "One Piece Tome 109 - Scan.cbz": 109,
            "Berserk Tome n°12.cbz": 12,
            "Rowling J. K - Harry Potter [Tome 1] - Harry Potter à l_école des sorciers.epub": 1,
            "Rowling J. K - Harry Potter [Tome 7] - Harry Potter et les reliques de la mort.epub": 7,
            "Les Mondes (Vol. 2) - Auteur.epub": 2,
            "1 - Eragon - Christopher Paolini.epub": 1,
            "Frieren - Vol. 3.5.cbz": 3.5,
            "Blue Lock (2018) [Digital] T07.cbz": 7,
            "20th Century Boys 05.cbz": 5,
            "Artbook (2020).cbz": None,
        }
        for name, number in cases.items():
            self.assertEqual(ohara.volume_number(name), number, name)


class Search(Library):
    RESULTS = [
        {"guid": "a", "title": "Berserk v42 (Digital)", "size": 3e8, "seeders": 100, "indexer": "Nyaa.si", "categories": [{"id": 7030}], "downloadUrl": "http://p/a"},
        {"guid": "b", "title": "Naruto T01 à T72 [CBZ] Fr", "size": 7e9, "seeders": 5, "indexer": "YggReborn", "categories": [{"id": 7000}], "magnetUrl": "magnet:?b"},
        {"guid": "c", "title": "Naruto S01E01 1080p", "categories": [{"id": 5000}]},
        {"guid": "d", "title": "Naruto - Tome 48 [CBZ] Fr", "size": 1e8, "seeders": 0, "indexer": "YggReborn", "categories": [{"id": 7000}]},
        {"guid": "e", "title": "Naruto Shippuden Tomes 1 à 3 FR", "size": 1e8, "seeders": 9, "indexer": "YggReborn", "categories": [{"id": 7000}]},
    ]
    INDEXERS = [{"id": 1, "name": "YggReborn", "enable": True}, {"id": 2, "name": "Nyaa.si", "enable": True}, {"id": 3, "name": "EZTV", "enable": True}]
    FACTS = {"Naruto": {"id": 11, "title": "Naruto"}, "Naruto Shippuden": {"id": 11, "title": "Naruto"}, "Berserk": {"id": 22}}

    def fake_prowlarr(self, calls):
        def fake(url, data=None, headers=None, timeout=60):
            calls.append(url)
            return self.INDEXERS if url.endswith("/indexer") else self.RESULTS
        return fake

    def test_find_releases_keeps_volumes(self):
        calls = []
        with mock.patch.object(ohara, "prowlarr_key", return_value="K"), mock.patch.object(ohara, "http_json", side_effect=self.fake_prowlarr(calls)):
            found = ohara.find_releases("naruto")
        self.assertIn("categories=7000&indexerIds=1&indexerIds=2", calls[1])
        self.assertNotIn("indexerIds=3", calls[1])
        self.assertEqual(len(found), 4)
        naruto = [r for r in found if r["title"].startswith("Naruto T01")][0]
        self.assertEqual((naruto["lang"], naruto["series"], naruto["range"], naruto["speed"]), ("FR", "Naruto", (1, 72), "correct"))
        self.assertEqual(ohara.found_releases[naruto["token"]]["_url"], "magnet:?b")

    def test_search_groups_by_series_best_first(self):
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
        with mock.patch.object(ohara, "prowlarr_key", return_value="K"), mock.patch.object(ohara, "http_json", side_effect=self.fake_prowlarr([])), \
                mock.patch.object(ohara, "lookup", side_effect=lambda n: self.FACTS.get(n, {})):
            groups = ohara.search("naruto")
        self.assertEqual([g["name"] for g in groups], ["Naruto", "Berserk"])
        naruto = groups[0]
        self.assertTrue(naruto["owned"])
        self.assertEqual(naruto["meta"]["id"], 11)
        self.assertEqual([r["title"][:12] for r in naruto["releases"]], ["Naruto T01 à", "Naruto Shipp", "Naruto - Tom"])
        self.assertNotIn("_url", naruto["releases"][0])
        self.assertFalse(groups[1]["owned"])

    def test_owned_name_by_anilist_id(self):
        ohara.save_state({"series": {"Naruto (VF)": {"anilist": 11}}})
        rel = [{"series": "Naruto Shippuden"}]
        self.assertEqual(ohara.owned_name(rel, {"id": 11}, {}), "Naruto (VF)")
        self.assertEqual(ohara.owned_name(rel, {"id": 99}, {}), "Naruto Shippuden")
        self.assertEqual(ohara.owned_name(rel, {}, {"narutoshippuden": "NS"}), "NS")

    def test_prowlarr_key_from_its_config(self):
        cfg = self.root / "config.xml"
        cfg.write_text("<Config><ApiKey>abc123</ApiKey></Config>")
        with mock.patch.object(ohara, "PROWLARR_CONFIG", str(cfg)):
            self.assertEqual(ohara.prowlarr_key(), "abc123")
        with mock.patch.object(ohara, "PROWLARR_KEY", "fromenv"):
            self.assertEqual(ohara.prowlarr_key(), "fromenv")


class Indexers(Library):
    FOUND = [
        {"id": 1, "name": "YggReborn", "enable": True, "capabilities": {"categories": [{"id": 7000}, {"id": 2000}]}},
        {"id": 2, "name": "EZTV", "enable": True, "capabilities": {"categories": [{"id": 5000}]}},
        {"id": 3, "name": "Nyaa.si", "enable": False, "capabilities": {"categories": [{"id": 7030}]}},
        {"id": 4, "name": "Knaben", "enable": True},
    ]

    def fake(self, url, data=None, headers=None, timeout=60):
        return [{"indexerId": 4, "disabledTill": "2999-01-01T00:00:00Z"}, {"indexerId": 1, "disabledTill": "2000-01-01T00:00:00Z"}, {"indexerId": 2}] if url.endswith("/indexerstatus") else self.FOUND

    def test_list_with_their_state(self):
        with mock.patch.object(ohara, "prowlarr_key", return_value="K"), mock.patch.object(ohara, "http_json", side_effect=self.fake):
            found = ohara.indexers()
        self.assertEqual([(i["name"], i["on"], i["failing"], i["chosen"], i["books"]) for i in found], [
            ("Knaben", True, True, True, False), ("Nyaa.si", False, False, True, True), ("YggReborn", True, False, True, True), ("EZTV", True, False, False, False)])

    def test_choice_is_kept_and_used(self):
        ohara.choose_indexers(["EZTV", 3])
        self.assertEqual(ohara.chosen_indexers(), ["EZTV"])
        with mock.patch.object(ohara, "http_json", side_effect=self.fake):
            self.assertEqual(ohara.indexer_ids("K"), [2])
        ohara.choose_indexers([])
        self.assertEqual(ohara.chosen_indexers(), ohara.INDEXERS)


class AniList(Library):
    ANSWER = {"data": {"Page": {"media": [{"id": 5, "title": {"romaji": "Sousou no Frieren", "english": None},
                                           "coverImage": {"extraLarge": None, "large": "http://c/l.jpg", "color": "#e4ae5d"},
                                           "volumes": None, "status": "RELEASING", "startDate": {"year": 2020}}]}}}

    def test_fetch(self):
        with mock.patch.object(ohara, "http_json", return_value=self.ANSWER) as call:
            meta = ohara.anilist_fetch("frieren")
        self.assertEqual(meta, {"id": 5, "title": "Sousou no Frieren", "cover": "http://c/l.jpg", "color": "#e4ae5d", "banner": None, "names": ["Sousou no Frieren"], "status": "En cours", "volumes": None, "chapters": None, "year": 2020})
        self.assertEqual(call.call_args.kwargs["headers"]["User-Agent"], "Ohara/1.0")
        with mock.patch.object(ohara, "http_json", return_value={"data": {"Page": {"media": []}}}):
            self.assertEqual(ohara.anilist_fetch("zzz"), {})

    def test_the_entry_named_like_the_series_wins(self):
        found = [{"title": {"romaji": "Nigai Kajitsu", "english": "A Bitter Fruit", "native": None}, "synonyms": ["BLUE PERIOD"]},
                 {"title": {"romaji": "Blue Period", "english": "Blue Period", "native": "ブルーピリオド"}, "synonyms": []},
                 {"title": {"romaji": "Blue Period Anthology", "english": None, "native": None}, "synonyms": None}]
        self.assertIs(ohara.best_match("Blue Period", found), found[1])
        self.assertIs(ohara.best_match("Blue Period", [found[0], found[2]]), found[0])
        self.assertIs(ohara.best_match("Blue Period Anthology", found), found[2])
        self.assertIs(ohara.best_match("Zzz", found), found[0])
        by_synonym = {"title": {"romaji": "X"}, "synonyms": ["BP"]}
        self.assertIs(ohara.best_match("B.P.", [found[0], by_synonym]), by_synonym)

    def test_lookup_is_kept(self):
        found = {"id": 5, "banner": None, "names": []}
        with mock.patch.object(ohara, "anilist_fetch", return_value=found) as fetch:
            self.assertEqual(ohara.lookup("Frieren"), found)
            self.assertEqual(ohara.lookup("frieren!"), found)
        fetch.assert_called_once()

    def test_answers_without_a_banner_are_asked_again(self):
        ohara.save_state({"lookups": {"frieren": {"id": 5}}})
        with mock.patch.object(ohara, "anilist_fetch", return_value={"id": 5, "banner": "b.jpg", "names": []}) as fetch:
            self.assertEqual(ohara.lookup("Frieren")["banner"], "b.jpg")
            ohara.lookup("Frieren")
        fetch.assert_called_once()

    def test_lookup_not_kept_when_anilist_is_down(self):
        with mock.patch.object(ohara, "anilist_fetch", side_effect=OSError):
            self.assertEqual(ohara.lookup("Frieren"), {})
        self.assertEqual(ohara.load_state()["lookups"], {})

    def test_refresh_meta_for_the_library(self):
        cbz(self.root / "Frieren" / "T1.cbz", ["1.png"])
        cbz(self.root / "Unknown" / "T1.cbz", ["1.png"])
        ohara.save_state({"downloads": {"H": {"series": "Naruto"}, "C": {"series": "Bleach"}}, "lookups": {"old": {"id": 1}, "bleach": {"id": 9, "banner": None, "names": []}},
                          "series": {"Naruto": {"anilist": None}, "Bleach": {"anilist": None}}})
        cbz(self.root / "Old" / "T1.cbz", ["1.png"])
        with mock.patch.object(ohara, "anilist_fetch", side_effect=lambda n: {"id": 5} if n == "Frieren" else {"id": 7} if n == "Naruto" else {}):
            ohara.refresh_meta()
        state = ohara.load_state()
        self.assertEqual(state["series"]["Frieren"]["anilist"], 5)
        self.assertNotIn("Unknown", state["series"])
        self.assertEqual(state["lookups"]["unknown"], {})
        self.assertEqual(state["lookups"]["naruto"], {"id": 7})
        self.assertEqual(state["series"]["Naruto"]["anilist"], 7)  # an empty id is filled
        self.assertEqual(state["series"]["Bleach"]["anilist"], 9)  # from an answer kept from before too
        self.assertEqual(state["lookups"]["old"], {})


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Transmission(Library):
    def test_rpc_takes_the_session_id_then_retries(self):
        answers = [
            urllib.error.HTTPError("u", 409, "conflict", {"X-Transmission-Session-Id": "S1"}, None),
            FakeResponse(json.dumps({"result": "success", "arguments": {"x": 1}}).encode()),
        ]
        sent = []

        def fake(req, timeout=30):
            sent.append(req.headers.get("X-transmission-session-id"))
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(ohara.rpc("session-get", {}), {"x": 1})
        self.assertEqual(sent[1], "S1")

    def test_transmission_login(self):
        self.assertNotIn("Authorization", ohara.transmission_headers())
        with mock.patch.object(ohara, "TRANSMISSION_USER", "me"), mock.patch.object(ohara, "TRANSMISSION_PASSWORD", "pw"):
            self.assertEqual(ohara.transmission_headers()["Authorization"], "Basic " + base64.b64encode(b"me:pw").decode())

    def test_rpc_errors(self):
        bad = FakeResponse(json.dumps({"result": "duplicate torrent"}).encode())
        with mock.patch("urllib.request.urlopen", return_value=bad), self.assertRaises(RuntimeError):
            ohara.rpc("torrent-add", {})
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("u", 500, "x", {}, None)), self.assertRaises(urllib.error.HTTPError):
            ohara.rpc("torrent-add", {})
        refuse = urllib.error.HTTPError("u", 409, "x", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=[refuse, refuse]), self.assertRaises(RuntimeError):
            ohara.rpc("torrent-add", {})

    def test_torrent_source(self):
        self.assertEqual(ohara.torrent_source("magnet:?xt=1"), {"filename": "magnet:?xt=1"})
        opener = mock.Mock()
        opener.open.return_value = FakeResponse(b"d4:info")
        with mock.patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(ohara.torrent_source("http://p/1"), {"metainfo": base64.b64encode(b"d4:info").decode()})
        opener.open.side_effect = ohara.MagnetFound("magnet:?xt=2")
        with mock.patch("urllib.request.build_opener", return_value=opener):
            self.assertEqual(ohara.torrent_source("http://p/2"), {"filename": "magnet:?xt=2"})

    def test_redirect_to_a_magnet_is_caught(self):
        h = ohara.KeepRedirect()
        for code in (301, 302, 303, 307, 308):
            with self.assertRaises(ohara.MagnetFound) as caught:
                getattr(h, f"http_error_{code}")(None, None, code, "", {"Location": "magnet:?xt=3"})
            self.assertEqual(str(caught.exception), "magnet:?xt=3")
        with mock.patch("urllib.request.HTTPRedirectHandler.http_error_302", return_value="next") as up:
            self.assertEqual(h.http_error_302(None, None, 302, "", {"Location": "http://p/2"}), "next")
        up.assert_called_once()

    def test_a_real_redirect_to_a_magnet(self):
        import http.server
        import threading as th

        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(301)
                self.send_header("Location", "magnet:?xt=urn:btih:abc")
                self.end_headers()

            def log_message(self, *a):
                pass
        server = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
        th.Thread(target=server.handle_request, daemon=True).start()
        self.assertEqual(ohara.torrent_source(f"http://127.0.0.1:{server.server_port}/dl"), {"filename": "magnet:?xt=urn:btih:abc"})
        server.server_close()

    def test_grab_adds_and_remembers(self):
        ohara.found_releases["t1"] = {"title": "Naruto [CBZ]", "series": "Naruto", "range": None, "_url": "magnet:?n"}
        with mock.patch.object(ohara, "rpc", return_value={"torrent-added": {"hashString": "H1"}}) as rpc, mock.patch.object(ohara, "lookup", return_value={}):
            done = ohara.grab("t1", "Naruto: Gaiden")
        self.assertEqual(done, {"series": "Naruto Gaiden", "hash": "H1"})
        args = rpc.call_args[0][1]
        self.assertEqual(args["filename"], "magnet:?n")
        self.assertTrue(args["download-dir"].startswith(ohara.TRANSMISSION_INCOMING + "/"))
        self.assertEqual(ohara.load_state()["downloads"]["H1"]["series"], "Naruto Gaiden")

    def test_grab_and_follow(self):
        ohara.found_releases["t2"] = {"title": "Frieren T01-T14", "series": "Frieren", "range": (1, 14), "_url": "magnet:?f"}
        with mock.patch.object(ohara, "rpc", return_value={"torrent-duplicate": {"hashString": "H2"}}), mock.patch.object(ohara, "lookup", return_value={"id": 5}), \
                mock.patch.object(ohara, "complete_later") as later:
            ohara.grab("t2", "", follow=True, query="frieren")
        later.assert_called_once_with("Frieren")
        state = ohara.load_state()
        self.assertEqual(state["series"]["Frieren"], {"follow": True, "query": "frieren", "anilist": 5})
        self.assertEqual(state["downloads"]["H2"]["range"], [1, 14])
        ohara.set_follow("Frieren", False)
        self.assertFalse(ohara.load_state()["series"]["Frieren"]["follow"])

    def test_a_webtoons_pack_makes_its_series_a_webtoon(self):
        ohara.found_releases["t3"] = {"title": "[Dalte] Ashtarte S1-2 (2022) (Digital) (Tappytoon)", "series": "Ashtarte", "range": None,
                                      "chapters": None, "size": 2e9, "token": "t3", "_url": "magnet:?a"}
        with mock.patch.object(ohara, "rpc", return_value={"torrent-added": {"hashString": "H3"}}), mock.patch.object(ohara, "lookup", return_value={}):
            ohara.grab("t3", "")
        entry = ohara.load_state()["series"]["Ashtarte"]
        self.assertEqual((entry["webtoon"], entry["taken"], entry["taken_size"]), (True, ["t3"], 2e9))
        ohara.save_state({"series": {"Ashtarte": {"webtoon": False}}})  # the switch said no: a pack does not say otherwise
        with mock.patch.object(ohara, "rpc", return_value={"torrent-added": {"hashString": "H4"}}), mock.patch.object(ohara, "lookup", return_value={}):
            ohara.grab("t3", "")
        self.assertFalse(ohara.load_state()["series"]["Ashtarte"]["webtoon"])

    def test_grab_unknown_token(self):
        with self.assertRaises(KeyError):
            ohara.grab("nope", "x")

    def test_cancel(self):
        ohara.save_state({"downloads": {"H1": {}}, "progress": {}})
        with mock.patch.object(ohara, "rpc") as rpc:
            ohara.cancel("H1")
        rpc.assert_called_once_with("torrent-remove", {"ids": ["H1"], "delete-local-data": True})
        self.assertEqual(ohara.load_state()["downloads"], {})

    def test_torrents(self):
        self.assertEqual(ohara.torrents([]), [])
        with mock.patch.object(ohara, "rpc", return_value={"torrents": [{"hashString": "H"}]}):
            self.assertEqual(ohara.torrents(["H"]), [{"hashString": "H"}])

    def test_safe_torrents(self):
        with mock.patch.object(ohara, "torrents", side_effect=OSError):
            self.assertEqual(ohara.safe_torrents(["H"]), [])


class Import(Library):
    def test_archives_are_moved_and_zip_becomes_cbz(self):
        src = self.root / ".incoming" / "f1"
        cbz(src / "Naruto" / "Naruto T01.cbz", ["1.png"])
        cbz(src / "Naruto" / "Naruto T02.zip", ["1.png"])
        (src / "Naruto" / "Naruto T03.pdf").write_bytes(b"%PDF")
        (src / "readme.nfo").write_text("x")
        (self.root / "Naruto").mkdir()
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
        (src / "Naruto" / "Bonus.cbz").write_bytes(b"x")
        (self.root / "Naruto" / "Bonus.cbz").write_bytes(b"x")
        self.assertEqual(ohara.import_download(src, "Naruto"), 3)
        names = sorted(p.name for p in (self.root / "Naruto").iterdir())
        self.assertEqual(names, ["Bonus (2).cbz", "Bonus.cbz", "Naruto T01.cbz", "Naruto T02.cbz", "Naruto T03.pdf"])

    def test_tomes_already_there_are_left_out(self):
        cbz(self.root / "Frieren" / "Frieren T01.cbz", ["1.png"])
        src = self.root / ".incoming" / "f9"
        for n in (1, 2):
            cbz(src / f"Frieren - Tome {n:02d}.cbz", ["1.png"])
        self.assertEqual(ohara.import_download(src, "Frieren"), 1)
        self.assertEqual(sorted(p.name for p in (self.root / "Frieren").iterdir()), ["Frieren - Tome 02.cbz", "Frieren T01.cbz"])

    def test_a_webtoons_chapters_come_in_one_by_one(self):
        cbz(self.root / "Ashtarte" / "Ashtarte c001 (2022) (Digital) (Dalte).cbz", ["1.png"])
        src = self.root / ".incoming" / "f8" / "Ashtarte (2022) (Digital) (Dalte)"
        for n in (0, 1, 2, 3):
            cbz(src / f"Ashtarte c{n:03d} (2022) (Digital) (Dalte).cbz", ["1.png"])
        self.assertEqual(ohara.import_download(src.parent, "Ashtarte"), 3)
        self.assertEqual(sorted(ohara.owned_numbers(self.root / "Ashtarte")), [0, 1, 2, 3])

    def test_cbr_is_unpacked_with_7zip(self):
        src = self.root / ".incoming" / "f2"
        src.mkdir(parents=True)
        (src / "Vol 1.cbr").write_bytes(b"rar")

        def fake_7z(cmd, check, capture_output):
            out = Path(cmd[3][2:])
            out.mkdir()
            (out / "p1.png").write_bytes(png())

        with mock.patch("subprocess.run", side_effect=fake_7z):
            self.assertEqual(ohara.import_download(src, "Berserk"), 1)
        with zipfile.ZipFile(self.root / "Berserk" / "Vol 1.cbz") as z:
            self.assertEqual(z.namelist(), ["p1.png"])

    def test_cbr_7zip_cannot_read_goes_to_bsdtar(self):
        src = self.root / ".incoming" / "f4"
        src.mkdir(parents=True)
        (src / "Vol 1.cbr").write_bytes(b"rar")
        tools = []

        def fake_run(cmd, check, capture_output):
            tools.append(cmd[0])
            if cmd[0] == "7z":
                raise subprocess.CalledProcessError(2, cmd)
            (Path(cmd[4]) / "p1.png").write_bytes(png())

        with mock.patch("subprocess.run", side_effect=fake_run):
            self.assertEqual(ohara.import_download(src, "Berserk"), 1)
        self.assertEqual(tools, ["7z", "bsdtar"])
        with zipfile.ZipFile(self.root / "Berserk" / "Vol 1.cbz") as z:
            self.assertEqual(z.namelist(), ["p1.png"])

    def test_plain_images_become_one_volume_per_folder(self):
        src = self.root / ".incoming" / "f3"
        for folder in ("Tome 2", "Tome 1"):
            (src / folder).mkdir(parents=True)
            for n in (10, 2, 1):
                (src / folder / f"{n}.jpg").write_bytes(b"j")
        self.assertEqual(ohara.import_download(src, "Frieren"), 2)
        with zipfile.ZipFile(self.root / "Frieren" / "Tome 1.cbz") as z:
            self.assertEqual(z.namelist(), ["1.jpg", "2.jpg", "10.jpg"])
        self.assertEqual(sorted(p.name for p in (self.root / "Frieren").iterdir()), ["Tome 1.cbz", "Tome 2.cbz"])  # no part left

    def test_a_volume_cut_short_is_not_taken_for_a_whole_one(self):
        src = self.root / ".incoming" / "f4" / "Tome 1"
        src.mkdir(parents=True)
        (src / "1.jpg").write_bytes(b"j")
        with mock.patch.object(ohara.zipfile.ZipFile, "write", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            ohara.zip_folder(src, self.root / "Tome 1.cbz")
        self.assertFalse((self.root / "Tome 1.cbz").exists())
        self.assertNotIn(1, ohara.owned_numbers(self.root))

    def test_images_at_the_top(self):
        src = self.root / ".incoming" / "Oneshot"
        src.mkdir(parents=True)
        (src / "1.jpg").write_bytes(b"j")
        self.assertEqual(ohara.import_download(src, "Oneshot"), 1)
        self.assertTrue((self.root / "Oneshot" / "Oneshot.cbz").exists())

    def test_check_downloads_files_the_finished_ones(self):
        ohara.save_state({"downloads": {"H1": {"series": "Naruto", "title": "t", "folder": "f1"}, "H2": {"series": "X", "title": "t", "folder": "f2"}}, "progress": {}})
        cbz(self.root / ".incoming" / "f1" / "T1.cbz", ["1.png"])
        live = [{"hashString": "H1", "percentDone": 1}, {"hashString": "H2", "percentDone": 0.4}, {"hashString": "H9", "percentDone": 1}]
        with mock.patch.object(ohara, "torrents", return_value=live), mock.patch.object(ohara, "rpc") as rpc:
            ohara.check_downloads()
        rpc.assert_called_once_with("torrent-remove", {"ids": ["H1"], "delete-local-data": True})
        self.assertTrue((self.root / "Naruto" / "T1.cbz").exists())
        self.assertFalse((self.root / ".incoming" / "f1").exists())
        self.assertEqual(list(ohara.load_state()["downloads"]), ["H2"])

    def test_check_downloads_small_first_and_one_failure_holds_nothing_back(self):
        ohara.save_state({"downloads": {"BIG": {"series": "One Piece", "title": "pack", "folder": "big"},
                                        "BAD": {"series": "X", "title": "bad", "folder": "bad"},
                                        "SMALL": {"series": "Jujutsu Kaisen", "title": "t", "folder": "small"}}, "progress": {}})
        live = [{"hashString": "BIG", "percentDone": 1, "totalSize": 900},
                {"hashString": "BAD", "percentDone": 1, "totalSize": 5},
                {"hashString": "SMALL", "percentDone": 1, "totalSize": 10}]
        filed = []

        def fake_import(source, series):
            if source.name == "bad":
                raise OSError("unreadable")
            filed.append(source.name)

        with mock.patch.object(ohara, "torrents", return_value=live), mock.patch.object(ohara, "rpc"), \
                mock.patch.object(ohara, "import_download", side_effect=fake_import):
            ohara.check_downloads()
        self.assertEqual(filed, ["small", "big"])
        self.assertEqual(list(ohara.load_state()["downloads"]), ["BAD"])

    def test_watch_survives_errors(self):
        with mock.patch.object(ohara, "check_downloads", side_effect=OSError("down")), \
                mock.patch.object(ohara.time, "sleep", side_effect=StopIteration), self.assertRaises(StopIteration):
            ohara.watch()


class Reading(Library):
    def setUp(self):
        super().setUp()
        cbz(self.root / "Naruto" / "Naruto T02.cbz", ["b/10.png", "b/2.png", "__MACOSX/._2.png", "b/.hidden.png", "notes.txt"])
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png", "2.png"])
        (self.root / "Naruto" / "Naruto T03.pdf").write_bytes(b"%PDF")
        cbz(self.root / "Naruto" / "Naruto T04.cbz", ["1.png"])
        (self.root / "Empty").mkdir()
        (self.root / ".ohara").mkdir(exist_ok=True)

    def test_pages_in_reading_order(self):
        self.assertEqual(ohara.pages(self.root / "Naruto" / "Naruto T02.cbz"), ["b/2.png", "b/10.png"])
        data, name = ohara.page_bytes(self.root / "Naruto" / "Naruto T02.cbz", 1)
        self.assertEqual(name, "b/10.png")
        self.assertTrue(data.startswith(b"\x89PNG"))

    def test_volume_path_stays_in_the_library(self):
        self.assertEqual(ohara.volume_path("Naruto/Naruto T01.cbz").name, "Naruto T01.cbz")
        for bad in ("../etc/passwd", "Naruto", ".ohara/state.json", "Naruto/none.cbz"):
            with self.assertRaises(KeyError):
                ohara.volume_path(bad)

    def test_library_and_progress(self):
        ohara.save_progress("Naruto/Naruto T01.cbz", 1, 2)
        ohara.save_progress("Naruto/Naruto T02.cbz", 0, 2)
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            lib = ohara.library()
        self.assertEqual([s["name"] for s in lib["series"]], ["Naruto"])
        vols = lib["series"][0]["volumes"]
        self.assertEqual([v["label"] for v in vols], ["Tome 1", "Tome 2", "Tome 3", "Tome 4"])
        self.assertEqual([v["done"] for v in vols], [True, False, False, False])
        self.assertFalse(vols[2]["readable"])
        self.assertEqual(lib["series"][0]["read"], 1)
        self.assertEqual(lib["last"]["id"], "Naruto/Naruto T02.cbz")
        self.assertEqual(lib["last"]["series"], "Naruto")

    def test_downloads_in_the_library(self):
        ohara.save_state({"downloads": {"H1": {"series": "A", "title": "a"}, "H2": {"series": "B", "title": "b"}, "H3": {"series": "C", "title": "c"}, "H4": {"series": "D", "title": "d"}}, "progress": {}})
        live = [
            {"hashString": "H1", "percentDone": 0.5, "eta": 60},
            {"hashString": "H2", "percentDone": 1},
            {"hashString": "H3", "percentDone": 0.1, "error": 3, "errorString": "no space"},
        ]
        with mock.patch.object(ohara, "safe_torrents", return_value=live):
            d = {x["hash"]: x for x in ohara.library()["downloads"]}
        self.assertEqual((d["H1"]["pct"], d["H1"]["state"], d["H1"]["eta"]), (50, "downloading", 60))
        self.assertEqual(d["H2"]["state"], "done")
        self.assertEqual((d["H3"]["state"], d["H3"]["error"]), ("error", "no space"))
        self.assertEqual(d["H4"]["state"], "unknown")
        self.assertIsNone(d["H1"]["cover"])

    def test_marking_read_and_unread(self):
        ohara.save_progress("Naruto/Naruto T02.cbz", 0, 2)
        before = reading()["Naruto/Naruto T02.cbz"]["at"]
        ohara.mark_read(["Naruto/Naruto T01.cbz", "Naruto/Naruto T02.cbz", "Naruto/Naruto T03.pdf"], True)
        progress = reading()
        self.assertEqual(progress["Naruto/Naruto T01.cbz"], {"page": 1, "pages": 2, "at": 0})
        self.assertEqual(progress["Naruto/Naruto T02.cbz"]["at"], before)
        self.assertEqual(progress["Naruto/Naruto T03.pdf"], {"page": 0, "pages": 1, "at": 0})
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            lib = ohara.library()
        self.assertEqual([v["done"] for v in lib["series"][0]["volumes"]], [True, True, True, False])
        self.assertEqual(lib["last"]["id"], "Naruto/Naruto T02.cbz")
        ohara.mark_read(["Naruto/Naruto T01.cbz"], False)
        self.assertNotIn("Naruto/Naruto T01.cbz", reading())
        with self.assertRaises(KeyError):
            ohara.mark_read(["../x"], True)

    def test_the_back_of_a_series_bays(self):
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            naruto = ohara.library()["series"][0]
        self.assertEqual((naruto["decor"], naruto["kept"]), ("banner", None))
        for decor in ("cover", "none", "vol:Naruto/Naruto T02.cbz", "banner"):
            ohara.set_decor("Naruto", decor)
            self.assertEqual(ohara.load_state()["series"]["Naruto"]["decor"], decor)
        for wrong in ("vol:Naruto/nope.cbz", "vol:../x", "vol:Other/Naruto T02.cbz", "own:1", "url:javascript:x", "url:https://a b", "gold"):
            with self.assertRaises(KeyError):
                ohara.set_decor("Naruto", wrong)
        self.assertEqual(ohara.load_state()["series"]["Naruto"]["decor"], "banner")

    def test_an_image_of_its_own_on_the_back_of_the_bays(self):
        from PIL import Image
        png = io.BytesIO()
        Image.new("RGB", (3000, 1000), "red").save(png, "PNG")
        answer = mock.MagicMock()
        answer.__enter__.return_value.read.return_value = png.getvalue()
        with mock.patch.object(ohara.urllib.request, "urlopen", return_value=answer) as get:
            done = ohara.set_decor("Naruto", "url:https://example.org/wall.png")
        self.assertEqual(get.call_args[0][0].full_url, "https://example.org/wall.png")
        kept = ohara.decor_kept("Naruto")
        self.assertEqual(done["decor"], f"own:{kept}")
        self.assertEqual(Image.open(ohara.decor_file("Naruto")).size, (1600, 533))
        ohara.set_decor("Naruto", "none")
        ohara.set_decor("Naruto", done["decor"])
        self.assertEqual(ohara.load_state()["series"]["Naruto"]["decor"], done["decor"])
        with self.assertRaises(ValueError):
            ohara.keep_decor("Naruto", b"not an image")
        with self.assertRaises(KeyError):
            ohara.keep_decor("Nobody", png.getvalue())
        answer.__enter__.return_value.read.return_value = b"x" * (ohara.DECOR_MAX + 1)
        with mock.patch.object(ohara.urllib.request, "urlopen", return_value=answer), self.assertRaises(ValueError):
            ohara.fetch_decor("Naruto", "https://example.org/huge.png")

    def test_volume_pages_and_next_readable(self):
        ohara.save_progress("Naruto/Naruto T02.cbz", 1, 2)
        info = ohara.volume_pages("Naruto/Naruto T02.cbz")
        self.assertEqual(info, {"id": "Naruto/Naruto T02.cbz", "series": "Naruto", "label": "Tome 2", "number": 2.0, "chapter": False, "rtl": True, "count": 2, "wide": None, "page": 1, "next": "Naruto/Naruto T04.cbz"})
        self.assertIsNone(ohara.volume_pages("Naruto/Naruto T04.cbz")["next"])

    def test_the_size_of_a_page_from_its_first_bytes(self):
        from PIL import Image

        def made(fmt, size=(300, 200), **kw):
            b = io.BytesIO()
            Image.new("RGB", size, "red").save(b, fmt, **kw)
            return b.getvalue()
        exif = Image.Exif()
        exif[0x010E] = "x" * 3000  # a long description before the frame
        cases = {"lossy WebP": made("WEBP"), "lossless WebP": made("WEBP", lossless=True), "extended WebP": made("WEBP", exif=exif.tobytes()),
                 "PNG": made("PNG"), "JPEG": made("JPEG", exif=exif.tobytes()), "progressive JPEG": made("JPEG", progressive=True)}
        for name, data in cases.items():
            with self.subTest(name):
                self.assertEqual(ohara.image_size(data[:ohara.HEAD]), (300, 200))
        for data in (b"x", b"", made("WEBP")[:20], made("JPEG", exif=exif.tobytes())[:200], made("GIF"), b"RIFF\0\0\0\0WEBPVP8Z" + b"\0" * 20):
            self.assertIsNone(ohara.image_size(data))

    def test_the_wide_pages_are_found_once_and_kept(self):
        from PIL import Image
        path = self.root / "Manga" / "Manga T01.cbz"
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as z:
            for name, size in (("1.webp", (200, 300)), ("2.webp", (600, 300)), ("3.jpg", (200, 300)), ("4.txt", None)):
                b = io.BytesIO()
                if size:
                    Image.new("RGB", size, "red").save(b, "JPEG" if name.endswith("jpg") else "WEBP")
                z.writestr(name, b.getvalue())
            z.writestr("5.png", b"broken")
        self.assertIsNone(ohara.known_wide(path))
        self.assertEqual(ohara.wide_pages(path), [1])
        ohara.shapes_memory.clear()
        with mock.patch.object(ohara.zipfile, "ZipFile", side_effect=AssertionError("not again")):
            self.assertEqual(ohara.wide_pages(path), [1])  # from the disk
        os.utime(path, (1, 1))
        self.assertIsNone(ohara.known_wide(path))  # the file changed: found again
        ohara.shapes_file(path).write_text("{")
        self.assertIsNone(ohara.known_wide(path))

    def test_pages_the_size_of_a_screen(self):
        from PIL import Image
        self.assertEqual([ohara.page_width(w) for w in (None, "", "x", -3, 700, 1200, 1201, 2400, 3000)], [0, 0, 0, 0, 800, 1200, 1600, 2400, 0])
        path = self.root / "Manga" / "Manga T01.cbz"
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as z:
            for name, size, colour in (("1.jpg", (3000, 2000), (128, 130, 126)), ("2.png", (900, 1300), "red"), ("3.jpg", (2000, 3000), (200, 40, 40))):
                b = io.BytesIO()
                Image.new("RGB", size, colour).save(b, "JPEG" if name.endswith("jpg") else "PNG")
                z.writestr(name, b.getvalue())
        made = ohara.size_page(path, 0, 1200)
        img = Image.open(io.BytesIO(made))
        self.assertEqual((img.format, img.size), ("WEBP", (1200, 800)))
        self.assertEqual((ohara.sized_dir(path, 1200) / "0.webp").read_bytes(), made)
        r, g, b = img.convert("RGB").getpixel((600, 400))
        self.assertTrue(r == g == b)  # grey, its stray colour gone
        small = Image.open(io.BytesIO(ohara.size_page(path, 1, 1200)))  # narrower: only in WebP
        self.assertEqual((small.size, small.mode), ((900, 1300), "RGB"))
        r, g, b = Image.open(io.BytesIO(ohara.size_page(path, 2, 800))).convert("RGB").getpixel((5, 5))
        self.assertGreater(r - g, 100)  # a page in colour keeps it
        self.assertTrue(ohara.franky.looks_grey(Image.new("1", (4, 4))))
        with mock.patch.object(ohara, "page_bytes", side_effect=AssertionError("not again")):
            self.assertEqual(ohara.size_page(path, 0, 1200), made)  # from memory
            ohara.page_memory.clear()
            self.assertEqual(ohara.size_page(path, 0, 1200), made)  # from the disk
        self.assertIs(ohara.page_lock("a"), ohara.page_lock("a"))

    def test_the_pages_used_longest_ago_leave_memory(self):
        ohara.page_memory.clear()
        ohara.torrents_seen.clear()
        with mock.patch.object(ohara, "PAGES_RAM", 10):
            ohara.remember("a", b"1234")
            ohara.remember("b", b"1234")
            self.assertEqual(ohara.remembered("a"), b"1234")  # a used again
            ohara.remember("c", b"1234")
        self.assertEqual(list(ohara.page_memory), ["a", "c"])
        self.assertIsNone(ohara.remembered("b"))
        ohara.page_memory.clear()
        ohara.torrents_seen.clear()

    def test_a_volume_is_made_ahead_from_the_page_read(self):
        path = self.root / "Naruto" / "Naruto T01.cbz"
        done = []
        with mock.patch.object(ohara, "size_page", side_effect=lambda p, n, w: done.append(n)), \
                mock.patch.object(ohara.threading, "Thread") as thread:
            ohara.warm(path, 800, 1)
            run = thread.call_args.kwargs["target"]
            run()
            self.assertEqual(done, [1, 0])
            ohara.warm(path, 800, 0)  # another volume opened: the first stops
            done.clear()
            run()
            self.assertEqual(done, [])
        self.assertTrue(ohara.sized_dir(path, 800).is_dir())
        with mock.patch.object(ohara, "size_page", side_effect=OSError("bad page")), mock.patch.object(ohara.threading, "Thread") as thread:
            ohara.warm(path, 800, 0)
            thread.call_args.kwargs["target"]()  # says so and stops

    def test_only_the_volumes_read_last_keep_their_pages(self):
        ohara.trim_pages()
        root = ohara.STATE_DIR / "pages"
        for i in range(4):
            (root / f"v{i}").mkdir(parents=True)
            os.utime(root / f"v{i}", (i, i))
        ohara.trim_pages(keep=2)
        self.assertEqual(sorted(f.name for f in root.iterdir()), ["v2", "v3"])

    def test_cover_is_made_once(self):
        path = self.root / "Naruto" / "Naruto T01.cbz"
        first = ohara.cover(path)
        self.assertTrue(first.startswith(b"\xff\xd8"))
        with mock.patch.object(ohara, "page_bytes", side_effect=AssertionError("not again")):
            self.assertEqual(ohara.cover(path), first)

    def test_status_for_the_home_card(self):
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            s = ohara.status()
        self.assertEqual((s["series"], s["volumes"], s["new"], s["downloads"], s["last"]), (1, 4, 4, [], None))

    def test_broken_state_file(self):
        (self.root / ".ohara" / "state.json").write_text("{")
        self.assertEqual(ohara.load_state(), {"downloads": {}, "series": {}, "lookups": {}, "settings": {}, "spines": {}, "music": {}, "moods": {}, "franky": {}, "chapters": {}, "dismissed": {},
                                             "readers": {"1": {"name": "", "progress": {}}}})


class Http(Reading):
    def call(self, method, path, body=None, cookie=None):
        h = ohara.Handler.__new__(ohara.Handler)
        h.path, h.command, h.request_version, h.requestline = path, method, "HTTP/1.1", ""
        raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b""
        h.headers = {"Content-Length": str(len(raw)), **({"Cookie": cookie} if cookie else {})}
        h.rfile, h.wfile = io.BytesIO(raw), io.BytesIO()
        h.client_address = ("10.0.0.2", 5000)
        h.server = mock.Mock()
        h.close_connection = True
        getattr(h, "do_" + method)()
        head, _, payload = h.wfile.getvalue().partition(b"\r\n\r\n")
        return int(head.split()[1]), head.decode(), payload

    def call_range(self, path, rng):
        h = ohara.Handler.__new__(ohara.Handler)
        h.path, h.command, h.request_version, h.requestline = path, "GET", "HTTP/1.1", ""
        h.headers = {"Content-Length": "0", "Range": rng}
        h.rfile, h.wfile = io.BytesIO(b""), io.BytesIO()
        h.client_address = ("10.0.0.2", 5000)
        h.server = mock.Mock()
        h.close_connection = True
        h.do_GET()
        head, _, payload = h.wfile.getvalue().partition(b"\r\n\r\n")
        return int(head.split()[1]), head.decode(), payload

    def test_music_routes(self):
        with mock.patch.object(ohara, "music", return_value={"albums": []}) as music:
            self.assertEqual(json.loads(self.call("GET", "/api/music?series=N&lang=en")[2]), {"albums": []})
        music.assert_called_once_with("N", "en")
        with mock.patch.object(ohara, "find_soundtracks", return_value=[{"token": "t", "_url": "x"}]):
            self.assertEqual(json.loads(self.call("GET", "/api/soundtracks?series=N")[2]), [{"token": "t"}])
        with mock.patch.object(ohara, "grab_music", return_value={"state": "downloading"}) as grab:
            self.assertEqual(self.call("POST", "/api/music", {"series": "N"})[0], 200)
        grab.assert_called_once_with("N", None)
        with mock.patch.object(ohara, "set_mood", return_value={"moods": []}) as mood:
            self.call("POST", "/api/mood", {"series": "N", "name": "Calme", "tracks": ["a"], "lang": "fr"})
        mood.assert_called_once_with("N", "Calme", ["a"], "fr")

    def test_pages_api(self):
        code, _, body = self.call("GET", "/api/pages?vol=Naruto%2FNaruto%20T01.cbz")
        self.assertEqual((code, json.loads(body)["count"]), (200, 2))
        self.assertEqual(json.loads(self.call("GET", "/api/wide?vol=Naruto/Naruto%20T01.cbz")[2]), {"wide": []})
        self.assertEqual(json.loads(self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz")[2])["wide"], [])
        code, head, body = self.call("GET", "/api/page?vol=Naruto/Naruto%20T01.cbz&n=1")
        self.assertEqual(code, 200)
        self.assertIn("image/png", head)
        self.assertEqual(self.call("GET", "/api/page?vol=../x&n=0")[0], 404)

    def test_cover_and_file(self):
        code, head, _ = self.call("GET", "/api/cover?vol=Naruto/Naruto%20T01.cbz")
        self.assertIn("image/jpeg", head)
        code, head, body = self.call("GET", "/api/file?vol=Naruto/Naruto%20T03.pdf")
        self.assertEqual((code, body), (200, b"%PDF"))
        self.assertIn("application/pdf", head)

    def test_library_status_and_progress(self):
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            self.assertEqual(self.call("GET", "/api/library")[0], 200)
            code, head, _ = self.call("GET", "/api/status.json")
        self.assertIn("Access-Control-Allow-Origin: *", head)
        self.assertEqual(self.call("POST", "/api/progress", {"vol": "Naruto/Naruto T01.cbz", "page": 1, "count": 2})[0], 200)
        self.assertEqual(reading()["Naruto/Naruto T01.cbz"]["page"], 1)

    def test_search_grab_cancel(self):
        with mock.patch.object(ohara, "search", return_value=[{"token": "t"}]) as search:
            self.assertEqual(json.loads(self.call("GET", "/api/search?q=naruto")[2]), [{"token": "t"}])
            self.assertEqual(json.loads(self.call("GET", "/api/search?q=")[2]), [])
        search.assert_called_once_with("naruto")
        with mock.patch.object(ohara, "grab", return_value={"series": "N", "hash": "H"}):
            self.assertEqual(json.loads(self.call("POST", "/api/grab", {"token": "t", "series": "N"})[2])["hash"], "H")
        with mock.patch.object(ohara, "complete", return_value={"sent": [], "nowhere": [3]}):
            self.assertEqual(json.loads(self.call("POST", "/api/complete", {"series": "N"})[2])["nowhere"], [3])
        with mock.patch.object(ohara, "set_follow") as follow:
            self.assertEqual(self.call("POST", "/api/follow", {"series": "N", "follow": True})[0], 200)
        follow.assert_called_once_with("N", True)
        with mock.patch.object(ohara, "indexers", return_value=[{"name": "X"}]) as listed, mock.patch.object(ohara, "choose_indexers") as choose:
            self.assertEqual(json.loads(self.call("GET", "/api/indexers")[2]), [{"name": "X"}])
            self.assertEqual(self.call("POST", "/api/indexers", {"indexers": ["X"]})[0], 200)
        choose.assert_called_once_with(["X"])
        lighter = {"done": 0, "total": 3, "saved": 0}
        self.assertEqual(json.loads(self.call("GET", "/api/settings")[2]), {"spines": "tome", "brook": True, "franky": False, "ribbon": True, "discord": False, "lighter": lighter})
        self.assertEqual(json.loads(self.call("POST", "/api/settings", {"spines": "sobre", "brook": False, "franky": False, "ribbon": False})[2]),
                         {"spines": "sobre", "brook": False, "franky": False, "ribbon": False, "discord": False, "lighter": lighter})
        self.assertEqual(self.call("GET", "/api/crop?vol=Naruto/Naruto%20T01.cbz")[0], 404)
        ohara.read_spine(self.root / "Naruto" / "Naruto T01.cbz")
        with mock.patch.object(ohara, "warm") as warm:
            code, _, payload = self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz&w=1000")
        self.assertEqual((code, json.loads(payload)["count"]), (200, 2))
        warm.assert_called_once_with((self.root / "Naruto" / "Naruto T01.cbz").resolve(), 1200, 0)
        with mock.patch.object(ohara, "warm") as warm:
            self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz")
        warm.assert_not_called()
        with mock.patch.object(ohara, "size_page", return_value=b"SMALL"):
            code, head, payload = self.call("GET", "/api/page?vol=Naruto/Naruto%20T01.cbz&n=0&w=800")
        self.assertEqual((code, payload), (200, b"SMALL"))
        self.assertIn("image/webp", head)
        code, head, payload = self.call("GET", "/api/page?vol=Naruto/Naruto%20T01.cbz&n=0")  # as it is
        self.assertIn("image/png", head)
        self.assertIn("HTTP/1.1 200", head)
        code, head, _ = self.call("GET", "/api/nothing-here")
        self.assertEqual(code, 404)
        self.assertIn("Connection: close", head)
        code, head, _ = self.call("GET", "/api/crop?vol=Naruto/Naruto%20T01.cbz")
        self.assertEqual(code, 200)
        self.assertIn("image/jpeg", head)
        with mock.patch.object(ohara, "mark_read", return_value={"ok": True}) as mark:
            self.assertEqual(self.call("POST", "/api/read", {"vols": ["a", 3], "read": 1})[0], 200)
        mark.assert_called_once_with(["a"], True, None)
        with mock.patch.object(ohara, "set_decor", return_value={"ok": True}) as decor:
            self.assertEqual(self.call("POST", "/api/decor", {"series": "Naruto", "decor": "none"})[0], 200)
        decor.assert_called_once_with("Naruto", "none")
        with mock.patch.object(ohara, "keep_decor", return_value={"ok": True}) as keep:
            self.assertEqual(self.call("POST", "/api/decor/image?series=Naruto", b"IMG")[0], 200)
        keep.assert_called_once_with("Naruto", b"IMG")
        with mock.patch.object(ohara, "DECOR_MAX", 2):
            self.assertEqual(self.call("POST", "/api/decor/image?series=Naruto", b"IMG")[0], 502)
        self.assertEqual(self.call("GET", "/api/decor?series=Naruto")[0], 404)
        ohara.decor_file("Naruto").parent.mkdir(parents=True, exist_ok=True)
        ohara.decor_file("Naruto").write_bytes(b"JPG")
        code, head, payload = self.call("GET", "/api/decor?series=Naruto")
        self.assertEqual((code, payload), (200, b"JPG"))
        self.assertIn("image/jpeg", head)
        with mock.patch.object(ohara, "cancel") as cancel:
            self.assertEqual(self.call("POST", "/api/cancel", {"hash": "H"})[0], 200)
        cancel.assert_called_once_with("H")  # unknown to Ohara: only cancelled
        ohara.save_state({"downloads": {"P": {"series": "N", "title": "N T01-T09", "folder": "p"}, "O": {"series": "N", "title": "OST", "folder": "o", "kind": "ost"}}})
        with mock.patch.object(ohara, "rpc"):
            self.call("POST", "/api/cancel", {"hash": "P"})
            self.call("POST", "/api/cancel", {"hash": "O"})
        state = ohara.load_state()
        self.assertEqual((state["downloads"], state["series"]["N"]["skipped"], state["music"]["N"]["skipped"]), ({}, ["N T01-T09"], ["OST"]))
        ohara.save_state({"downloads": {"Q": {"series": "N", "title": "N T01-T09 bis", "folder": "q"}}})
        with mock.patch.object(ohara, "rpc"), mock.patch.object(ohara, "complete", return_value={"sent": [], "nowhere": [3]}) as complete:
            code, _, payload = self.call("POST", "/api/another", {"hash": "Q"})
        self.assertEqual((code, json.loads(payload)), (200, {"sent": [], "nowhere": [3]}))
        complete.assert_called_once_with("N")

    def test_errors_become_json(self):
        with mock.patch.object(ohara, "search", side_effect=OSError("prowlarr down")):
            code, _, body = self.call("GET", "/api/search?q=x")
        self.assertEqual((code, json.loads(body)["error"]), (502, "prowlarr down"))

    def test_static_pages(self):
        code, head, body = self.call("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"Ohara", body)
        self.assertIn("text/html", head)
        self.assertEqual(self.call("GET", "/read")[0], 200)
        self.assertIn("text/javascript", self.call("GET", "/reader.js")[1])
        self.assertEqual(self.call("GET", "/../ohara.py")[0], 404)
        self.assertEqual(self.call("GET", "/nothing.css")[0], 404)

    def test_log_is_quiet(self):
        ohara.Handler.log_message(None, "x")


class Readers(Library):
    """Each reader their own reading, the volumes shared."""
    call = Http.call

    def setUp(self):
        super().setUp()
        for name, files in [("Naruto T01.cbz", ["1.png", "2.png"]), ("Naruto T02.cbz", ["1.png", "2.png"]), ("Naruto T04.cbz", ["1.png"])]:
            cbz(self.root / "Naruto" / name, files)
        (self.root / "Naruto" / "Naruto T03.pdf").write_bytes(b"%PDF")

    def test_the_reading_kept_before_readers_is_the_first_ones(self):
        ohara.save_state({"progress": {"Naruto/Naruto T01.cbz": {"page": 1, "pages": 2, "at": 5}}})
        state = ohara.load_state()
        self.assertNotIn("progress", state)
        self.assertEqual(ohara.readers(state), {"readers": [{"id": "1", "name": ""}], "reader": "1"})
        self.assertEqual(reading(state), {"Naruto/Naruto T01.cbz": {"page": 1, "pages": 2, "at": 5}})

    def test_a_lone_reader_is_never_asked_who_reads(self):
        self.assertEqual(self.call("POST", "/api/progress", {"vol": "Naruto/Naruto T01.cbz", "page": 1, "count": 2}, cookie="ohara-reader=gone")[0], 200)
        self.assertEqual(reading()["Naruto/Naruto T01.cbz"]["page"], 1)

    def test_two_readers_read_apart(self):
        ohara.save_progress("Naruto/Naruto T01.cbz", 1, 2)
        robin = ohara.add_reader("  Nico   Robin ")
        self.assertEqual(robin["readers"][1]["name"], "Nico Robin")
        rid = robin["reader"]
        me, her = "ohara-reader=1", f"ohara-reader={rid}"
        self.call("POST", "/api/progress", {"vol": "Naruto/Naruto T02.cbz", "page": 0, "count": 2}, cookie=her)
        self.call("POST", "/api/read", {"vols": ["Naruto/Naruto T04.cbz"], "read": True}, cookie=her)
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            mine = json.loads(self.call("GET", "/api/library", cookie=me)[2])
            hers = json.loads(self.call("GET", "/api/library", cookie=her)[2])
            nobody = json.loads(self.call("GET", "/api/library")[2])
        done = lambda lib: [v["done"] for v in lib["series"][0]["volumes"]]
        self.assertEqual((done(mine), mine["last"]["id"], mine["reader"]), ([True, False, False, False], "Naruto/Naruto T01.cbz", "1"))
        self.assertEqual((done(hers), hers["last"]["id"], hers["reader"]), ([False, False, False, True], "Naruto/Naruto T02.cbz", rid))
        self.assertEqual((done(nobody), nobody["last"], nobody["reader"]), ([False] * 4, None, None))
        self.assertEqual(json.loads(self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz", cookie=me)[2])["page"], 1)
        self.assertEqual(json.loads(self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz", cookie=her)[2])["page"], 0)

    def test_who_reads_is_asked_among_several(self):
        ohara.add_reader("Robin")
        for method, path, body in [("POST", "/api/progress", {"vol": "Naruto/Naruto T01.cbz", "page": 1, "count": 2}),
                                   ("POST", "/api/read", {"vols": ["Naruto/Naruto T01.cbz"], "read": True}),
                                   ("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz", None)]:
            code, _, payload = self.call(method, path, body, cookie="ohara-reader=gone; other=1")
            self.assertEqual((code, json.loads(payload)), (401, {"error": "reader"}))
        self.assertEqual(reading(), {})
        self.assertEqual(json.loads(self.call("GET", "/api/readers", cookie='ohara-reader="bad')[2])["reader"], None)

    def test_renaming_and_forgetting_a_reader(self):
        rid = json.loads(self.call("POST", "/api/readers", {"name": "Robin"})[2])["reader"]
        self.call("POST", "/api/progress", {"vol": "Naruto/Naruto T01.cbz", "page": 1, "count": 2}, cookie=f"ohara-reader={rid}")
        renamed = json.loads(self.call("POST", "/api/readers", {"id": "1", "name": "Luffy"}, cookie=f"ohara-reader={rid}")[2])
        self.assertEqual(([r["name"] for r in renamed["readers"]], renamed["reader"]), (["Luffy", "Robin"], rid))
        self.assertEqual(self.call("POST", "/api/readers", {"name": " "})[0], 502)
        self.assertEqual(self.call("POST", "/api/readers", {"id": "nobody", "name": "X"})[0], 404)
        ohara.rename_volume("Naruto/Naruto T01.cbz", "Naruto T01 bis.cbz")
        self.assertEqual(list(ohara.load_state()["readers"][rid]["progress"]), ["Naruto/Naruto T01 bis.cbz"])
        left = json.loads(self.call("POST", "/api/readers", {"id": "1", "forget": True})[2])
        self.assertEqual(left, {"readers": [{"id": rid, "name": "Robin"}], "reader": rid})
        self.assertEqual(self.call("POST", "/api/readers", {"id": rid, "forget": True})[0], 404)  # the last one stays

    def test_franky_leaves_a_volume_anyone_is_reading(self):
        rid = ohara.add_reader("Robin")["reader"]
        ohara.save_progress("Naruto/Naruto T01.cbz", 0, 2, rid)
        state = ohara.load_state()
        self.assertGreater(ohara.last_opened(state, "Naruto/Naruto T01.cbz"), 0)
        self.assertEqual(ohara.last_opened(state, "Naruto/Naruto T02.cbz"), 0)
        self.assertEqual(ohara.franky_next(state).name, "Naruto T02.cbz")


class Follow(Library):
    def rel(self, title, seeders=5, lang="FR", size=1e9):
        return {"title": title, "series": ohara.guess_series(title), "range": ohara.tome_range(title), "lang": lang, "seeders": seeders, "size": size, "token": title}

    def test_plan_fills_every_missing_tome(self):
        for n in (3, 4):
            cbz(self.root / "Frieren" / f"T{n:02d}.cbz", ["1.png"])
        state = {"downloads": {"H": {"series": "Frieren", "range": [5, 5]}, "X": {"series": "Other", "range": [1, 9]}, "Y": {"series": "Frieren"}}}
        releases = [
            self.rel("Frieren T01 - T02 FR", seeders=3),
            self.rel("Frieren T06 - T14 FR", seeders=50),
            self.rel("Frieren T01 à T14 FR", seeders=20),
            self.rel("Frieren T15 FR", seeders=0),
            self.rel("Frieren T15 - T16 eng", lang="EN"),
            self.rel("Frieren Artbook FR"),
        ]
        picks, nowhere = ohara.plan("Frieren", releases, state)
        self.assertEqual([r["title"] for r in picks], ["Frieren T01 à T14 FR"])
        self.assertEqual(nowhere, [15])
        picks, nowhere = ohara.plan("Frieren", releases[:2], state, total=16)
        self.assertEqual([r["title"] for r in picks], ["Frieren T06 - T14 FR", "Frieren T01 - T02 FR"])
        self.assertEqual(nowhere, [15, 16])

    def test_plan_prefers_the_lighter_edition(self):
        releases = [
            self.rel("One Piece en couleurs - T001-104 CBZ", seeders=8, size=102e9),
            self.rel("[Compressé] One Piece - T001-104 CBZ", seeders=6, size=16e9),
            self.rel("One Piece - T050 [CBZ] Fr", seeders=30, size=150e6),
        ]
        picks, nowhere = ohara.plan("One Piece", releases, {"downloads": {}})
        self.assertEqual([r["title"][:14] for r in picks], ["[Compressé] On"])
        self.assertEqual(nowhere, [])

    def test_plan_drops_packs_a_later_one_covers(self):
        cbz(self.root / "One Piece" / "One Piece T098.cbz", ["1.png"])
        releases = [
            self.rel("One Piece - T001 à T094 [CBR]", seeders=3, size=14.7e9),
            self.rel("One Piece T01 à T103 - Fr", seeders=3, size=16.4e9),
            self.rel("One Piece T103 [CBZ] Fr", seeders=2, size=0.2e9),
            self.rel("One Piece - T105 [CBZ] Fr", seeders=3, size=0.1e9),
            self.rel("One Piece T106-114 Scan CBZ", seeders=23, size=2.8e9),
            self.rel("One piece - T109 [CBZ] Fr", seeders=4, size=0.05e9),
        ]
        picks, nowhere = ohara.plan("One Piece", releases, {"downloads": {}})
        self.assertEqual(sorted(r["range"] for r in picks), [(1, 103), (105, 105), (106, 114)])
        self.assertEqual(nowhere, [104])

    def test_slow_releases_cost_more(self):
        need = {1, 2}
        fast = self.rel("X T01 - T02 FR", seeders=10, size=1e9)
        slow = dict(fast, seeders=1)
        self.assertLess(ohara.cost(fast, need), ohara.cost(slow, need))

    def test_colour_editions_are_another_series(self):
        entry = {"anilist": 21}
        facts = {"One Piece en couleurs": {"id": 21}, "One Piece - Édition Originale": {"id": 21}}
        colour = self.rel("One Piece en couleurs - T001-104 CBZ")
        original = self.rel("One Piece - Édition Originale - Tome 98")
        self.assertFalse(ohara.same_series(colour, "One Piece", entry, facts))
        self.assertTrue(ohara.same_series(original, "One Piece", entry, facts))
        self.assertTrue(ohara.same_series(colour, "One Piece en couleurs", entry, facts))
        self.assertFalse(ohara.same_series(original, "One Piece en couleurs", entry, facts))  # not the black and white one
        self.assertFalse(ohara.same_series(original, "One Piece", {}, facts))

    def test_a_colour_edition_takes_the_facts_of_the_series_it_colours(self):
        self.assertEqual([ohara.uncoloured(n) for n in ("One Piece en couleurs", "Naruto (Colour)", "Dr. Stone - Colored", "Bleach")],
                         ["One Piece", "Naruto", "Dr. Stone", "Bleach"])
        with mock.patch.object(ohara, "anilist_fetch", return_value={"id": 21, "banner": "b", "names": []}) as fetch:
            self.assertEqual(ohara.lookup("One Piece en couleurs")["id"], 21)
        fetch.assert_called_once_with("One Piece")
        self.assertEqual(ohara.load_state()["lookups"]["onepieceencouleurs"]["id"], 21)
        self.assertFalse(ohara.fresh({}, "One Piece en couleurs"))  # a miss from before: asked again
        self.assertTrue(ohara.fresh({}, "Bleach"))

    def test_plan_with_nothing_to_find(self):
        self.assertEqual(ohara.plan("Frieren", [], {"downloads": {}}), ([], []))
        self.assertEqual(ohara.plan("Frieren", [], {"downloads": {}}, total=2), ([], [1, 2]))

    def test_complete_grabs_the_plan(self):
        ohara.save_state({"series": {"Frieren": {"query": "frieren", "anilist": 5}}, "lookups": {"frieren": {"id": 5, "volumes": 3}}})
        found = [self.rel("Frieren T01 - T02 FR"), self.rel("Frieren Anthology T03 FR")]
        facts = {"Frieren": {"id": 5}, "Frieren Anthology": {"id": 6}}
        with mock.patch.object(ohara, "find_releases", return_value=found) as find, mock.patch.object(ohara, "lookups", return_value=facts), \
                mock.patch.object(ohara, "grab") as grab:
            done = ohara.complete("Frieren")
        find.assert_called_once_with("frieren")
        grab.assert_called_once_with("Frieren T01 - T02 FR", "Frieren")
        self.assertEqual(done, {"sent": [{"title": "Frieren T01 - T02 FR", "range": (1, 2)}], "nowhere": [3]})

    def chapters(self, title, seeders=5, lang="EN", size=1e9):
        return dict(self.rel(title, seeders, lang, size), chapters=ohara.chapter_range(title))

    def test_a_webtoon_takes_the_english_pack_with_the_most_missing_chapters(self):
        for n in (1, 2, 3):
            cbz(self.root / "Blade" / f"Blade c{n:03d}.cbz", ["1.png"])
        releases = [
            self.chapters("Blade ch001-030 [WEBTOON]", seeders=50),
            self.chapters("Blade ch001-158 (Complete) [WEBTOON]", seeders=4),
            self.chapters("Blade ch159-160 [WEBTOON]", seeders=0),  # nobody shares it
            self.chapters("Blade ch161 [WEBTOON]", lang="JP"),
            self.chapters("Blade ch100-170 [WEBTOON]", seeders=2),
        ]
        picks, nowhere = ohara.webtoon_plan("Blade", releases, {"downloads": {}}, total=175)
        self.assertEqual([r["title"] for r in picks], ["Blade ch001-158 (Complete) [WEBTOON]", "Blade ch100-170 [WEBTOON]"])
        self.assertEqual(nowhere, list(range(171, 176)))
        picks, nowhere = ohara.webtoon_plan("Blade", releases, {"downloads": {"H": {"series": "Blade"}}})
        self.assertEqual((picks, nowhere), ([], []))  # one on its way: its chapters are not known yet

    def test_a_webtoons_packs_without_chapters_bigger_than_the_last(self):
        packs = [self.chapters("[Dalte] Ashtarte S1 (2022) (Digital) (Tappytoon)", size=1e9),
                 self.chapters("[Dalte] Ashtarte S1-2 (2022) (Digital) (Tappytoon) | Ongoing", size=2e9, seeders=1),
                 self.chapters("[Other] Ashtarte (2022) (Digital)", size=2e9, seeders=9)]
        picks, _ = ohara.webtoon_plan("Ashtarte", packs, {"downloads": {}})
        self.assertEqual([r["title"] for r in picks], ["[Other] Ashtarte (2022) (Digital)"])  # as big, more seeders
        state = {"downloads": {}, "series": {"Ashtarte": {"taken": [picks[0]["token"]], "taken_size": 2e9}}}
        self.assertEqual(ohara.webtoon_plan("Ashtarte", packs, state), ([], []))  # nothing bigger since
        bigger = self.chapters("[Dalte] Ashtarte S1-3 (2022) (Digital) (Tappytoon) | Ongoing", size=3e9, seeders=1)
        self.assertEqual(ohara.webtoon_plan("Ashtarte", packs + [bigger], state)[0], [bigger])
        cbz(self.root / "Ashtarte" / "Ashtarte c001.cbz", ["1.png"])
        self.assertEqual(ohara.webtoon_plan("Ashtarte", packs, {"downloads": {}}, total=1), ([], []))  # every chapter here

    def test_complete_follows_a_webtoon_by_chapters_and_a_manga_by_tomes(self):
        cbz(self.root / "Blade" / "Blade c001.cbz", ["1.png"])
        ohara.save_state({"series": {"Blade": {"query": "blade"}, "Frieren": {"query": "frieren"}},
                          "lookups": {"blade": {"chapters": 3}, "frieren": {"volumes": 2}}})
        found = [self.chapters("Blade ch001-003 [WEBTOON]"), self.rel("Blade T01 FR"), self.rel("Frieren T01 - T02 FR"), self.chapters("Frieren ch001-020")]
        with mock.patch.object(ohara, "find_releases", return_value=found), mock.patch.object(ohara, "lookups", return_value={}), \
                mock.patch.object(ohara, "grab") as grab:
            self.assertEqual(ohara.complete("Blade"), {"sent": [{"title": "Blade ch001-003 [WEBTOON]", "range": None}], "nowhere": []})
            self.assertEqual(ohara.complete("Frieren")["sent"], [{"title": "Frieren T01 - T02 FR", "range": (1, 2)}])
        self.assertEqual([c.args for c in grab.call_args_list], [("Blade ch001-003 [WEBTOON]", "Blade"), ("Frieren T01 - T02 FR", "Frieren")])

    def test_the_webtoon_switch(self):
        cbz(self.root / "Blade" / "Blade c001.cbz", ["1.png"])
        cbz(self.root / "Frieren" / "Frieren T01.cbz", ["1.png"])
        ohara.save_state({"lookups": {"blade": {"volumes": 1, "chapters": 3}}})
        info = ohara.series_info(self.root / "Blade", ohara.load_state())
        self.assertEqual((info["webtoon"], info["missing"]), (True, [2, 3]))  # chapters, from its files
        self.assertFalse(ohara.series_info(self.root / "Frieren", ohara.load_state())["webtoon"])
        with mock.patch.object(ohara, "complete_later") as later:
            ohara.set_webtoon("Blade", False)
            ohara.set_follow("Frieren", True)
            ohara.set_webtoon("Frieren", True)
        self.assertEqual([c.args for c in later.call_args_list], [("Frieren",), ("Frieren",)])  # followed: completed at once
        state = ohara.load_state()
        self.assertFalse(ohara.is_webtoon("Blade", state["series"]["Blade"]))
        self.assertTrue(ohara.is_webtoon("Frieren", state["series"]["Frieren"]))
        self.assertFalse(ohara.is_webtoon("Nowhere", {}))

    def test_complete_later_runs_in_the_background(self):
        with mock.patch.object(ohara, "complete", side_effect=OSError("prowlarr down")) as complete:
            ohara.complete_later("Frieren")
            for _ in range(100):
                if complete.called:
                    break
                ohara.time.sleep(0.01)
        complete.assert_called_once_with("Frieren")

    def test_following_completes_at_once(self):
        with mock.patch.object(ohara, "complete_later") as later:
            ohara.set_follow("Frieren", True)
            ohara.set_follow("Frieren", False)
        later.assert_called_once_with("Frieren")

    def test_check_follows_grabs_for_followed_series_only(self):
        cbz(self.root / "Frieren" / "T01.cbz", ["1.png"])
        ohara.save_state({"series": {"Frieren": {"follow": True, "query": "frieren", "anilist": 5}, "Naruto": {"follow": False}}})
        found = [self.rel("Sousou no Frieren T02 FR"), self.rel("Frieren Anthology T03 FR"), self.rel("Frieren T01 FR")]
        facts = {"Sousou no Frieren": {"id": 5}, "Frieren Anthology": {"id": 6}, "Frieren": {"id": 5}}
        with mock.patch.object(ohara, "find_releases", return_value=found) as find, mock.patch.object(ohara, "lookups", return_value=facts), \
                mock.patch.object(ohara, "grab") as grab:
            ohara.check_follows()
        find.assert_called_once_with("frieren")
        grab.assert_called_once_with("Sousou no Frieren T02 FR", "Frieren")
        self.assertGreater(ohara.load_state()["followed_at"], 0)

    def test_follows_are_due_every_twelve_hours(self):
        self.assertTrue(ohara.follows_due())
        ohara.save_state({"followed_at": ohara.time.time()})
        self.assertFalse(ohara.follows_due())
        with mock.patch.object(ohara, "check_downloads") as downloads, mock.patch.object(ohara, "check_follows") as follows, \
                mock.patch.object(ohara, "read_spines") as spines, mock.patch.object(ohara, "brook_pass") as brook, \
                mock.patch.object(ohara, "chapters_pass") as wiki, mock.patch.object(ohara, "backup_state") as backup:
            ohara.tick()
        backup.assert_called_once()
        wiki.assert_called_once()
        spines.assert_called_once()
        brook.assert_called_once()
        downloads.assert_called_once()
        follows.assert_not_called()

    def test_series_info_missing_new_and_followed(self):
        for n in (1, 2, 5):
            cbz(self.root / "Frieren" / f"Frieren T{n:02d}.cbz", ["1.png"])
        old = self.root / "Frieren" / "Frieren T01.cbz"
        os.utime(old, (0, 0))
        ohara.save_state({"series": {"Frieren": {"follow": True}}, "lookups": {"frieren": {"id": 5, "cover": "c", "volumes": 8}},
                          "downloads": {"H": {"series": "Frieren", "range": [7, 7]}},
                          "progress": {"Frieren/Frieren T02.cbz": {"page": 3, "pages": 10, "at": 1}}})
        info = ohara.series_info(self.root / "Frieren", ohara.load_state())
        self.assertEqual((info["follow"], info["meta"]["cover"], info["missing"], info["coming"]), (True, "c", [3, 4, 6, 8], [7]))
        self.assertEqual([v["new"] for v in info["volumes"]], [False, False, True])
        self.assertEqual(info["new"], 1)


class Robin(Library):
    def cover(self, colour=(30, 90, 200), left=(240, 230, 210)):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (300, 450), colour)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, 29, 449], fill=left)
        for i in range(0, 120, 6):  # something busy near the top right
            d.line([(200 + i % 60, 40), (260, 40 + i)], fill=(255, 255, 0), width=2)
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()

    def test_reads_a_cover(self):
        import robin
        info, crop = robin.read_cover(self.cover())
        self.assertEqual(info["edge"], "#f0e6d2")
        self.assertEqual(info["main"], "#1e5ac8")
        self.assertEqual(info["ink"], "#1b130b")
        self.assertTrue(crop.startswith(b"\xff\xd8"))
        dark, _ = robin.read_cover(self.cover(left=(20, 20, 20)))
        self.assertEqual(dark["ink"], "#fdf6e6")

    def test_liveliest_square_is_where_things_happen(self):
        import robin
        from PIL import Image
        img = Image.open(io.BytesIO(self.cover())).convert("RGB")
        square = robin.liveliest(img)
        self.assertEqual(square.size, (robin.CROP, robin.CROP))
        yellow = sum(1 for p in square.getdata() if p[0] > 200 and p[1] > 200 and p[2] < 100)
        self.assertGreater(yellow, 20)

    def test_accent_and_palette(self):
        import robin
        self.assertEqual(robin.accent([(10, (100, 100, 100))], (100, 100, 100)), (100, 100, 100))
        self.assertEqual(robin.accent([(10, (100, 100, 100)), (5, (250, 10, 10)), (3, (120, 110, 100))], (100, 100, 100)), (250, 10, 10))

    def test_spines_read_a_few_at_a_time_and_kept(self):
        for n in range(1, 4):
            path = self.root / "Frieren" / f"Frieren T{n:02d}.cbz"
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("001.png", self.cover())
        (self.root / "Frieren" / "Extra.pdf").write_bytes(b"%PDF")
        self.assertEqual(ohara.read_spines(limit=2), 2)
        self.assertEqual(ohara.read_spines(limit=2), 1)
        self.assertEqual(ohara.read_spines(limit=2), 0)
        state = ohara.load_state()
        info = ohara.spine_of("Frieren/Frieren T01.cbz", state["spines"])
        self.assertEqual(set(info), {"edge", "main", "accent", "ink"})
        self.assertIsNone(ohara.spine_of("Frieren/none.cbz", state["spines"]))
        self.assertTrue(ohara.crop_path("Frieren/Frieren T01.cbz").exists())
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            vols = {v["file"]: v for v in ohara.library()["series"][0]["volumes"]}
        self.assertEqual(vols["Frieren T01.cbz"]["spine"]["main"], info["main"])
        self.assertIsNone(vols["Extra.pdf"]["spine"])

    def test_a_broken_volume_does_not_stop_robin(self):
        path = self.root / "Broken" / "T01.cbz"
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("001.png", b"not an image")
        self.assertEqual(ohara.read_spines(), 1)
        self.assertEqual(ohara.load_state()["spines"], {})

    def test_spine_style_setting(self):
        self.assertEqual(ohara.settings(), {"spines": "tome", "brook": True, "franky": False, "ribbon": True, "discord": False})  # Franky waits to be asked
        self.assertEqual(ohara.set_settings({"spines": "reliure", "franky": True})["spines"], "reliure")
        self.assertEqual(ohara.settings(), {"spines": "reliure", "brook": True, "franky": True, "ribbon": True, "discord": False})
        ohara.set_settings({"spines": "neon", "brook": "yes", "franky": "no", "ribbon": 0})
        self.assertEqual(ohara.settings(), {"spines": "reliure", "brook": True, "franky": True, "ribbon": True, "discord": False})


class Franky(Library):
    """Each volume rebuilt lighter, in WebP."""

    def volume(self, name, pages, extra=()):
        from PIL import Image
        path = self.root / "Manga" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as z:
            for page, colour in pages:
                b = io.BytesIO()
                img = Image.effect_noise((600, 900), 60).convert("RGB")
                if colour:
                    img = Image.merge("RGB", (img.getchannel(0), Image.new("L", img.size, 30), Image.new("L", img.size, 200)))
                img.save(b, "JPEG" if page.endswith(".jpg") else "PNG", quality=97)
                z.writestr(page, b.getvalue())
            for name_, data in extra:
                z.writestr(name_, data)
        os.utime(path, (1000, 1000))
        return path

    def test_a_volume_rebuilt_lighter_in_webp(self):
        from PIL import Image
        path = self.volume("Manga T01.cbz", [("001.jpg", False), ("002.png", True)], [("ComicInfo.xml", b"<x/>")])
        sizes = ohara.franky.rebuild(path)
        self.assertLess(sizes["after"], sizes["before"] * 0.9)
        self.assertEqual(sizes["after"], path.stat().st_size)
        self.assertEqual(path.stat().st_mtime, 1000)  # not a new volume
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.namelist(), ["001.webp", "002.webp", "ComicInfo.xml"])
            self.assertEqual(z.read("ComicInfo.xml"), b"<x/>")
            r, g, blue = Image.open(io.BytesIO(z.read("002.webp"))).convert("RGB").getpixel((1, 1))
            self.assertGreater(blue - g, 120)  # colour kept
        self.assertTrue(ohara.franky.done(path))
        self.assertEqual([p.name for p in path.parent.iterdir()], ["Manga T01.cbz"])  # nothing left beside
        self.assertEqual(ohara.pages(path), ["001.webp", "002.webp"])

    def test_a_volume_already_squeezed_is_not_rebuilt(self):
        path = self.volume("Manga T04.cbz", [("001.jpg", False), ("002.jpg", False)])
        before = path.read_bytes()
        with mock.patch.object(ohara.franky, "page", return_value=None), mock.patch.object(ohara.franky, "write") as write:
            self.assertEqual(ohara.franky.rebuild(path), {"before": len(before), "after": len(before)})
        write.assert_not_called()
        self.assertEqual(path.read_bytes(), before)

    def test_a_volume_lighter_when_tried_but_not_once_written_is_left(self):
        path = self.volume("Manga T05.cbz", [("001.jpg", False)])
        before = path.read_bytes()
        with mock.patch.object(ohara.franky, "promising", return_value=True), mock.patch.object(ohara.franky, "page", return_value=None):
            self.assertEqual(ohara.franky.rebuild(path), {"before": len(before), "after": len(before)})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["Manga T05.cbz"])

    def test_a_volume_not_worth_it_is_left_as_it_is(self):
        path = self.volume("Manga T02.cbz", [])
        with zipfile.ZipFile(path, "a") as z:
            z.writestr("001.webp", b"already light")
        before = path.read_bytes()
        self.assertEqual(ohara.franky.rebuild(path), {"before": len(before), "after": len(before)})
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(ohara.franky.done(path))

    def test_a_page_not_lighter_stays(self):
        from PIL import Image
        b = io.BytesIO()
        Image.effect_noise((300, 300), 90).convert("RGB").save(b, "JPEG", quality=5)  # already squeezed hard
        self.assertIsNone(ohara.franky.page(b.getvalue()))
        b = io.BytesIO()
        see_through = Image.effect_noise((300, 300), 60).convert("RGBA")
        see_through.putalpha(128)
        see_through.save(b, "PNG")
        self.assertEqual(Image.open(io.BytesIO(ohara.franky.page(b.getvalue()))).mode, "RGBA")  # transparency kept

    def test_a_volume_that_does_not_check_out_is_left(self):
        path = self.volume("Manga T03.cbz", [("001.jpg", False)])
        before = path.read_bytes()
        with mock.patch.object(ohara.franky, "check", side_effect=ValueError("not as written")), self.assertRaises(ValueError):
            ohara.franky.rebuild(path)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["Manga T03.cbz"])
        with zipfile.ZipFile(path, "a") as z:
            z.writestr("broken.webp", b"not a page")
        with self.assertRaises(Exception):
            ohara.franky.check(path, ohara.zipfile.ZipFile(path).namelist())

    def test_franky_goes_through_the_library(self):
        first = self.volume("Manga T01.cbz", [("001.jpg", False)])
        read = self.volume("Manga T02.cbz", [("001.jpg", False)])
        broken = self.root / "Manga" / "Manga T03.cbz"
        broken.write_bytes(b"not a zip")
        ohara.save_progress("Manga/Manga T02.cbz", 0, 1)  # being read: left for later
        ohara.pages(first)
        self.assertEqual(ohara.franky_progress(), {"done": 0, "total": 3, "saved": 0})
        self.assertTrue(ohara.franky_one())
        self.assertEqual(ohara.pages(first), ["001.webp"])  # its pages read again
        self.assertTrue(ohara.franky_one())  # the broken one, noted and left
        self.assertFalse(ohara.franky_one())
        seen = ohara.load_state()["franky"]
        self.assertEqual(sorted(seen), ["Manga/Manga T01.cbz", "Manga/Manga T03.cbz"])
        self.assertEqual(seen["Manga/Manga T03.cbz"], [0, 0])
        progress = ohara.franky_progress()
        self.assertEqual((progress["done"], progress["total"]), (2, 3))
        self.assertGreater(progress["saved"], 0)
        state = ohara.load_state()
        reading(state)["Manga/Manga T02.cbz"]["at"] = 0
        ohara.save_state(state)
        with mock.patch.object(ohara.franky, "done", return_value=True):  # already rebuilt
            self.assertTrue(ohara.franky_one())
        self.assertEqual(ohara.load_state()["franky"]["Manga/Manga T02.cbz"], [read.stat().st_size] * 2)

    def test_franky_rests_when_all_is_done_or_he_is_off(self):
        ohara.set_settings({"franky": True})
        left = self.root / "Manga" / ".Manga T01.cbz.franky"
        left.parent.mkdir(parents=True)
        left.write_bytes(b"half")
        calls = []
        with mock.patch.object(ohara.os, "nice"), mock.patch.object(ohara, "franky_one", side_effect=[True, OSError("disk")]), \
                mock.patch.object(ohara.time, "sleep", side_effect=lambda s: calls.append(s) if len(calls) < 2 else (_ for _ in ()).throw(StopIteration)):
            with self.assertRaises(StopIteration):
                ohara.franky_loop()
        self.assertEqual(calls, [1, ohara.FRANKY_REST])
        self.assertFalse(left.exists())  # what he left half written is gone
        ohara.set_settings({"franky": False})
        with mock.patch.object(ohara.os, "nice"), mock.patch.object(ohara, "franky_one") as one, \
                mock.patch.object(ohara.time, "sleep", side_effect=StopIteration), self.assertRaises(StopIteration):
            ohara.franky_loop()
        one.assert_not_called()


NUMBERED_PAGE = """
{{Graphic novel list
| VolumeNumber    = 1
| ChapterListCol1 =
{{Numbered list|start=1
|{{Nihongo|"Ryomen Sukuna"|両面宿儺}}
|{{Nihongo|"For Myself"|自分のために}}
}}
| ChapterListCol2 = {{Numbered list|start=3
|{{Nihongo|"Girl of Steel"|鋼の少女}}
|
}}
| LicensedTitle = Ryomen Sukuna
}}
{{Graphic novel list
| VolumeNumber    = {{0}}2
| ChapterListCol1 = <!--{{Numbered list|start=4
|{{Nihongo|"Not yet"|まだ}}
}}-->
}}
== Chapters not yet in tankōbon format ==
{{Numbered list|start=4
|"Later"
}}
"""

HASHED_PAGE = """
{{Graphic novel list
| VolumeNumber=1
| ChapterList=
#<li value="1">{{nihongo|"Uzumaki Naruto!"|うずまきナルト!}}</li>
#{{nihongo-s|"Konohamaru"|木ノ葉丸}}
| LicensedTitle=The Tests of the Ninja
}}
{{Graphic novel list
| VolumeNumber=2
| ChapterList=
#{{nihongo-s|"The Worst Client"|最悪の依頼人}}
}}
"""


class Chapters(Library):
    """The chapters each volume holds, from Wikipedia's lists."""

    def test_numbered_lists_and_volumes_to_come(self):
        self.assertEqual(ohara.chapters.read(NUMBERED_PAGE), {1: [1, 3]})

    def test_hashed_lists_go_on_from_the_volume_before(self):
        self.assertEqual(ohara.chapters.read(HASHED_PAGE), {1: [1, 2], 2: [3, 3]})

    def test_a_series_pages_and_its_names(self):
        answers = {
            "List of Jujutsu Kaisen chapters": ["Lists of Jujutsu Kaisen chapters", "List of Jujutsu Kaisen chapters (1–3)", "List of Jujutsu Kaisen chapters (4–6)", "List of Jujutsu Kaisen chapters spin-off"],
        }

        def ask(params):
            if params["action"] == "query":
                return {"query": {"prefixsearch": [{"title": t} for t in answers.get(params["pssearch"], [])]}}
            return {"parse": {"wikitext": NUMBERED_PAGE if "1–3" in params["page"] else HASHED_PAGE.replace("=1\n", "=4\n").replace("=2\n", "=5\n")}}
        with mock.patch.object(ohara.chapters, "ask", side_effect=ask):
            self.assertEqual(ohara.chapters.list_pages("Jujutsu Kaisen"), ["List of Jujutsu Kaisen chapters (1–3)", "List of Jujutsu Kaisen chapters (4–6)"])
            self.assertEqual(ohara.chapters.chapters(["Sorcery Fight", "Jujutsu Kaisen"]), {1: [1, 3], 4: [1, 2], 5: [3, 3]})
            self.assertEqual(ohara.chapters.chapters(["Nobody"]), {})

    def test_wikipedia_is_asked_politely(self):
        answer = mock.MagicMock()
        answer.__enter__.return_value = io.BytesIO(b'{"ok": 1}')
        with mock.patch.object(ohara.chapters.urllib.request, "urlopen", return_value=answer) as get:
            self.assertEqual(ohara.chapters.ask({"action": "query"}), {"ok": 1})
        req = get.call_args[0][0]
        self.assertIn("formatversion=2", req.full_url)
        self.assertIn("Ohara", req.get_header("User-agent"))
        with mock.patch.object(ohara.chapters, "ask", return_value={"parse": {"wikitext": "x"}}):
            self.assertEqual(ohara.chapters.wikitext("T"), "x")

    def test_one_series_a_pass_and_on_its_volumes(self):
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
        cbz(self.root / "Naruto" / "Naruto T01.5.cbz", ["1.png"])
        cbz(self.root / "Zetman" / "Zetman T01.cbz", ["1.png"])
        ohara.save_state({"lookups": {"naruto": {"title": "Naruto", "names": ["NARUTO", "Naruto"]}}})
        with mock.patch.object(ohara.chapters, "chapters", return_value={1: [1, 7]}) as read:
            ohara.chapters_pass()
            ohara.chapters_pass()
            ohara.chapters_pass()  # both done: nothing more this month
        self.assertEqual([c.args[0] for c in read.call_args_list], [["Naruto", "NARUTO"], ["Zetman"]])
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            naruto = next(s for s in ohara.library()["series"] if s["name"] == "Naruto")
        self.assertEqual({v["number"]: v["chapters"] for v in naruto["volumes"]}, {1: [1, 7], 1.5: None})
        state = ohara.load_state()
        state["chapters"]["Naruto"]["at"] = 0
        ohara.save_state(state)
        with mock.patch.object(ohara.chapters, "chapters", side_effect=OSError("away")):
            ohara.chapters_pass()  # said, and tried again next pass
        self.assertEqual(ohara.load_state()["chapters"]["Naruto"]["at"], 0)


    def test_a_webtoons_chapters_are_not_the_tomes_wikipedia_lists(self):
        cbz(self.root / "Ashtarte" / "Ashtarte c001 (2022) (Digital) (Dalte).cbz", ["1.png"])
        ohara.save_state({"chapters": {"Ashtarte": {"volumes": {"1": [1, 7]}, "at": 0}}})
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            [ashtarte] = ohara.library()["series"]
        [v] = ashtarte["volumes"]
        self.assertEqual((v["number"], v["label"], v["chapter"], v["chapters"]), (1, "Chapitre 1", True, None))


class StuckTransmission(Library):
    def test_the_library_does_not_wait_on_a_stuck_transmission(self):
        ohara.torrents_seen.clear()
        known = {"hashString": "H", "percentDone": 0.5}
        with mock.patch.object(ohara, "rpc", return_value={"torrents": [known]}) as rpc:
            self.assertEqual(ohara.safe_torrents(["H"]), [known])
        self.assertEqual(rpc.call_args.args[2], ohara.TORRENTS_WAIT)
        with mock.patch.object(ohara, "rpc", side_effect=TimeoutError("stuck")):
            self.assertEqual(ohara.safe_torrents(["H", "unseen"]), [known])  # what it said last
        self.assertEqual(ohara.torrents([]), [])


class DenDen(Library):
    """What Ohara says on Discord."""

    def test_the_words_of_a_message(self):
        d = ohara.den_den
        self.assertEqual(d.tomes([9, 3, 7, 8]), "T3 et T7 à T9")
        self.assertEqual(d.tomes([12.5]), "T12.5")
        self.assertEqual(d.tomes([1, 2, 4, 6, 7], "en"), "T1 to T2, T4 and T6 to T7")
        msg = d.arrived("Naruto", [12, 13, 14], "cover.jpg", "http://pi:8585/#Naruto")
        embed = msg["embeds"][0]
        self.assertEqual((embed["title"], embed["url"], embed["thumbnail"]), ("3 tomes de Naruto arrivés", "http://pi:8585/#Naruto", {"url": "cover.jpg"}))
        self.assertNotIn("username", msg)  # the webhook's own name and picture
        self.assertEqual(d.sign(msg, "Professeur Clover")["username"], "Professeur Clover")
        self.assertIs(d.sign(msg, ""), msg)
        self.assertEqual(embed["description"], "T12 à T14\n[Les lire dans Ohara](http://pi:8585/#Naruto)")
        self.assertEqual(d.arrived("Bleach", [1], lang="en")["embeds"][0], {"title": "1 volume of Bleach in", "description": "T1", "color": d.COLOUR})
        found = d.found("One Piece", [{"title": "One Piece T115", "range": [115, 115]}])["embeds"][0]
        self.assertEqual((found["title"], found["description"]), ("Du nouveau pour One Piece", "En route : T115."))
        self.assertEqual(d.found("X", [{"title": "X Intégrale", "range": None}], lang="en")["embeds"][0]["description"], "On its way: X Intégrale.")

    def test_a_message_goes_out_and_is_tried_again(self):
        d = ohara.den_den
        with mock.patch.object(d.urllib.request, "urlopen") as urlopen:
            d.send("https://discord/hook", {"content": "x"})
        req = urlopen.call_args.args[0]
        self.assertEqual((req.full_url, req.get_method(), json.loads(req.data)), ("https://discord/hook", "POST", {"content": "x"}))
        self.assertIn("Ohara", req.get_header("User-agent"))  # Discord turns away Python's own
        with mock.patch.object(d, "send", side_effect=[OSError("away"), OSError("away"), None]) as send, mock.patch.object(d.time, "sleep") as sleep:
            d.post("hook", {}, start=False).run()
        self.assertEqual((send.call_count, sleep.call_count), (3, 2))
        with mock.patch.object(d, "send", side_effect=OSError("away")) as send, mock.patch.object(d.time, "sleep"):
            d.post("hook", {}, tries=2, start=False).run()  # given up after two
        self.assertEqual(send.call_count, 2)
        with mock.patch.object(d.threading.Thread, "start") as start:
            d.post("hook", {})
        start.assert_called_once()

    def test_a_channel_linked_from_the_settings(self):
        hook = "https://discord.com/api/webhooks/123/abc-DEF_9"
        for wrong in ("http://discord.com/api/webhooks/1/a", "https://evil.example/api/webhooks/1/a", "nope"):
            with self.assertRaises(ValueError):
                ohara.link_discord(wrong)
        with mock.patch.object(ohara.den_den, "send", side_effect=OSError("HTTP Error 404: Not Found")):
            with self.assertRaises(OSError):  # Discord does not take it: not kept
                ohara.link_discord(hook)
        self.assertFalse(ohara.settings()["discord"])
        with mock.patch.object(ohara.den_den, "send") as send:
            self.assertTrue(ohara.link_discord(" " + hook + " ", "http://dpi.local:8585/")["discord"])
        self.assertEqual(send.call_args.args[1]["embeds"][0]["title"], "Ohara est relié à ce salon")
        self.assertEqual(ohara.discord(), (hook, "http://dpi.local:8585"))
        with mock.patch.object(ohara.den_den, "send") as send:
            Http.call(self, "POST", "/api/discord", {"url": ""})  # unlinked
        send.assert_not_called()
        self.assertEqual(ohara.discord(), ("", "http://dpi.local:8585"))
        with mock.patch.object(ohara, "DISCORD_WEBHOOK", "env-hook"):
            self.assertEqual(ohara.discord()[0], "env-hook")
        self.assertEqual(ohara.den_den.linked("en")["embeds"][0]["title"], "Ohara is linked to this channel")

    def test_ohara_tells_the_tomes_come_in_and_those_following_finds(self):
        told = []
        with mock.patch.object(ohara, "DISCORD_WEBHOOK", ""):
            self.assertIsNone(ohara.tell(ohara.den_den.arrived, "Naruto", [1]))
        with mock.patch.object(ohara, "DISCORD_WEBHOOK", "hook"), mock.patch.object(ohara, "OHARA_URL", "http://pi:8585"), \
                mock.patch.object(ohara.den_den, "post", side_effect=lambda hook, payload: told.append((hook, payload))):
            ohara.save_state({"lookups": {"naruto": {"cover": "c.jpg"}}})
            ohara.tell(ohara.den_den.arrived, "Naruto", [1])
            self.assertEqual(told[-1][1]["embeds"][0]["url"], "http://pi:8585/#Naruto")
            self.assertEqual(told[-1][1]["embeds"][0]["thumbnail"], {"url": "c.jpg"})
            cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
            cbz(self.root / ".incoming" / "f" / "Naruto T01.cbz", ["1.png"])  # had already
            cbz(self.root / ".incoming" / "f" / "Naruto T02.cbz", ["1.png"])
            with mock.patch.object(ohara, "rpc"):
                ohara.file_download("H", {"series": "Naruto", "folder": "f"})
            self.assertEqual(told[-1][1]["embeds"][0]["title"], "1 tome de Naruto arrivé")
            self.assertEqual(told[-1][1]["embeds"][0]["description"].split("\n")[0], "T2")
            ohara.save_state({"series": {"Naruto": {"follow": True}, "Bleach": {"follow": True}, "Dune": {"follow": False}}})
            answers = {"Naruto": {"sent": [{"title": "Naruto T03", "range": [3, 3]}], "nowhere": []}, "Bleach": {"sent": [], "nowhere": [9]}}
            told.clear()
            with mock.patch.object(ohara, "complete", side_effect=lambda s: answers[s]):
                ohara.check_follows()
            self.assertEqual([p["embeds"][0]["title"] for _, p in told], ["Du nouveau pour Naruto"])


class Backups(Library):
    def test_a_copy_of_the_state_a_day_seven_days_kept(self):
        ohara.backup_state("2026-11-01")  # no state yet: nothing
        self.assertFalse((ohara.STATE_DIR / "backups").exists())
        ohara.save_state({"progress": {"a": {"page": 3}}})
        for day in range(1, 10):
            ohara.backup_state(f"2026-11-{day:02d}")
        ohara.save_state({"progress": {}})
        ohara.backup_state("2026-11-09")  # once a day: the morning's copy stays
        kept = sorted(p.name for p in (ohara.STATE_DIR / "backups").iterdir())
        self.assertEqual(kept, [f"state-2026-11-{d:02d}.json" for d in range(3, 10)])
        self.assertEqual(json.loads((ohara.STATE_DIR / "backups" / "state-2026-11-09.json").read_text())["progress"], {"a": {"page": 3}})


class GivingUp(Library):
    """A release that does not come, given up on, is not taken again."""

    def test_a_release_given_up_is_not_taken_again(self):
        (self.root / ".incoming" / "f1").mkdir(parents=True)
        ohara.save_state({"downloads": {"H1": {"series": "Frieren", "title": "Frieren T01-T03 FR", "folder": "f1", "range": [1, 3]}}})
        with mock.patch.object(ohara, "rpc") as rpc:
            self.assertEqual(ohara.give_up("H1"), "Frieren")
        rpc.assert_called_once_with("torrent-remove", {"ids": ["H1"], "delete-local-data": True})
        state = ohara.load_state()
        self.assertEqual((state["downloads"], state["series"]["Frieren"]["skipped"]), ({}, ["Frieren T01-T03 FR"]))
        self.assertFalse((self.root / ".incoming" / "f1").exists())
        with self.assertRaises(KeyError):
            ohara.give_up("H1")
        dead = {"title": "Frieren T01-T03 FR", "lang": "FR", "range": (1, 3), "seeders": 9, "size": 1}
        other = {"title": "Frieren - T01 à T03 FR", "lang": "FR", "range": (1, 3), "seeders": 2, "size": 2}
        picks, nowhere = ohara.plan("Frieren", [dead, other], ohara.load_state(), 3)
        self.assertEqual(([r["title"] for r in picks], nowhere), (["Frieren - T01 à T03 FR"], []))


class Chopper(Library):
    """What ails the library, and the remedies."""

    def setUp(self):
        super().setUp()
        self.exams = mock.patch.object(ohara.chopper, "EXAMS", [])
        self.cures = mock.patch.object(ohara.chopper, "CURES", {})
        self.loaded = mock.patch.object(ohara.chopper, "_loaded", True)
        music = mock.patch.object(ohara, "MUSIC", self.root / ".ost")
        for p in (self.exams, self.cures, self.loaded, music):
            p.start()
            self.addCleanup(p.stop)
        ohara.ailments_seen.update(at=0, list=[])

    def test_examinations_their_ailments_and_remedies(self):
        c = ohara.chopper
        said = c.words("Deux fois", "Twice")
        fixed = []

        @c.exam
        def twice(snap):
            return [c.ailment("twice", "B", said, [c.remedy("fix", said, risky=True, what="b")], series="B", severity="advice"),
                    c.ailment("twice", "A", said, [c.remedy("fix", said, what="a")], series="A"),
                    c.ailment("twice", "A", said, [], series="A")]  # the same, said again

        @c.exam
        def broken(snap):
            raise ValueError("an examination that fails")

        @c.cure("fix")
        def fix(o, what):
            fixed.append((o, what))

        found = c.examine({})
        self.assertEqual([a["id"] for a in found], ["twice:A", "twice:B"])
        self.assertEqual(found[1]["remedies"][0], {"kind": "fix", "label": said, "risky": True, "args": {"what": "b"}})
        self.assertEqual(c.examine({}, {"twice:A"})[0]["id"], "twice:B")
        self.assertEqual(c.apply(found, "twice:A", 0, "ohara"), {"ok": True})
        self.assertEqual(fixed, [("ohara", "a")])
        for aid, index in (("gone", 0), ("twice:A", 3), ("twice:A", -1)):
            with self.assertRaises(KeyError):
                c.apply(found, aid, index, "ohara")
        with self.assertRaises(AssertionError):
            c.ailment("x", "y", said, [], severity="dire")

    def test_the_ailments_are_found_kept_treated_and_set_aside(self):
        c = ohara.chopper
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
        (self.root / "Naruto" / "notes.txt").write_text("x")
        (self.root / ".incoming" / "leftover").mkdir(parents=True)
        seen = []
        treated = []

        @c.exam
        def look(snap):
            seen.append(snap)
            return [c.ailment("look", "N", c.words("a", "a"), [c.remedy("treat", c.words("b", "b"))], series="Naruto")]

        @c.cure("treat")
        def treat(o):
            treated.append(o)
            return {"said": "done"}

        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            self.assertEqual(ohara.ailments(), [])  # never examined on the page's own asking
            ohara.examine_due()
            self.assertEqual(len(ohara.ailments()), 1)
            ohara.examine_due()  # kept a while
            self.assertEqual(len(seen), 1)
            snap = seen[0]
            self.assertEqual([f["name"] for f in snap["files"]["Naruto"]], ["Naruto T01.cbz", "notes.txt"])
            self.assertEqual(snap["files"]["Naruto"][1]["size"], 1)
            self.assertEqual(snap["incoming"], ["leftover"])
            self.assertEqual(snap["series"][0]["name"], "Naruto")
            done = ohara.treat("look:N", 0)
            self.assertEqual(done["done"], {"said": "done"})
            self.assertIs(treated[0], ohara)
            self.assertEqual(ohara.dismiss("look:N"), [])
            self.assertIn("look:N", ohara.load_state()["dismissed"])
            self.assertEqual(len(ohara.dismiss("look:N", on=False)), 1)
            code, _, payload = Http.call(self, "GET", "/api/ailments?fresh=1")
            self.assertEqual((code, json.loads(payload)[0]["id"]), (200, "look:N"))
            self.assertEqual(Http.call(self, "POST", "/api/ailments/treat", {"id": "look:N", "remedy": 0})[0], 200)
            self.assertEqual(Http.call(self, "POST", "/api/ailments/treat", {"id": "gone"})[0], 404)
            self.assertEqual(Http.call(self, "POST", "/api/ailments/dismiss", {"id": "look:N"})[0], 200)

    def test_renaming_a_volume_keeps_where_you_are(self):
        cbz(self.root / "Potter" / "Rowling [Tome 1].epub", ["1.png"])
        cbz(self.root / "Potter" / "Potter T01.epub", ["1.png"])  # the name is taken: another is found
        ohara.save_state({"progress": {"Potter/Rowling [Tome 1].epub": {"page": 3, "pages": 9, "at": 5}}, "spines": {"Potter/Rowling [Tome 1].epub": {"c": 1}},
                          "series": {"Potter": {"decor": "vol:Potter/Rowling [Tome 1].epub"}}})
        new = ohara.rename_volume("Potter/Rowling [Tome 1].epub", "Potter T01.epub")
        self.assertEqual(new, "Potter/Potter T01 (2).epub")
        state = ohara.load_state()
        self.assertEqual(reading(state), {new: {"page": 3, "pages": 9, "at": 5}})
        self.assertEqual(list(state["spines"]), [new])
        self.assertEqual(state["series"]["Potter"]["decor"], "vol:" + new)
        ohara.delete_volume(new)
        self.assertFalse((self.root / new).exists())
        self.assertEqual(reading(), {})

    def test_renaming_a_series_takes_everything_with_it(self):
        old = "Christopher Paolini Eragon"
        cbz(self.root / old / "Eragon T01.cbz", ["1.png"])
        cbz(self.root / "Naruto" / "Naruto T01.cbz", ["1.png"])
        (ohara.MUSIC / old / "Album").mkdir(parents=True)
        ohara.decor_file(old).parent.mkdir(parents=True, exist_ok=True)
        ohara.decor_file(old).write_bytes(b"jpg")
        vid = old + "/Eragon T01.cbz"
        ohara.save_state({"progress": {vid: {"page": 1}, "Naruto/Naruto T01.cbz": {"page": 2}}, "franky": {vid: [2, 1]},
                          "series": {old: {"follow": True, "decor": "vol:" + vid}}, "music": {old: {"state": "ready"}}, "chapters": {old: {"at": 1}},
                          "lookups": {ohara.norm(old): {"id": 9}}, "downloads": {"H": {"series": old}}})
        self.assertEqual(ohara.rename_series(old, "Eragon"), "Eragon")
        self.assertTrue((self.root / "Eragon" / "Eragon T01.cbz").exists())
        self.assertTrue((ohara.MUSIC / "Eragon" / "Album").exists())
        self.assertEqual(ohara.decor_file("Eragon").read_bytes(), b"jpg")
        state = ohara.load_state()
        self.assertEqual(reading(state), {"Eragon/Eragon T01.cbz": {"page": 1}, "Naruto/Naruto T01.cbz": {"page": 2}})
        self.assertEqual(state["franky"], {"Eragon/Eragon T01.cbz": [2, 1]})
        self.assertEqual(state["series"], {"Eragon": {"follow": True, "decor": "vol:Eragon/Eragon T01.cbz"}})
        self.assertEqual((list(state["music"]), list(state["chapters"])), (["Eragon"], ["Eragon"]))
        self.assertEqual(state["lookups"]["eragon"], {"id": 9})
        self.assertEqual(state["downloads"]["H"]["series"], "Eragon")
        for taken in ("Naruto", "", "Eragon"):
            with self.assertRaises(KeyError):
                ohara.rename_series("Eragon" if taken != "Eragon" else "Nobody", taken)


def mp3(title):
    """A tiny MP3 with an ID3v2.3 TIT2 frame."""
    text = b"\x03" + title.encode()
    frame = b"TIT2" + len(text).to_bytes(4, "big") + b"\x00\x00" + text
    size = len(frame)
    syncsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
    return b"ID3\x03\x00\x00" + syncsafe + frame + b"\xff\xfb" + b"\x00" * 64


def flac(title):
    """A tiny FLAC head: STREAMINFO, then a Vorbis comment with TITLE."""
    vendor = b"ohara"
    comment = f"TITLE={title}".encode()
    block = len(vendor).to_bytes(4, "little") + vendor + (1).to_bytes(4, "little") + len(comment).to_bytes(4, "little") + comment
    streaminfo = b"\x00" + (34).to_bytes(3, "big") + b"\x00" * 34
    return b"fLaC" + streaminfo + bytes([0x84]) + len(block).to_bytes(3, "big") + block


class BrookPicks(unittest.TestCase):
    def rel(self, title, cats=(3000,), seeders=5, size=500e6):
        return {"title": title, "categories": [{"id": c} for c in cats], "seeders": seeders, "size": size}

    def test_soundtracks_only(self):
        import brook
        names = brook.names_of("Frieren", {"names": ["Sousou no Frieren", "Frieren: Beyond Journey's End", "F"]})
        self.assertIn("sousounofrieren", names)
        self.assertNotIn("f", names)
        self.assertTrue(brook.is_soundtrack(self.rel("[ZAIA] Frieren Beyond Journey's End Original Soundtrack"), names))
        self.assertTrue(brook.is_soundtrack(self.rel("葬送のフリーレン Sousou no Frieren サウンドトラック", cats=(3040,)), names))
        self.assertFalse(brook.is_soundtrack(self.rel("Frieren OST", cats=(5070,)), names))
        self.assertFalse(brook.is_soundtrack(self.rel("Frieren Vol. 1 Unabridged Audiobook OST"), names))
        self.assertFalse(brook.is_soundtrack(self.rel("Frieren Opening Single"), names))
        self.assertFalse(brook.is_soundtrack(self.rel("Naruto OST"), names))

    def test_best_first(self):
        import brook
        self.assertEqual([brook.health(n) for n in (25, 10, 9, 3, 2, 1, 0)], [0, 0, 1, 1, 2, 2, 3])
        lime = self.rel("OP OST (Mp3 320kbps)", seeders=3, size=430e6)
        nyaa = self.rel("OP Original Soundtrack ELBAPH [FLAC]", seeders=18, size=340e6)
        self.assertEqual(sorted([lime, nyaa], key=brook.best_first), [nyaa, lime])
        found = [
            self.rel("A OST Collection", seeders=11, size=4.9e9),
            self.rel("A OST [FLAC]", seeders=3, size=900e6),
            self.rel("A OST (MP3 320)", seeders=2, size=300e6),
            self.rel("A OST mp3", seeders=0, size=600e6),
            self.rel("A Soundtrack", seeders=9, size=700e6),
        ]
        self.assertEqual([r["title"] for r in sorted(found, key=brook.best_first)],
                         ["A OST Collection", "A Soundtrack", "A OST [FLAC]", "A OST (MP3 320)", "A OST mp3"])
        self.assertEqual(brook.size_penalty(1e9), 0)
        self.assertGreater(brook.size_penalty(10e9), brook.size_penalty(5e9))

    def test_titles(self):
        import brook
        self.assertEqual(brook.clean_title("01 - We Are!"), "We Are!")
        self.assertEqual(brook.clean_title("Disc 2 - 07_Overtaken"), "Overtaken")
        self.assertEqual(brook.clean_title("12. Binks no Sake"), "Binks no Sake")
        self.assertEqual(brook.clean_title("Interlude"), "Interlude")
        self.assertEqual(brook.clean_title("01"), "01")
        self.assertEqual(brook.track_title(Path("x/01 - a.mp3"), mp3("Mabataki")), "Mabataki")
        self.assertEqual(brook.track_title(Path("x/02 - b.flac"), flac("Zoltraak")), "Zoltraak")
        self.assertEqual(brook.track_title(Path("x/01.mp3"), mp3("01_Shippuuden")), "Shippuuden")
        self.assertEqual(brook.track_title(Path("x/03.mp3"), mp3("03_ Homecoming")), "Homecoming")
        self.assertEqual(brook.track_title(Path("x/07.mp3"), mp3("7 Seas")), "7 Seas")
        self.assertEqual(brook.track_title(Path("x/09.mp3"), mp3("09.")), "09.")
        self.assertEqual(brook.track_title(Path("x/03 - Untagged.mp3"), b"\xff\xfb\x00"), "Untagged")
        self.assertEqual(brook.track_title(Path("x/04 - Ogg.ogg"), b""), "Ogg")
        self.assertIsNone(brook.flac_title(b"fLaC" + bytes([0x80]) + (4).to_bytes(3, "big") + b"\x00" * 4))
        self.assertIsNone(brook.id3_title(b"ID3\x04\x00\x00\x00\x00\x00\x0a" + b"\x00" * 10))
        self.assertIsNone(brook.decode_text(b""))

    def test_album_of(self):
        import brook
        self.assertEqual(brook.album_of("Season 1/01 - a.mp3"), "Season 1")
        self.assertEqual(brook.album_of("01 - a.mp3"), "")
        self.assertEqual(brook.album_name("[261028] ONE PIECE Original Soundtrack ELBAPH part 1 [FLAC]"), "ONE PIECE Original Soundtrack ELBAPH part 1")
        self.assertEqual(brook.album_name("Season 1"), "Season 1")
        self.assertEqual(brook.album_name("[FLAC]"), "[FLAC]")


class Brook(Library):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(ohara, "MUSIC", self.root / ".ost")
        p.start()
        self.addCleanup(p.stop)

    def test_find_soundtracks(self):
        results = [
            {"guid": "a", "title": "Frieren Original Soundtrack [FLAC]", "categories": [{"id": 3000}], "seeders": 20, "size": 3e8, "indexer": "Nyaa.si"},
            {"guid": "b", "title": "Frieren T01 [CBZ]", "categories": [{"id": 7000}], "seeders": 50, "size": 3e8, "indexer": "Nyaa.si"},
        ]
        with mock.patch.object(ohara, "lookup", return_value={"names": ["Sousou no Frieren"]}), \
                mock.patch.object(ohara, "prowlarr_key", return_value="K"), mock.patch.object(ohara, "audio_indexer_ids", return_value=[1]), \
                mock.patch.object(ohara, "http_json", return_value=results) as http:
            found = ohara.find_soundtracks("Frieren")
            self.assertEqual([r["title"] for r in found], ["Frieren Original Soundtrack [FLAC]"])
            self.assertIn("categories=3000", http.call_args_list[0][0][0])
            ohara.save_state({"music": {"Frieren": {"state": "none", "skipped": ["Frieren Original Soundtrack [FLAC]"]}}})
            self.assertEqual(ohara.find_soundtracks("Frieren"), [])

    def test_soundtracks_of_a_colour_edition_each_title_once(self):
        results = [
            {"guid": "a", "title": "One Piece OST [MP3]", "categories": [{"id": 3000}], "seeders": 4, "size": 3e8, "indexer": "Nyaa.si"},
            {"guid": "b", "title": "One Piece OST [MP3]", "categories": [{"id": 3000}], "seeders": 40, "size": 3e8, "indexer": "Knaben"},
        ]
        with mock.patch.object(ohara, "lookup", return_value={}) as lookup, \
                mock.patch.object(ohara, "prowlarr_key", return_value="K"), mock.patch.object(ohara, "audio_indexer_ids", return_value=[1]), \
                mock.patch.object(ohara, "http_json", return_value=results) as http:
            found = ohara.find_soundtracks("One Piece en couleurs")
        self.assertEqual([(r["title"], r["seeders"]) for r in found], [("One Piece OST [MP3]", 40)])
        lookup.assert_called_once_with("One Piece")
        self.assertIn("query=One+Piece+OST", http.call_args_list[0][0][0])

    def test_audio_indexers(self):
        found = [{"id": 1, "enable": True, "capabilities": {"categories": [{"id": 3000}]}},
                 {"id": 2, "enable": True, "capabilities": {"categories": [{"id": 7000}]}},
                 {"id": 3, "enable": False, "capabilities": {"categories": [{"id": 3040}]}},
                 {"id": 4, "enable": True}]
        with mock.patch.object(ohara, "http_json", return_value=found):
            self.assertEqual(ohara.audio_indexer_ids("K"), [1])

    def test_a_soundtrack_that_never_starts_is_given_up(self):
        d = {"series": "One Piece", "title": "OP OST", "folder": "ost-1", "kind": "ost", "at": 1000}
        self.assertFalse(ohara.stalled(d, {"percentDone": 0}, 1000 + 3600))
        self.assertTrue(ohara.stalled(d, {"percentDone": 0}, 1000 + 7 * 3600))
        self.assertFalse(ohara.stalled(d, {"percentDone": 0.01}, 1000 + 7 * 3600))
        self.assertFalse(ohara.stalled(dict(d, kind="volumes"), {"percentDone": 0}, 1000 + 7 * 3600))
        ohara.save_state({"downloads": {"H": d}, "music": {"One Piece": {"state": "downloading", "title": "OP OST", "skipped": ["older"]}}})
        with mock.patch.object(ohara, "torrents", return_value=[{"hashString": "H", "percentDone": 0}]), mock.patch.object(ohara, "rpc") as rpc:
            ohara.check_downloads()
        rpc.assert_called_once_with("torrent-remove", {"ids": ["H"], "delete-local-data": True})
        state = ohara.load_state()
        self.assertEqual(state["downloads"], {})
        self.assertEqual(state["music"]["One Piece"]["skipped"], ["older", "OP OST"])
        self.assertEqual(ohara.music_status("One Piece"), {"state": "none"})
        ohara.set_music("One Piece", state="searching")
        self.assertEqual(ohara.load_state()["music"]["One Piece"]["skipped"], ["older", "OP OST"])

    def test_grab_the_best_or_say_none(self):
        best = {"token": "t1", "title": "Frieren OST", "seeders": 3, "_url": "magnet:?x"}
        with mock.patch.object(ohara, "find_soundtracks", return_value=[dict(best, seeders=0)]):
            self.assertEqual(ohara.grab_music("Frieren"), {"state": "notfound"})
        with mock.patch.object(ohara, "find_soundtracks", return_value=[best]), \
                mock.patch.object(ohara, "rpc", return_value={"torrent-added": {"hashString": "H"}}) as rpc:
            status = ohara.grab_music("Frieren")
        self.assertEqual(status, {"state": "downloading", "title": "Frieren OST"})
        self.assertIn("/ost-", rpc.call_args[0][1]["download-dir"])
        self.assertEqual(ohara.load_state()["downloads"]["H"]["kind"], "ost")
        ohara.found_releases["t2"] = dict(best, token="t2")
        with mock.patch.object(ohara, "rpc", return_value={"torrent-duplicate": {"hashString": "H2"}}):
            ohara.grab_music("Frieren", "t2")
        with self.assertRaises(KeyError):
            ohara.grab_music("Frieren", "unknown")

    def test_import_by_album_with_covers_and_archives(self):
        src = self.root / ".incoming" / "ost-1"
        (src / "Frieren OST" / "Disc 1").mkdir(parents=True)
        (src / "Frieren OST" / "Disc 1" / "01 - Zoltraak.flac").write_bytes(flac("Zoltraak"))
        (src / "Frieren OST" / "Disc 1" / "folder.jpg").write_bytes(b"jpg")
        (src / "loose.mp3").write_bytes(mp3("Loose"))
        (src / "Bonus.zip").write_bytes(b"zip")

        def fake_7z(cmd, check, capture_output):
            out = Path(cmd[3][2:])
            out.mkdir()
            (out / "Bonus 1.mp3").write_bytes(mp3("Extra"))

        with mock.patch("subprocess.run", side_effect=fake_7z):
            self.assertEqual(ohara.import_music(src, "Frieren"), 3)
        found = {a["name"]: a for a in ohara.albums("Frieren")}
        self.assertEqual(set(found), {"Disc 1", "Bonus", "Frieren"})
        self.assertEqual(found["Disc 1"]["tracks"][0]["title"], "Zoltraak")
        self.assertEqual(found["Disc 1"]["art"], "Frieren/Disc 1/cover.jpg")
        self.assertEqual(found["Frieren"]["tracks"], [{"id": "Frieren/Frieren/loose.mp3", "title": "Loose"}])
        self.assertEqual(ohara.music_status("Frieren"), {"state": "ready"})
        empty = self.root / ".incoming" / "ost-2"
        empty.mkdir(parents=True)
        self.assertEqual(ohara.import_music(empty, "Empty"), 0)
        self.assertEqual(ohara.music_status("Empty"), {"state": "notfound"})

    def test_music_moods_and_paths(self):
        folder = self.root / ".ost" / "Frieren" / "Season 1"
        folder.mkdir(parents=True)
        (folder / "01 - a.mp3").write_bytes(mp3("Journey"))
        m = ohara.music("Frieren")
        self.assertEqual(m["status"], {"state": "ready"})
        self.assertEqual(m["albums"][0]["tracks"], [{"id": "Frieren/Season 1/01 - a.mp3", "title": "Journey"}])
        self.assertEqual(ohara.set_mood("Frieren", " Calme ", ["Frieren/Season 1/01 - a.mp3", 3])["moods"], [{"name": "Calme", "tracks": ["Frieren/Season 1/01 - a.mp3"]}])
        self.assertEqual(ohara.set_mood("Frieren", "Calme", [])["moods"], [])
        with self.assertRaises(KeyError):
            ohara.set_mood("Frieren", " ", ["x"])
        self.assertEqual(ohara.music_path("Frieren/Season 1/01 - a.mp3").name, "01 - a.mp3")
        for bad in ("../state.json", "Frieren/none.mp3"):
            with self.assertRaises(KeyError):
                ohara.music_path(bad)
        self.assertEqual(ohara.albums("Nothing"), [])

    def test_titles_in_japanese_are_translated_once_and_kept(self):
        folder = self.root / ".ost" / "One Piece" / "[261028] エルバフ OST [FLAC]"
        folder.mkdir(parents=True)
        (folder / "01. a.mp3").write_bytes(mp3("エルバフの宴"))
        (folder / "02. b.mp3").write_bytes(mp3("MMA"))

        class Now:  # the translation runs at once, not in the background
            def __init__(self, target, args, daemon):
                self.run = lambda: target(*args)

            def start(self):
                self.run()
        google = lambda lines: [[[lines, "x"]], None, "ja"]
        answers = {"エルバフ OST\nエルバフの宴": google("Elbaph OST\nLe banquet d'Elbaph")}
        asked = lambda url, headers, timeout: answers[urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["q"][0]]
        with mock.patch.object(ohara.threading, "Thread", Now), mock.patch.object(ohara, "http_json", side_effect=asked) as http:
            first = ohara.music("One Piece", "fr")
            self.assertTrue(first["translating"])
            self.assertEqual(first["albums"][0]["tracks"][0]["title"], "エルバフの宴")  # not yet
            m = ohara.music("One Piece", "xx")  # an unknown language: French
        self.assertEqual(http.call_count, 1)
        self.assertIn("tl=fr", http.call_args[0][0])
        self.assertFalse(m["translating"])
        self.assertEqual([t["title"] for t in m["albums"][0]["tracks"]], ["Le banquet d'Elbaph (エルバフの宴)", "MMA"])
        self.assertEqual((m["albums"][0]["id"], m["albums"][0]["name"]), ("エルバフ OST", "Elbaph OST (エルバフ OST)"))
        self.assertNotIn("translating", ohara.music("One Piece"))
        ohara.translations["kept"] = None
        with mock.patch.object(ohara, "http_json", side_effect=AssertionError("not again")):
            self.assertEqual(ohara.music("One Piece", "fr")["albums"][0]["tracks"][0]["title"], "Le banquet d'Elbaph (エルバフの宴)")
        self.assertEqual(ohara.said_title("MMA", "MMA"), "MMA")
        self.assertEqual(ohara.said_title("宴", "fête d'Elbaph"), "Fête d'Elbaph (宴)")

    def test_a_batch_that_loses_its_lines_is_translated_line_by_line(self):
        said = {"一\n二": [[["un deux", "x"]]], "一": [[["un", "x"]]], "二": [[["deux\n", "x"], [None]]]}
        asked = lambda url, headers, timeout: said[urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["q"][0]]
        with mock.patch.object(ohara, "http_json", side_effect=asked):
            self.assertEqual(ohara.translate(["一", "二"], "fr"), {"一": "un", "二": "deux"})

    def test_google_away_waits_an_hour(self):
        found = [{"name": "x", "tracks": [{"id": "a", "title": "宴"}]}]
        with mock.patch.object(ohara, "http_json", side_effect=OSError("offline")):
            ohara.translate_missing(["宴"], "fr")
        self.assertGreater(ohara.translations["failed"], 0)
        with mock.patch.object(ohara.threading, "Thread", side_effect=AssertionError("not now")):
            self.assertFalse(ohara.say_titles(found, "fr"))
        with ohara.translating:  # another series being translated: this one waits its turn
            ohara.translate_missing(["宴"], "fr")
        self.assertEqual(ohara.kept_translations(), {})

    def test_brook_pass_one_series_at_a_time(self):
        for name in ("Berserk", "Frieren"):
            cbz(self.root / name / "T01.cbz", ["1.png"])
        ohara.set_settings({"brook": False})
        self.assertIsNone(ohara.brook_pass())
        ohara.set_settings({"brook": True})
        with mock.patch.object(ohara, "grab_music", return_value={"state": "downloading"}) as grab:
            self.assertEqual(ohara.brook_pass(), {"state": "downloading"})
        grab.assert_called_once_with("Berserk")
        ohara.set_music("Berserk", state="downloading")
        with mock.patch.object(ohara, "grab_music", side_effect=OSError("prowlarr away")):
            self.assertIsNone(ohara.brook_pass())
        self.assertEqual(ohara.music_status("Frieren"), {"state": "error"})
        ohara.set_music("Frieren", state="notfound")
        self.assertIsNone(ohara.brook_pass())

    def test_a_colour_edition_plays_the_originals_music(self):
        folder = self.root / ".ost" / "One Piece" / "OST 1"
        folder.mkdir(parents=True)
        (folder / "01 - a.mp3").write_bytes(mp3("We Are!"))
        ohara.set_mood("One Piece en couleurs", "Combat", ["One Piece/OST 1/01 - a.mp3"])
        self.assertEqual(ohara.music("One Piece en couleurs"), ohara.music("One Piece"))
        self.assertEqual(ohara.music("One Piece")["moods"], [{"name": "Combat", "tracks": ["One Piece/OST 1/01 - a.mp3"]}])
        with mock.patch.object(ohara, "find_soundtracks", return_value=[]) as find:
            self.assertEqual(ohara.grab_music("One Piece en couleurs"), {"state": "notfound"})
        find.assert_called_once_with("One Piece")
        self.assertEqual(ohara.music_status("One Piece"), {"state": "notfound"})

    def test_brook_looks_once_for_an_original_and_its_colour_edition(self):
        for name in ("One Piece en couleurs", "One Piece"):
            cbz(self.root / name / "T01.cbz", ["1.png"])
        ohara.set_settings({"brook": True})
        with mock.patch.object(ohara, "grab_music", return_value={"state": "downloading"}) as grab:
            ohara.brook_pass()
        grab.assert_called_once_with("One Piece")
        self.assertEqual(set(ohara.load_state()["music"]), {"One Piece"})

    def test_when_brook_looks_again(self):
        self.assertTrue(ohara.music_due(None, 0))
        self.assertTrue(ohara.music_due({"state": "none", "at": 5}, 6))
        self.assertFalse(ohara.music_due({"state": "downloading", "at": 0}, 10 ** 9))
        self.assertFalse(ohara.music_due({"state": "error", "at": 1000}, 1000 + 1800))
        self.assertTrue(ohara.music_due({"state": "error", "at": 1000}, 1000 + 3601))
        self.assertFalse(ohara.music_due({"state": "notfound", "at": 0}, 86400))
        self.assertTrue(ohara.music_due({"state": "notfound", "at": 0}, 8 * 86400))

    def test_track_streaming_with_ranges(self):
        folder = self.root / ".ost" / "Frieren"
        folder.mkdir(parents=True)
        (folder / "a.mp3").write_bytes(bytes(range(100)))
        (folder / "cover.jpg").write_bytes(b"jpg")
        fake = Http("test_log_is_quiet")
        fake.root = self.root
        code, head, body = fake.call("GET", "/api/track?id=Frieren/a.mp3")
        self.assertEqual((code, len(body)), (200, 100))
        self.assertIn("audio/mpeg", head)
        code, head, body = fake.call_range("/api/track?id=Frieren/a.mp3", "bytes=10-19")
        self.assertEqual((code, body), (206, bytes(range(10, 20))))
        self.assertIn("Content-Range: bytes 10-19/100", head)
        code, _, body = fake.call_range("/api/track?id=Frieren/a.mp3", "bytes=-5")
        self.assertEqual(body, bytes(range(95, 100)))
        code, _, body = fake.call_range("/api/track?id=Frieren/a.mp3", "bytes=90-")
        self.assertEqual(body, bytes(range(90, 100)))
        self.assertEqual(fake.call("GET", "/api/art?id=Frieren/cover.jpg")[2], b"jpg")


class Main(Library):
    def test_main_starts_the_watch_and_the_server(self):
        with mock.patch.object(ohara.threading, "Thread") as thread, mock.patch.object(ohara, "ThreadingHTTPServer") as server:
            ohara.main()
        self.assertEqual(thread.return_value.start.call_count, 4)
        server.return_value.serve_forever.assert_called_once()
        self.assertTrue((self.root / ".incoming").is_dir())


if __name__ == "__main__":
    unittest.main()
