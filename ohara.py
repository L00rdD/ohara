"""Ohara: a manga library on the Pi. Finds volumes through Prowlarr, downloads them
with Transmission, files them in /manga/<Series>/, follows the series for their new
volumes and serves them to the reader. Covers and series facts come from AniList.

Only the standard library and Pillow (for the covers). Every setting comes from the
environment (see README.md and docker-compose.yml)."""

import base64
import collections
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
import http.cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import brook  # noqa: E402
import chapters  # noqa: E402
import chopper  # noqa: E402
import den_den  # noqa: E402
import franky  # noqa: E402
import robin  # noqa: E402
from names import (LANG_ORDER, chapter_range, guess_series, is_chapter, language, natural, norm,  # noqa: E402
                   safe_name, speed, tome_range, volume_label, volume_number, webtoon_pack)

MANGA = Path(os.environ.get("OHARA_MANGA", "/manga"))
STATE_DIR = MANGA / ".ohara"
MUSIC = MANGA / ".ost"
INCOMING = MANGA / ".incoming"
# the same folder as Transmission sees it
TRANSMISSION_INCOMING = os.environ.get("OHARA_TRANSMISSION_DIR", "/data/manga/.incoming")
TRANSMISSION_URL = os.environ.get("OHARA_TRANSMISSION_URL", "http://transmission:9091/transmission/rpc")
PROWLARR_URL = os.environ.get("OHARA_PROWLARR_URL", "http://prowlarr:9696")
PROWLARR_KEY = os.environ.get("OHARA_PROWLARR_KEY", "")
PROWLARR_CONFIG = os.environ.get("OHARA_PROWLARR_CONFIG", "/config/prowlarr/config.xml")
TRANSMISSION_USER = os.environ.get("OHARA_TRANSMISSION_USER", "")
TRANSMISSION_PASSWORD = os.environ.get("OHARA_TRANSMISSION_PASSWORD", "")
INDEXERS = [n.strip() for n in os.environ.get("OHARA_INDEXERS", "YggReborn,Nyaa.si,Knaben").split(",") if n.strip()]
ANILIST = "https://graphql.anilist.co"
FOLLOW_EVERY = float(os.environ.get("OHARA_FOLLOW_HOURS", "12")) * 3600
NEW_FOR = 7 * 86400  # a volume stays "new" a week, until it is opened
WEB = Path(__file__).with_name("web")
PORT = int(os.environ.get("OHARA_PORT", "8585"))
# Discord (see den_den.py): a channel's webhook, the address Ohara is reached at for the
# links of its messages, and their language
DISCORD_WEBHOOK = os.environ.get("OHARA_DISCORD_WEBHOOK", "")
OHARA_URL = os.environ.get("OHARA_URL", "").rstrip("/")
DISCORD_LANG = "en" if os.environ.get("OHARA_DISCORD_LANG") == "en" else "fr"
DISCORD_NAME = os.environ.get("OHARA_DISCORD_NAME", "")  # else the webhook's own name

IMAGE = re.compile(r"\.(jpe?g|png|webp|gif|avif)$", re.I)
READABLE = (".cbz", ".zip")
KEPT = (".cbz", ".zip", ".pdf", ".epub")
ARCHIVES = (".cbr", ".rar", ".cb7", ".7z")
VIDEO = re.compile(r"(?i)\b(1080p|720p|2160p|x26[45]|hevc|web-?dl|webrip|bluray)\b|\.(mkv|mp4|avi)\b")
EPISODE = re.compile(r"(?i)\bs\d\d(e\d\d)?\b")  # a show's season and episode, or a webtoon's season
BOOKISH = re.compile(r"(?i)\b(cbz|cbr|cb7|tomes?|t\d{1,3}|vol(ume)?s?\.?\s*\d+|v\d{1,3}|scans?)\b")

lock = threading.Lock()


# ---------- state: downloads, reading progress, followed series, AniList answers ----------

def load_state():
    try:
        state = json.loads((STATE_DIR / "state.json").read_text())
    except (OSError, ValueError):
        state = {}
    for key in ("downloads", "series", "lookups", "settings", "spines", "music", "moods", "franky", "chapters", "dismissed"):
        state.setdefault(key, {})
    if "readers" not in state:  # a state from before the readers: its reading is the first one's
        state["readers"] = {FIRST_READER: {"name": "", "progress": state.pop("progress", {})}}
    return state


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / "state.tmp"
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    tmp.replace(STATE_DIR / "state.json")


BACKUPS_KEPT = 7  # days of the state kept in .ohara/backups


def backup_state(today=None):
    """Once a day, a copy of the state (where you are in each volume, every choice made)
    in .ohara/backups, the last BACKUPS_KEPT days kept: a state emptied by mistake can
    be put back by hand."""
    src = STATE_DIR / "state.json"
    if not src.exists():
        return
    folder = STATE_DIR / "backups"
    out = folder / f"state-{today or time.strftime('%Y-%m-%d')}.json"
    if out.exists():
        return
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, out)
    for old in sorted(folder.glob("state-*.json"))[:-BACKUPS_KEPT]:
        old.unlink()


def update_state(change):
    """Applies change(state) under the lock and saves the result."""
    with lock:
        state = load_state()
        result = change(state)
        save_state(state)
        return result


def series_entry(state, name):
    return state["series"].setdefault(name, {"follow": False, "query": name})


# ---------- readers: the volumes are shared, where each one is in them is not ----------

FIRST_READER = "1"  # the reader given the reading kept before there were readers
READER_NAME = 30  # characters at most in a reader's name


class NoReader(Exception):
    """A request about reading that does not say who reads, among several readers."""


def reader_of(state, rid):
    """Who reads: the reader asked for, else the only one there is (a library read by
    one person never asks), else None."""
    known = state["readers"]
    if rid in known:
        return rid
    return next(iter(known)) if len(known) == 1 else None


def progress_of(state, rid):
    """Where a reader is in each volume ({} when who reads cannot be told)."""
    rid = reader_of(state, rid)
    return state["readers"][rid].setdefault("progress", {}) if rid else {}


def reading_of(state, rid):
    """A reader's progress, to change it: NoReader when who reads cannot be told."""
    if not reader_of(state, rid):
        raise NoReader()
    return progress_of(state, rid)


def readers(state, rid=None):
    """The readers, in the order they came, and the one asking."""
    listed = [{"id": k, "name": r.get("name", "")} for k, r in state["readers"].items()]
    return {"readers": listed, "reader": reader_of(state, rid)}


def reader_name(name):
    name = " ".join(str(name).split())[:READER_NAME]
    if not name:
        raise ValueError("a reader needs a name")
    return name


def add_reader(name):
    """A new reader, starting with nothing read."""
    name, rid = reader_name(name), secrets.token_hex(4)

    def change(state):
        state["readers"][rid] = {"name": name, "progress": {}}
        return readers(state, rid)
    return update_state(change)


def rename_reader(rid, name, asking=None):
    name = reader_name(name)

    def change(state):
        state["readers"][rid]["name"] = name
        return readers(state, asking)
    return update_state(change)


def forget_reader(rid, asking=None):
    """Forgets a reader and their reading; the last one stays."""
    def change(state):
        if rid not in state["readers"] or len(state["readers"]) < 2:
            raise KeyError(rid)
        del state["readers"][rid]
        return readers(state, asking)
    return update_state(change)


def move_reading(state, rename):
    """Every reader's progress, its volumes renamed by rename(id) -> new id or None."""
    for r in state["readers"].values():
        r["progress"] = move_keys(r.get("progress", {}), rename)


def last_opened(state, vid):
    """When anyone last opened a volume."""
    return max((r.get("progress", {}).get(vid, {}).get("at", 0) for r in state["readers"].values()), default=0)


# ---------- AniList: cover, colour, status and number of volumes of a series ----------

ANILIST_QUERY = """query($s: String) { Page(perPage: 6) { media(search: $s, type: MANGA, sort: SEARCH_MATCH) {
  id title { romaji english native } synonyms coverImage { extraLarge large color } bannerImage volumes chapters status startDate { year } } } }"""
STATUS = {"RELEASING": "En cours", "FINISHED": "Terminé", "HIATUS": "En pause", "CANCELLED": "Arrêté", "NOT_YET_RELEASED": "À paraître"}


def anilist_fetch(name):
    body = json.dumps({"query": ANILIST_QUERY, "variables": {"s": name}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "Ohara/1.0"}
    found = http_json(ANILIST, data=body, headers=headers, timeout=15)["data"]["Page"]["media"]
    if not found:
        return {}
    m = best_match(name, found)
    return {
        "id": m["id"],
        "title": m["title"]["english"] or m["title"]["romaji"],
        "cover": m["coverImage"]["extraLarge"] or m["coverImage"]["large"],
        "color": m["coverImage"]["color"],
        "banner": m.get("bannerImage"),
        "names": [n for n in [m["title"]["romaji"], m["title"]["english"], *(m.get("synonyms") or [])] if n],
        "status": STATUS.get(m["status"], ""),
        "volumes": m["volumes"],
        "chapters": m.get("chapters"),
        "year": (m.get("startDate") or {}).get("year"),
    }


def normalised(names):
    """The names compared, without those that normalise to nothing (Japanese only)."""
    return [n for n in (norm(x or "") for x in names) if n]


def best_match(name, found):
    """The AniList entry titled like the name, else one with it as a synonym, else
    one whose title contains it, else AniList's first answer."""
    want = norm(name)
    ranks = [
        [m for m in found if want in normalised(m["title"].values())],
        [m for m in found if want in normalised(m.get("synonyms") or [])],
        [m for m in found if any(want in t or t in want for t in normalised(m["title"].values()))],
        found,
    ]
    return next(r for r in ranks if r)[0]


def fresh(cached, name=""):
    """An AniList answer kept since banners and names are asked for, or a known miss;
    a colour edition's miss is asked again, under the name of the series it colours."""
    if not cached:
        return uncoloured(name) == name.strip()
    return "banner" in cached and "names" in cached


def uncoloured(name):
    """A series' name without its colour words: "One Piece en couleurs" → "One Piece"."""
    return re.sub(r"[\s\-–:()\[\]]+$", "", re.sub(r"(?i)\b(en )?couleurs?\b|\bcolou?r(ed)?\b|カラー", "", name)).strip()


def lookup(name):
    """The AniList facts of a series name, asked once and kept (an empty dict when
    AniList does not know it; nothing kept when it does not answer). A colour edition
    is asked under the name of the series it colours, whose banner, cover and chapters
    are its own."""
    key = norm(name)
    cached = load_state()["lookups"].get(key)
    # kept answers from before the banners and names were asked for are asked again
    if cached is not None and fresh(cached, name):
        return cached
    try:
        found = anilist_fetch(uncoloured(name) or name)
    except Exception:
        return {}

    def keep(state):
        state["lookups"][key] = found
    update_state(keep)
    return found


def lookups(names):
    with ThreadPoolExecutor(6) as pool:
        return dict(zip(names, pool.map(lookup, names)))


# ---------- Prowlarr ----------

def prowlarr_key():
    """OHARA_PROWLARR_KEY, or else the key in Prowlarr's own config.xml (mounted)."""
    if PROWLARR_KEY:
        return PROWLARR_KEY
    text = Path(PROWLARR_CONFIG).read_text()
    return re.search(r"<ApiKey>([^<]+)</ApiKey>", text).group(1)


def http_json(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def chosen_indexers():
    """The indexers to search, by name: those picked in the settings, or else
    OHARA_INDEXERS."""
    return load_state()["settings"].get("indexers") or INDEXERS


def indexer_ids(key):
    found = http_json(f"{PROWLARR_URL}/api/v1/indexer", headers={"X-Api-Key": key})
    chosen = chosen_indexers()
    return [i["id"] for i in found if i["name"] in chosen and i.get("enable")]


def indexers():
    """Every indexer of Prowlarr, whether Prowlarr has it on, whether it is failing,
    and whether Ohara searches it."""
    key = prowlarr_key()
    found = http_json(f"{PROWLARR_URL}/api/v1/indexer", headers={"X-Api-Key": key})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    # set aside by Prowlarr after failures, until disabledTill
    failing = {s["indexerId"] for s in http_json(f"{PROWLARR_URL}/api/v1/indexerstatus", headers={"X-Api-Key": key}) if (s.get("disabledTill") or "") > now}
    chosen = chosen_indexers()
    out = [{"name": i["name"], "on": bool(i.get("enable")), "failing": i["id"] in failing, "chosen": i["name"] in chosen,
            "books": any(c.get("id", 0) // 1000 == 7 for c in (i.get("capabilities") or {}).get("categories", []))} for i in found]
    return sorted(out, key=lambda i: (not i["chosen"], i["name"].lower()))


def choose_indexers(names):
    def change(state):
        state["settings"]["indexers"] = [n for n in names if isinstance(n, str)]
    update_state(change)


def is_manga(result):
    """Books (where YggReborn, Nyaa and Knaben file manga), or a title that says
    CBZ or tomes; never videos, music, games or adult releases."""
    title = result.get("title", "")
    cats = [c.get("id", 0) for c in result.get("categories", [])]
    books = any(7000 <= c < 8000 for c in cats)
    if VIDEO.search(title) or (EPISODE.search(title) and not books) or any(2000 <= c < 7000 for c in cats):
        return False
    return books or bool(BOOKISH.search(title))


def release(result):
    """What the page needs of a Prowlarr result; the token stands for it in a grab."""
    token = hashlib.sha1((result.get("guid") or result["title"]).encode()).hexdigest()[:16]
    seeders = result.get("seeders", 0)
    return {
        "token": token,
        "title": result["title"],
        "series": guess_series(result["title"]),
        "lang": language(result["title"], result.get("indexer", "")),
        "range": tome_range(result["title"]),
        "chapters": chapter_range(result["title"]),
        "size": result.get("size", 0),
        "seeders": seeders,
        "speed": speed(seeders),
        "indexer": result.get("indexer", ""),
        "_url": result.get("magnetUrl") or result.get("downloadUrl"),
    }


found_releases = {}


def find_releases(query, category=7000, keep=is_manga, which=None):
    """Every release of a category Prowlarr finds for query that keep() accepts (manga
    volumes by default) on the indexers which() picks (those chosen in the settings
    by default), remembered for a grab."""
    key = prowlarr_key()
    ids = (which or indexer_ids)(key)
    # asking for the category on the indexers' side: manga are under Books, not drowned in videos
    params = [("query", query), ("type", "search"), ("categories", category)] + [("indexerIds", i) for i in ids]
    url = f"{PROWLARR_URL}/api/v1/search?" + urllib.parse.urlencode(params)
    results = [release(r) for r in http_json(url, headers={"X-Api-Key": key}, timeout=150) if keep(r)]
    for r in results:
        found_releases[r["token"]] = r
    return results


def coverage(r):
    return r["range"][1] - r["range"][0] + 1 if r["range"] else 0


def best_first(r):
    """French, then a release that will come, then the most tomes, then the most seeders."""
    return (LANG_ORDER[r["lang"]], r["seeders"] == 0, -coverage(r), -r["seeders"])


def public(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


def group_releases(results):
    """{AniList id or name: [releases]}: one group per series, whatever the release calls it."""
    names = sorted({r["series"] for r in results})
    facts = lookups(names)
    groups = {}
    for r in results:
        meta = facts.get(r["series"]) or {}
        groups.setdefault(meta.get("id") or norm(r["series"]), []).append(r)
    return groups, facts


def search(query):
    """The series found for query, each with its releases, the best one first."""
    results = find_releases(query)
    groups, facts = group_releases(results)
    have = {norm(n): n for n in library_names()}
    out = []
    for releases in groups.values():
        releases.sort(key=best_first)
        meta = facts.get(releases[0]["series"]) or {}
        name = owned_name(releases, meta, have)
        out.append({"name": name, "meta": meta, "owned": name in have.values(), "releases": [public(r) for r in releases]})
    out.sort(key=lambda g: (LANG_ORDER[g["releases"][0]["lang"]], -sum(r["seeders"] for r in g["releases"])))
    return out


def owned_name(releases, meta, have):
    """The folder a group goes to: the series already in the library under one of its
    names, or else the name the best release gives it."""
    for r in releases:
        if norm(r["series"]) in have:
            return have[norm(r["series"])]
    for state_name, entry in load_state()["series"].items():
        if meta.get("id") and entry.get("anilist") == meta.get("id"):
            return state_name
    return safe_name(releases[0]["series"])


# ---------- Transmission ----------

session = {"id": ""}


def rpc(method, arguments, timeout=30):
    body = json.dumps({"method": method, "arguments": arguments}).encode()
    for _ in range(2):
        req = urllib.request.Request(TRANSMISSION_URL, data=body, headers=transmission_headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                answer = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 409:
                raise
            session["id"] = e.headers.get("X-Transmission-Session-Id", "")
            continue
        if answer.get("result") != "success":
            raise RuntimeError(answer.get("result"))
        return answer.get("arguments", {})
    raise RuntimeError("Transmission refuses the session")


def transmission_headers():
    headers = {"X-Transmission-Session-Id": session["id"]}
    if TRANSMISSION_USER:
        pair = f"{TRANSMISSION_USER}:{TRANSMISSION_PASSWORD}".encode()
        headers["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    return headers


class KeepRedirect(urllib.request.HTTPRedirectHandler):
    """Follows redirects, but hands back a magnet link (urllib refuses to follow one)."""

    def http_error_302(self, req, fp, code, msg, headers):
        location = headers.get("Location") or headers.get("URI") or ""
        if location.startswith("magnet:"):
            raise MagnetFound(location)
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


class MagnetFound(Exception):
    pass


def torrent_source(url):
    """{"filename": magnet} or {"metainfo": base64 .torrent}: Transmission cannot always
    reach Prowlarr from inside the VPN, so Ohara fetches the file itself."""
    if url.startswith("magnet:"):
        return {"filename": url}
    try:
        with urllib.request.build_opener(KeepRedirect).open(url, timeout=60) as r:
            data = r.read()
    except MagnetFound as m:
        return {"filename": str(m)}
    return {"metainfo": base64.b64encode(data).decode()}


def grab(token, series, follow=False, query=""):
    r = found_releases.get(token)
    if not r:
        raise KeyError("search again: this result is no longer known")
    series = safe_name(series or r["series"])
    folder = hashlib.sha1(token.encode()).hexdigest()[:10]
    args = torrent_source(r["_url"])
    args["download-dir"] = f"{TRANSMISSION_INCOMING}/{folder}"
    added = rpc("torrent-add", args)
    t = added.get("torrent-added") or added.get("torrent-duplicate")
    meta = lookup(series)
    webtoon = webtoon_pack(r["title"]) or is_webtoon(series, load_state()["series"].get(series, {}))

    def note(state):
        state["downloads"][t["hashString"]] = {"series": series, "title": r["title"], "folder": folder, "range": r["range"], "at": time.time()}
        entry = series_entry(state, series)
        entry["anilist"] = meta.get("id") or entry.get("anilist")
        if webtoon:
            take_pack(entry, r)
        if follow:
            entry.update(follow=True, query=query or entry.get("query") or series)
    update_state(note)
    if follow:
        complete_later(series)
    return {"series": series, "hash": t["hashString"]}


def set_follow(series, on):
    def change(state):
        series_entry(state, series)["follow"] = bool(on)
    update_state(change)
    if on:
        complete_later(series)


def cancel(torrent_hash):
    rpc("torrent-remove", {"ids": [torrent_hash], "delete-local-data": True})
    update_state(lambda s: s["downloads"].pop(torrent_hash, None))


def torrents(hashes, timeout=30):
    if not hashes:
        return []
    fields = ["hashString", "percentDone", "status", "error", "errorString", "rateDownload", "eta", "totalSize"]
    return rpc("torrent-get", {"ids": hashes, "fields": fields}, timeout).get("torrents", [])


# ---------- import: files a finished download into its series folder ----------

def zip_folder(folder, target):
    """Turns a folder of images into one .cbz. It is written under a hidden name and
    only then given its own, so a volume cut short (Ohara stopped while it was being
    made) is never taken for a whole one."""
    images = sorted((p for p in folder.rglob("*") if IMAGE.search(p.name)), key=lambda p: natural(str(p)))
    part = target.with_name(f".{target.name}.part")
    with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as z:
        for p in images:
            z.write(p, p.relative_to(folder).as_posix())
    part.replace(target)


def extract(path, out):
    """Opens an archive into out with 7-Zip, or with bsdtar for the RARs 7-Zip cannot
    read (Alpine's 7-Zip is built without RAR)."""
    try:
        subprocess.run(["7z", "x", "-y", f"-o{out}", str(path)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        out.mkdir(parents=True, exist_ok=True)
        subprocess.run(["bsdtar", "-xf", str(path), "-C", str(out)], check=True, capture_output=True)


def unpack_archive(path, target):
    """A .cbr/.cb7 becomes a .cbz (7-Zip or bsdtar reads them); the original is left behind."""
    tmp = path.with_suffix(".unpacked")
    extract(path, tmp)
    zip_folder(tmp, target)
    shutil.rmtree(tmp, ignore_errors=True)


def free_name(folder, name):
    target = folder / name
    n = 2
    while target.exists():
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def owned_numbers(dest):
    """The numbers of the volumes a series has: its readable files, not what is left of
    one being made."""
    return {volume_number(p.name) for p in volumes(dest)} - {None} if dest.exists() else set()


def import_download(source, series):
    """Moves every volume found under source into MANGA/series, leaving out the tomes
    already there (a pack often repeats them). Returns how many came in."""
    dest = MANGA / series
    owned = owned_numbers(dest)
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    files = sorted((p for p in source.rglob("*") if p.is_file()), key=lambda p: natural(str(p)))
    for p in files:
        if p.suffix.lower() not in KEPT + ARCHIVES or volume_number(p.name) in owned:
            continue
        file_volume(p, dest)
        count += 1
    if not count and not any(p.suffix.lower() in KEPT + ARCHIVES for p in files):
        count = import_image_folders(source, dest)
    return count


def file_volume(p, dest):
    """Files one volume into dest under a name not taken: a .zip becomes a .cbz, a
    .cbr/.cb7 is converted. Returns where it went."""
    ext = p.suffix.lower()
    target = free_name(dest, p.name if ext in (".cbz", ".pdf", ".epub") else p.stem + ".cbz")
    if ext in ARCHIVES:
        unpack_archive(p, target)
    else:
        shutil.move(str(p), target)
    return target


# ---------- adding by hand: volumes sent from the computer or the phone ----------

def received(body, size, out):
    """Writes the size bytes of a request's body to out, a megabyte at a time."""
    with out.open("wb") as f:
        left = size
        while left > 0:
            chunk = body.read(min(1 << 20, left))
            if not chunk:
                raise ValueError("cut short")
            f.write(chunk)
            left -= len(chunk)


def add_volume(series, name, body, size):
    """A volume sent by hand, filed in its series' folder as a download is; a series
    not in the library yet is made, and AniList asked about it. It comes into a hidden
    folder of .incoming first, so a volume cut short never reaches the shelves."""
    name, series = Path(name).name, safe_name(series)
    if Path(name).suffix.lower() not in KEPT + ARCHIVES or name.startswith("."):
        raise ValueError("not a volume")
    new = series not in library_names()
    work = INCOMING / f".added-{secrets.token_hex(6)}"
    work.mkdir(parents=True)
    try:
        part = work / safe_name(name)
        received(body, size, part)
        dest = MANGA / series
        dest.mkdir(parents=True, exist_ok=True)
        target = file_volume(part, dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if new:
        threading.Thread(target=refresh_meta, daemon=True).start()
    return {"series": series, "id": volume_id(target)}


def shelf_for(name):
    """The series a file or a folder sent seems to be of, by its name: one of the
    library's when it says so ("known"), else the name of a new one."""
    stem = Path(name).stem if Path(name).suffix.lower() in KEPT + ARCHIVES else name
    guess = safe_name(guess_series(stem))
    known = {norm(n): n for n in library_names()}
    return {"name": known.get(norm(guess), guess), "known": norm(guess) in known}


def import_image_folders(source, dest):
    """A release of plain images: each folder holding images becomes one volume."""
    folders = sorted({p.parent for p in source.rglob("*") if IMAGE.search(p.name)}, key=lambda p: natural(str(p)))
    for f in folders:
        name = f.name if f != source else source.name
        zip_folder(f, free_name(dest, name + ".cbz"))
    return len(folders)


MUSIC_STALL = 6 * 3600  # a soundtrack still at nothing after this is given up


def stalled(d, t, now):
    """A soundtrack download that has not started at all after MUSIC_STALL."""
    return d.get("kind") == "ost" and t["percentDone"] == 0 and now - d.get("at", now) > MUSIC_STALL


def give_up_music(torrent_hash, d):
    """Drops a soundtrack that does not come, and remembers not to take it again:
    Brook picks the next best at his next pass."""
    rpc("torrent-remove", {"ids": [torrent_hash], "delete-local-data": True})
    shutil.rmtree(INCOMING / d["folder"], ignore_errors=True)

    def change(state):
        state["downloads"].pop(torrent_hash, None)
        skipped = state["music"].get(d["series"], {}).get("skipped", []) + [d["title"]]
        state["music"][d["series"]] = {"state": "none", "at": time.time(), "skipped": skipped}
    update_state(change)
    print(f"brook {d['series']}: gave up on {d['title']}", flush=True)


def check_downloads():
    """Files the finished downloads and forgets them, and gives up on the soundtracks
    that never start. Runs every 30 s."""
    downloads = load_state()["downloads"]
    # the small ones first, so that a big pack does not keep them waiting
    for t in sorted(torrents(list(downloads)), key=lambda t: t.get("totalSize", 0)):
        d = downloads.get(t["hashString"])
        if d and stalled(d, t, time.time()):
            give_up_music(t["hashString"], d)
        elif d and t["percentDone"] >= 1:
            try:
                file_download(t["hashString"], d)
            except Exception as e:  # one bad download must not hold the others back
                print("file:", d["title"], e, flush=True)


def file_download(torrent_hash, d):
    """Files one finished download, then drops its torrent and its folder; the tomes
    that came in are said on Discord."""
    source = INCOMING / d["folder"]
    if d.get("kind") == "ost":
        import_music(source, d["series"])
    else:
        before = owned_numbers(MANGA / d["series"])
        import_download(source, d["series"])
        came = sorted(owned_numbers(MANGA / d["series"]) - before)
        if came:
            tell(den_den.arrived, d["series"], came)
    rpc("torrent-remove", {"ids": [torrent_hash], "delete-local-data": True})
    shutil.rmtree(source, ignore_errors=True)
    update_state(lambda s: s["downloads"].pop(torrent_hash, None))


# ---------- following: new volumes of a series, fetched by themselves ----------

def tomes_of(r):
    lo, hi = r["range"] or (0, -1)
    return set(range(lo, hi + 1))


def coming_tomes(series, state):
    """The tomes of a series already on their way."""
    coming = set()
    for d in state["downloads"].values():
        if d["series"] == series and d.get("range"):
            coming |= set(range(d["range"][0], d["range"][1] + 1))
    return coming


def cost(r, need):
    """What one missing tome costs through release r: its share of the size, plus a
    fixed price per torrent (fewer, bigger packs) and more for slow ones."""
    per_tome = (r["size"] + 300e6) / len(tomes_of(r) & need)
    return per_tome * (1.5 if r["seeders"] < 3 else 1)


def plan(series, releases, state, total=None):
    """The releases to download so that the series has every tome from 1 to the last
    one out (the most AniList counts or a French release holds): each pick is the
    cheapest per missing tome (see cost), until nothing more helps; a release given
    up on before (see give_up) is not taken again.
    Returns (releases, tomes still nowhere to be found)."""
    french = [r for r in releases if r["lang"] == "FR" and r["range"]]
    skipped = set(state.get("series", {}).get(series, {}).get("skipped", []))
    usable = [r for r in french if r["seeders"] > 0 and r["title"] not in skipped]
    # a tome out with nobody sharing it yet still counts as out
    last = max([total or 0] + [r["range"][1] for r in french])
    have = {int(n) for n in owned_numbers(MANGA / series)} | coming_tomes(series, state)
    need = set(range(1, last + 1)) - have
    picks = []
    while need:
        helpful = [r for r in usable if tomes_of(r) & need]
        if not helpful:
            break
        best = min(helpful, key=lambda r: cost(r, need))
        picks.append(best)
        need -= tomes_of(best)
        usable.remove(best)
    return prune(picks, set(range(1, last + 1)) - have), sorted(need)


def prune(picks, wanted):
    """Drops the picks whose missing tomes the others bring anyway, the heaviest
    first: a cheap first pick can be made useless by a bigger later one."""
    kept = list(picks)
    for p in sorted(picks, key=lambda r: -r["size"]):
        others = set().union(*(tomes_of(r) for r in kept if r is not p))
        if tomes_of(p) & wanted <= others:
            kept.remove(p)
    return kept


# ---------- webtoons: followed by chapters, in English ----------

def is_webtoon(series, entry):
    """Whether a series is followed by chapters: as the switch on its sheet says, else
    when its files are chapters."""
    if "webtoon" in entry:
        return bool(entry["webtoon"])
    d = MANGA / series
    return d.is_dir() and any(is_chapter(p.name) for p in volumes(d))


def set_webtoon(series, on):
    def change(state):
        series_entry(state, series)["webtoon"] = bool(on)
    update_state(change)
    if on and load_state()["series"][series].get("follow"):
        complete_later(series)


def take_pack(entry, r):
    """Remembers a webtoon pack taken, not to take it again; and, for one that does not
    say its chapters, its size: only a bigger one (the pack uploaded again with more
    chapters) is worth taking after it. Turns the series to a webtoon, unless the switch
    said otherwise."""
    entry.setdefault("webtoon", True)
    entry["taken"] = (entry.get("taken", []) + [r["token"]])[-50:]
    if not r.get("chapters"):
        entry["taken_size"] = max(entry.get("taken_size", 0), r["size"])


def chapters_of(r):
    lo, hi = r.get("chapters") or (0, -1)
    return set(range(lo, hi + 1))


def webtoon_plan(series, releases, state, total=None):
    """The packs to download so that a webtoon has every chapter up to the last one out
    (AniList's count, or the most a pack says): those saying their chapters, the one
    bringing the most missing first, then the most seeders; else, when none says them,
    the biggest pack bigger than any taken before. Nothing while one is on its way: its
    chapters are not known before it comes. English packs count, not Japanese ones.
    Returns (releases, chapters still nowhere to be found)."""
    if any(d["series"] == series and d.get("kind", "volumes") == "volumes" for d in state["downloads"].values()):
        return [], []
    entry = state.get("series", {}).get(series, {})
    usable = usable_packs(releases, entry)
    last = max([total or 0] + [max(chapters_of(r), default=0) for r in usable])
    need = set(range(1, last + 1)) - {int(n) for n in owned_numbers(MANGA / series)}
    picks = chapter_picks(usable, need)
    if picks or (total and not need):
        return picks, sorted(need)
    blind = [r for r in usable if not r.get("chapters") and r["size"] > entry.get("taken_size", 0)]
    return sorted(blind, key=lambda r: (-r["size"], -r["seeders"]))[:1], []


def usable_packs(releases, entry):
    """The packs that can come (shared by someone, not in Japanese) and were neither
    taken nor given up on before."""
    passed = set(entry.get("taken", [])) | set(entry.get("skipped", []))
    return [r for r in releases if r["lang"] != "JP" and r["seeders"] > 0 and not {r["token"], r["title"]} & passed]


def chapter_picks(usable, need):
    """The packs saying their chapters that bring the missing ones, the one bringing
    the most first, then the most seeders; need is left with what none brings."""
    picks = []
    while True:
        helpful = [r for r in usable if chapters_of(r) & need and r not in picks]
        if not helpful:
            return picks
        best = max(helpful, key=lambda r: (len(chapters_of(r) & need), r["seeders"]))
        picks.append(best)
        need -= chapters_of(best)


COLOUR = re.compile(r"(?i)\b(en )?couleurs?\b|\bcolou?r(ed)?\b|カラー")


def same_series(r, series, entry, facts):
    """Whether a release belongs to a series: same name, or same AniList entry and the
    same colours (a colour edition and the original share their AniList entry)."""
    if norm(r["series"]) == norm(series):
        return True
    meta = facts.get(r["series"]) or {}
    if not entry.get("anilist") or meta.get("id") != entry.get("anilist"):
        return False
    return bool(COLOUR.search(series)) == bool(COLOUR.search(r["title"]))


def complete(series):
    """Downloads every missing tome of a series that can be found. Returns the
    releases sent and the tomes nobody has."""
    state = load_state()
    entry = state["series"].get(series, {})
    releases = find_releases(entry.get("query") or series)
    facts = lookups(sorted({r["series"] for r in releases}))
    mine = [r for r in releases if same_series(r, series, entry, facts)]
    facts_of = state["lookups"].get(norm(series)) or {}
    if is_webtoon(series, entry):
        picks, nowhere = webtoon_plan(series, mine, state, facts_of.get("chapters"))
    else:
        picks, nowhere = plan(series, mine, state, facts_of.get("volumes"))
    for r in picks:
        print(f"complete: {series} ← {r['title']}", flush=True)
        grab(r["token"], series)
    return {"sent": [{"title": r["title"], "range": r["range"]} for r in picks], "nowhere": nowhere}


def give_up(torrent_hash):
    """Drops a download that does not come, and remembers its release not to take it
    again for its series. Returns the series."""
    d = load_state()["downloads"].get(torrent_hash)
    if not d:
        raise KeyError(torrent_hash)
    cancel(torrent_hash)
    if d.get("folder"):
        shutil.rmtree(INCOMING / d["folder"], ignore_errors=True)

    def change(state):
        entry = series_entry(state, d["series"])
        entry["skipped"] = sorted(set(entry.get("skipped", [])) | {d["title"]})
    update_state(change)
    return d["series"]


def complete_later(series):
    threading.Thread(target=safe_complete, args=(series,), daemon=True).start()


def safe_complete(series):
    try:
        return complete(series)
    except Exception as e:
        print(f"complete {series}:", e, flush=True)
        return None


WEBHOOK = re.compile(r"https://(?:discord|discordapp)\.com/api/webhooks/\d+/[\w-]+$")


def discord():
    """The Discord channel Ohara speaks to and its own address (for the links): those
    set in the settings, else OHARA_DISCORD_WEBHOOK and OHARA_URL."""
    st = load_state()["settings"]
    return st.get("discord") or DISCORD_WEBHOOK, st.get("address") or OHARA_URL


def link_discord(url, address=""):
    """Links a Discord channel from the settings, pasted from a phone as well: the
    webhook is tried at once with a message, and kept only if Discord takes it. An
    empty url unlinks."""
    url = url.strip()
    if url and not WEBHOOK.match(url):
        raise ValueError("not a webhook")
    if url:
        den_den.send(url, den_den.sign(den_den.linked(DISCORD_LANG), DISCORD_NAME))

    def change(state):
        state["settings"]["discord"] = url
        if address:
            state["settings"]["address"] = address.rstrip("/")
    update_state(change)
    return settings_page()


def tell(message, series, what):
    """Says something of a series on Discord (see den_den.py), with its cover and a
    link to it, when a channel is linked."""
    webhook, address = discord()
    if not webhook:
        return None
    cover = (load_state()["lookups"].get(norm(series)) or {}).get("cover")
    link = f"{address}/#{urllib.parse.quote(series)}" if address else None
    return den_den.post(webhook, den_den.sign(message(series, what, cover, link, DISCORD_LANG), DISCORD_NAME))


def check_follows():
    """Keeps every followed series complete: missing tomes and new ones, said on
    Discord when some are sent for."""
    for series, entry in load_state()["series"].items():
        if entry.get("follow"):
            sent = (safe_complete(series) or {}).get("sent")
            if sent:
                tell(den_den.found, series, sent)

    def stamp(s):
        s["followed_at"] = time.time()
    update_state(stamp)


def follows_due():
    return time.time() - load_state().get("followed_at", 0) >= FOLLOW_EVERY


def tick():
    backup_state()
    check_downloads()
    read_spines()
    brook_pass()
    chapters_pass()
    if follows_due():
        check_follows()


def watch():
    while True:
        try:
            tick()
        except Exception as e:  # Transmission restarting, a disk hiccup: try again later
            print("watch:", e, flush=True)
        time.sleep(30)


# ---------- the chapters of each volume, from Wikipedia (see chapters.py) ----------

CHAPTERS_AGAIN = 30 * 86400  # a series' chapters are read again a month later


def chapters_pass():
    """Reads the chapters of one series whose are missing or a month old: one series a
    pass, not to weigh on Wikipedia."""
    state = load_state()
    now = time.time()
    for name in sorted(library_names(), key=natural):
        if now - state["chapters"].get(name, {}).get("at", 0) > CHAPTERS_AGAIN:
            meta = state["lookups"].get(norm(name)) or {}
            try:
                names = dict.fromkeys(n for n in [name, meta.get("title"), *meta.get("names", [])] if n)
                found = chapters.chapters(list(names))
            except Exception as e:  # Wikipedia away: next pass
                print(f"chapters {name}:", e, flush=True)
                return

            def change(state):
                state["chapters"][name] = {"at": now, "volumes": {str(k): v for k, v in found.items()}}
            update_state(change)
            return


# ---------- Robin: what each volume's spine needs, read from its cover ----------

SPINE_STYLES = ("tome", "reliure", "sobre")


def crop_path(vid):
    return STATE_DIR / "crops" / (hashlib.sha1(vid.encode()).hexdigest() + ".jpg")


def spine_of(vid, spines):
    """A volume's spine colours, when Robin has read its cover."""
    info = (spines or {}).get(vid)
    return {k: v for k, v in info.items() if k != "at"} if info else None


def read_spine(path):
    """Robin reads one volume's cover: colours kept in the state, the illustration's
    square in .ohara/crops."""
    vid = volume_id(path)
    data, _ = page_bytes(path, 0)
    info, crop = robin.read_cover(data)
    out = crop_path(vid)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(crop)
    info["at"] = path.stat().st_mtime

    def keep(state):
        state["spines"][vid] = info
    update_state(keep)


def read_spines(limit=10):
    """Reads the covers Robin has not read yet (or that changed), a few at a time
    so the Pi stays free. Returns how many were read."""
    spines = load_state()["spines"]
    todo = [p for n in library_names() for p in volumes(MANGA / n)
            if p.suffix.lower() in READABLE and (spines.get(volume_id(p)) or {}).get("at") != p.stat().st_mtime]
    for p in todo[:limit]:
        try:
            read_spine(p)
        except Exception as e:  # a broken archive: try the others
            print(f"robin {p.name}:", e, flush=True)
    return min(len(todo), limit)


def settings():
    st = load_state()["settings"]
    return {"spines": st.get("spines", "tome"), "brook": st.get("brook", True), "franky": st.get("franky", False),
            "ribbon": st.get("ribbon", True), "discord": bool(st.get("discord") or DISCORD_WEBHOOK)}


def settings_page():
    """The settings, and how far Franky has gone through the library."""
    return {**settings(), "lighter": franky_progress()}


def set_settings(changes):
    def change(state):
        if changes.get("spines") in SPINE_STYLES:
            state["settings"]["spines"] = changes["spines"]
        for key in ("brook", "franky", "ribbon"):
            if isinstance(changes.get(key), bool):
                state["settings"][key] = changes[key]
    update_state(change)
    return settings_page()


# ---------- Franky: every volume rebuilt lighter, one after the other ----------

FRANKY_REST = 300  # seconds before looking again, once every volume is done
FRANKY_BUSY = 3600  # a volume opened within this is left for later


def library_volumes():
    """Every .cbz of the library, series after series."""
    for name in sorted(library_names(), key=natural):
        yield from (p for p in volumes(MANGA / name) if p.suffix.lower() in READABLE)


def franky_next(state):
    """The next volume Franky has not seen, leaving those being read, by anyone."""
    now = time.time()
    for path in library_volumes():
        vid = volume_id(path)
        if vid not in state["franky"] and now - last_opened(state, vid) > FRANKY_BUSY:
            return path
    return None


def franky_one():
    """Rebuilds the next volume lighter (see franky.py) and notes its sizes before and
    after; a volume he fails on is noted too, not to be tried again. False when there
    is none left."""
    path = franky_next(load_state())
    if not path:
        return False
    vid = volume_id(path)
    try:
        size = path.stat().st_size
        sizes = [size, size] if franky.done(path) else list(franky.rebuild(path).values())
        print(f"franky {vid}: {sizes[0] // 2**20} → {sizes[1] // 2**20} MB", flush=True)
    except Exception as e:  # a broken archive: left as it is
        sizes = [0, 0]
        print(f"franky {vid}: {e}", flush=True)
    for key in [k for k in pages_cache if k[0] == str(path)]:
        pages_cache.pop(key, None)  # its pages have new names, at the same date

    def change(state):
        state["franky"][vid] = sizes
    update_state(change)
    return True


def franky_progress():
    seen = load_state()["franky"]
    vids = [volume_id(p) for p in library_volumes()]
    done = [seen[v] for v in vids if v in seen]
    return {"done": len(done), "total": len(vids), "saved": sum(a - b for a, b in done)}


def franky_loop():
    """Franky works in the background, at a low priority, a volume after the other, once
    switched on in the settings: he replaces the originals, so he is off at first."""
    os.nice(10)  # only this thread, on Linux
    for left in MANGA.glob("*/.*.franky"):  # a volume he was writing when Ohara stopped
        left.unlink(missing_ok=True)
    while True:
        try:
            busy = settings()["franky"] and franky_one()
        except Exception as e:
            print("franky:", e, flush=True)
            busy = False
        time.sleep(1 if busy else FRANKY_REST)


# ---------- Brook: the music of each series ----------

MUSIC_RETRY = 7 * 86400  # a series without a soundtrack is looked for again a week later
MUSIC_ERROR_RETRY = 3600  # after a failure (Prowlarr or Transmission away), an hour later


def tune(series):
    """The series whose music a series plays: a colour edition plays the original's,
    looked for, downloaded and filed once, its ambiences shared."""
    return uncoloured(series) or series


def music_due(status, now):
    """Whether Brook should look for a series' music now."""
    if not status:
        return True
    wait = {"none": 0, "notfound": MUSIC_RETRY, "error": MUSIC_ERROR_RETRY}.get(status.get("state"))
    return wait is not None and now - status.get("at", 0) > wait


def audio_indexer_ids(key):
    """Every indexer Prowlarr has on that files music (an Audio category): Brook
    searches them all, not only those chosen for the manga."""
    found = http_json(f"{PROWLARR_URL}/api/v1/indexer", headers={"X-Api-Key": key})
    cats = lambda i: [c.get("id", 0) for c in (i.get("capabilities") or {}).get("categories", [])]
    return [i["id"] for i in found if i.get("enable") and any(3000 <= c < 4000 for c in cats(i))]


def find_soundtracks(series):
    """The soundtrack releases of a series (a colour edition's are the original's), the
    best first (see brook.best_first), each title once, without those Brook already
    gave up on."""
    series = tune(series)
    meta = lookup(series)
    names = brook.names_of(series, meta)
    skipped = set(load_state()["music"].get(series, {}).get("skipped", []))
    keep = lambda r: brook.is_soundtrack(r, names) and r["title"] not in skipped
    found = {}
    for query in (f"{series} OST", f"{series} soundtrack"):
        for r in find_releases(query, category=3000, keep=keep, which=audio_indexer_ids):
            found[r["token"]] = r
    # the same release from several indexers is shown once, the best seeded
    best = {}
    for r in sorted(found.values(), key=brook.best_first):
        best.setdefault(r["title"], r)
    return list(best.values())


def set_music(series, **status):
    """Brook's status for a series; the releases he gave up on are kept across."""
    def change(state):
        skipped = state["music"].get(series, {}).get("skipped", [])
        state["music"][series] = dict(status, at=time.time(), **({"skipped": skipped} if skipped else {}))
    update_state(change)


def grab_music(series, token=None):
    """Downloads a soundtrack for a series: the release given, or the best Brook finds."""
    series = tune(series)
    if token:
        r = found_releases.get(token)
        if not r:
            raise KeyError("search again: this result is no longer known")
    else:
        found = [r for r in find_soundtracks(series) if r["seeders"] > 0]
        if not found:
            set_music(series, state="notfound")
            return music_status(series)
        r = found[0]
    folder = "ost-" + hashlib.sha1(r["token"].encode()).hexdigest()[:10]
    args = torrent_source(r["_url"])
    args["download-dir"] = f"{TRANSMISSION_INCOMING}/{folder}"
    added = rpc("torrent-add", args)
    t = added.get("torrent-added") or added.get("torrent-duplicate")

    def note(state):
        state["downloads"][t["hashString"]] = {"series": series, "title": r["title"], "folder": folder, "range": None, "kind": "ost", "at": time.time()}
        skipped = state["music"].get(series, {}).get("skipped", [])
        state["music"][series] = {"state": "downloading", "title": r["title"], "at": time.time(), **({"skipped": skipped} if skipped else {})}
    update_state(note)
    return music_status(series)


def unpack_audio(source):
    """Opens the archives (.zip, .rar, .7z) of a soundtrack where they are."""
    for p in list(source.rglob("*")):
        if p.suffix.lower() in (".zip", ".rar", ".7z"):
            extract(p, p.with_suffix(""))


def import_music(source, series):
    """Files a soundtrack's tracks in MUSIC/series/<album>/, each album with its cover
    when the release has one. Returns how many tracks came in."""
    unpack_audio(source)
    dest = MUSIC / safe_name(series)
    tracks = [p for p in source.rglob("*") if p.suffix.lower() in brook.AUDIO]
    for p in tracks:
        album = safe_name(p.parent.name if p.parent != source else series)
        folder = dest / album
        folder.mkdir(parents=True, exist_ok=True)
        art = next((a for a in sorted(p.parent.iterdir()) if a.suffix.lower() in brook.ART), None)
        if art and not any((folder / f"cover{x}").exists() for x in brook.ART):
            shutil.copy(art, folder / ("cover" + art.suffix.lower()))
        shutil.move(str(p), free_name(folder, p.name))
    set_music(series, state="ready" if tracks else "notfound")
    return len(tracks)


titles_cache = {}


def title_of(path):
    key = (str(path), path.stat().st_mtime)
    if key not in titles_cache:
        with path.open("rb") as f:
            titles_cache[key] = brook.track_title(path, f.read(65536))
    return titles_cache[key]


def music_path(tid):
    """The file of a track id, refusing anything outside the music folder."""
    p = (MUSIC / tid).resolve()
    if MUSIC.resolve() not in p.parents or not p.is_file():
        raise KeyError(tid)
    return p


def albums(series):
    """The albums of a series' music: [{id, name, art, tracks: [{id, title}]}], the id
    the name before any translation."""
    root = MUSIC / safe_name(series)
    if not root.exists():
        return []
    found = {}
    for p in sorted(root.rglob("*"), key=lambda p: natural(str(p))):
        if p.suffix.lower() in brook.AUDIO:
            rel = p.relative_to(root).as_posix()
            found.setdefault(brook.album_of(rel), []).append({"id": p.relative_to(MUSIC).as_posix(), "title": title_of(p)})
    out = []
    for name, tracks in found.items():
        folder = root / name if name else root
        art = next((a for a in folder.glob("cover.*") if a.suffix.lower() in brook.ART), None)
        shown = brook.album_name(name) if name else series
        out.append({"id": shown, "name": shown, "art": art.relative_to(MUSIC).as_posix() if art else None, "tracks": tracks})
    return out


def music_status(series):
    status = dict(load_state()["music"].get(series, {"state": "none"}))
    status.pop("at", None)
    status.pop("skipped", None)
    return status


def music(series, lang=None):
    """A series' music; titles in Japanese, Chinese or Korean said in the interface's
    language, the original after them in brackets, once translated."""
    series = tune(series)
    state = load_state()
    found = albums(series)
    status = music_status(series)
    if found and status.get("state") in ("none", "notfound"):
        status = {"state": "ready"}
    moods = [{"name": k, "tracks": v} for k, v in sorted(state["moods"].get(series, {}).items())]
    out = {"status": status, "albums": found, "moods": moods}
    if lang:
        out["translating"] = say_titles(found, lang)
    return out


# ---------- titles translated ----------
# A soundtrack's titles are often in Japanese. They are translated once into the
# interface's language by Google Translate (its free endpoint, without a key: only the
# titles are sent), in the background, and kept in .ohara/translations.json.
FOREIGN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff66-\uff9f]")  # kana, kanji, hangul
LANGS = ("fr", "en")
TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_RETRY = 3600  # after Google failed, an hour before asking again
translations = {"kept": None, "failed": 0}
translations_lock = threading.Lock()
translating = threading.Lock()


def translations_file():
    return STATE_DIR / "translations.json"


def kept_translations():
    """{lang: {original: translation}}, read from the disk once."""
    with translations_lock:
        if translations["kept"] is None:
            try:
                translations["kept"] = json.loads(translations_file().read_text())
            except (OSError, ValueError):
                translations["kept"] = {}
        return translations["kept"]


def keep_translations(lang, found):
    with translations_lock:
        translations["kept"].setdefault(lang, {}).update(found)
        out = translations_file()
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(translations["kept"], ensure_ascii=False))
        tmp.replace(out)


def said_title(title, said):
    """"Le banquet d'Elbaph (エルバフの宴)", a capital first; the title alone when not
    translated."""
    return f"{said[:1].upper()}{said[1:]} ({title})" if said and said != title else title


def say_titles(found, lang):
    """Gives the albums and tracks of found their translated titles; True while some
    are still being translated."""
    lang = lang if lang in LANGS else LANGS[0]
    known = kept_translations().get(lang, {})
    titles = [a["name"] for a in found] + [t["title"] for a in found for t in a["tracks"]]
    missing = sorted({t for t in titles if FOREIGN.search(t) and t not in known})
    for a in found:
        a["name"] = said_title(a["name"], known.get(a["name"]))
        for t in a["tracks"]:
            t["title"] = said_title(t["title"], known.get(t["title"]))
    if not missing or time.time() - translations["failed"] < TRANSLATE_RETRY:
        return False
    threading.Thread(target=translate_missing, args=(missing, lang), daemon=True).start()
    return True


def translate_missing(texts, lang):
    """Translates texts and keeps them, one series at a time; a failure waits an hour."""
    if not translating.acquire(blocking=False):
        return
    try:
        keep_translations(lang, translate(texts, lang))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        translations["failed"] = time.time()
        print(f"translate: {e}", flush=True)
    finally:
        translating.release()


def translate(texts, lang):
    """{text: translation}, asked of Google 40 lines at a time; a batch that comes
    back with another number of lines is asked again one line at a time."""
    found = {}
    for i in range(0, len(texts), 40):
        batch = texts[i:i + 40]
        lines = google_translate("\n".join(batch), lang).split("\n")
        if len(lines) != len(batch):
            lines = [google_translate(t, lang) for t in batch]
        found.update({t: said.strip() for t, said in zip(batch, lines) if said.strip()})
    return found


def google_translate(text, lang):
    query = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": lang, "dt": "t", "q": text})
    answer = http_json(f"{TRANSLATE_URL}?{query}", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    return "".join(part[0] for part in answer[0] if part and part[0])


def set_mood(series, name, tracks, lang=None):
    """Creates, changes or (with no tracks) removes one of a series' own ambiences."""
    series, name = tune(series), (name or "").strip()[:60]
    if not name:
        raise KeyError("an ambience needs a name")

    def change(state):
        moods = state["moods"].setdefault(series, {})
        if tracks:
            moods[name] = [t for t in tracks if isinstance(t, str)]
        else:
            moods.pop(name, None)
    update_state(change)
    return music(series, lang)


def brook_pass():
    """Brook looks for the music of one series that has none yet (or that he did not
    find a week ago), if he is allowed to."""
    if not settings()["brook"]:
        return None
    state = load_state()
    for series in sorted({tune(s) for s in library_names()}, key=natural):
        if music_due(state["music"].get(series), time.time()) and not albums(series):
            set_music(series, state="searching")
            try:
                return grab_music(series)
            except Exception as e:  # Prowlarr or Transmission away: try again in an hour
                set_music(series, state="error")
                print(f"brook {series}:", e, flush=True)
                return None
    return None


# ---------- library ----------

def volume_id(path):
    return path.resolve().relative_to(MANGA.resolve()).as_posix()


def volume_path(vid):
    """The file of a volume id, refusing anything outside the library."""
    p = (MANGA / vid).resolve()
    if MANGA.resolve() not in p.parents or not p.is_file() or p.name.startswith("."):
        raise KeyError(vid)
    return p


def volumes(series_dir):
    files = [p for p in series_dir.iterdir() if p.is_file() and p.suffix.lower() in KEPT and not p.name.startswith(".")]
    return sorted(files, key=lambda p: natural(p.name))


DECORS = ("banner", "cover", "none")
DECOR_MAX = 25 * 1024 * 1024  # bytes of an image sent or fetched for a decor


def decor_file(series):
    return STATE_DIR / "decors" / (hashlib.sha1(series.encode()).hexdigest() + ".jpg")


def decor_kept(series):
    """When the series' own image was kept (to tell its versions apart), or None."""
    f = decor_file(series)
    return int(f.stat().st_mtime) if f.exists() else None


def decor_ok(series, decor):
    if decor.startswith("vol:"):
        return decor[4:].startswith(series + "/") and volume_path(decor[4:]).is_file()
    if decor.startswith("own:"):
        return decor_kept(series) is not None
    return decor in DECORS


def choose_decor(series, decor):
    def change(state):
        series_entry(state, series)["decor"] = decor
    update_state(change)
    return {"ok": True, "decor": decor}


def set_decor(series, decor):
    """The back of a series' bays: its AniList banner (the default), its AniList cover,
    a volume's cover ("vol:<id>"), its own image ("own:<when>") or bare wood. An image
    from the web ("url:<address>") is fetched and kept as its own image."""
    if decor.startswith("url:"):
        return fetch_decor(series, decor[4:])
    if not decor_ok(series, decor):
        raise KeyError(decor)
    return choose_decor(series, decor)


def keep_decor(series, data):
    """An image of a series' own for the back of its bays, sent or fetched from the web:
    kept in .ohara/decors as a JPEG of at most 1600 px, and chosen."""
    from PIL import Image, ImageOps
    if series not in library_names():
        raise KeyError(series)
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        raise ValueError("not an image") from None
    img.thumbnail((1600, 1600))
    out = decor_file(series)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=85)
    return choose_decor(series, f"own:{decor_kept(series)}")


def fetch_decor(series, url):
    if not re.match(r"https?://\S+$", url):
        raise KeyError(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Ohara)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(DECOR_MAX + 1)
    if len(data) > DECOR_MAX:
        raise ValueError("image too big")
    return keep_decor(series, data)


def library_names():
    if not MANGA.exists():
        return []
    return [d.name for d in MANGA.iterdir() if d.is_dir() and not d.name.startswith(".") and volumes(d)]


def wiki_chapters(vols, known):
    """Gives each tome the chapters Wikipedia lists for it; a webtoon's chapter is not
    the tome of its number."""
    for v in vols:
        whole = v["number"] and v["number"] == int(v["number"]) and not v["chapter"]
        v["chapters"] = known.get(str(int(v["number"]))) if whole else None


def series_info(d, state, rid=None):
    vols = [volume_info(v, progress_of(state, rid), state["spines"]) for v in volumes(d)]
    wiki_chapters(vols, state["chapters"].get(d.name, {}).get("volumes", {}))
    entry = state["series"].get(d.name, {})
    meta = state["lookups"].get(norm(d.name)) or {}
    numbers = {int(v["number"]) for v in vols if v["number"]}
    webtoon = entry.get("webtoon", any(v["chapter"] for v in vols))
    last = max([meta.get("chapters" if webtoon else "volumes") or 0] + list(numbers))
    coming = coming_tomes(d.name, state)
    return {
        "name": d.name,
        "volumes": vols,
        "read": sum(v["done"] for v in vols),
        "new": sum(v["new"] for v in vols),
        "follow": entry.get("follow", False),
        "webtoon": bool(webtoon),
        "decor": entry.get("decor", "banner"),
        "kept": decor_kept(d.name),
        "meta": meta,
        "missing": [n for n in range(1, last + 1) if n not in numbers and n not in coming],
        "coming": sorted(coming),
    }


def series_list(state, rid=None):
    dirs = sorted((MANGA / n for n in library_names()), key=lambda d: natural(d.name))
    return [series_info(d, state, rid) for d in dirs]


def volume_info(path, progress, spines=None):
    vid = volume_id(path)
    p = progress.get(vid, {})
    readable = path.suffix.lower() in READABLE
    return {
        "id": vid,
        "label": volume_label(path.name),
        "number": volume_number(path.name),
        "chapter": is_chapter(path.name),  # a webtoon's chapter, not a tome
        "file": path.name,
        "readable": readable,
        "page": p.get("page", 0),
        "pages": p.get("pages", 0),
        "done": bool(p.get("pages")) and p.get("page", 0) >= p["pages"] - 1,
        "new": not p and time.time() - path.stat().st_mtime < NEW_FOR,
        "at": p.get("at", 0),
        "spine": spine_of(vid, spines),
    }


def library(rid=None):
    """The library as a reader sees it: the series, where they are in them, the downloads."""
    state = load_state()
    series = series_list(state, rid)
    live = {t["hashString"]: t for t in safe_torrents(list(state["downloads"]))}
    downloads = [download_info(h, d, live.get(h)) for h, d in state["downloads"].items()]
    for d in downloads:
        d["cover"] = (state["lookups"].get(norm(d["series"])) or {}).get("cover")
    return {"series": series, "downloads": downloads, "last": last_read(series), **readers(state, rid)}


TORRENTS_WAIT = 4  # seconds the library waits for Transmission before saying what it knew
torrents_seen = {}


def safe_torrents(hashes):
    """How the downloads are going, for the page: Transmission's answer, or when it does
    not answer in TORRENTS_WAIT (stuck, restarting), what it said last, so that the
    library never waits on it."""
    try:
        found = torrents(hashes, TORRENTS_WAIT)
    except Exception:
        return [torrents_seen[h] for h in hashes if h in torrents_seen]
    torrents_seen.update((t["hashString"], t) for t in found)
    return found


def download_info(torrent_hash, d, t):
    info = {"hash": torrent_hash, "series": d["series"], "title": d["title"], "range": d.get("range"), "kind": d.get("kind", "volumes"), "pct": 0, "state": "unknown"}
    if t:
        info["pct"] = round(t["percentDone"] * 100)
        info["eta"] = t.get("eta", -1)
        info["state"] = "error" if t.get("error") else "done" if t["percentDone"] >= 1 else "downloading"
        info["error"] = t.get("errorString", "")
    return info


def last_read(series):
    vols = [dict(v, series=s["name"], meta=s["meta"]) for s in series for v in s["volumes"] if v["at"]]
    return max(vols, key=lambda v: v["at"]) if vols else None


# ---------- Chopper: what ails the library, and the remedies (see chopper.py) ----------

def snapshot():
    """What Chopper's examinations look at: the library as the page sees it, the state,
    every file of each series' folder ({name, size, mtime}, those Ohara does not read
    too), and what is left in .incoming."""
    state = load_state()
    lib = library()
    files = {}
    for name in library_names():
        found = sorted((p for p in (MANGA / name).iterdir() if p.is_file()), key=lambda p: natural(p.name))
        files[name] = [{"name": p.name, "size": p.stat().st_size, "mtime": p.stat().st_mtime} for p in found]
    incoming = sorted(p.name for p in INCOMING.iterdir()) if INCOMING.exists() else []
    return {"series": lib["series"], "downloads": lib["downloads"], "state": state, "files": files, "incoming": incoming, "now": time.time()}


ailments_seen = {"at": 0, "list": []}
AILMENTS_EVERY = 300  # seconds between two examinations in the background


def ailments(fresh=False):
    """The ailments found last; examined now only when asked (the 🩺 opened, a remedy
    chosen): an examination reads every folder of the library, slow on a busy disk, so
    the page's own loading never waits for one."""
    if fresh:
        ailments_seen["list"] = chopper.examine(snapshot(), set(load_state()["dismissed"]))
        ailments_seen["at"] = time.time()
    return ailments_seen["list"]


def examine_due():
    """Examines the library in the background, every AILMENTS_EVERY."""
    if time.time() - ailments_seen["at"] > AILMENTS_EVERY:
        ailments(fresh=True)


def doctor_loop():
    """Chopper on his own round, not waiting behind the downloads and Brook's searches."""
    while True:
        try:
            examine_due()
        except Exception as e:
            print("chopper:", e, flush=True)
        time.sleep(30)


def treat(aid, index):
    """Runs a remedy chosen, then examines the library again."""
    done = chopper.apply(ailments(fresh=True), aid, index, sys.modules[__name__])
    return {"done": done, "ailments": ailments(fresh=True)}


def dismiss(aid, on=True):
    """Sets an ailment aside (it is not said again), or takes it back."""
    def change(state):
        state["dismissed"] = {**state["dismissed"], aid: time.time()} if on else {k: v for k, v in state["dismissed"].items() if k != aid}
    update_state(change)
    return ailments(fresh=True)


def move_keys(table, rename):
    """A state table (a dict) with its keys renamed by rename(key) -> new key or None."""
    return {rename(k) or k: v for k, v in table.items()}


def rename_volume(vid, name):
    """Renames a volume's file in its folder, keeping where you are in it, its spine,
    what Franky noted and a decor made of its cover. Returns the new id."""
    path = volume_path(vid)
    target = free_name(path.parent, safe_name(name))
    path.rename(target)
    new = volume_id(target)
    moved = lambda k: new if k == vid else None

    def change(state):
        move_reading(state, moved)
        for key in ("spines", "franky"):
            state[key] = move_keys(state[key], moved)
        for entry in state["series"].values():
            if entry.get("decor") == "vol:" + vid:
                entry["decor"] = "vol:" + new
    update_state(change)
    return new


def rename_series(old, new):
    """Renames a series: its folder, its music, its own decor image, and everything the
    state keeps of it and of its volumes. KeyError when the name is taken."""
    if not new.strip():
        raise KeyError(new)
    new = safe_name(new)
    src, dst = MANGA / old, MANGA / new
    if not src.is_dir() or dst.exists():
        raise KeyError(new)
    src.rename(dst)
    if (MUSIC / safe_name(old)).exists() and not (MUSIC / new).exists():
        (MUSIC / safe_name(old)).rename(MUSIC / new)
    if decor_file(old).exists():
        decor_file(old).replace(decor_file(new))
    prefix = old + "/"
    moved_vol = lambda k: new + "/" + k[len(prefix):] if k.startswith(prefix) else None
    moved_name = lambda k: new if k == old else None

    def change(state):
        move_reading(state, moved_vol)
        for key in ("spines", "franky"):
            state[key] = move_keys(state[key], moved_vol)
        for key in ("series", "music", "moods", "chapters"):
            state[key] = move_keys(state[key], moved_name)
        if norm(old) in state["lookups"] and norm(new) not in state["lookups"]:
            state["lookups"][norm(new)] = state["lookups"][norm(old)]
        entry = state["series"].get(new, {})
        if entry.get("decor", "").startswith("vol:" + prefix):
            entry["decor"] = "vol:" + new + "/" + entry["decor"][len("vol:" + prefix):]
        for d in state["downloads"].values():
            if d.get("series") == old:
                d["series"] = new
    update_state(change)
    return new


def delete_volume(vid):
    """Deletes a volume's file, and what the state kept of it."""
    volume_path(vid).unlink()

    def change(state):
        for r in state["readers"].values():
            r.get("progress", {}).pop(vid, None)
        for key in ("spines", "franky"):
            state[key].pop(vid, None)
    update_state(change)


def refresh_meta():
    """Asks AniList about the series of the library it has not been asked about yet, and
    notes on each series the AniList entry it is (an empty one filled, one set kept)."""
    state = load_state()
    names = set(library_names()) | {d["series"] for d in state["downloads"].values()}
    stale = lambda n: norm(n) not in state["lookups"] or not fresh(state["lookups"][norm(n)], n)
    missing = sorted(n for n in names if stale(n))
    found = lookups(missing)

    def keep(state):
        for name in sorted(names):
            meta = found.get(name) or state["lookups"].get(norm(name)) or {}
            if meta.get("id") and not state["series"].get(name, {}).get("anilist"):
                series_entry(state, name)["anilist"] = meta["id"]
    update_state(keep)


# ---------- pages ----------

pages_cache = {}


def pages(path):
    """The image names of a .cbz, in reading order (cached per file and date)."""
    key = (str(path), path.stat().st_mtime)
    if key not in pages_cache:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if IMAGE.search(n) and "__MACOSX" not in n and not Path(n).name.startswith(".")]
        pages_cache[key] = sorted(names, key=natural)
    return pages_cache[key]


def page_bytes(path, n):
    names = pages(path)
    with zipfile.ZipFile(path) as z:
        return z.read(names[n]), names[n]


# ---------- double pages ----------
# Some volumes keep a double page as one wide image (One Piece en couleurs) where others
# cut it in two; the reader shows a wide one alone and pairs the pages around it as the
# book does. Reading a page's size costs the library's disk about 10 ms whatever is
# read, two seconds a volume: it is done once, in the background, and kept in
# .ohara/shapes.
HEAD = 32768  # bytes read from a page to find its size; a JPEG's may come late
shapes_memory = {}


def image_size(head):
    """(width, height) from the first bytes of a WebP, PNG or JPEG; None when they do
    not tell."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return webp_size(head[12:16], head[20:30])
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    if head[:2] == b"\xff\xd8":
        return jpeg_size(head)
    return None


def webp_size(kind, body):
    """A WebP's size from its first chunk: extended, lossless or lossy."""
    if len(body) < 10:
        return None
    if kind == b"VP8X":
        return 1 + int.from_bytes(body[4:7], "little"), 1 + int.from_bytes(body[7:10], "little")
    if kind == b"VP8L":
        bits = int.from_bytes(body[1:5], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    if kind == b"VP8 ":
        return int.from_bytes(body[6:8], "little") & 0x3FFF, int.from_bytes(body[8:10], "little") & 0x3FFF
    return None


def jpeg_size(head):
    """A JPEG's size, from its first frame header past the markers before it."""
    i = 2
    while i + 9 <= len(head) and head[i] == 0xFF:
        marker = head[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(head[i + 7:i + 9], "big"), int.from_bytes(head[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(head[i + 2:i + 4], "big")
    return None


def shapes_file(path):
    return STATE_DIR / "shapes" / (hashlib.sha1(volume_id(path).encode()).hexdigest() + ".json")


def known_wide(path):
    """The wide pages of a volume, if already found; None otherwise."""
    key = (str(path), path.stat().st_mtime)
    if key not in shapes_memory:
        try:
            kept = json.loads(shapes_file(path).read_text())
        except (OSError, ValueError):
            return None
        if kept.get("mtime") != key[1]:
            return None
        shapes_memory[key] = kept["wide"]
    return shapes_memory[key]


def wide_pages(path):
    """The pages of a volume wider than tall, as indexes; found once and kept."""
    with page_lock("shapes:" + str(path)):
        found = known_wide(path)
        if found is None:
            names = pages(path)
            with zipfile.ZipFile(path) as z:
                sizes = [image_size(z.open(n).read(HEAD)) for n in names]
            found = [i for i, size in enumerate(sizes) if size and size[0] > size[1]]
            out = shapes_file(path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"mtime": path.stat().st_mtime, "wide": found}))
            shapes_memory[(str(path), path.stat().st_mtime)] = found
        return found


# ---------- pages the size of the screen ----------
# Scans are often far wider than a screen (3000 px, over a megabyte). The reader asks
# for pages at its width, rounded up to one of WIDTHS; Ohara makes each page once, at
# most that wide and in WebP (black and white ones without their stray colours, lighter),
# keeps it in .ohara/pages,
# and makes those of a volume ahead of the reader as soon as it is opened.
WIDTHS = (800, 1200, 1600, 2400)
PAGES_KEPT = 12  # volumes whose pages are kept at the size of a screen
warming = {"job": None}  # the volume being made ahead; opening another stops it
WARMERS = 2  # pages made ahead at once
PAGES_RAM = 128 * 1024 * 1024  # bytes of pages kept in memory: two or three volumes
page_locks = {}
page_locks_guard = threading.Lock()
page_memory = collections.OrderedDict()


def page_width(w):
    """The width asked, rounded up to one of WIDTHS; 0 for the pages as they are."""
    try:
        w = int(w or 0)
    except ValueError:
        return 0
    return next((x for x in WIDTHS if x >= w), 0) if w > 0 else 0


def sized_dir(path, w):
    return STATE_DIR / "pages" / f"{hashlib.sha1(volume_id(path).encode()).hexdigest()}-{w}"


def page_lock(key):
    """One lock per page, so the reader and the making ahead never make it twice."""
    with page_locks_guard:
        return page_locks.setdefault(key, threading.Lock())


def size_page(path, n, w):
    """Page n at most w pixels wide, as WebP bytes: from memory, else from the disk,
    else made now and kept on both. The library's disk is slow to read while it is busy
    (a fraction of a second a page), so the volume read is kept in memory."""
    out = sized_dir(path, w) / f"{n}.webp"
    key = str(out)
    data = remembered(key)
    if data is None:
        with page_lock(key):
            data = remembered(key) or (out.read_bytes() if out.exists() else make_page(path, n, w, out))
            remember(key, data)
    return data


def remembered(key):
    with page_locks_guard:
        if key in page_memory:
            page_memory.move_to_end(key)
        return page_memory.get(key)


def remember(key, data):
    """Keeps a page in memory, letting go of those used longest ago past PAGES_RAM."""
    with page_locks_guard:
        page_memory[key] = data
        page_memory.move_to_end(key)
        while sum(len(d) for d in page_memory.values()) > PAGES_RAM:
            page_memory.popitem(last=False)


def make_page(path, n, w, out):
    from PIL import Image
    data, _ = page_bytes(path, n)
    img = Image.open(io.BytesIO(data))
    if img.width > w:
        img.draft(img.mode, (w, img.height * w // img.width))
    img = img.convert("L" if franky.looks_grey(img) else "RGB")
    img.thumbnail((w, img.height))
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=75, method=2)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(buf.getvalue())
    tmp.replace(out)
    return buf.getvalue()


def trim_pages(keep=PAGES_KEPT):
    """Only the pages of the volumes read last are kept at the size of a screen."""
    root = STATE_DIR / "pages"
    if not root.exists():
        return
    folders = sorted(root.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in folders[keep:]:
        shutil.rmtree(f, ignore_errors=True)


def warm(path, w, start):
    """Makes a volume's pages at width w in the background, two at a time, from the
    page the reader is at to the end, then those before, and brings them into memory;
    opening another volume stops it."""
    job = object()
    warming["job"] = job
    folder = sized_dir(path, w)
    folder.mkdir(parents=True, exist_ok=True)
    os.utime(folder)
    trim_pages()
    count = len(pages(path))
    order = iter(list(range(start, count)) + list(range(min(start, count))))

    def run():
        for n in order:
            if warming["job"] is not job:
                return
            try:
                size_page(path, n, w)
            except Exception as e:
                print(f"pages {path.name} {n}: {e}", flush=True)
                return
    for _ in range(WARMERS):
        threading.Thread(target=run, daemon=True).start()


def cover(path):
    """A small JPEG of a volume's first page, made once and kept in .ohara/covers."""
    out = STATE_DIR / "covers" / (hashlib.sha1(volume_id(path).encode()).hexdigest() + ".jpg")
    if not out.exists():
        from PIL import Image
        data, _ = page_bytes(path, 0)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((360, 540))
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "JPEG", quality=80)
    return out.read_bytes()


def volume_pages(vid, rid=None):
    path = volume_path(vid)
    series = path.parent
    vols = volumes(series)
    i = vols.index(path)
    nxt = next((v for v in vols[i + 1:] if v.suffix.lower() in READABLE), None)
    state = load_state()
    if not reader_of(state, rid):
        raise NoReader()
    saved = progress_of(state, rid).get(vid, {})
    return {
        "id": vid,
        "series": series.name,
        "label": volume_label(path.name),
        "number": volume_number(path.name),
        "chapter": is_chapter(path.name),
        "rtl": not is_webtoon(series.name, state["series"].get(series.name, {})),
        "count": len(pages(path)),
        "wide": known_wide(path),
        "page": saved.get("page", 0),
        "next": volume_id(nxt) if nxt else None,
        "eyecatches": eyecatches(series.name),
    }


EYECATCH_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                  ".svg": "image/svg+xml"}  # a drawing, animated


def eyecatch_folder(series):
    return STATE_DIR / "eyecatches" / safe_name(series)


def eyecatch_files(folder):
    """The eyecatches in a folder, by name; not its folders nor its hidden files."""
    if not folder.is_dir():
        return {}
    return {p.name: p for p in folder.iterdir()
            if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in EYECATCH_TYPES}


def eyecatch_paths(series):
    """The videos and animated drawings played between two volumes of a series, as the
    anime's eyecatch between the two halves of an episode, by name: those put in
    .ohara/eyecatches/<series>/; for a series without any, the generic ones put in
    .ohara/eyecatches/ itself, or else Ohara's own (web/eyecatches)."""
    return (eyecatch_files(eyecatch_folder(series)) or eyecatch_files(STATE_DIR / "eyecatches")
            or eyecatch_files(WEB / "eyecatches"))


def eyecatches(series):
    return sorted(eyecatch_paths(series))


def save_progress(vid, page, count, rid=None):
    volume_path(vid)

    def note(state):
        reading_of(state, rid)[vid] = {"page": int(page), "pages": int(count), "at": time.time()}
    update_state(note)


def mark_read(vids, read, rid=None):
    """Marks volumes as read (at their last page) or back to unread. The time of
    reading is kept, so marking a volume does not make it the one on the lectern."""
    paths = {vid: volume_path(vid) for vid in vids}

    if not read:  # said in the log: where you were is lost
        print(f"reading: back to unread: {len(vids)} volume(s), {', '.join(sorted(vids))[:300]}", flush=True)

    def change(state):
        progress = reading_of(state, rid)
        for vid, path in paths.items():
            if not read:
                progress.pop(vid, None)
                continue
            count = len(pages(path)) if path.suffix.lower() in READABLE else 1
            at = progress.get(vid, {}).get("at", 0)
            progress[vid] = {"page": max(0, count - 1), "pages": count, "at": at}
    update_state(change)
    return {"ok": True}


def status(rid=None):
    """The home page's card."""
    lib = library(rid)
    vols = sum(len(s["volumes"]) for s in lib["series"])
    new = sum(s["new"] for s in lib["series"])
    return {"series": len(lib["series"]), "volumes": vols, "new": new, "downloads": lib["downloads"], "last": lib["last"]}


# ---------- HTTP ----------

TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
         ".avif": "image/avif", ".pdf": "application/pdf", ".epub": "application/epub+zip", ".woff2": "font/woff2"}


class Handler(BaseHTTPRequestHandler):
    # one connection kept open for the pages of a volume, not one per page; an idle one
    # is let go after a minute
    protocol_version = "HTTP/1.1"
    timeout = 60
    disable_nagle_algorithm = True  # a page's headers and body go out without waiting

    def handle(self):
        """A phone letting go of a connection kept open is no error to report."""
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            pass

    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def query(self):
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def reader(self):
        """The reader this browser was given (the ohara-reader cookie), or None."""
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            return None
        return jar["ohara-reader"].value if "ohara-reader" in jar else None

    def do_GET(self):
        self.route(GET_ROUTES)

    def do_POST(self):
        self.route(POST_ROUTES)

    def route(self, routes):
        path = urllib.parse.urlsplit(self.path).path
        action = routes.get(path)
        try:
            if action:
                return action(self)
            return self.static(path)
        except KeyError as e:
            # a body may be left unread: the connection is not kept
            self.send(404, {"error": str(e)}, extra={"Connection": "close"})
        except NoReader:  # the page asks who reads
            self.send(401, {"error": "reader"}, extra={"Connection": "close"})
        except Exception as e:
            self.send(502, {"error": str(e)}, extra={"Connection": "close"})

    def static(self, path):
        name = {"/": "index.html", "/read": "read.html"}.get(path, path.lstrip("/"))
        f = (WEB / name).resolve()
        if WEB.resolve() not in f.parents or not f.is_file():
            raise KeyError(path)
        self.send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"), {"Cache-Control": "no-cache"})


def get_search(h):
    q = h.query().get("q", "").strip()
    h.send(200, search(q) if q else [])


def get_page(h):
    q = h.query()
    path, n, w = volume_path(q["vol"]), int(q.get("n", 0)), page_width(q.get("w"))
    if w:
        data, ctype = size_page(path, n, w), "image/webp"
    else:
        data, name = page_bytes(path, n)
        ctype = TYPES.get(Path(name).suffix.lower(), "image/jpeg")
    h.send(200, data, ctype, {"Cache-Control": "max-age=604800"})


def get_pages(h):
    """A volume to read; with the reader's width, its pages are made ahead."""
    q = h.query()
    info = volume_pages(q["vol"], h.reader())
    w = page_width(q.get("w"))
    if w and info["count"]:
        warm(volume_path(q["vol"]), w, min(info["page"], info["count"] - 1))
    if info["wide"] is None:
        threading.Thread(target=wide_pages, args=(volume_path(q["vol"]),), daemon=True).start()
    h.send(200, info)


def get_wide(h):
    """The wide pages of a volume, found now if they were not yet."""
    h.send(200, {"wide": wide_pages(volume_path(h.query()["vol"]))})


def get_file(h):
    """A PDF or EPUB as is, for the browser's own viewer; streamed, they can be big."""
    path = volume_path(h.query()["vol"])
    h.send_response(200)
    h.send_header("Content-Type", TYPES.get(path.suffix.lower(), "application/octet-stream"))
    h.send_header("Content-Length", str(path.stat().st_size))
    h.end_headers()
    with path.open("rb") as f:
        shutil.copyfileobj(f, h.wfile)


def get_cover(h):
    h.send(200, cover(volume_path(h.query()["vol"])), "image/jpeg", {"Cache-Control": "max-age=604800"})


def post_grab(h):
    b = h.body()
    h.send(200, grab(b["token"], b.get("series", ""), b.get("follow", False), b.get("query", "")))


def post_follow(h):
    b = h.body()
    set_follow(b["series"], b["follow"])
    h.send(200, {"ok": True})


def post_webtoon(h):
    b = h.body()
    set_webtoon(b["series"], b["webtoon"])
    h.send(200, {"ok": True})


def post_decor(h):
    b = h.body()
    h.send(200, set_decor(b["series"], str(b.get("decor", ""))))


def post_decor_image(h):
    n = int(h.headers.get("Content-Length") or 0)
    if n > DECOR_MAX:
        raise ValueError("image too big")
    h.send(200, keep_decor(h.query()["series"], h.rfile.read(n)))


def get_decor(h):
    f = decor_file(h.query()["series"])
    if not f.exists():
        raise KeyError("decor")
    h.send(200, f.read_bytes(), "image/jpeg", {"Cache-Control": "max-age=31536000"})


def post_discord(h):
    b = h.body()
    h.send(200, link_discord(str(b.get("url", "")), str(b.get("address", ""))))


def post_treat(h):
    b = h.body()
    h.send(200, treat(str(b["id"]), int(b.get("remedy", 0))))


def post_dismiss(h):
    b = h.body()
    h.send(200, dismiss(str(b["id"]), bool(b.get("on", True))))


def post_progress(h):
    b = h.body()
    save_progress(b["vol"], b["page"], b["count"], h.reader())
    h.send(200, {"ok": True})


def post_complete(h):
    h.send(200, complete(h.body()["series"]))


def post_indexers(h):
    choose_indexers(h.body()["indexers"])
    h.send(200, indexers())


def get_crop(h):
    vid = h.query()["vol"]
    volume_path(vid)
    path = crop_path(vid)
    if not path.exists():
        raise KeyError("no crop yet")
    h.send(200, path.read_bytes(), "image/jpeg", {"Cache-Control": "max-age=86400"})


def post_settings(h):
    h.send(200, set_settings(h.body()))


def send_file(h, path, ctype):
    """A file, or the part of it a Range header asks for (audio needs it to seek)."""
    size = path.stat().st_size
    start, end = 0, size - 1
    m = re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range") or "")
    if m and (m.group(1) or m.group(2)):
        start = int(m.group(1)) if m.group(1) else size - int(m.group(2))
        end = min(int(m.group(2)), size - 1) if m.group(1) and m.group(2) else end
    h.send_response(206 if m else 200)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    if m:
        h.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    h.end_headers()
    with path.open("rb") as f:
        f.seek(start)
        left = end - start + 1
        while left > 0:
            chunk = f.read(min(65536, left))
            if not chunk:
                break
            h.wfile.write(chunk)
            left -= len(chunk)


def get_eyecatch(h):
    q = h.query()
    path = eyecatch_paths(q["series"]).get(q["name"])
    if not path:
        raise KeyError(q["name"])
    send_file(h, path, EYECATCH_TYPES[path.suffix.lower()])


def post_add(h):
    q = h.query()
    if not q.get("series", "").strip():
        raise KeyError("series")
    h.send(200, add_volume(q["series"], q["name"], h.rfile, int(h.headers.get("Content-Length") or 0)))


def get_track(h):
    path = music_path(h.query()["id"])
    send_file(h, path, brook.AUDIO.get(path.suffix.lower(), "application/octet-stream"))


def get_art(h):
    path = music_path(h.query()["id"])
    h.send(200, path.read_bytes(), TYPES.get(path.suffix.lower(), "image/jpeg"), {"Cache-Control": "max-age=86400"})


def get_soundtracks(h):
    h.send(200, [public(r) for r in find_soundtracks(h.query()["series"])])


def post_music(h):
    b = h.body()
    h.send(200, grab_music(b["series"], b.get("token")))


def post_mood(h):
    b = h.body()
    h.send(200, set_mood(b["series"], b.get("name"), b.get("tracks") or [], b.get("lang")))


def post_read(h):
    b = h.body()
    h.send(200, mark_read([v for v in b.get("vols", []) if isinstance(v, str)], bool(b.get("read")), h.reader()))


def post_readers(h):
    """A reader added ({name}), renamed ({id, name}) or forgotten ({id, forget}); the
    readers then, and the one asking."""
    b = h.body()
    if b.get("forget"):
        return h.send(200, forget_reader(str(b["id"]), h.reader()))
    if b.get("id"):
        return h.send(200, rename_reader(str(b["id"]), b.get("name", ""), h.reader()))
    h.send(200, add_reader(b.get("name", "")))


def drop(torrent_hash):
    """Cancels a download from the lantern, remembering its release so that following
    the series does not take it again (a soundtrack the way Brook gives one up)."""
    d = load_state()["downloads"].get(torrent_hash)
    if d and d.get("kind") == "ost":
        give_up_music(torrent_hash, d)
    elif d:
        give_up(torrent_hash)
    else:
        cancel(torrent_hash)


def post_cancel(h):
    drop(h.body()["hash"])
    h.send(200, {"ok": True})


def post_another(h):
    """Gives a download up and looks for its tomes among the other releases."""
    h.send(200, complete(give_up(h.body()["hash"])))


GET_ROUTES = {
    "/api/search": get_search,
    "/api/library": lambda h: h.send(200, library(h.reader())),
    "/api/readers": lambda h: h.send(200, readers(load_state(), h.reader())),
    "/api/pages": get_pages,
    "/api/page": get_page,
    "/api/wide": get_wide,
    "/api/file": get_file,
    "/api/cover": get_cover,
    "/api/decor": get_decor,
    "/api/eyecatch": get_eyecatch,
    "/api/eyecatches": lambda h: h.send(200, {"names": eyecatches(h.query()["series"]),
                                              "own": bool(eyecatch_files(eyecatch_folder(h.query()["series"])))}),
    "/api/shelf": lambda h: h.send(200, shelf_for(h.query()["name"])),
    "/api/ailments": lambda h: h.send(200, ailments(fresh=h.query().get("fresh") == "1")),
    "/api/indexers": lambda h: h.send(200, indexers()),
    "/api/crop": get_crop,
    "/api/music": lambda h: h.send(200, music(h.query()["series"], h.query().get("lang"))),
    "/api/soundtracks": get_soundtracks,
    "/api/track": get_track,
    "/api/art": get_art,
    "/api/settings": lambda h: h.send(200, settings_page()),
    "/api/status.json": lambda h: h.send(200, status(h.reader()), extra={"Access-Control-Allow-Origin": "*"}),
}
POST_ROUTES = {"/api/grab": post_grab, "/api/follow": post_follow, "/api/webtoon": post_webtoon, "/api/complete": post_complete, "/api/progress": post_progress, "/api/indexers": post_indexers, "/api/settings": post_settings, "/api/music": post_music, "/api/mood": post_mood, "/api/read": post_read, "/api/decor": post_decor, "/api/decor/image": post_decor_image, "/api/ailments/treat": post_treat, "/api/ailments/dismiss": post_dismiss, "/api/cancel": post_cancel, "/api/discord": post_discord, "/api/another": post_another, "/api/readers": post_readers, "/api/add": post_add}


def main():
    MANGA.mkdir(parents=True, exist_ok=True)
    INCOMING.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=refresh_meta, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()
    threading.Thread(target=franky_loop, daemon=True).start()
    threading.Thread(target=doctor_loop, daemon=True).start()
    print(f"Ohara on port {PORT}, library in {MANGA}", flush=True)
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
