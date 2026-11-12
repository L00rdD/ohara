"""Tests of Chopper's examinations of files and formats (ailments_files.py):
python3 -m unittest test_ailments_files.py"""

import importlib.util
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_spec = importlib.util.spec_from_file_location("ohara", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ohara.py"))
ohara = sys.modules.get("ohara")  # one copy for every test module, as there is one when Ohara runs
if ohara is None:
    ohara = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(ohara)
    sys.modules["ohara"] = ohara  # Chopper's remedies are given it

import ailments_files as af  # noqa: E402

NOW = 1_000_000


def vol(series, name, number):
    return {"id": f"{series}/{name}", "label": f"Tome {number:g}" if number is not None else name, "number": number, "file": name}


def snap(series, files=None, franky=None):
    """A snapshot made by hand: {series: [(file, number)]}, the files of each folder
    {series: [(name, size, mtime)]} (the volumes, at 1 byte, when not given)."""
    files = files or {}
    out = {"series": [], "files": {}, "state": {"franky": franky or {}}, "now": NOW, "downloads": [], "incoming": []}
    for name, vols in series.items():
        out["series"].append({"name": name, "volumes": [vol(name, f, n) for f, n in vols]})
        listed = files.get(name, [(f, 1, 0) for f, _ in vols])
        out["files"][name] = [{"name": f, "size": size, "mtime": mtime} for f, size, mtime in listed]
    return out


def ids(found):
    return [a["id"] for a in found]


def cbz(path, names=("1.png",)):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, b"x")
    return path


class Words(unittest.TestCase):
    def test_tomes_said_as_ranges(self):
        self.assertEqual(af.tomes([3.0]), {"fr": "le tome 3", "en": "tome 3"})
        self.assertEqual(af.tomes([11.0, 12.0, 13.0]), {"fr": "les tomes 11 à 13", "en": "tomes 11 to 13"})
        self.assertEqual(af.tomes([5.0, 1.0, 2.0, 3.0, 8.0, 7.0]), {"fr": "les tomes 1 à 3, 5 et 7 à 8", "en": "tomes 1 to 3, 5 and 7 to 8"})
        self.assertEqual(af.tomes([1.0, 1.5, 2.0]), {"fr": "les tomes 1, 1.5 et 2", "en": "tomes 1, 1.5 and 2"})

    def test_formats_named(self):
        self.assertEqual((af.the_format(".epub", False), af.the_format(".pdf", False), af.the_format(".pdf", True)), ("l'EPUB", "le PDF", "les PDF"))


class SeveralFormats(unittest.TestCase):
    ERAGON = "Christopher Paolini Eragon"

    def test_a_whole_series_in_two_formats_is_one_ailment(self):
        vols = [(f"{n} - Eragon.epub", float(n)) for n in range(1, 6)] + [(f"{n}-Eragon.pdf", float(n)) for n in range(1, 6)]
        found = af.several_formats(snap({self.ERAGON: vols, "Naruto": [("Naruto T01.cbz", 1.0)]}))
        self.assertEqual(ids(found), [f"formats:{self.ERAGON}|.pdf+.epub"])
        a = found[0]
        self.assertEqual((a["series"], a["severity"]), (self.ERAGON, "advice"))
        self.assertEqual(a["text"], {"fr": "Les tomes 1 à 5 sont chacun en PDF et en EPUB.", "en": "Tomes 1 to 5 are each in PDF and in EPUB."})
        pdf, epub = a["remedies"]
        self.assertEqual(pdf["label"], {"fr": "Garder les PDF (supprimer les EPUB)", "en": "Keep the PDFs (delete the EPUBs)"})
        self.assertEqual(pdf["args"]["vids"], sorted(f"{self.ERAGON}/{n} - Eragon.epub" for n in range(1, 6)))
        self.assertEqual(epub["args"]["vids"], sorted(f"{self.ERAGON}/{n}-Eragon.pdf" for n in range(1, 6)))
        self.assertTrue(pdf["risky"] and epub["risky"])

    def test_tomes_in_other_formats_are_said_apart(self):
        jjk = [("T25.cbz", 25.0), ("T26.cbz", 26.0), ("T26.epub", 26.0), ("T27.cbz", 27.0), ("T27.epub", 27.0), ("T27.pdf", 27.0), ("Extra.pdf", None)]
        found = af.several_formats(snap({"JJK": jjk}))
        self.assertEqual(ids(found), ["formats:JJK|.cbz+.epub", "formats:JJK|.cbz+.pdf+.epub"])
        self.assertEqual(found[0]["text"]["fr"], "Le tome 26 est en CBZ et en EPUB.")
        self.assertEqual(found[0]["remedies"][1]["label"], {"fr": "Garder l'EPUB (supprimer le CBZ)", "en": "Keep the EPUB (delete the CBZ)"})
        self.assertEqual(found[1]["remedies"][0]["label"]["fr"], "Garder le CBZ (supprimer le PDF et l'EPUB)")
        self.assertEqual(found[1]["remedies"][0]["args"]["vids"], ["JJK/T27.epub", "JJK/T27.pdf"])


class Editions(unittest.TestCase):
    def test_tomes_twice_in_the_same_format(self):
        vols = [(f"JJK T{n} (PapriKa+).cbz", float(n)) for n in range(11, 19)] + [(f"JJK T{n}.cbz", float(n)) for n in range(11, 20)]
        files = {"JJK": [(f"JJK T{n} (PapriKa+).cbz", 100, 1) for n in range(11, 19)] + [(f"JJK T{n}.cbz", 50, 2) for n in range(11, 20)]}
        found = af.editions(snap({"JJK": vols, "Naruto": [("Naruto T01.cbz", 1.0)]}, files))
        self.assertEqual(ids(found), ["editions:JJK"])
        a = found[0]
        self.assertEqual(a["text"], {"fr": "Les tomes 11 à 18 sont chacun là en deux éditions.", "en": "Tomes 11 to 18 are each here in two editions."})
        larger, recent = a["remedies"]
        self.assertEqual(larger["args"]["vids"], sorted(f"JJK/JJK T{n}.cbz" for n in range(11, 19)))
        self.assertEqual(recent["args"]["vids"], sorted(f"JJK/JJK T{n} (PapriKa+).cbz" for n in range(11, 19)))
        self.assertTrue(larger["risky"] and recent["risky"])
        self.assertEqual(recent["label"]["fr"], "Garder le plus récent")

    def test_one_remedy_when_the_larger_is_the_more_recent(self):
        vols = [("A.cbz", 3.0), ("B.cbz", 3.0), ("C.cbz", 3.0), ("A.epub", 3.0)]
        files = {"S": [("A.cbz", 10, 5), ("B.cbz", 20, 6), ("C.cbz", 5, 1), ("A.epub", 1, 1)]}
        a = af.editions(snap({"S": vols}, files))[0]
        self.assertEqual(a["text"]["fr"], "Le tome 3 est là en plusieurs éditions.")
        self.assertEqual(len(a["remedies"]), 1)
        self.assertEqual(a["remedies"][0]["args"]["vids"], ["S/A.cbz", "S/C.cbz"])


class Strays(unittest.TestCase):
    def test_archives_junk_and_leftovers(self):
        files = {"S": [("T01.cbz", 1, 0), ("T02.cbr", 1, 0), ("notes.txt", 1, 0), (".T03.cbz.part", 1, NOW - 7200),
                       (".T01.cbz.franky", 1, NOW - 10), (".DS_Store", 1, 0)],
                 "N": [("N01.cbz", 1, 0), ("a.rar", 1, 0), ("b.7z", 1, 0), ("c.nfo", 1, 0), ("d.jpg", 1, 0),
                       (".x.part", 1, 0), (".y.franky", 1, 0)]}
        found = af.strays(snap({"S": [("T01.cbz", 1.0)], "N": [("N01.cbz", 1.0)]}, files))
        self.assertEqual(ids(found), ["archives:S", "junk:S", "leftovers:S", "archives:N", "junk:N", "leftovers:N"])
        archive, junk, leftover = found[:3]
        self.assertEqual(archive["severity"], "trouble")
        self.assertEqual(archive["text"]["fr"], "T02.cbr : une archive que tu ne peux pas lire ici.")
        self.assertEqual([r["kind"] for r in archive["remedies"]], ["convert_archives", "delete_files"])
        self.assertEqual(archive["remedies"][0]["args"], {"series": "S", "names": ["T02.cbr"]})
        self.assertEqual(archive["remedies"][0]["label"]["fr"], "Le convertir en CBZ")
        self.assertEqual((junk["severity"], junk["text"]["fr"]), ("advice", "notes.txt : Ohara ne le lit pas."))
        self.assertEqual(leftover["remedies"][0]["args"]["names"], [".T03.cbz.part"])  # the .franky one may be at work
        self.assertEqual(leftover["text"]["fr"], ".T03.cbz.part : un reste d'un tome pas fini.")
        self.assertTrue(all(r["risky"] for a in found for r in a["remedies"]))
        archives, junk, leftovers = found[3:]
        self.assertEqual(archives["text"]["en"], "a.rar, b.7z: archives you cannot read here.")
        self.assertEqual(archives["remedies"][1]["label"], {"fr": "Les supprimer", "en": "Delete them"})
        self.assertEqual(junk["text"]["fr"], "c.nfo, d.jpg : Ohara ne les lit pas.")
        self.assertEqual(leftovers["text"]["en"], ".x.part, .y.franky: leftovers of an unfinished volume.")

    def test_a_tidy_folder_is_fine(self):
        self.assertEqual(af.strays(snap({"S": [("T01.cbz", 1.0), ("T01.pdf", 1.0)]})), [])


class Broken(unittest.TestCase):
    def test_a_volume_franky_could_not_open(self):
        franky = {"S/T02.cbz": [0, 0], "S/T01.cbz": [9, 5], "S/Gone.cbz": [0, 0], "S/Extra.cbz": [0, 0]}
        found = af.broken(snap({"S": [("T01.cbz", 1.0), ("T02.cbz", 2.0), ("Extra.cbz", None)]}, franky=franky))
        self.assertEqual(ids(found), ["broken:S/T02.cbz", "broken:S/Extra.cbz"])
        self.assertEqual(found[0]["text"]["fr"], "Le tome 2 (T02.cbz) ne s'ouvre pas : le fichier est sans doute abîmé.")
        self.assertEqual(found[1]["text"]["en"], "The volume (Extra.cbz) does not open: the file is most likely damaged.")
        delete, again = found[0]["remedies"]
        self.assertEqual((delete["kind"], delete["args"]), ("delete_volumes", {"vids": ["S/T02.cbz"]}))
        self.assertEqual((again["kind"], again["args"]), ("fetch_again", {"vid": "S/T02.cbz", "series": "S"}))
        self.assertTrue(delete["risky"] and again["risky"])

    def test_nothing_without_franky(self):
        s = snap({"S": [("T01.cbz", 1.0)]})
        s["state"] = {}
        self.assertEqual(af.broken(s), [])


class Cures(unittest.TestCase):
    """The remedies, on a temporary library."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for name, value in {"MANGA": root, "STATE_DIR": root / ".ohara", "INCOMING": root / ".incoming", "MUSIC": root / ".ost"}.items():
            p = mock.patch.object(ohara, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.root = root

    def examine(self):
        with mock.patch.object(ohara, "safe_torrents", return_value=[]):
            return {a["id"]: a for a in ohara.chopper.examine(ohara.snapshot())}

    def treat(self, found, aid, label):
        a = found[aid]
        index = next(i for i, r in enumerate(a["remedies"]) if r["label"]["en"] == label)
        return ohara.chopper.apply(list(found.values()), aid, index, ohara)

    def test_keeping_one_format_and_one_edition(self):
        for name in ("1 - Eragon.epub", "1-Eragon.pdf", "2 - Eragon.epub", "2-Eragon.pdf"):
            cbz(self.root / "Eragon" / name)
        cbz(self.root / "JJK" / "JJK T11 (PapriKa+).cbz", ["1.png", "2.png"])
        cbz(self.root / "JJK" / "JJK T11.cbz")
        ohara.save_state({"progress": {"Eragon/1 - Eragon.epub": {"page": 2}}})
        found = self.examine()
        done = self.treat(found, "formats:Eragon|.pdf+.epub", "Keep the PDFs (delete the EPUBs)")
        self.assertEqual(sorted(done["deleted"]), ["Eragon/1 - Eragon.epub", "Eragon/2 - Eragon.epub"])
        self.assertEqual(sorted(p.name for p in (self.root / "Eragon").iterdir()), ["1-Eragon.pdf", "2-Eragon.pdf"])
        self.assertEqual(ohara.load_state()["readers"]["1"]["progress"], {})
        self.treat(found, "editions:JJK", "Keep the larger file (often the better scan)")
        self.assertEqual([p.name for p in (self.root / "JJK").iterdir()], ["JJK T11 (PapriKa+).cbz"])
        self.assertNotIn("editions:JJK", self.examine())
        self.assertEqual(af.delete_volumes(ohara, ["JJK/JJK T11.cbz"]), {"deleted": []})  # gone already

    def test_strays_deleted_and_archives_converted(self):
        cbz(self.root / "S" / "T01.cbz")
        cbz(self.root / "S" / "T02.cbr", ["2.png", "3.png"])
        (self.root / "S" / "T03.cbr").write_bytes(b"not an archive")
        (self.root / "S" / "notes.txt").write_text("x")
        (self.root / "S" / ".T04.cbz.part").write_bytes(b"x")
        os.utime(self.root / "S" / ".T04.cbz.part", (0, 0))

        def extract(path, out):
            with zipfile.ZipFile(path) as z:
                z.extractall(out)
        with mock.patch.object(ohara, "extract", extract):
            found = self.examine()
            done = self.treat(found, "archives:S", "Convert them to CBZ")
        self.assertEqual(done, {"converted": ["T02.cbr"], "failed": ["T03.cbr"]})
        with zipfile.ZipFile(self.root / "S" / "T02.cbz") as z:
            self.assertEqual(sorted(z.namelist()), ["2.png", "3.png"])
        self.assertEqual(self.treat(found, "junk:S", "Delete it"), {"deleted": ["notes.txt"]})
        self.assertEqual(self.treat(found, "leftovers:S", "Delete it"), {"deleted": [".T04.cbz.part"]})
        self.assertEqual(sorted(p.name for p in (self.root / "S").iterdir()), ["T01.cbz", "T02.cbz", "T03.cbr"])
        self.assertEqual(self.treat(self.examine(), "archives:S", "Delete it"), {"deleted": ["T03.cbr"]})
        self.assertEqual(af.convert_archives(ohara, "S", ["T03.cbr"]), {"converted": [], "failed": []})  # gone already

    def test_nothing_outside_the_series_folder(self):
        cbz(self.root / "S" / "T01.cbz")
        (self.root / "secret.txt").write_text("x")
        for series, name in (("S", "../secret.txt"), ("..", "secret.txt"), ("S", "sub/x.txt")):
            with self.assertRaises(KeyError):
                af.delete_files(ohara, series, [name])
        self.assertTrue((self.root / "secret.txt").exists())

    def test_a_broken_volume_deleted_and_fetched_again(self):
        cbz(self.root / "S" / "T01.cbz")
        cbz(self.root / "S" / "T02.cbz")
        ohara.save_state({"franky": {"S/T01.cbz": [0, 0], "S/T02.cbz": [0, 0]}})
        found = self.examine()
        self.assertIn("broken:S/T01.cbz", found)
        with mock.patch.object(ohara, "complete", return_value={"sent": [], "nowhere": [1]}) as complete:
            done = self.treat(found, "broken:S/T01.cbz", "Delete it and fetch it again")
            self.assertEqual(af.fetch_again(ohara, "S/T01.cbz", "S"), {"sent": [], "nowhere": [1]})  # gone already
        self.assertEqual(done, {"sent": [], "nowhere": [1]})
        complete.assert_called_with("S")
        self.assertFalse((self.root / "S" / "T01.cbz").exists())
        self.assertEqual(ohara.load_state()["franky"], {"S/T02.cbz": [0, 0]})
        self.treat(found, "broken:S/T02.cbz", "Delete it")
        self.assertFalse((self.root / "S").exists() and any((self.root / "S").iterdir()))


if __name__ == "__main__":
    unittest.main()
