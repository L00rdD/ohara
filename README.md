# Ohara

A manga library for a home server, made to read the volumes you own anywhere, on the
computer or the phone, without wearing out the paper ones. Type a title: Ohara finds
the volumes through your [Prowlarr](https://prowlarr.com/) indexers, picks the best
release, downloads it with [Transmission](https://transmissionbt.com/), files every
volume in its series' folder and lets you read it in the browser. Follow a series and
it fetches the missing volumes, then the new ones as they come out.

Named after the island of scholars in *One Piece*, whose library stood around the
Tree of Knowledge.

## What it does

- **Inside the Tree of Knowledge.** The library is the round wall of a hollow trunk,
  drawn in 3D around you: one bay per series with its carved plaque, the volumes on
  the shelves by their spines, the missing ones as empty places. Turn it by dragging,
  with the wheel, the arrow keys or the buttons on the sides; light falls from the
  canopy on the bay in front, lanterns hang on the posts, dust floats in the light.
- **Spines and decor.** Scans hardly ever hold a volume's real spine, and no public
  database has them, so Robin, Ohara's librarian, reads the cover of each volume
  that comes in: the colour of its left edge (where a cover meets its spine), its
  main and accent colours, and the liveliest square of the illustration for the top
  of the spine. Three styles of spines in the settings: *Comme le tome* (from the
  cover), *Reliure d'Ohara* (leather in the series' colour, gilt bands) and *Sobre*.
  Each series' bays wear its AniList banner on their back wall. A long series takes
  as many bays as its volumes need; small ones (a shelf's worth) share a bay, each on
  its own shelf under a small plaque. A tome kept in several formats (an EPUB and a
  PDF) stands once, and counts once. The contents (≡) list every series A to Z and
  turn the rotunda to it.
- **Ambient music.** Brook, Ohara's musician, finds the soundtrack of each series that
  comes in among the indexers' audio releases (its title must name the series, under
  any of its AniList names, and say OST or soundtrack; with seeders, MP3 over FLAC,
  a sensible size), downloads it and files it by album in `.ost/<Series>/`, archives
  opened. In the reader, a ♪ pill opens the player: the ambiences of the series being
  read (your own ones, its albums, everything shuffled), the track playing with its
  controls (repeat, volume), and its tracks, each one ready to go into one of your
  ambiences (Fight, Calm…). The music goes on from one volume to the next, starts
  again where you left it, and the phone's lock screen controls it. Brook can be
  switched off in the settings; a series' sheet says what he did and lets you pick
  another soundtrack. Your own music files can go in `.ost/<Series>/<Album>/` too.
- **Where you are.** A volume read wears a gilt tick on its spine, one started a
  ribbon; a plaque says how much of its series is read. A series' sheet says how many
  volumes are read, started and still to read, with *Tout marquer comme lu* and *Tout
  remettre à zéro* (touched twice), and each volume's ⋯ menu marks it read, reads up
  to it (handy for a series already read on paper) or puts it back to unread. On the
  shelves, touching a volume pins a card under the lectern: read it, mark it read (or
  back to unread), or open its series' sheet; touching it again opens it. The card
  says which chapters the volume holds, read from the English Wikipedia's lists of
  chapters for the series that have one.
- **The back of the shelves.** A series' bays wear its AniList banner by default; its
  sheet lets you put its AniList cover there instead, bare wood, a volume's cover (from
  that volume's ⋯ menu), or an image of its own: sent from the phone or the computer,
  or fetched from a link. Ohara keeps that image itself, in `.ohara/decors`.
- **The lectern.** The volume you are reading (or the next one, once it is finished) lies open in the middle of the rotunda (its ✕ puts it away, the 📖 in the corner or reading another volume brings it back; its red ribbon can be taken off in the settings),
  at your page, a ribbon in it: touch it to carry on. Other volumes you started keep
  a ribbon hanging from their spine. The rotunda opens facing the series being read.
- **The lantern.** Downloads under way light the lantern in the header, the more the
  further they have come; it opens on a parchment with each one. Off when idle.
- **One result per series.** Search from the header: the releases an indexer returns
  are grouped by series, whatever each one calls it ("Frieren", "Sousou no Frieren"),
  on a librarian's index card with the cover, status and number of volumes from
  [AniList](https://anilist.co). The best release is picked for you (French first,
  then one that has seeders, then the most volumes) and said in one sentence:
  *Tomes 1 à 14 en français, 3,6 Go, téléchargement rapide*. Ohara asks the indexers
  for their *Books* category and drops videos, music, games and adult releases.
- **The whole series.** A series' sheet says which volumes are missing and fetches
  them: the cheapest releases per missing volume (a fixed price per torrent favours
  packs, slow torrents cost more, colour editions count as another series), then
  drops the packs a bigger one made useless. A followed series is kept complete, at
  once and every 12 hours.
- **Filing.** When a download is done, the volumes go to `<library>/<Series>/` and the
  torrent is removed (no seeding). Volumes already there are left out of a pack.
  `.zip` becomes `.cbz`, `.cbr`/`.cb7` are converted with 7-Zip, a release of plain
  images becomes one `.cbz` per folder. PDF and EPUB open in the browser's viewer.
- **Reading.** Left to right: a click on the right half turns to the next page, on
  the left half back. One page or two side by side, fitted to the height or the
  width; the page reached is saved on the server, so another device picks it up.
  Pages come at the width of the screen, in WebP, made from the page you are at as
  soon as a volume opens, and kept in `.ohara/pages` (for the last 12 volumes opened)
  and in memory for the volumes being read, as the library's disk is slow when busy.
  The reader then fetches the whole volume in the background and keeps it in memory,
  so turning a page does not wait on the network; near the end, the next volume gets
  ready. A page shows only once it is whole, the one before stays until then.
- **Franky, the shipwright.** In the background, one volume after the other, Franky
  remakes each `.cbz`'s pages in WebP at quality 85, at their own size: the difference
  does not show, the room saved does (about 40 % on a black and white series). A few
  pages tried first tell whether a volume is worth it; a series already well squeezed
  is left as it is. The new volume is written under a hidden name, checked, and only
  then replaces the original, which is gone. As he replaces your files, Franky is off
  until you switch him on in the settings, which then say how far he has gone. The
  volumes being read wait.
- **Chopper, the doctor.** Chopper examines the library and says what ails it under
  the 🩺 in the header (and on each series' sheet): a tome kept twice, a file Ohara
  cannot read, a folder named after its author, a download that never starts… Each
  ailment comes with remedies to choose from, or can be set aside for good; nothing
  is changed without your choice, and a remedy that renames or deletes files asks to
  be touched twice. Renaming a volume or a series keeps where you are in it. Each
  family of examinations is a file of its own, `ailments_*.py`.
- **Kept safe.** Once a day, the state (where you are in each volume, every choice
  made) is copied to `.ohara/backups`, the last 7 days kept. A download that never
  comes can be given up for another release of the same tomes; Ohara remembers the
  one given up on and does not take it again.
- **French or English.** The flag in the header switches the interface; the choice
  is kept in the browser.
- **Settings.** Where to search: Prowlarr's indexers, each with its state (failing,
  off in Prowlarr, no Books category), ticked or not, and a link to add one in
  Prowlarr.

## Run it

You need Docker, a Prowlarr with at least one indexer that files manga under *Books*
(for French volumes, YggReborn; Nyaa.si and Knaben for the rest), and Transmission.

1. Copy `docker-compose.yml`, set `OHARA_PROWLARR_KEY`, the library folder and the
   network Prowlarr and Transmission are on.
2. Transmission must see the library's `.incoming` folder: mount the same disk in
   both containers and set `OHARA_TRANSMISSION_DIR` to the path Transmission uses.
3. `docker compose up -d --build`, then open `http://<host>:8585`.

| Variable | Default | |
| :--- | :--- | :--- |
| `OHARA_PROWLARR_URL` | `http://prowlarr:9696` | |
| `OHARA_PROWLARR_KEY` | | Prowlarr's API key. Without it, Ohara reads it from `OHARA_PROWLARR_CONFIG`. |
| `OHARA_PROWLARR_CONFIG` | `/config/prowlarr/config.xml` | Prowlarr's `config.xml`, mounted read-only, if you prefer that to the key. |
| `OHARA_INDEXERS` | `YggReborn,Nyaa.si,Knaben` | The Prowlarr indexers to search until some are ticked in the settings. |
| `OHARA_TRANSMISSION_URL` | `http://transmission:9091/transmission/rpc` | |
| `OHARA_TRANSMISSION_USER`, `OHARA_TRANSMISSION_PASSWORD` | | When Transmission asks for a login. |
| `OHARA_TRANSMISSION_DIR` | `/data/manga/.incoming` | The library's `.incoming` folder as Transmission sees it. |
| `OHARA_MANGA` | `/manga` | The library inside the container. |
| `OHARA_FOLLOW_HOURS` | `12` | How often followed series are completed. |
| `OHARA_PORT` | `8585` | |

Ohara fetches each `.torrent` itself and hands it to Transmission, so it works when
Transmission sits behind a VPN that cannot reach Prowlarr.

## The library

```text
manga/
├── Frieren/
│   ├── Frieren T01.cbz
│   └── …
├── .ost/           the music of each series, by album
├── .incoming/      downloads under way
└── .ohara/         state.json (downloads, reading progress, followed series,
                    AniList answers) and the covers made from the volumes
```

Volumes you already have can go straight into a series folder: Ohara reads the volume
number in the file name (`T05`, `Tome 5`, `v05`, `Vol. 5`).

## API

`GET /api/status.json` (CORS open) gives the number of series and volumes, the new
volumes, the downloads under way and the volume being read, for a dashboard card.
The page itself uses `/api/search`, `/api/library`, `/api/grab`, `/api/complete`,
`/api/follow`, `/api/pages`, `/api/page`, `/api/cover`, `/api/file`,
`/api/progress` and `/api/cancel`.

## Development

Python 3 with only the standard library, plus Pillow for the covers; plain HTML, CSS
and JavaScript for the pages: `i18n.js` (the words in French and English),
`words.js` (what is said and shown, decided from the data), `rotunda.js` (the
rotunda's geometry and what each bay holds), `library.js` (the page),
`robin.py` (what a spine needs, read from a cover), `franky.py` (a volume rebuilt
lighter), `chapters.py` (the chapters of each volume, from Wikipedia), `chopper.py` and
`ailments_*.py` (what ails the library, and the remedies), `brook.py` (which soundtrack,
and the titles of its tracks), `ui.js`, `search.js` and `settings.js` (the drawer of
the search and the settings), `music.js` and `player.js` (the reader's music), `sheet.js` (a series' sheet),
`reader.js` (the reader).

```bash
python3 -m unittest test_ohara.py   # the server, without Prowlarr, Transmission or a socket
node --test tests/                  # words.js, rotunda.js, reader.js
OHARA_MANGA=/tmp/manga python3 ohara.py
```

## Credits

- Series facts and covers: [AniList](https://anilist.co)'s public API.
- Titles in [Cormorant Garamond](https://github.com/CatharsisFonts/Cormorant), under
  the SIL Open Font License (`web/fonts/OFL-cormorant-garamond.txt`).

Ohara downloads what your indexers offer. Download only what you have the right to.

## License

MIT
