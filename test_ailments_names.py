"""Tests of Chopper's examinations of names and numbers (ailments_names.py), on
snapshots made by hand, and of their cures on a temporary library:
python3 -m unittest test_ailments_names.py"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = sys.modules.get("ohara")
if ohara is None:
    ohara = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ohara)
    sys.modules["ohara"] = ohara  # as it is when it runs: Chopper's remedies are given it

import ailments_names as an  # noqa: E402
from names import volume_number  # noqa: E402


def vol(series, file):
    return {"id": f"{series}/{file}", "file": file, "number": volume_number(file)}


def series(name, files, meta=None):
    return {"name": name, "volumes": [vol(name, f) for f in files], "meta": meta or {}}


def snap(*shelves):
    return {"series": list(shelves)}


def ids(found):
    return [a["id"] for a in found]


class Readings(unittest.TestCase):
    def test_small_readings(self):
        self.assertEqual(an.word_list("L'Aîné - Christopher_Paolini"), ["l", "aine", "christopher", "paolini"])
        self.assertTrue(an.part_of(["eragon"], ["christopher", "paolini", "eragon"]))
        self.assertFalse(an.part_of(["eragon"], ["eragon"]))
        self.assertFalse(an.holds([], ["eragon"]))
        self.assertEqual([an.roman(r) for r in ("I", "IV", "IX", "XII", "MCMXC", "", "IIII", "Vi")], [1, 4, 9, 12, 1990, None, None, None])
        self.assertEqual((an.tome(7, 3), an.tome(10.5, 2), an.tome(3.0, 2)), ("T007", "T10.5", "T03"))
        self.assertEqual((an.width([1, 9]), an.width([105.0]), an.width([])), (2, 3, 2))
        self.assertEqual(an.shown(list("abcde")), "a, b, c, d, …")
        self.assertEqual(an.pattern("One Piece Tome 109 - Scan.cbz"), an.pattern("One Piece Tome 1 - Scan.epub"))

    def test_numbers_read_where_the_names_differ(self):
        self.assertEqual(an.pattern_numbers(["Eragon I", "Eragon II", "Eragon III"]), [1, 2, 3])
        self.assertEqual(an.pattern_numbers(["Naruto (1)", "Naruto (10)", "Naruto (2)"]), [1, 10, 2])
        self.assertEqual(an.pattern_numbers(["Livre I - Eragon", "Livre II - L'Aîné"]), [1, 2])
        for names in (["Naruto Gaiden", "Naruto Hiden"], ["Eragon I"], ["A (1)", "A (1)b"], ["Ab", "A"]):
            self.assertIsNone(an.pattern_numbers(names), names)

    def test_folder_names_stripped(self):
        cases = {"[Team X] Naruto": "Naruto", "Naruto (2002) FR": "Naruto", "Naruto - Scan": "Naruto",
                 "Naruto 2002 VF": "Naruto", "Naruto Tomes 1-72": "Naruto", "Dr. Stone": "Dr. Stone", "[FR]": ""}
        for name, bare in cases.items():
            self.assertEqual(an.stripped(name), bare, name)

    def test_the_parts_of_a_file_name_that_could_be_a_title(self):
        self.assertEqual(an.file_segments("1 - Eragon - Christopher Paolini"), ["Eragon", "Christopher Paolini"])
        self.assertEqual(an.file_segments("1-Eragon-Christopher-Paolini"), ["Eragon", "Christopher", "Paolini"])
        self.assertEqual(an.file_segments("One Piece 105 (2023)"), ["One Piece"])
        self.assertEqual(an.file_segments("[Compressé] Naruto [Team Chromatique] - Tome #001 - [V2]"), ["Naruto"])

    def test_the_examinations_are_chopper_s(self):
        for fn in (an.volumes_without_number, an.folder_names, an.files_named_in_several_ways):
            self.assertIn(fn, an.chopper.EXAMS)
        self.assertIs(an.chopper.CURES["names_rename_files"], an.rename_files)
        self.assertIs(an.chopper.CURES["names_rename_folder"], an.rename_folder)


class Unnumbered(unittest.TestCase):
    def test_volumes_numbered_in_name_order(self):
        s = series("Eragon", ["Eragon.epub", "Eragon.pdf", "L'Aîné.epub", "Brisingr.epub"])
        [a] = an.volumes_without_number(snap(s))
        self.assertEqual((a["id"], a["series"], a["severity"]), ("unnumbered:Eragon", "Eragon", "trouble"))
        self.assertEqual(a["text"]["fr"], "« Eragon » : 4 tomes sans numéro (Brisingr.epub, Eragon.epub, Eragon.pdf, L'Aîné.epub).")
        [r] = a["remedies"]
        self.assertEqual((r["kind"], r["risky"], r["args"]["series"]), ("names_rename_files", True, "Eragon"))
        self.assertEqual(r["args"]["names"], [["Eragon/Brisingr.epub", "Eragon T01.epub"], ["Eragon/Eragon.epub", "Eragon T02.epub"],
                                              ["Eragon/Eragon.pdf", "Eragon T02.pdf"], ["Eragon/L'Aîné.epub", "Eragon T03.epub"]])
        self.assertEqual(r["label"]["fr"], "Les numéroter dans l'ordre des noms (« Eragon T01.epub »…)")
        self.assertEqual(ids(an.volumes_without_number(snap(s))), ids([a]))  # the same id, examination after examination

    def test_numbers_read_in_the_names_come_first(self):
        s = series("Eragon", ["Eragon I.epub", "Eragon II.epub", "Eragon III.epub", "Eragon IV.epub", "Eragon V.epub"])
        [a] = an.volumes_without_number(snap(s))
        by_pattern, by_name = a["remedies"]
        self.assertEqual(by_pattern["label"]["en"], "Read their number in their name (« Eragon T01.epub »…)")
        self.assertEqual([new for _, new in by_pattern["args"]["names"]], [f"Eragon T0{n}.epub" for n in (1, 2, 3, 4, 5)])
        # name order: I, II, III, IV, V, the fourth and fifth in another order
        self.assertEqual(by_name["args"]["names"][3], ["Eragon/Eragon IV.epub", "Eragon T04.epub"])
        self.assertIn(", …)", a["text"]["en"])

    def test_beside_numbered_volumes_only_a_reading_that_takes_no_number_twice(self):
        held = series("Naruto", ["Naruto T01.cbz", "Naruto (02).cbz", "Naruto (03).cbz"])
        [a] = an.volumes_without_number(snap(held))
        self.assertEqual(a["remedies"][0]["args"]["names"], [["Naruto/Naruto (02).cbz", "Naruto T02.cbz"], ["Naruto/Naruto (03).cbz", "Naruto T03.cbz"]])
        clash = series("Naruto", ["Naruto T01.cbz", "Naruto (01).cbz", "Naruto (03).cbz"])
        gaiden = series("Naruto", ["Naruto T01.cbz", "Naruto Gaiden.cbz"])
        lone = series("Akira", ["Akira.cbz"])
        numbered = series("Bleach", ["Bleach T01.cbz", "Bleach T02.cbz"])
        self.assertEqual(an.volumes_without_number(snap(clash, gaiden, lone, numbered)), [])

    def test_a_volume_already_so_named_is_left_out(self):
        self.assertIsNone(an.numbering_remedy(None, None, None))
        s = series("A", ["A T01.cbz", "A T02.cbz"])
        numbered = [(v, v["number"]) for v in s["volumes"]]
        self.assertIsNone(an.numbering_remedy(s, numbered, lambda first: first))


class FolderNames(unittest.TestCase):
    def test_a_folder_named_after_its_author(self):
        files = ["1 - Eragon - Christopher Paolini.epub", "1-Eragon-Christopher-Paolini.pdf", "2 - L'Aine - Christopher Paolini.epub",
                 "2-L_Aine-Christopher-Paolini.pdf", "3 - Brisingr - Christopher Paolini.epub"]
        s = series("Christopher Paolini Eragon", files)
        [a] = an.folder_names(snap(s))
        self.assertEqual((a["id"], a["severity"]), ("folder_name:Christopher Paolini Eragon", "advice"))
        self.assertEqual(a["text"]["fr"], "Le dossier « Christopher Paolini Eragon » porte le nom de l'auteur, « Christopher Paolini ».")
        [r] = a["remedies"]
        self.assertEqual((r["kind"], r["risky"], r["args"]), ("names_rename_folder", True, {"old": "Christopher Paolini Eragon", "new": "Eragon"}))
        self.assertEqual(r["label"], {"fr": "Renommer le dossier en « Eragon »", "en": "Rename the folder « Eragon »"})
        taken = series("Eragon", ["Eragon T01.cbz"])
        self.assertEqual(an.folder_names(snap(s, taken)), [])  # the name is another series'

    def test_a_folder_with_junk_around_the_title(self):
        meta = {"title": "NARUTO", "names": ["NARUTO", "Naruto"]}
        s = series("[Team X] Naruto (2002) FR", ["[Team X] Naruto T01.cbz", "[Team X] Naruto T02.cbz"], meta)
        [a] = an.folder_names(snap(s))
        self.assertEqual(a["text"]["en"], "The folder « [Team X] Naruto (2002) FR » holds more than the series' title.")
        self.assertEqual([r["args"]["new"] for r in a["remedies"]], ["NARUTO", "Naruto"])
        scan = series("Naruto - Scan", ["Naruto - Scan 01.cbz", "Naruto - Scan 02.cbz"])
        self.assertEqual([r["args"]["new"] for r in an.folder_names(snap(scan))[0]["remedies"]], ["Naruto"])

    def test_a_folder_holding_a_name_of_the_series_and_more(self):
        meta = {"title": "Jujutsu Kaisen", "names": ["Sorcery Fight"]}
        s = series("Sorcery Fight Akutami", ["JJK T01.cbz", "JJK T02.cbz"], meta)
        [a] = an.folder_names(snap(s))
        self.assertEqual(a["text"]["fr"], "Le dossier « Sorcery Fight Akutami » ne porte peut-être pas que le titre de la série.")
        self.assertEqual([r["args"]["new"] for r in a["remedies"]], ["Jujutsu Kaisen"])
        both = series("Kishimoto - Naruto", ["Kishimoto - Naruto T01.cbz", "Kishimoto - Naruto T02.cbz"])
        self.assertEqual([r["args"]["new"] for r in an.folder_names(snap(both))[0]["remedies"]], ["Kishimoto", "Naruto"])

    def test_a_folder_named_well_is_left_alone(self):
        shelves = [series("One Piece", ["One Piece T001.cbz", "One Piece 105 (2023).cbz"], {"title": "One Piece", "names": ["ONE PIECE"]}),
                   series("Harry Potter", ["Rowling J. K - Harry Potter [Tome 1] - Harry Potter à l_école des sorciers.epub",
                                           "Rowling J. K - Harry Potter [Tome 2] - Harry Potter et la chambre des secrets.epub"]),
                   series("Shingeki", ["Shingeki T01.cbz"], {"title": "Attack on Titan", "names": []}),
                   series("Dr. Stone", ["Dr. Stone T01.cbz"], {"title": None})]
        self.assertEqual(an.folder_names(snap(*shelves)), [])


class FileNames(unittest.TestCase):
    FILES = ["One Piece 105 (2023).cbz", "One Piece T001 (Eiichiro ODA) [eBook officiel 1920].cbz", "One Piece T002 (Eiichiro ODA) [eBook officiel 1598].cbz",
             "One Piece T099.cbz", "One Piece Tome 109 - Scan.cbz", "One Piece Tome 109 - Scan.epub"]

    def test_files_named_in_several_ways(self):
        [a] = an.files_named_in_several_ways(snap(series("One Piece", self.FILES, {"id": 13})))
        self.assertEqual((a["id"], a["severity"]), ("file_names:One Piece", "advice"))
        self.assertEqual(a["text"]["fr"], "Les fichiers de « One Piece » sont nommés de 4 façons.")
        [r] = a["remedies"]
        self.assertEqual(r["label"]["fr"], "Tous les renommer comme « One Piece T001.cbz », « One Piece T002.cbz »…")
        self.assertEqual([new for _, new in r["args"]["names"]],
                         ["One Piece T001.cbz", "One Piece T002.cbz", "One Piece T105.cbz", "One Piece T109.cbz", "One Piece T109.epub"])
        self.assertTrue(r["risky"])  # T099 is so named already

    def test_series_left_out(self):
        shelves = [series("Naruto", [f"[Compressé] Naruto [Team Chromatique] - Tome #00{n} - [V{n}].cbz" for n in (1, 2)]),
                   series("Bleach", ["Bleach T01.cbz", "Bleach 2.cbz", "Bleach Gaiden.cbz"]),  # one without a number
                   series("Berserk", ["Berserk T01.cbz", "Berserk 1 (2023).cbz"]),  # two would be Berserk T01.cbz
                   series("Empty", []),
                   series("Harry Potter", ["Rowling [Tome 1] - L'école des sorciers.epub", "Harry Potter T02.epub"])]  # unknown to AniList: a novel
        self.assertEqual(an.files_named_in_several_ways(snap(*shelves)), [])


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")


class Cures(unittest.TestCase):
    """The remedies, on a temporary library."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        patches = {"MANGA": root, "STATE_DIR": root / ".ohara", "INCOMING": root / ".incoming", "MUSIC": root / ".ost"}
        for name, value in patches.items():
            p = mock.patch.object(ohara, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def test_renaming_files_keeps_where_you_are_and_does_no_harm_twice(self):
        for f in ("One Piece 105 (2023).cbz", "One Piece Tome 106 - Scan.cbz", "One Piece T107.cbz", "One Piece Tome 107.cbz"):
            touch(self.root / "One Piece" / f)
        ohara.save_state({"progress": {"One Piece/One Piece 105 (2023).cbz": {"page": 4, "pages": 9}}})
        names = [["One Piece/One Piece 105 (2023).cbz", "One Piece T105.cbz"], ["One Piece/One Piece Tome 106 - Scan.cbz", "One Piece T106.cbz"],
                 ["One Piece/Gone.cbz", "One Piece T108.cbz"],  # gone meanwhile
                 ["One Piece/One Piece Tome 107.cbz", "One Piece T107.cbz"]]  # the name is taken
        self.assertEqual(an.rename_files(ohara, "One Piece", names), {"renamed": 2})
        self.assertEqual(sorted(p.name for p in (self.root / "One Piece").iterdir()),
                         ["One Piece T105.cbz", "One Piece T106.cbz", "One Piece T107.cbz", "One Piece Tome 107.cbz"])
        self.assertEqual(ohara.load_state()["progress"], {"One Piece/One Piece T105.cbz": {"page": 4, "pages": 9}})
        self.assertEqual(an.rename_files(ohara, "One Piece", names), {"renamed": 0})
        self.assertEqual(an.rename_files(ohara, "One Piece", [["One Piece/One Piece T107.cbz", "One Piece T107.cbz"]]), {"renamed": 0})

    def test_renaming_a_folder_keeps_where_you_are_and_does_no_harm_twice(self):
        old = "Christopher Paolini Eragon"
        touch(self.root / old / "1 - Eragon.epub")
        touch(self.root / "Naruto" / "Naruto T01.cbz")
        ohara.save_state({"progress": {old + "/1 - Eragon.epub": {"page": 2, "pages": 300}}, "series": {old: {"follow": True}}})
        self.assertEqual(an.rename_folder(ohara, old, "Eragon"), {"renamed": "Eragon"})
        state = ohara.load_state()
        self.assertEqual(state["progress"], {"Eragon/1 - Eragon.epub": {"page": 2, "pages": 300}})
        self.assertEqual(state["series"], {"Eragon": {"follow": True}})
        self.assertEqual(an.rename_folder(ohara, old, "Eragon"), {"renamed": None})  # twice
        self.assertEqual(an.rename_folder(ohara, "Eragon", "Naruto"), {"renamed": None})  # taken
        self.assertTrue((self.root / "Eragon" / "1 - Eragon.epub").exists())

    def test_a_remedy_found_by_the_examination_is_run_through_chopper(self):
        for f in ("Eragon I.epub", "Eragon II.epub"):
            touch(self.root / "Eragon" / f)
        ohara.save_state({"progress": {"Eragon/Eragon II.epub": {"page": 1}}})
        found = an.volumes_without_number(snap(series("Eragon", ["Eragon I.epub", "Eragon II.epub"])))
        self.assertEqual(an.chopper.apply(found, "unnumbered:Eragon", 0, ohara), {"renamed": 2})
        self.assertEqual(ohara.load_state()["progress"], {"Eragon/Eragon T02.epub": {"page": 1}})


if __name__ == "__main__":
    unittest.main()
