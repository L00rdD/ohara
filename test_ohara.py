"""Tests of ohara.py, without Prowlarr, Transmission or a socket:
python3 -m unittest test_ohara.py"""

import base64
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ohara)


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
        self.assertEqual(meta, {"id": 5, "title": "Sousou no Frieren", "cover": "http://c/l.jpg", "color": "#e4ae5d", "banner": None, "names": ["Sousou no Frieren"], "status": "En cours", "volumes": None, "year": 2020})
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
        ohara.save_state({"downloads": {"H": {"series": "Naruto"}}, "lookups": {"old": {"id": 1}}})
        cbz(self.root / "Old" / "T1.cbz", ["1.png"])
        with mock.patch.object(ohara, "anilist_fetch", side_effect=lambda n: {"id": 5} if n == "Frieren" else {"id": 7} if n == "Naruto" else {}):
            ohara.refresh_meta()
        state = ohara.load_state()
        self.assertEqual(state["series"]["Frieren"]["anilist"], 5)
        self.assertNotIn("Unknown", state["series"])
        self.assertEqual(state["lookups"]["unknown"], {})
        self.assertEqual(state["lookups"]["naruto"], {"id": 7})
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

    def test_plain_images_become_one_volume_per_folder(self):
        src = self.root / ".incoming" / "f3"
        for folder in ("Tome 2", "Tome 1"):
            (src / folder).mkdir(parents=True)
            for n in (10, 2, 1):
                (src / folder / f"{n}.jpg").write_bytes(b"j")
        self.assertEqual(ohara.import_download(src, "Frieren"), 2)
        with zipfile.ZipFile(self.root / "Frieren" / "Tome 1.cbz") as z:
            self.assertEqual(z.namelist(), ["1.jpg", "2.jpg", "10.jpg"])

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
        before = ohara.load_state()["progress"]["Naruto/Naruto T02.cbz"]["at"]
        ohara.mark_read(["Naruto/Naruto T01.cbz", "Naruto/Naruto T02.cbz", "Naruto/Naruto T03.pdf"], True)
        progress = ohara.load_state()["progress"]
        self.assertEqual(progress["Naruto/Naruto T01.cbz"], {"page": 1, "pages": 2, "at": 0})
        self.assertEqual(progress["Naruto/Naruto T02.cbz"]["at"], before)
        self.assertEqual(progress["Naruto/Naruto T03.pdf"], {"page": 0, "pages": 1, "at": 0})
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            lib = ohara.library()
        self.assertEqual([v["done"] for v in lib["series"][0]["volumes"]], [True, True, True, False])
        self.assertEqual(lib["last"]["id"], "Naruto/Naruto T02.cbz")
        ohara.mark_read(["Naruto/Naruto T01.cbz"], False)
        self.assertNotIn("Naruto/Naruto T01.cbz", ohara.load_state()["progress"])
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
        self.assertEqual(info, {"id": "Naruto/Naruto T02.cbz", "series": "Naruto", "label": "Tome 2", "count": 2, "page": 1, "next": "Naruto/Naruto T04.cbz"})
        self.assertIsNone(ohara.volume_pages("Naruto/Naruto T04.cbz")["next"])

    def test_pages_the_size_of_a_screen(self):
        from PIL import Image
        self.assertEqual([ohara.page_width(w) for w in (None, "", "x", -3, 700, 1200, 1201, 2400, 3000)], [0, 0, 0, 0, 800, 1200, 1600, 2400, 0])
        path = self.root / "Manga" / "Manga T01.cbz"
        path.parent.mkdir(parents=True)
        with zipfile.ZipFile(path, "w") as z:
            for name, size, mode in (("1.jpg", (3000, 2000), "L"), ("2.png", (900, 1300), "RGB")):
                b = io.BytesIO()
                Image.new(mode, size, 128).save(b, "JPEG" if name.endswith("jpg") else "PNG")
                z.writestr(name, b.getvalue())
        made = ohara.size_page(path, 0, 1200)
        img = Image.open(made)
        self.assertEqual((img.size, img.mode), ((1200, 800), "L"))
        self.assertIsNone(ohara.size_page(path, 1, 800))  # hardly wider: as it is
        with mock.patch.object(ohara, "page_bytes", side_effect=AssertionError("not again")):
            self.assertEqual(ohara.size_page(path, 0, 1200), made)
            self.assertIsNone(ohara.size_page(path, 1, 800))

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
        self.assertEqual(ohara.load_state(), {"downloads": {}, "progress": {}, "series": {}, "lookups": {}, "settings": {}, "spines": {}, "music": {}, "moods": {}})


class Http(Reading):
    def call(self, method, path, body=None):
        h = ohara.Handler.__new__(ohara.Handler)
        h.path, h.command, h.request_version, h.requestline = path, method, "HTTP/1.1", ""
        raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b""
        h.headers = {"Content-Length": str(len(raw))}
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
        with mock.patch.object(ohara, "music", return_value={"albums": []}):
            self.assertEqual(json.loads(self.call("GET", "/api/music?series=N")[2]), {"albums": []})
        with mock.patch.object(ohara, "find_soundtracks", return_value=[{"token": "t", "_url": "x"}]):
            self.assertEqual(json.loads(self.call("GET", "/api/soundtracks?series=N")[2]), [{"token": "t"}])
        with mock.patch.object(ohara, "grab_music", return_value={"state": "downloading"}) as grab:
            self.assertEqual(self.call("POST", "/api/music", {"series": "N"})[0], 200)
        grab.assert_called_once_with("N", None)
        with mock.patch.object(ohara, "set_mood", return_value={"moods": []}) as mood:
            self.call("POST", "/api/mood", {"series": "N", "name": "Calme", "tracks": ["a"]})
        mood.assert_called_once_with("N", "Calme", ["a"])

    def test_pages_api(self):
        code, _, body = self.call("GET", "/api/pages?vol=Naruto%2FNaruto%20T01.cbz")
        self.assertEqual((code, json.loads(body)["count"]), (200, 2))
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
        self.assertEqual(ohara.load_state()["progress"]["Naruto/Naruto T01.cbz"]["page"], 1)

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
        self.assertEqual(json.loads(self.call("GET", "/api/settings")[2]), {"spines": "tome", "brook": True})
        self.assertEqual(json.loads(self.call("POST", "/api/settings", {"spines": "sobre", "brook": False})[2]), {"spines": "sobre", "brook": False})
        self.assertEqual(self.call("GET", "/api/crop?vol=Naruto/Naruto%20T01.cbz")[0], 404)
        ohara.read_spine(self.root / "Naruto" / "Naruto T01.cbz")
        with mock.patch.object(ohara, "warm") as warm:
            code, _, payload = self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz&w=1000")
        self.assertEqual((code, json.loads(payload)["count"]), (200, 2))
        warm.assert_called_once_with((self.root / "Naruto" / "Naruto T01.cbz").resolve(), 1200, 0)
        with mock.patch.object(ohara, "warm") as warm:
            self.call("GET", "/api/pages?vol=Naruto/Naruto%20T01.cbz")
        warm.assert_not_called()
        sized = self.root / "sized.jpg"
        sized.write_bytes(b"SMALL")
        with mock.patch.object(ohara, "size_page", return_value=sized):
            code, head, payload = self.call("GET", "/api/page?vol=Naruto/Naruto%20T01.cbz&n=0&w=800")
        self.assertEqual((code, payload), (200, b"SMALL"))
        self.assertIn("image/jpeg", head)
        with mock.patch.object(ohara, "size_page", return_value=None):
            code, head, payload = self.call("GET", "/api/page?vol=Naruto/Naruto%20T01.cbz&n=0&w=800")
        self.assertIn("image/png", head)
        code, head, _ = self.call("GET", "/api/crop?vol=Naruto/Naruto%20T01.cbz")
        self.assertEqual(code, 200)
        self.assertIn("image/jpeg", head)
        with mock.patch.object(ohara, "mark_read", return_value={"ok": True}) as mark:
            self.assertEqual(self.call("POST", "/api/read", {"vols": ["a", 3], "read": 1})[0], 200)
        mark.assert_called_once_with(["a"], True)
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
        cancel.assert_called_once_with("H")

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
        self.assertFalse(ohara.same_series(original, "One Piece", {}, facts))

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
                mock.patch.object(ohara, "read_spines") as spines, mock.patch.object(ohara, "brook_pass") as brook:
            ohara.tick()
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
        self.assertEqual(ohara.settings(), {"spines": "tome", "brook": True})
        self.assertEqual(ohara.set_settings({"spines": "reliure"})["spines"], "reliure")
        self.assertEqual(ohara.set_settings({"spines": "neon", "brook": "yes"}), {"spines": "reliure", "brook": True})


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
        self.assertEqual(thread.return_value.start.call_count, 2)
        server.return_value.serve_forever.assert_called_once()
        self.assertTrue((self.root / ".incoming").is_dir())


if __name__ == "__main__":
    unittest.main()
