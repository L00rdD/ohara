"""Den Den Mushi, Ohara's snail phone: tells a Discord channel when tomes come in and
when following a series finds new ones. It speaks through the channel's webhook, set
in OHARA_DISCORD_WEBHOOK; without one, it says nothing. A message goes out in the
background, and is tried again a few times when Discord does not answer."""

import json
import threading
import time
import urllib.request

COLOUR = 0xC9A46A  # the gilt of Ohara's plaques
WORDS = {
    "fr": {
        "and": " et ",
        "to": " à ",
        "arrived": lambda n, series: f"{n} tome{'s' if n > 1 else ''} de {series} arrivé{'s' if n > 1 else ''}",
        "found": lambda series: f"Du nouveau pour {series}",
        "on_its_way": lambda what: f"En route : {what}.",
        "read": "Les lire dans Ohara",
    },
    "en": {
        "and": " and ",
        "to": " to ",
        "arrived": lambda n, series: f"{n} volume{'s' if n > 1 else ''} of {series} in",
        "found": lambda series: f"Something new for {series}",
        "on_its_way": lambda what: f"On its way: {what}.",
        "read": "Read them in Ohara",
    },
}


def tomes(numbers, lang="fr"):
    """"T3, T7 à T9" for [3, 7, 8, 9]: the tomes as runs."""
    w = WORDS[lang]
    runs = []
    for n in sorted(numbers):
        if runs and n - runs[-1][1] == 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    said = [f"T{a:g}" if a == b else f"T{a:g}{w['to']}T{b:g}" for a, b in runs]
    return ", ".join(said[:-1]) + w["and"] + said[-1] if len(said) > 1 else said[0]


def card(title, description, cover=None, link=None):
    embed = {"title": title, "description": description, "color": COLOUR}
    if cover:
        embed["thumbnail"] = {"url": cover}
    if link:
        embed["url"] = link
    return {"username": "Ohara", "embeds": [embed]}


def arrived(series, numbers, cover=None, link=None, lang="fr"):
    """The message for tomes just filed in a series."""
    w = WORDS[lang]
    text = tomes(numbers, lang) + (f"\n[{w['read']}]({link})" if link else "")
    return card(w["arrived"](len(numbers), series), text, cover, link)


def found(series, releases, cover=None, link=None, lang="fr"):
    """The message for releases a followed series has just sent for."""
    w = WORDS[lang]
    numbers = sorted({n for r in releases if r.get("range") for n in range(r["range"][0], r["range"][1] + 1)})
    what = tomes(numbers, lang) if numbers else ", ".join(r["title"] for r in releases)
    return card(w["found"](series), w["on_its_way"](what), cover, link)


def send(webhook, payload):
    req = urllib.request.Request(webhook, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "Ohara (github.com/L00rdD/ohara)"})
    with urllib.request.urlopen(req, timeout=20):
        pass


def post(webhook, payload, tries=3, wait=60, start=True):
    """Posts a message in the background, tried again when Discord does not answer."""
    def run():
        for attempt in range(tries):
            try:
                return send(webhook, payload)
            except Exception as e:
                print(f"discord: {e}", flush=True)
                if attempt + 1 < tries:
                    time.sleep(wait)
    thread = threading.Thread(target=run, daemon=True)
    if start:
        thread.start()
    return thread
