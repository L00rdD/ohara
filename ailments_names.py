"""Chopper's examinations of names and numbers: volumes without a number, a series
folder named after its author or wrapped in junk, a series whose files are named in
several ways. Each says what could be done, and nothing is renamed but by a remedy
chosen; renames go through ohara.rename_volume and ohara.rename_series, which keep
the reading progress and all the state says of a volume or a series."""

import re
from pathlib import Path

import chopper
from chopper import ailment, remedy, words
from names import BRACKETS, SERIES_END, guess_series, natural, norm, safe_name

ROMAN = re.compile(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})")
# a number heading what is left of a name once what all the names share is taken out
LEADING_NUMBER = re.compile(r"^\W*(\d+|[IVXLCDM]+)(?![^\W_])")
YEAR = re.compile(r"\b(19|20)\d\d\b")
JUNK = re.compile(r"(?i)(?<![^\W_])(scans?|e-?book|digital|officiel|official|cbz|cbr|pdf|epub|complete|int[ée]grale|"
                  r"fr|vf|vff|vostfr|french|fran[cç]ais|truefrench|eng|english|vo|raw)(?![^\W_])")
SPACED_DASH = re.compile(r"\s+[-–]\s+")
EDGE_NUMBER = re.compile(r"^\d+\s+|\s+\d+$")
SHOWN = 4  # files named in an ailment's text before "…"


# ---------- small readings ----------

def word_list(text):
    """The words of a name, flattened by norm: "L'Aîné - Paolini" → ["l", "aine", "paolini"]."""
    return [w for w in (norm(p) for p in re.split(r"[\W_]+", text)) if w]


def holds(run, whole):
    """Whether the words run stand side by side in whole."""
    n = len(run)
    return n > 0 and any(whole[i:i + n] == run for i in range(len(whole) - n + 1))


def part_of(run, whole):
    """Whether run stands in whole and is not all of it."""
    return len(run) < len(whole) and holds(run, whole)


def roman(text):
    """12 for "XII", None for what is not a Roman number."""
    if not text or not ROMAN.fullmatch(text):
        return None
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for a, b in zip(text, text[1:] + " "):
        total += -values[a] if values.get(b, 0) > values[a] else values[a]
    return total


def tome(number, width):
    """"T007" for 7 at width 3, "T10.5" for 10.5 at width 2."""
    whole = int(number)
    rest = f"{number - whole:g}"[1:] if number != whole else ""
    return f"T{whole:0{width}d}{rest}"


def width(numbers):
    """The digits a series needs: two at least, three past 99."""
    return max([2] + [len(str(int(n))) for n in numbers])


def shown(files):
    head = ", ".join(files[:SHOWN])
    return head + (", …" if len(files) > SHOWN else "")


def stems(vols):
    """The distinct stems of volumes in name order, each with its files: a tome in
    several formats is one stem."""
    out = {}
    for v in sorted(vols, key=lambda v: natural(v["file"])):
        out.setdefault(Path(v["file"]).stem, []).append(v)
    return out


def renames(series, numbered, w):
    """[[id, new file name]] for volumes given numbers, those already so named left out."""
    out = []
    for v, n in numbered:
        new = safe_name(f"{series} {tome(n, w)}{Path(v['file']).suffix}")
        if new != v["file"]:
            out.append([v["id"], new])
    return out


def rename_remedy(label, series, pairs):
    return remedy("names_rename_files", label, risky=True, series=series, names=pairs)


# ---------- volumes without a number ----------

def common_ends(texts):
    """What all the texts start and end with, cut back so as not to end or start in
    the middle of a word or a number."""
    head = texts[0]
    tail = texts[0]
    for t in texts[1:]:
        while not t.startswith(head):
            head = head[:-1]
        while not t.endswith(tail):
            tail = tail[1:]
    head = re.sub(r"[^\W_]+$", "", head)
    tail = re.sub(r"^[^\W_]+", "", tail)
    return len(head), len(tail)


def read_number(middle):
    m = LEADING_NUMBER.match(middle)
    if not m:
        return None
    token = m.group(1)
    return float(token) if token.isdigit() else roman(token)


def pattern_numbers(names):
    """The number each name says where the names differ ("Eragon I", "Eragon II" →
    [1, 2]), or None when they do not all say one, or say the same twice."""
    if len(names) < 2:
        return None
    head, tail = common_ends(names)
    found = [read_number(n[head:len(n) - tail] if head + tail <= len(n) else "") for n in names]
    if None in found or len(set(found)) < len(found):
        return None
    return found


def numbered_by_pattern(series):
    """[(volume, number)] read from the pattern of the names of the volumes without a
    number, or None; numbers the series already has are not taken twice."""
    loose = stems([v for v in series["volumes"] if v["number"] is None])
    found = pattern_numbers(list(loose))
    held = {v["number"] for v in series["volumes"] if v["number"] is not None}
    if found is None or held & set(found):
        return None
    return [(v, n) for vols, n in zip(loose.values(), found) for v in vols]


def numbered_in_order(series):
    """[(volume, number)] counting the volumes in name order, when none has a number
    and there are two at least (one alone is a one-shot); else None."""
    if any(v["number"] is not None for v in series["volumes"]):
        return None
    loose = stems(series["volumes"])
    if len(loose) < 2:
        return None
    return [(v, float(i)) for i, vols in enumerate(loose.values(), 1) for v in vols]


def numbering_remedy(series, numbered, label):
    if not numbered:
        return None
    pairs = renames(series["name"], numbered, width(n for _, n in numbered))
    return rename_remedy(label(pairs[0][1]), series["name"], pairs) if pairs else None


def unnumbered(series):
    """The ailment of a series with volumes Ohara reads no number in, or None."""
    files = sorted((v["file"] for v in series["volumes"] if v["number"] is None), key=natural)
    if not files:
        return None
    by_name = numbering_remedy(series, numbered_in_order(series), lambda first: words(
        f"Les numéroter dans l'ordre des noms (« {first} »…)", f"Number them in name order (« {first} »…)"))
    by_pattern = numbering_remedy(series, numbered_by_pattern(series), lambda first: words(
        f"Lire leur numéro dans leur nom (« {first} »…)", f"Read their number in their name (« {first} »…)"))
    cures = [r for r in (by_pattern, by_name) if r]
    if not cures:
        return None
    name = series["name"]
    text = words(f"« {name} » : {len(files)} tomes sans numéro ({shown(files)}).",
                 f"« {name} »: {len(files)} volumes without a number ({shown(files)}).")
    return ailment("unnumbered", name, text, cures, series=name)


@chopper.exam
def volumes_without_number(snapshot):
    return [a for a in map(unnumbered, snapshot["series"]) if a]


# ---------- a series folder that is not just the series' title ----------

def stripped(name):
    """The folder name without brackets, years, language tags, scan or format words,
    or tome ranges: "[Team X] Naruto (2002) FR" → "Naruto"."""
    t = YEAR.sub(" ", BRACKETS.sub(" ", name))
    t = SERIES_END.sub("", JUNK.sub(" ", t))
    t = re.sub(r"\s+", " ", t).strip(" -–+:,")
    return safe_name(t) if t else ""


def file_segments(stem):
    """The parts of a volume's name that could be a title: "1 - Eragon - Christopher
    Paolini" → ["Eragon", "Christopher Paolini"]; numbers, brackets, tome, scan and
    language words out."""
    t = guess_series(JUNK.sub(" ", stem))
    parts = SPACED_DASH.split(t) if " " in t else t.split("-")
    out = [EDGE_NUMBER.sub("", p).strip(" -–+:,") for p in parts]
    return [p for p in out if re.search(r"[^\W\d_]", p)]


def titles_in_files(name, files):
    """The parts of the folder name the volumes' names say on their own, and the
    author's name: a part every volume says beside a part only some say ("Eragon")
    is the author's, the others' being the titles of the books."""
    folder = word_list(name)
    everywhere = [word_list(BRACKETS.sub(" ", Path(f).stem)) for f in files]
    found = {}
    for f in files:
        for part in file_segments(Path(f).stem):
            run = word_list(part)
            if part_of(run, folder):
                found.setdefault(tuple(run), part)
    constant = {run for run in found if all(holds(list(run), w) for w in everywhere)}
    varying = [found[run] for run in found if run not in constant]
    if varying and constant:
        return varying, found[max(constant, key=len)]
    return list(found.values()), None


def anilist_titles(name, meta):
    """The AniList title when it differs, and whether the folder holds one of the
    series' names with more around it."""
    title = meta.get("title") or ""
    folder = word_list(name)
    wrapped = any(part_of(word_list(n), folder) for n in [title] + list(meta.get("names") or []) if n)
    return ([safe_name(title)] if title else []), wrapped


def folder_candidates(series, taken):
    """The names the folder could take, and why it looks wrong (None when it does not)."""
    name = series["name"]
    files = [v["file"] for v in series["volumes"]]
    from_files, author = titles_in_files(name, files)
    bare = stripped(name)
    from_anilist, wrapped = anilist_titles(name, series["meta"])
    reason = "author" if author else "junk" if bare and bare != name else "more" if from_files or wrapped else None
    names = from_anilist + [safe_name(t) for t in from_files] + [bare]
    out = []
    for n in names:
        if n and n != name and norm(n) not in taken and n not in out:
            out.append(n)
    return out, reason, author


def folder_text(name, reason, author):
    if reason == "author":
        return words(f"Le dossier « {name} » porte le nom de l'auteur, « {author} ».",
                     f"The folder « {name} » holds the author's name, « {author} ».")
    if reason == "junk":
        return words(f"Le dossier « {name} » porte autre chose que le titre de la série.",
                     f"The folder « {name} » holds more than the series' title.")
    return words(f"Le dossier « {name} » ne porte peut-être pas que le titre de la série.",
                 f"The folder « {name} » may hold more than the series' title.")


def folder_name(series, taken):
    """The ailment of a series folder named after more than its title, or None."""
    name = series["name"]
    candidates, reason, author = folder_candidates(series, taken - {norm(name)})
    if not reason or not candidates:
        return None
    cures = [remedy("names_rename_folder", words(f"Renommer le dossier en « {c} »", f"Rename the folder « {c} »"),
                    risky=True, old=name, new=c) for c in candidates]
    return ailment("folder_name", name, folder_text(name, reason, author), cures, series=name, severity="advice")


@chopper.exam
def folder_names(snapshot):
    taken = {norm(s["name"]) for s in snapshot["series"]}
    return [a for a in (folder_name(s, taken) for s in snapshot["series"]) if a]


# ---------- the files of a series named in several ways ----------

def pattern(file):
    """The shape of a volume's name: its numbers as #, its extension out."""
    return re.sub(r"\d+", "#", Path(file).stem)


def file_names(series):
    """The ailment of a series whose numbered volumes are named in several ways, or
    None; a series where two files would take the same name is left out."""
    vols = series["volumes"]
    if not vols or any(v["number"] is None for v in vols):
        return None
    shapes = {pattern(v["file"]) for v in vols}
    if len(shapes) < 2:
        return None
    name = series["name"]
    w = width(v["number"] for v in vols)
    targets = [safe_name(f"{name} {tome(v['number'], w)}{Path(v['file']).suffix}").lower() for v in vols]
    if len(set(targets)) < len(targets):
        return None
    pairs = renames(name, sorted(((v, v["number"]) for v in vols), key=lambda p: p[1]), w)
    examples = ", ".join(f"« {new} »" for _, new in pairs[:2])
    text = words(f"Les fichiers de « {name} » sont nommés de {len(shapes)} façons.",
                 f"The files of « {name} » are named in {len(shapes)} ways.")
    label = words(f"Tous les renommer comme {examples}…", f"Rename them all like {examples}…")
    return ailment("file_names", name, text, [rename_remedy(label, name, pairs)], series=name, severity="advice")


@chopper.exam
def files_named_in_several_ways(snapshot):
    return [a for a in map(file_names, snapshot["series"]) if a]


# ---------- cures ----------

@chopper.cure("names_rename_files")
def rename_files(o, series, names):
    """Renames each volume to its new name; one gone, already so named, or whose new
    name is taken is passed over, so that running it twice does no harm."""
    done = 0
    for vid, new in names:
        try:
            path = o.volume_path(vid)
        except KeyError:
            continue
        if path.name == new or (path.parent / new).exists():
            continue
        o.rename_volume(vid, new)
        done += 1
    return {"renamed": done}


@chopper.cure("names_rename_folder")
def rename_folder(o, old, new):
    """Renames a series folder, unless it has gone or the new name is taken."""
    if not (o.MANGA / old).is_dir() or (o.MANGA / new).exists():
        return {"renamed": None}
    return {"renamed": o.rename_series(old, new)}
