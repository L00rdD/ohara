"""The chapters each volume of a series holds, read from the English Wikipedia's lists
of chapters ("List of One Piece chapters (1–186)", "List of Naruto chapters (Part I)"…),
the one place that keeps them for licensed series. Only their numbers are kept. A
series too little known to have such a list has none."""

import json
import re
import urllib.parse
import urllib.request

API = "https://en.wikipedia.org/w/api.php"
VOLUME = re.compile(r"\|\s*VolumeNumber\s*=\s*([^\n|]*)")
NUMBERED = re.compile(r"\{\{\s*Numbered list\s*\|\s*start\s*=\s*(\d+)", re.I)
PARAM = re.compile(r"^\|\s*\w+\s*=")


def ask(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    req = urllib.request.Request(url, headers={"User-Agent": "Ohara (github.com/L00rdD/ohara)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def list_pages(name):
    """The pages listing a series' chapters: "List of <name> chapters", and its parts."""
    prefix = f"List of {name} chapters"
    found = ask({"action": "query", "list": "prefixsearch", "pssearch": prefix, "pslimit": 20})
    titles = [p["title"] for p in found["query"]["prefixsearch"]]
    return [t for t in titles if t.lower() == prefix.lower() or t.lower().startswith(prefix.lower() + " (")]


def wikitext(title):
    return ask({"action": "parse", "page": title, "prop": "wikitext", "redirects": 1})["parse"]["wikitext"]


def numbered(block):
    """The chapters of {{Numbered list|start=N|…}} lists: N on, one an item."""
    chapters = []
    for m in NUMBERED.finditer(block):
        count = 0
        for line in block[m.end():].splitlines()[1:]:
            line = line.strip()
            if line.startswith("}}") or PARAM.match(line):
                break
            count += line.startswith("|") and len(line) > 1
        chapters += range(int(m.group(1)), int(m.group(1)) + count)
    return chapters


def hashed(block, after):
    """The chapters of "#" lists: from <li value="N">, or on from the volume before."""
    items = [line for line in block.splitlines() if line.startswith("#")]
    if not items:
        return []
    start = re.search(r'value\s*=\s*"?(\d+)', items[0])
    first = int(start.group(1)) if start else after + 1
    return list(range(first, first + len(items)))


def read(text):
    """{volume: [first chapter, last chapter]} from a list's wikitext. Volumes still to
    come are commented out on Wikipedia, and so left out."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    marks = list(VOLUME.finditer(text))
    found, last = {}, 0
    for m, nxt in zip(marks, marks[1:] + [None]):
        number = re.search(r"\d+", m.group(1))
        block = text[m.end():nxt.start() if nxt else len(text)]
        block = block.split("\n==")[0]  # not the chapters not yet in a volume, after it
        chapters = numbered(block) or hashed(block, last)
        if number and chapters:
            found[int(number.group())] = [min(chapters), max(chapters)]
            last = max(chapters)
    return found


def chapters(names):
    """{volume: [first, last]} for the first of a series' names Wikipedia has a list for."""
    for name in names:
        pages = list_pages(name)
        if pages:
            found = {}
            for title in pages:
                found.update(read(wikitext(title)))
            return found
    return {}
