"""Chopper's examinations of the downloads, and of what they leave behind in .incoming:
a download that never starts or stays in error, one Transmission no longer knows, one
finished but never filed, the folders nobody waits for, and two downloads bringing the
same tomes.

The cures only ever touch .incoming (and, by filing a download, the series' folder):
each looks again at the state before acting, so that a remedy chosen twice, or after
the download went away by itself, does nothing more."""

import shutil

import chopper
from chopper import ailment, remedy, words

STUCK_AFTER = 12 * 3600  # a pack still at nothing after this is not coming
LOST_AFTER = 3600  # a download Transmission no longer knows, past the time it takes to add it
UNFILED_AFTER = 30 * 60  # Ohara files a finished download within a minute


def ago(seconds):
    """A duration said plainly: hours under two days, days beyond."""
    hours = max(1, round(seconds / 3600))
    if hours < 48:
        return words(f"{hours} h", f"{hours} h")
    days = round(hours / 24)
    return words(f"{days} jours", f"{days} days")


def sent(snap, info):
    """The state's entry of a download (empty when the state has forgotten it)."""
    return snap["state"]["downloads"].get(info["hash"]) or {}


def since(snap, entry, key="at"):
    return snap["now"] - entry.get(key, snap["now"])


# ---------- a download that does not come ----------

def stuck_text(info, entry, snap):
    if info["state"] == "error":
        why = info.get("error") or "?"
        return words(f"« {info['title']} » est en erreur : {why}.", f"“{info['title']}” is in error: {why}.")
    d = ago(since(snap, entry))
    return words(f"« {info['title']} » n'a pas commencé depuis {d['fr']} : personne ne le partage peut-être plus.",
                 f"“{info['title']}” has not started for {d['en']}: maybe nobody shares it any more.")


def is_stuck(info, entry, snap):
    """In error, or a pack of volumes still at nothing long after it was sent; the
    soundtracks that do not start are Brook's (see ohara.stalled)."""
    if info["state"] == "error":
        return True
    waiting = info["state"] == "downloading" and info["pct"] == 0
    return info["kind"] != "ost" and waiting and since(snap, entry) > STUCK_AFTER


@chopper.exam
def stuck(snap):
    """A download that does not come: cancel it, or give it up for another release of
    the same tomes (ohara remembers the one given up on, not to take it again)."""
    found = []
    for info in snap["downloads"]:
        entry = sent(snap, info)
        if is_stuck(info, entry, snap):
            remedies = [remedy("dl-cancel", words("L'annuler", "Cancel it"), risky=True, hash=info["hash"])]
            if info["kind"] != "ost":
                remedies.insert(0, remedy("dl-another", words("L'annuler et en chercher un autre", "Cancel it and look for another"), risky=True, hash=info["hash"]))
            found.append(ailment("dl-stuck", info["hash"], stuck_text(info, entry, snap), remedies, series=info["series"]))
    return found


@chopper.cure("dl-another")
def cure_another(o, hash):
    """Gives a download up and looks for its tomes again, among the other releases."""
    if hash not in o.load_state()["downloads"]:
        return {"sent": [], "nowhere": []}
    return o.complete(o.give_up(hash))


# ---------- a download removed outside Ohara ----------

@chopper.exam
def lost(snap):
    unknown = [i for i in snap["downloads"] if i["state"] == "unknown"]
    if len(unknown) > 1 and len(unknown) == len(snap["downloads"]):
        return []  # none known at all: Transmission is away, not every download gone
    found = []
    for info in unknown:
        entry = sent(snap, info)
        if since(snap, entry) <= LOST_AFTER:
            continue
        text = words(f"Transmission ne connaît plus « {info['title']} » : il a été retiré hors d'Ohara.",
                     f"Transmission no longer knows “{info['title']}”: it was removed outside Ohara.")
        remedies = [remedy("dl-forget", words("L'oublier", "Forget it"), hash=info["hash"]),
                    remedy("dl-forget", words("L'oublier et effacer ce qu'il a laissé", "Forget it and delete what it left"),
                           risky=True, hash=info["hash"], wipe=True)]
        found.append(ailment("dl-lost", info["hash"], text, remedies, series=info["series"]))
    return found


# ---------- a download finished but never filed ----------

@chopper.exam
def unfiled(snap):
    found = []
    for info in snap["downloads"]:
        entry = sent(snap, info)
        done = info["state"] == "done" or info["pct"] >= 100
        # Transmission does not say when it finished: the time it was sent stands for it
        if not done or since(snap, entry, "done_at" if "done_at" in entry else "at") <= UNFILED_AFTER:
            continue
        text = words(f"« {info['title']} » est fini mais n'a pas été rangé : le ranger échoue.",
                     f"“{info['title']}” is finished but was not filed: filing it fails.")
        remedies = [remedy("dl-file", words("Essayer de le ranger à nouveau", "Try filing it again"), hash=info["hash"]),
                    remedy("dl-cancel", words("L'abandonner", "Drop it"), risky=True, hash=info["hash"])]
        found.append(ailment("dl-unfiled", info["hash"], text, remedies, series=info["series"]))
    return found


# ---------- what is left in .incoming ----------

@chopper.exam
def leftovers(snap):
    waited = {d.get("folder") for d in snap["state"]["downloads"].values()}
    found = []
    for name in snap["incoming"]:
        if name in waited:
            continue
        text = words(f"« {name} » traîne dans .incoming : aucun téléchargement ne l'attend.",
                     f"“{name}” lies in .incoming: no download waits for it.")
        found.append(ailment("dl-leftover", name, text, [remedy("dl-delete", words("L'effacer", "Delete it"), risky=True, name=name)],
                             severity="advice"))
    return found


# ---------- the same tomes coming twice ----------

def tomes(entry):
    lo, hi = entry["range"]
    return set(range(lo, hi + 1))


def span(numbers):
    lo, hi = min(numbers), max(numbers)
    return f"T{lo}" if lo == hi else f"T{lo}–T{hi}"


def twice_ailment(old, new, series, common):
    (_, a), (h, b) = old, new
    text = words(f"« {a['title']} » et « {b['title']} » apportent tous deux {span(common)}.",
                 f"“{a['title']}” and “{b['title']}” both bring {span(common)}.")
    cancel = remedy("dl-cancel", words("Annuler le plus récent", "Cancel the newer one"), risky=True, hash=h)
    return ailment("dl-twice", f"{old[0]}+{h}", text, [cancel], series=series, severity="advice")


@chopper.exam
def twice(snap):
    packs = sorted(((h, d) for h, d in snap["state"]["downloads"].items() if d.get("kind", "volumes") == "volumes" and d.get("range")),
                   key=lambda p: (p[1].get("at", 0), p[0]))
    found = []
    for i, old in enumerate(packs):
        for new in packs[i + 1:]:
            common = tomes(old[1]) & tomes(new[1])
            if old[1]["series"] == new[1]["series"] and common:
                found.append(twice_ailment(old, new, old[1]["series"], common))
    return found


# ---------- the cures ----------

def inside(o, name):
    """The path of one entry of .incoming; a name that is not plainly one of its entries
    (empty, dots, a slash) is refused, so nothing outside it is ever reached."""
    if not name or name in (".", "..") or any(c in name for c in "/\\\0"):
        raise KeyError(f"not an entry of .incoming: {name!r}")
    return o.INCOMING / name


def remove(o, name):
    """Deletes one entry of .incoming, and nothing else. A link is taken away, not what
    it points to."""
    p = inside(o, name)
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists() or p.is_symlink():
        p.unlink()


def empty(o, name):
    p = o.INCOMING / name
    return p.is_dir() and not p.is_symlink() and not any(p.iterdir())


@chopper.cure("dl-cancel")
def cure_cancel(o, hash):
    """Drops a download and its folder (Transmission forgets an id it does not know). A
    soundtrack is given up the way Brook does it, so that he takes another."""
    entry = o.load_state()["downloads"].get(hash)
    folder = (entry or {}).get("folder")
    if folder is not None:
        inside(o, folder)  # a folder that is not one of .incoming's: nothing is done
    if entry and entry.get("kind") == "ost":
        return o.give_up_music(hash, entry)
    o.cancel(hash)
    if folder:
        remove(o, folder)


@chopper.cure("dl-forget")
def cure_forget(o, hash, wipe=False):
    """Forgets a download Transmission no longer has, and its folder when it is empty
    or when asked to; refused while Transmission still has it."""
    if o.torrents([hash]):
        raise RuntimeError("Transmission still has this download")
    entry = o.update_state(lambda s: s["downloads"].pop(hash, None))
    folder = (entry or {}).get("folder")
    if folder and (wipe or empty(o, folder)):
        remove(o, folder)


@chopper.cure("dl-file")
def cure_file(o, hash):
    """Files a finished download once more; nothing when it was filed meanwhile."""
    entry = o.load_state()["downloads"].get(hash)
    if not entry:
        return {"gone": True}
    inside(o, entry.get("folder", ""))
    o.file_download(hash, entry)


@chopper.cure("dl-delete")
def cure_delete(o, name):
    """Deletes a leftover of .incoming, unless a download has taken it meanwhile."""
    if any(d.get("folder") == name for d in o.load_state()["downloads"].values()):
        raise KeyError(f"a download waits for {name}")
    remove(o, name)
