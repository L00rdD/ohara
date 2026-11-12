"""What Ohara reads in names: the series and the tomes of a release title, the
number of a volume file, the language of a release. Pure functions, no I/O."""

import re
import unicodedata
from pathlib import Path

FRENCH = re.compile(r"(?i)\b(fr|vf|vff|french|fran[cç]ais|truefrench)\b")
ENGLISH = re.compile(r"(?i)\b(eng|english|scanlated|digital|viz|yen press)\b")
JAPANESE = re.compile(r"(?i)\b(jp|jap|raw)\b|[぀-ヿ]|巻")
FRENCH_TRACKERS = ("YggReborn", "Torrent9", "World-torrent")
LANG_ORDER = {"FR": 0, "EN": 1, "?": 2, "JP": 3}

# "T05", "Tome 5", "Tome #5", "Tome n°5", "v05", "Vol. 5", "Volume 5"; not the t of "Scantrad"
_TOME = r"(?<![a-z])(?:tomes?|t|vol(?:ume)?s?\.?|v)[\s._-]*(?:#|n[°o]\.?)?\s*0*"
BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}")
# a tome said in brackets, "[Tome 1]", "(Vol. 2)"; not "[V2]", a scan's version
BRACKETED_TOME = re.compile(r"(?i)[\[(]\s*(?:tomes?|vol(?:ume)?s?\.?)\s*(?:#|n[°o]\.?)?\s*0*(\d+(?:\.\d+)?)\s*[\])]")
LONE_NUMBER = re.compile(r"(?<![\d.])(\d{1,4}(?:\.\d+)?)(?![\d])")
VOLUME = re.compile(r"(?i)" + _TOME + r"(\d+(?:\.\d+)?)")
TOME_RANGE = re.compile(r"(?i)" + _TOME + r"(\d{1,4})(?:\s*(?:à|-|–|to|&|et)\s*(?:(?:tomes?|t|vol\.?|v)[\s._-]*)?0*(\d{1,4}))?(?!\d)")
# a webtoon's chapter or episode: "c001", "ch. 12", "Chapter 5", "Episode 3"
CHAPTER = re.compile(r"(?i)(?<![^\W\d_])(?:c|ch|chap|chapters?|chapitres?|ep|[ée]pisodes?)[\s._-]*#?\s*0*(\d+(?:\.\d+)?)")
# a webtoon's season: "S1", "S1-2", "Season 2", "Saison 2"
SEASON = r"s(?:eason|aison)?\s*\d{1,2}"
# a run of chapters in a release title: "ch001-158", "c045-060", "Chapters 1 to 30"
CHAPTER_RANGE = re.compile(r"(?i)(?<![^\W\d_])(?:c|ch|chap|chapters?|chapitres?|ep|[ée]pisodes?)[\s._-]*#?\s*0*(\d{1,4})"
                           r"(?:\s*(?:à|-|–|to)\s*(?:(?:c|ch|chap)\.?\s*)?0*(\d{1,4}))?(?!\d)")
# what says a release is a webtoon's: its word, a webtoon store, a season
WEBTOON = re.compile(r"(?i)\bweb-?toons?\b|\btappytoon\b|\blezhin\b|\bs(?:eason|aison)?\s*\d{1,2}(?:\s*-\s*\d{1,2})?\b")
SERIES_END = re.compile(r"(?i)[\s._-]*(\b(tomes?|t\d+|vol(ume)?s?|v\d+|int[ée]grale|cbz|cbr|pdf|epub|ebook|complete|chapitres?|"
                        r"(?:c|ch|chap|chapters?|ep|episodes?)\.?\s*\d+|" + SEASON + r")\b|\d+\s*(à|-|to)\s*\d+|\|).*$")


def natural(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text)]


def norm(name):
    """A name to compare series by: no accents, case, spaces or punctuation."""
    flat = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", flat.lower())


def guess_series(title):
    """The series name in a release title: "Naruto - T01 à T72 [CBZ] Fr" → "Naruto"."""
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}", " ", title)
    t = re.sub(r"[._]+", " ", t)
    t = SERIES_END.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" -–+:,")
    return t or title.strip()


def safe_name(name):
    """A series name usable as a folder name."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:120] or "Sans titre"


def volume_number(filename):
    """5.0 for "Naruto T05.cbz", None when the name gives no number. What is in
    brackets is left out ("[V2]" is a scan's version, "(2023)" a year) unless it is
    the only tome said ("Harry Potter [Tome 1]"); without a word for tome, the last
    number standing alone is taken ("One Piece 105")."""
    name = BRACKETS.sub(" ", Path(filename).stem)
    m = VOLUME.search(name) or BRACKETED_TOME.search(Path(filename).stem) or CHAPTER.search(name)
    if m:
        return float(m.group(1))
    lone = LONE_NUMBER.findall(name)
    return float(lone[-1]) if lone else None


def is_chapter(filename):
    """Whether a file holds a webtoon's chapter rather than a tome: "Ashtarte c001
    (2022) (Digital).cbz", "Return of the Blossoming Blade - #001 - Episode 1.cbz"."""
    name = BRACKETS.sub(" ", Path(filename).stem)
    return not VOLUME.search(name) and bool(CHAPTER.search(name))


def volume_label(filename):
    n = volume_number(filename)
    if n is None:
        return Path(filename).stem
    return f"{'Chapitre' if is_chapter(filename) else 'Tome'} {n:g}"


def tome_range(title):
    """(1, 72) for "Naruto - T01 à T72", (98, 98) for "Tome 98", None when the
    title gives no tome."""
    m = TOME_RANGE.search(title)
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return (lo, hi) if hi >= lo else (lo, lo)


def chapter_range(title):
    """(1, 158) for "… ch001-158", (12, 12) for "… c012", None when the title says no
    chapter (a season, "S1-2", says which chapters only inside)."""
    m = CHAPTER_RANGE.search(BRACKETS.sub(" ", title))
    if not m:
        return None
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return (lo, hi) if hi >= lo else (lo, lo)


def webtoon_pack(title):
    """Whether a release is a webtoon's chapters: it says webtoon, a webtoon store or
    a season, or it holds chapters in English rather than tomes."""
    english_chapters = chapter_range(title) and not tome_range(title) and language(title) != "FR"
    return bool(WEBTOON.search(title) or english_chapters)


def language(title, indexer=""):
    """FR, EN, JP or ?; a French tracker's release is French unless it says otherwise."""
    if FRENCH.search(title):
        return "FR"
    if ENGLISH.search(title):
        return "EN"
    if JAPANESE.search(title):
        return "JP"
    return "FR" if indexer in FRENCH_TRACKERS else "?"


def speed(seeders):
    """How fast a release will come, in words."""
    if seeders >= 10:
        return "rapide"
    if seeders >= 3:
        return "correct"
    return "lent" if seeders else "bloqué"
