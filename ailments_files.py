"""Chopper's examinations of files and formats: a tome kept in several formats, a tome
there twice in the same format (two editions), files of a series' folder Ohara does
not read, and volumes Franky could not open."""

import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

from chopper import ailment, cure, exam, remedy, words

FORMATS = (".cbz", ".zip", ".pdf", ".epub")  # those kept, the readable ones first
ARCHIVES = (".cbr", ".rar", ".cb7", ".7z")  # those Ohara turns into a .cbz
LEFTOVERS = (".part", ".franky")  # a volume being made, or being rebuilt by Franky
LEFTOVER_AGE = 3600  # seconds before a leftover is taken for one: before, it may be at work


# ---------- words ----------

def fmt(ext):
    return ext.lstrip(".").upper()


def number(n):
    return f"{n:g}"


def runs(numbers):
    """Consecutive tomes put together: [1, 2, 3, 5] → [(1, 3), (5, 5)]."""
    out = []
    for n in sorted(numbers):
        if out and n == out[-1][1] + 1 and n == int(n):
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def listed(items, conj):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {conj} " + items[-1]


def tomes(numbers):
    """Tomes said in French and in English, as ranges when they follow each other:
    "les tomes 1 à 5 et 8" / "tomes 1 to 5 and 8"; "le tome 3" / "tome 3"."""
    spans = runs(numbers)
    fr = [number(a) if a == b else f"{number(a)} à {number(b)}" for a, b in spans]
    en = [number(a) if a == b else f"{number(a)} to {number(b)}" for a, b in spans]
    if len(numbers) == 1:
        return words("le tome " + fr[0], "tome " + en[0])
    return words("les tomes " + listed(fr, "et"), "tomes " + listed(en, "and"))


def capital(text):
    return text[:1].upper() + text[1:]


def the_format(ext, many):
    """"les EPUB", "le PDF", "l'EPUB"."""
    if many:
        return "les " + fmt(ext)
    return ("l'" if fmt(ext)[0] in "AEIOU" else "le ") + fmt(ext)


# ---------- what the snapshot says ----------

def by_number(series):
    """A series' volumes with a number, by number."""
    found = defaultdict(list)
    for v in series["volumes"]:
        if v["number"] is not None:
            found[v["number"]].append(v)
    return found


def files_of(snapshot, series):
    return {f["name"]: f for f in snapshot["files"].get(series["name"], [])}


def ordered(exts):
    return sorted(exts, key=lambda e: FORMATS.index(e) if e in FORMATS else len(FORMATS))


def ext_of(v):
    return Path(v["file"]).suffix.lower()


# ---------- the same tome in several formats ----------

@exam
def several_formats(snapshot):
    """A tome kept in several formats, said once for all the tomes of a series kept in
    the same formats (a series all in EPUB and in PDF is one ailment)."""
    found = []
    for s in snapshot["series"]:
        groups = defaultdict(dict)  # formats → {number: volumes}
        for n, vols in by_number(s).items():
            exts = tuple(ordered({ext_of(v) for v in vols}))
            if len(exts) > 1:
                groups[exts][n] = vols
        found += [formats_ailment(s["name"], exts, tomes_kept) for exts, tomes_kept in groups.items()]
    return found


def formats_ailment(series, exts, kept):
    many = len(kept) > 1
    said = tomes(list(kept))
    names_fr = listed(["en " + fmt(e) for e in exts], "et")
    names_en = listed(["in " + fmt(e) for e in exts], "and")
    text = words(f"{capital(said['fr'])} {'sont chacun' if many else 'est'} {names_fr}.",
                 f"{capital(said['en'])} {'are each' if many else 'is'} {names_en}.")
    remedies = [keep_format(e, exts, kept, many) for e in exts]
    return ailment("formats", f"{series}|{'+'.join(exts)}", text, remedies, series=series, severity="advice")


def keep_format(ext, exts, kept, many):
    others = [e for e in exts if e != ext]
    gone = [v["id"] for vols in kept.values() for v in vols if ext_of(v) != ext]
    fr = listed([the_format(e, many) for e in others], "et")
    en = listed([fmt(e) + ("s" if many else "") for e in others], "and")
    label = words(f"Garder {the_format(ext, many)} (supprimer {fr})",
                  f"Keep the {fmt(ext)}{'s' if many else ''} (delete the {en})")
    return remedy("delete_volumes", label, risky=True, vids=sorted(gone))


# ---------- the same tome twice in the same format ----------

@exam
def editions(snapshot):
    """A tome there twice or more in the same format (two editions), said once for a
    series, with which tomes."""
    found = []
    for s in snapshot["series"]:
        sizes = files_of(snapshot, s)
        twins = []  # each a list of volumes: one tome, one format
        for vols in by_number(s).values():
            same = defaultdict(list)
            for v in vols:
                same[ext_of(v)].append(dict(v, size=sizes.get(v["file"], {}).get("size", 0), mtime=sizes.get(v["file"], {}).get("mtime", 0)))
            twins += [t for t in same.values() if len(t) > 1]
        if twins:
            found.append(editions_ailment(s["name"], twins))
    return found


def editions_ailment(series, twins):
    numbers = sorted({t[0]["number"] for t in twins})
    said = tomes(numbers)
    count = ("deux", "two") if all(len(t) == 2 for t in twins) else ("plusieurs", "several")
    many = len(numbers) > 1
    text = words(f"{capital(said['fr'])} {'sont chacun' if many else 'est'} là en {count[0]} éditions.",
                 f"{capital(said['en'])} {'are each' if many else 'is'} here in {count[1]} editions.")
    larger = keep_one(twins, lambda v: (v["size"], v["mtime"]))
    recent = keep_one(twins, lambda v: (v["mtime"], v["size"]))
    remedies = [remedy("delete_volumes", words("Garder le plus gros fichier (souvent le meilleur scan)", "Keep the larger file (often the better scan)"), risky=True, vids=larger)]
    if recent != larger:
        remedies.append(remedy("delete_volumes", words("Garder le plus récent", "Keep the more recent one"), risky=True, vids=recent))
    return ailment("editions", series, text, remedies, series=series, severity="advice")


def keep_one(twins, best):
    """The volumes to delete to keep, of each tome, the best by best(volume)."""
    gone = []
    for t in twins:
        kept = max(t, key=best)
        gone += [v["id"] for v in t if v is not kept]
    return sorted(gone)


@cure("delete_volumes")
def delete_volumes(o, vids):
    """Deletes volumes; one already gone is passed over."""
    deleted = []
    for vid in vids:
        try:
            o.delete_volume(vid)
            deleted.append(vid)
        except (KeyError, FileNotFoundError):
            pass
    return {"deleted": deleted}


# ---------- files of a series' folder Ohara does not read ----------

@exam
def strays(snapshot):
    """In each series' folder: archives to turn into a .cbz, files Ohara cannot read,
    and leftovers of a volume cut short."""
    found = []
    for s in snapshot["series"]:
        kept = {v["file"] for v in s["volumes"]}
        archives, junk, leftovers = [], [], []
        for f in snapshot["files"].get(s["name"], []):
            name = f["name"]
            if name.startswith("."):
                if name.endswith(LEFTOVERS) and snapshot["now"] - f["mtime"] > LEFTOVER_AGE:
                    leftovers.append(name)
            elif Path(name).suffix.lower() in ARCHIVES:
                archives.append(name)
            elif name not in kept:
                junk.append(name)
        found += stray_ailments(s["name"], archives, junk, leftovers)
    return found


def stray_ailments(series, archives, junk, leftovers):
    out = []
    many = lambda names: len(names) > 1
    if archives:
        them = ("les", "them") if many(archives) else ("le", "it")
        text = words(f"{shown(archives)} : {'des archives' if many(archives) else 'une archive'} que tu ne peux pas lire ici.",
                     f"{shown(archives)}: {'archives' if many(archives) else 'an archive'} you cannot read here.")
        out.append(ailment("archives", series, text, [
            remedy("convert_archives", words(f"{capital(them[0])} convertir en CBZ", f"Convert {them[1]} to CBZ"), risky=True, series=series, names=archives),
            remedy("delete_files", words(f"{capital(them[0])} supprimer", f"Delete {them[1]}"), risky=True, series=series, names=archives)], series=series))
    if junk:
        text = words(f"{shown(junk)} : Ohara ne {'les' if many(junk) else 'le'} lit pas.", f"{shown(junk)}: Ohara does not read {'them' if many(junk) else 'it'}.")
        out.append(ailment("junk", series, text, [delete_them(series, junk)], series=series, severity="advice"))
    if leftovers:
        text = words(f"{shown(leftovers)} : {'des restes' if many(leftovers) else 'un reste'} d'un tome pas fini.",
                     f"{shown(leftovers)}: {'leftovers' if many(leftovers) else 'a leftover'} of an unfinished volume.")
        out.append(ailment("leftovers", series, text, [delete_them(series, leftovers)], series=series, severity="advice"))
    return out


def shown(names):
    return ", ".join(names)


def delete_them(series, names):
    label = words("Les supprimer", "Delete them") if len(names) > 1 else words("Le supprimer", "Delete it")
    return remedy("delete_files", label, risky=True, series=series, names=names)


def stray_path(o, series, name):
    """A file of a series' folder, hidden or not, refusing anything elsewhere; None when
    it is gone already."""
    folder = (o.MANGA / series).resolve()
    p = (folder / name).resolve()
    if p.parent != folder or o.MANGA.resolve() not in folder.parents:
        raise KeyError(name)
    return p if p.is_file() else None


@cure("delete_files")
def delete_files(o, series, names):
    deleted = []
    for name in names:
        p = stray_path(o, series, name)
        if p:
            p.unlink()
            deleted.append(name)
    return {"deleted": deleted}


@cure("convert_archives")
def convert_archives(o, series, names):
    """Turns archives into .cbz, each deleted once its .cbz holds pages; one that cannot
    be opened is left as it is and said."""
    done, failed = [], []
    for name in names:
        p = stray_path(o, series, name)
        if p:
            (done if convert(o, p) else failed).append(name)
    return {"converted": done, "failed": failed}


def convert(o, path):
    target = o.free_name(path.parent, path.stem + ".cbz")
    try:
        o.unpack_archive(path, target)
        with zipfile.ZipFile(target) as z:
            pages = [n for n in z.namelist() if o.IMAGE.search(n)]
    except Exception as e:
        print(f"chopper: {path.name}: {e}", flush=True)
        pages = []
    shutil.rmtree(path.with_suffix(".unpacked"), ignore_errors=True)
    if not pages:
        target.unlink(missing_ok=True)
        return False
    path.unlink()
    return True


# ---------- volumes Franky could not open ----------

@exam
def broken(snapshot):
    """A volume Franky could not open is most likely broken."""
    failed = snapshot["state"].get("franky", {})
    found = []
    for s in snapshot["series"]:
        for v in s["volumes"]:
            if failed.get(v["id"]) == [0, 0]:
                found.append(broken_ailment(s["name"], v))
    return found


def broken_ailment(series, v):
    said = tomes([v["number"]]) if v["number"] is not None else words("le volume", "the volume")
    text = words(f"{capital(said['fr'])} ({v['file']}) ne s'ouvre pas : le fichier est sans doute abîmé.",
                 f"{capital(said['en'])} ({v['file']}) does not open: the file is most likely damaged.")
    return ailment("broken", v["id"], text, [
        remedy("delete_volumes", words("Le supprimer", "Delete it"), risky=True, vids=[v["id"]]),
        remedy("fetch_again", words("Le supprimer et le chercher à nouveau", "Delete it and fetch it again"), risky=True, vid=v["id"], series=series)],
        series=series)


@cure("fetch_again")
def fetch_again(o, vid, series):
    try:
        o.delete_volume(vid)
    except (KeyError, FileNotFoundError):
        pass  # gone already: it is looked for all the same
    return o.complete(series)
