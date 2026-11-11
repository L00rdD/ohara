"""Chopper's examinations of what Ohara knows of each series: what AniList said of it
(nothing, or something that looks like another series), the tomes it lacks, a followed
series that is over, and a decor chosen that cannot be shown any more.

AniList is only asked in the cures: the examinations read the snapshot and nothing else."""

import re
from pathlib import PurePosixPath

import chopper
from chopper import ailment, remedy, words
from names import BRACKETS, guess_series, norm

YEAR = re.compile(r"\b(19|20)\d\d\b")
PART = re.compile(r"\s+[-–]\s+")  # what stands between the parts of a file name: "Tome 1 - Eragon - Paolini"
NAMES_OFFERED = 3  # other names AniList is asked again under, at most
FINISHED = "Terminé"  # AniList's FINISHED, as Ohara keeps it


# ---------- names: what else a series could be called ----------

def tidy(text):
    return re.sub(r"\s+", " ", text).strip(" -–,:.")


def cleaned(name):
    """A folder name without what is in brackets and without years."""
    return tidy(YEAR.sub(" ", BRACKETS.sub(" ", name)))


def file_titles(series):
    """What each volume's file name says its series is."""
    return [guess_series(PurePosixPath(v["file"]).stem) for v in series["volumes"]]


def common_parts(titles):
    """The parts of the file names (between spaced dashes) that every file name has,
    however it writes them: the series' title, or its author."""
    flat = [norm(t) for t in titles]
    parts = {}
    for t in titles:
        for p in PART.split(t):
            key = norm(p)
            if key and not key.isdigit() and all(key in f for f in flat):
                parts.setdefault(key, tidy(p))
    return list(parts.values())


def without(name, part):
    """The name with part taken out, whatever stands between its words."""
    pattern = r"[\W_]*".join(map(re.escape, re.findall(r"[^\W_]+", part)))
    return tidy(re.sub(pattern, " ", name, flags=re.I))


def distinct(names, skip=()):
    """The names, each once (by norm), but those skipped or empty."""
    seen, out = set(skip), []
    for n in names:
        if norm(n) and norm(n) not in seen:
            seen.add(norm(n))
            out.append(n)
    return out


def other_names(series):
    """Names AniList could know the series by, but its folder's: the folder name without
    brackets or years; when every file name has a part the folder name holds too (its
    author), the folder name without it; else the title every file name has. When the
    folder name is itself a part of every file name, the files say nothing more."""
    name = series["name"]
    base = cleaned(name)
    parts = common_parts(file_titles(series))
    found = [base]
    if not {norm(name), norm(base)} & {norm(p) for p in parts}:
        found += [without(base, p) if norm(p) in norm(base) else p for p in parts]
    return distinct(found, {norm(name)})


# ---------- what is read of a series ----------

def entry_of(snapshot, name):
    return snapshot["state"].get("series", {}).get(name, {})


def first_volume(series):
    """The volume of the smallest number (the first of the folder when none has one)."""
    return min(series["volumes"], key=lambda v: (v["number"] is None, v["number"] or 0))


def top_tome(series):
    return int(max((v["number"] for v in series["volumes"] if v["number"]), default=0))


def word_keys(text):
    return {norm(w) for w in re.findall(r"[^\W_]+", text or "") if len(norm(w)) >= 4}


def alike(ours, theirs):
    """Whether two lists of names share something: one name inside another once
    normalised, or a word of four letters or more."""
    mine = [k for k in map(norm, ours) if k]
    found = [k for k in (norm(t or "") for t in theirs) if k]
    if any(a in b or b in a for a in mine for b in found):
        return True
    return bool(set().union(*map(word_keys, ours)) & set().union(*map(word_keys, theirs)))


def our_names(series, entry):
    return [series["name"], entry.get("query") or "", *other_names(series)]


def doubt(series, entry):
    """Why AniList's answer looks like another series' (in words), or None: the series
    owns tomes well past the count AniList gives, or no name of AniList's looks like
    any of ours."""
    meta = series["meta"]
    if not meta.get("id"):
        return None
    total, top = meta.get("volumes") or 0, top_tome(series)
    title = meta.get("title") or ""
    if total and top > total + max(3, total // 2):
        return words(f"AniList donne {total} tomes à « {title} », or tu as le tome {top} : ce n'est sans doute pas la même série.",
                     f"AniList gives “{title}” {total} volumes, yet you have volume {top}: it is likely not the same series.")
    if not alike(our_names(series, entry), [title, *(meta.get("names") or [])]):
        return words(f"AniList a pris « {series['name']} » pour « {title} » : leurs noms n'ont rien en commun.",
                     f"AniList took “{series['name']}” for “{title}”: their names have nothing in common.")
    return None


def runs(numbers):
    """Numbers as runs: [3, 7, 8, 9] → [(3, 3), (7, 9)]."""
    out = []
    for n in sorted(numbers):
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def said_runs(numbers, to):
    """"3, 7 à 9"."""
    return ", ".join(str(a) if a == b else f"{a} {to} {b}" for a, b in runs(numbers))


# ---------- remedies ----------

def ask_again(name, query):
    return remedy("anilist-ask", words(f"Demander à AniList « {query} »", f"Ask AniList for “{query}”"), series=name, query=query)


def first_cover(series):
    vid = first_volume(series)["id"]
    return remedy("decor-choose", words("Mettre la couverture de son premier tome au fond de ses étagères",
                                        "Put its first volume's cover at the back of its shelves"), series=series["name"], decor="vol:" + vid)


# ---------- the examinations ----------

def unknown_one(series, entry):
    name = series["name"]
    asked = norm(entry.get("query") or "")
    cures = [ask_again(name, n) for n in distinct(other_names(series), {asked})[:NAMES_OFFERED]]
    if series["decor"] == "banner" and series["volumes"]:
        cures.append(first_cover(series))
    text = words(f"AniList ne connaît pas « {name} » : pas de couverture, de bannière ni de couleur.",
                 f"AniList does not know “{name}”: no cover, banner or colour.")
    return ailment("anilist-unknown", name, text, cures, series=name, severity="advice")


@chopper.exam
def unknown(snapshot):
    """Series AniList knows nothing of (a novel, or a name it does not read)."""
    return [unknown_one(s, entry_of(snapshot, s["name"])) for s in snapshot["series"] if not s["meta"].get("id")]


@chopper.exam
def doubtful(snapshot):
    """Series AniList took for another one."""
    out = []
    for s in snapshot["series"]:
        why = doubt(s, entry_of(snapshot, s["name"]))
        if why:
            names = distinct([s["name"], *other_names(s)])[:NAMES_OFFERED]
            forget = remedy("anilist-forget", words("Oublier ce qu'a dit AniList", "Forget what AniList said"), series=s["name"])
            out.append(ailment("anilist-doubtful", s["name"], why, [*(ask_again(s["name"], n) for n in names), forget], series=s["name"]))
    return out


@chopper.exam
def missing(snapshot):
    """Series with holes among their tomes, nothing on its way (once it is there, the
    holes left are said); not when AniList's count is doubtful, the holes may be its."""
    out = []
    for s in snapshot["series"]:
        if s["missing"] and not s["coming"] and not doubt(s, entry_of(snapshot, s["name"])):
            many = len(s["missing"]) > 1
            fr = ("les tomes " if many else "le tome ") + said_runs(s["missing"], "à")
            en = ("volumes " if many else "volume ") + said_runs(s["missing"], "to")
            text = words(f"Il manque à « {s['name']} » {fr}.", f"“{s['name']}” lacks {en}.")
            fetch = remedy("tomes-fetch", words("Récupérer les tomes manquants", "Get the missing volumes"), series=s["name"])
            out.append(ailment("tomes-missing", s["name"], text, [fetch], series=s["name"], severity="advice"))
    return out


def over(series, entry):
    """A followed series AniList says is finished, all of it here or on its way: following
    it only looks for tomes that will not come."""
    whole = not series["missing"] and not series["coming"]
    return series["follow"] and series["meta"].get("status") == FINISHED and whole and not doubt(series, entry)


@chopper.exam
def followed_over(snapshot):
    out = []
    for s in snapshot["series"]:
        if over(s, entry_of(snapshot, s["name"])):
            text = words(f"« {s['name']} » est terminé et tu as tous ses tomes : le suivre ne sert plus à rien.",
                         f"“{s['name']}” is finished and you have all its volumes: following it is of no use any more.")
            stop = remedy("follow-stop", words("Ne plus le suivre", "Stop following it"), series=s["name"])
            out.append(ailment("follow-over", s["name"], text, [stop], series=s["name"], severity="advice"))
    return out


def decor_gone(series):
    """Whether the decor chosen cannot be shown: a volume's cover whose volume is gone,
    or the series' own image that is not kept any more."""
    decor = series["decor"]
    if decor.startswith("vol:"):
        return decor[4:] not in {v["id"] for v in series["volumes"]}
    return decor.startswith("own:") and series["kept"] is None


@chopper.exam
def lost_decor(snapshot):
    out = []
    for s in snapshot["series"]:
        if decor_gone(s):
            text = words(f"Le décor choisi pour « {s['name']} » n'existe plus : le fond de ses étagères reste vide.",
                         f"The decor chosen for “{s['name']}” is gone: the back of its shelves stays bare.")
            cures = [remedy("decor-choose", words("Revenir à la bannière", "Back to the banner"), series=s["name"], decor="banner")]
            if not s["meta"].get("banner") and s["volumes"]:
                cures.append(first_cover(s))
            out.append(ailment("decor-gone", s["name"], text, cures, series=s["name"]))
    return out


# ---------- the cures ----------

@chopper.cure("anilist-ask")
def cure_ask(o, series, query):
    """Asks AniList under another name, and keeps its answer as the series' (under the
    folder's name, where the library reads it) with the name asked as its query."""
    found = o.anilist_fetch(query)

    def keep(state):
        entry = o.series_entry(state, series)
        entry["query"] = query
        state["lookups"][o.norm(series)] = found
        if found.get("id"):
            entry["anilist"] = found["id"]
        else:
            entry.pop("anilist", None)
    o.update_state(keep)
    return {"title": found.get("title")}


@chopper.cure("anilist-forget")
def cure_forget(o, series):
    """Forgets AniList's answer: an empty one is kept (AniList is not asked again by
    itself) and the AniList id goes, so nothing of another series is shown."""
    def forget(state):
        state["lookups"][o.norm(series)] = {}
        state["series"].get(series, {}).pop("anilist", None)
    o.update_state(forget)


@chopper.cure("tomes-fetch")
def cure_fetch(o, series):
    return o.complete(series)


@chopper.cure("follow-stop")
def cure_stop(o, series):
    o.set_follow(series, False)


@chopper.cure("decor-choose")
def cure_decor(o, series, decor):
    return o.set_decor(series, decor)
