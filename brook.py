"""Brook, Ohara's musician: finds the soundtrack of each series among the indexers'
audio releases, and reads the albums and titles of the music once it is in.
Pure functions; ohara.py does the searching, downloading and serving."""

import re
from pathlib import Path

from names import norm

AUDIO = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/ogg",
         ".flac": "audio/flac", ".wav": "audio/wav"}
ART = (".jpg", ".jpeg", ".png", ".webp")
SOUNDTRACK = re.compile(r"(?i)\b(o\.?s\.?t|soundtracks?|original\s+sound\s*track|bgm|music\s+collection|score)\b|サウンドトラック|サントラ")
NOT_MUSIC = re.compile(r"(?i)\b(audiobook|drama\s*cd|radio|podcast)\b")
FORMAT_ORDER = [(re.compile(r"(?i)\bmp3\b|320|v0"), 0), (re.compile(r"(?i)\b(aac|m4a|opus)\b"), 1), (re.compile(r"(?i)\bflac\b|lossless"), 2)]
SIZE_SWEET = (150e6, 2.5e9)  # what a soundtrack weighs, from one album to a full collection


def is_audio(cats):
    return any(3000 <= c < 4000 for c in cats)


def names_of(series, meta):
    """The names a series may go by in a release title, compared without spaces or accents."""
    names = [series] + [n for n in (meta or {}).get("names", []) if n]
    return {norm(n) for n in names if len(norm(n)) >= 3}


def is_soundtrack(result, names):
    """An audio release whose title names the series and says it is a soundtrack."""
    title = result.get("title", "")
    cats = [c.get("id", 0) for c in result.get("categories", [])]
    if not is_audio(cats) or NOT_MUSIC.search(title) or not SOUNDTRACK.search(title):
        return False
    flat = norm(title)
    return any(n in flat for n in names)


def audio_format(title):
    """0 for MP3, 1 for AAC/Opus, 2 for FLAC, 1 when the title does not say."""
    for pattern, rank in FORMAT_ORDER:
        if pattern.search(title):
            return rank
    return 1


def size_penalty(size):
    """0 within the sweet spot, growing as a release gets too small or too heavy."""
    low, high = SIZE_SWEET
    if size < low:
        return (low - size) / low
    if size > high:
        return (size - high) / high
    return 0


def best_first(r):
    """With seeders first; then the right size, the lighter format, the most seeders."""
    return (r["seeders"] == 0, round(size_penalty(r["size"]) * 4), audio_format(r["title"]), -r["seeders"])


def clean_title(stem):
    """A track's title from its file name: "01 - We Are!" → "We Are!"."""
    t = re.sub(r"^\s*(disc\s*\d+\s*[-_.]?\s*)?\d{1,3}(\s*[-_.)]\s*|\s+)", "", stem, flags=re.I)
    t = re.sub(r"[_]+", " ", t).strip(" -.")
    return t or stem


def id3_title(head):
    """The TIT2 frame of an ID3v2.3/2.4 tag, from the first bytes of an MP3."""
    if len(head) < 10 or head[:3] != b"ID3":
        return None
    version = head[3]
    end = 10 + sum((b & 0x7F) << (7 * (3 - i)) for i, b in enumerate(head[6:10]))
    at = 10
    while at + 10 <= min(end, len(head)):
        frame, raw = head[at:at + 4], head[at + 4:at + 8]
        size = sum((b & 0x7F) << (7 * (3 - i)) for i, b in enumerate(raw)) if version == 4 else int.from_bytes(raw, "big")
        if not frame.strip(b"\x00") or size <= 0:
            return None
        if frame == b"TIT2":
            return decode_text(head[at + 10:at + 10 + size])
        at += 10 + size
    return None


def decode_text(data):
    if not data:
        return None
    encoding = {0: "latin-1", 1: "utf-16", 2: "utf-16-be", 3: "utf-8"}.get(data[0], "latin-1")
    text = data[1:].decode(encoding, errors="ignore").strip("\x00 ")
    return text or None


def flac_title(head):
    """The TITLE of a FLAC's Vorbis comment, from its first bytes."""
    if head[:4] != b"fLaC":
        return None
    at = 4
    while at + 4 <= len(head):
        last, kind, size = head[at] & 0x80, head[at] & 0x7F, int.from_bytes(head[at + 1:at + 4], "big")
        if kind == 4:
            return vorbis_title(head[at + 4:at + 4 + size])
        if last:
            return None
        at += 4 + size
    return None


def vorbis_title(block):
    at = 4 + int.from_bytes(block[0:4], "little")
    count = int.from_bytes(block[at:at + 4], "little")
    at += 4
    for _ in range(count):
        n = int.from_bytes(block[at:at + 4], "little")
        entry = block[at + 4:at + 4 + n].decode("utf-8", errors="ignore")
        at += 4 + n
        if entry.lower().startswith("title="):
            return entry[6:].strip() or None
    return None


def track_title(path, head):
    """A track's title: its tag when it has one, else its file name made readable."""
    tagged = id3_title(head) if path.suffix.lower() == ".mp3" else flac_title(head) if path.suffix.lower() == ".flac" else None
    return tagged or clean_title(Path(path).stem)


def album_of(relative):
    """The album of a track from its path under the series' music folder: its first
    folder, or the series' own folder for loose tracks."""
    parts = Path(relative).parts
    return parts[0] if len(parts) > 1 else ""
