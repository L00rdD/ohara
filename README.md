# Ohara

A manga library for a home server. Type a title: Ohara finds the volumes through your
[Prowlarr](https://prowlarr.com/) indexers, picks the best release, downloads it with
[Transmission](https://transmissionbt.com/), files every volume in its series' folder
and lets you read it in the browser, on the computer or the phone. Follow a series and
it fetches the missing volumes, then the new ones as they come out.

Named after the island of scholars in *One Piece*, whose library stood around the
Tree of Knowledge.

## What it does

- **One result per series.** The releases an indexer returns are grouped by series,
  whatever each one calls it ("Frieren", "Sousou no Frieren"), with the cover, the
  status and the number of volumes from [AniList](https://anilist.co). The best
  release is picked for you (French first, then one that has seeders, then the most
  volumes) and said in one sentence: *Tomes 1 à 14 en français, 3,6 Go,
  téléchargement rapide*. The other releases are folded below it.
- **Only books.** Ohara asks the indexers for their *Books* category and drops videos,
  music, games and adult releases.
- **The whole series.** A series page says which volumes are missing, from the first
  to the last one out, and fetches them: the cheapest releases per missing volume
  (a fixed price per torrent favours packs, slow torrents cost more, colour editions
  count as another series), then drops the packs a bigger one made useless.
- **Follow.** A followed series is kept complete: at once, then every 12 hours.
  New volumes wear a *Nouveau* ribbon until opened.
- **Filing.** When a download is done, the volumes go to `<library>/<Series>/` and the
  torrent is removed (no seeding). Volumes already there are left out of a pack.
  `.zip` becomes `.cbz`, `.cbr`/`.cb7` are converted with 7-Zip, a release of plain
  images becomes one `.cbz` per folder. PDF and EPUB are kept as they are and open in
  the browser's own viewer.
- **Reading.** The page opens on the volume you were reading. The reader goes left to
  right (a click on the right half turns to the next page, on the left half back), one
  page or two side by side, fitted to the height or the width. It preloads the next
  pages, offers the next volume at the end and saves the page reached on the server,
  so another device picks up where you stopped.

The interface is in French.

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
| `OHARA_INDEXERS` | `YggReborn,Nyaa.si,Knaben` | The Prowlarr indexers to search, by their name in Prowlarr. |
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
and JavaScript for the pages.

```bash
python3 -m unittest test_ohara.py   # the server, without Prowlarr, Transmission or a socket
node --test tests/                  # the pure parts of the pages
OHARA_MANGA=/tmp/manga python3 ohara.py
```

## Credits

- Series facts and covers: [AniList](https://anilist.co)'s public API.
- Titles in [Cormorant Garamond](https://github.com/CatharsisFonts/Cormorant), under
  the SIL Open Font License (`web/fonts/OFL-cormorant-garamond.txt`).

Ohara downloads what your indexers offer. Download only what you have the right to.

## License

MIT
