"""Chopper, Ohara's doctor: examines the library and says what ails it, each ailment
with the remedies to choose from, so that nothing is decided behind your back and
nothing needs more than a touch.

The examinations live in ailments_*.py, beside this file, each registering:
- @exam functions, given a snapshot of the library (see ohara.snapshot()), returning
  ailments made with ailment();
- @cure functions, by kind, run when a remedy of that kind is chosen; they are given
  the ohara module (to rename, delete or fetch) and the remedy's args. An examination
  never imports ohara itself: Ohara runs as __main__, an import would load it twice.

An ailment says itself in French and in English: its text and its remedies' labels
are {"fr": …, "en": …}, so each examination brings its own words."""

import importlib
import sys
import traceback
from pathlib import Path

EXAMS = []
CURES = {}
SEVERITIES = ("trouble", "advice")  # something wrong, or something that could be better


def exam(fn):
    """Registers an examination: fn(snapshot) -> [ailment]."""
    EXAMS.append(fn)
    return fn


def cure(kind):
    """Registers what a remedy of this kind does: fn(ohara, **args)."""
    def register(fn):
        CURES[kind] = fn
        return fn
    return register


def words(fr, en):
    return {"fr": fr, "en": en}


def remedy(kind, label, risky=False, **args):
    """A remedy: what to run (kind, args), what it is called, and whether it changes
    files for good (then it asks to be touched twice)."""
    return {"kind": kind, "label": label, "risky": risky, "args": args}


def ailment(kind, key, text, remedies, series=None, severity="trouble"):
    """An ailment, its id stable from one examination to the next (kind and key), so
    that an ailment set aside stays aside."""
    assert severity in SEVERITIES, severity
    return {"id": f"{kind}:{key}", "kind": kind, "series": series, "severity": severity, "text": text, "remedies": remedies}


_loaded = False


def load():
    """Imports every ailments_*.py beside this file, once."""
    global _loaded
    if _loaded:
        return
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    for f in sorted(here.glob("ailments_*.py")):
        importlib.import_module(f.stem)
    _loaded = True


def examine(snapshot, dismissed=()):
    """Every ailment of the library, but those set aside; an examination that fails is
    said in the log and skipped, the others go on."""
    load()
    found = []
    for fn in EXAMS:
        try:
            found += fn(snapshot)
        except Exception:
            print(f"chopper {fn.__name__}:", traceback.format_exc(limit=3), flush=True)
    seen = set()
    out = []
    for a in found:
        if a["id"] not in dismissed and a["id"] not in seen:
            seen.add(a["id"])
            out.append(a)
    return sorted(out, key=lambda a: (a["series"] or "", SEVERITIES.index(a["severity"]), a["id"]))


def apply(ailments, aid, index, ohara):
    """Runs the remedy number index of the ailment aid. KeyError when either is not
    there any more (the library changed meanwhile)."""
    load()
    found = next((a for a in ailments if a["id"] == aid), None)
    if found is None or not 0 <= index < len(found["remedies"]):
        raise KeyError(aid)
    r = found["remedies"][index]
    return CURES[r["kind"]](ohara, **r["args"]) or {"ok": True}
