// Tests of the pure parts of Ohara's pages (web/*.js): node --test tests/
const test = require("node:test");
const assert = require("node:assert");
const Reader = require("../web/reader.js");
const Ohara = require("../web/words.js");
const I18n = require("../web/i18n.js");

const fr = (fn) => { I18n.set("fr"); return fn(); };
const en = (fn) => { I18n.set("en"); const r = fn(); I18n.set("fr"); return r; };

test("single pages, one at a time", () => {
  assert.deepEqual(Reader.spread(3, 10, false), [3]);
  assert.equal(Reader.after(3, 10, false), 4);
  assert.equal(Reader.before(3, 10, false), 2);
  assert.equal(Reader.before(0, 10, false), 0);
  assert.equal(Reader.after(9, 10, false), 10);
});

test("two pages: the cover alone, then pairs", () => {
  assert.deepEqual(Reader.spread(0, 10, true), [0]);
  assert.deepEqual(Reader.spread(2, 10, true), [1, 2]);
  assert.deepEqual(Reader.spread(9, 10, true), [9]);
  assert.equal(Reader.after(2, 10, true), 3);
  assert.equal(Reader.before(4, 10, true), 1);
  assert.equal(Reader.before(1, 10, true), 0);
});

test("the right half turns to the next page, the left half back", () => {
  assert.equal(Reader.zone(0.1), "prev");
  assert.equal(Reader.zone(0.5), "next");
});

test("sizes in Mo and Go", () => {
  assert.equal(Ohara.size(7.41e9), "7,4 Go");
  assert.equal(Ohara.size(3.6e8), "360 Mo");
  assert.equal(Ohara.size(1000), "1 Mo");
  assert.equal(en(() => Ohara.size(7.41e9)), "7.4 GB");
  assert.equal(en(() => Ohara.size(3.6e8)), "360 MB");
});

test("tomes and releases in both languages", () => {
  assert.equal(fr(() => Ohara.tomes([1, 14])), "Tomes 1 à 14");
  assert.equal(fr(() => Ohara.tomes([98, 98])), "Tome 98");
  assert.equal(fr(() => Ohara.tomes(null)), "Tomes non précisés");
  assert.equal(en(() => Ohara.tomes([1, 14])), "Volumes 1 to 14");
  const r = { lang: "FR", size: 3.6e9, speed: "rapide" };
  assert.equal(fr(() => Ohara.describe(r)), "en français, 3,6 Go, téléchargement rapide");
  assert.equal(en(() => Ohara.describe(r)), "in French, 3.6 GB, fast download");
  assert.equal(fr(() => Ohara.describe({ ...r, speed: "autre" })), "en français, 3,6 Go, téléchargement autre");
});

test("where a volume is in its reading", () => {
  const v = { readable: true, pages: 0, page: 0, done: false, new: false };
  assert.equal(fr(() => Ohara.readingState(v)), "pas encore commencé");
  assert.equal(fr(() => Ohara.readingState({ ...v, new: true })), "nouveau");
  assert.equal(fr(() => Ohara.readingState({ ...v, pages: 195, page: 7 })), "page 8 sur 195");
  assert.equal(en(() => Ohara.readingState({ ...v, pages: 195, page: 7 })), "page 8 of 195");
  assert.equal(fr(() => Ohara.readingState({ ...v, done: true })), "lu");
  assert.equal(fr(() => Ohara.readingState({ ...v, readable: false })), "s'ouvre dans le navigateur");
});

test("a download in words", () => {
  assert.equal(fr(() => Ohara.eta(-1)), "");
  assert.equal(fr(() => Ohara.eta(600)), "encore 10 min");
  assert.equal(en(() => Ohara.eta(7200)), "2 h left");
  assert.equal(fr(() => Ohara.downloadState({ state: "error", error: "no space" })), "bloqué : no space");
  assert.equal(fr(() => Ohara.downloadState({ state: "done" })), "rangement");
  assert.equal(fr(() => Ohara.downloadState({ state: "unknown" })), "en attente");
  assert.equal(fr(() => Ohara.downloadState({ state: "downloading", pct: 42, eta: 600 })), "42 %, encore 10 min");
  assert.equal(fr(() => Ohara.downloadState({ state: "downloading", pct: 3, eta: -1 })), "3 %");
});

test("tomes in spans", () => {
  assert.equal(fr(() => Ohara.spans([1, 2, 3, 5, 7, 8])), "1 à 3, 5, 7 et 8");
  assert.equal(en(() => Ohara.spans([1, 2, 3, 9])), "1 to 3 and 9");
  assert.equal(fr(() => Ohara.spans([])), "");
  assert.equal(fr(() => Ohara.tomesWord([1, 2, 3])), "les tomes 1 à 3");
  assert.equal(fr(() => Ohara.tomesWord([7])), "le tome 7");
});

test("what a completion did", () => {
  const two = { sent: [{ range: [1, 72] }, { range: [98, 98] }], nowhere: [] };
  assert.equal(fr(() => Ohara.completeText(two)), "2 téléchargements lancés : tomes 1 à 72, tome 98.");
  const one = { sent: [{ range: [1, 14] }], nowhere: [15, 16] };
  assert.equal(fr(() => Ohara.completeText(one)), "Téléchargement lancé : tomes 1 à 14. Introuvables pour l'instant : 15 et 16. Ohara réessaiera si tu suis la série.");
  assert.equal(en(() => Ohara.completeText({ sent: [], nowhere: [] })), "No French release found for these volumes.");
});

test("what is known of a series", () => {
  assert.deepEqual(fr(() => Ohara.seriesFacts({ volumes: [1, 2] }, { status: "En cours", volumes: 114 })), ["En cours de parution", "114 tomes parus", "2 chez toi"]);
  assert.deepEqual(en(() => Ohara.seriesFacts(undefined, { status: "Terminé" })), ["Finished"]);
  assert.deepEqual(fr(() => Ohara.seriesFacts(undefined, { status: "Inconnu" })), ["Inconnu"]);
});

test("the volume a series opens on, and its button", () => {
  const a = { readable: true, pages: 0, done: true, number: 1, label: "Tome 1" };
  const b = { readable: true, pages: 120, page: 3, done: false, number: 2, label: "Tome 2" };
  const c = { readable: true, pages: 0, done: false, number: 3, label: "Tome 3" };
  assert.equal(Ohara.nextToRead({ volumes: [a, b, c] }), b);
  assert.equal(Ohara.nextToRead({ volumes: [a, c] }), c);
  assert.equal(Ohara.nextToRead({ volumes: [a] }), a);
  assert.equal(fr(() => Ohara.readLabel(b)), "Reprendre le tome 2");
  assert.equal(fr(() => Ohara.readLabel(c)), "Lire le tome 3");
  assert.equal(fr(() => Ohara.readLabel(a)), "Relire le tome 1");
  assert.equal(en(() => Ohara.readLabel(b)), "Continue volume 2");
  assert.equal(fr(() => Ohara.readLabel({ ...c, number: null, label: "Artbook" })), "Lire le tome Artbook");
});

test("a volume opens in the reader, a PDF in the browser", () => {
  assert.equal(Ohara.openUrl({ id: "Naruto/T 1.cbz", readable: true }), "/read?vol=Naruto%2FT%201.cbz");
  assert.equal(Ohara.openUrl({ id: "Naruto/T3.pdf", readable: false }), "/api/file?vol=Naruto%2FT3.pdf");
});

test("how much the lantern holds", () => {
  assert.equal(Ohara.lanternLevel([]), 0);
  assert.equal(Ohara.lanternLevel([{ pct: 40 }, { pct: 80 }]), 0.6);
});

test("the language is kept, French by default", () => {
  I18n.set("de");
  assert.equal(I18n.get(), "fr");
  I18n.set("en");
  assert.equal(I18n.get(), "en");
  I18n.set("fr");
  assert.deepEqual(Object.keys(I18n.WORDS.fr).sort(), Object.keys(I18n.WORDS.en).sort());
});

const vol = (extra) => ({ id: "S/T5.cbz", number: 5, readable: true, pages: 0, page: 0, done: false, new: false, ...extra });
const series = (extra) => ({ name: "S", new: 0, volumes: [1, 2, 3], ...extra });

test("the look of a spine", () => {
  assert.deepEqual(Ohara.spineLook(vol(), series(), null), { cls: "vol", cover: false, height: null });
  assert.deepEqual(Ohara.spineLook(vol({ pages: 100, page: 3 }), series(), "S/T5.cbz"), { cls: "vol face", cover: true, height: 86 });
  assert.equal(Ohara.spineLook(vol({ pages: 100, page: 3 }), series(), null).cls, "vol marked");
  assert.equal(Ohara.spineLook(vol({ new: true }), series({ new: 1 }), null).cls, "vol fresh");
  assert.equal(Ohara.spineLook(vol({ new: true }), series({ new: 3 }), null).cls, "vol");
  assert.equal(Ohara.spineLook(vol({ done: true, pages: 10, page: 9 }), series(), null).cls, "vol done");
  assert.equal(Ohara.spineLook(vol({ readable: false }), series(), "S/T5.cbz").cover, false);
});

test("what the lectern shows", () => {
  assert.equal(Ohara.lecternState(null, []), "empty");
  assert.equal(Ohara.lecternState(null, [{}]), "hidden");
  assert.equal(Ohara.lecternState({}, [{}]), "reading");
  assert.equal(Ohara.lecternState({ id: "S/1" }, [{}], "S/1"), "away"); // put away
  assert.equal(Ohara.lecternState({ id: "S/2" }, [{}], "S/1"), "reading"); // back with another volume
  const url = (n) => `/api/page?vol=S%2FT5.cbz&n=${n}`;
  assert.deepEqual(Ohara.lecternPages(vol({ page: 0, pages: 195 })), [null, url(0)]);
  assert.deepEqual(Ohara.lecternPages(vol({ page: 7, pages: 195 })), [url(7), url(8)]);
  assert.deepEqual(Ohara.lecternPages(vol({ page: 8, pages: 195 })), [url(7), url(8)]);
  assert.deepEqual(Ohara.lecternPages(vol({ page: 194, pages: 195 })), [url(193), url(194)]);
  assert.deepEqual(Ohara.lecternPages(vol({ page: 195, pages: 196 })), [url(195), null]);
  assert.deepEqual(Ohara.lecternPages(vol({ page: 3, pages: 0 })), [url(3), url(4)]);
  assert.deepEqual(Ohara.lecternPages(vol({ readable: false })), [null, null]);
});

test("the lantern's glass", () => {
  assert.equal(Ohara.lanternFill([]), 34);
  assert.equal(Ohara.lanternFill([{ pct: 0 }]), 34 - 24 * 0.15);
  assert.equal(Ohara.lanternFill([{ pct: 100 }]), 10);
});

test("the look of a tile", () => {
  assert.deepEqual(Ohara.tileLook(vol()), { cls: "tome", cover: true, bar: null, state: "" });
  assert.deepEqual(Ohara.tileLook(vol({ pages: 10, page: 4, new: true })), { cls: "tome", cover: true, bar: 50, state: "new" });
  assert.equal(Ohara.tileLook(vol({ done: true, pages: 10, page: 9 })).cls, "tome done");
});

test("a speck of dust rises and wraps", () => {
  const p = { x: 50, y: 0, v: 10, p: 0 };
  const light = Ohara.moteStep(p, 100, 100, 0);
  assert.equal(p.y, 105);
  assert.ok(light >= 0 && light <= 1);
  const middle = { x: 50, y: 50, v: 0, p: 0 };
  const side = { x: 2, y: 50, v: 0, p: 0 };
  assert.ok(Ohara.moteStep(middle, 100, 100, 0) > Ohara.moteStep(side, 100, 100, 0));
});

test("what a key does", () => {
  assert.equal(Ohara.keyAction("ArrowLeft", false), "left");
  assert.equal(Ohara.keyAction("ArrowRight", false), "right");
  assert.equal(Ohara.keyAction("/", false), "search");
  assert.equal(Ohara.keyAction("Enter", false), "open");
  assert.equal(Ohara.keyAction("Escape", true), "close");
  assert.equal(Ohara.keyAction("ArrowLeft", true), null);
  assert.equal(Ohara.keyAction("x", false), null);
});

test("what is said of an indexer", () => {
  assert.deepEqual(fr(() => Ohara.indexerNotes({ on: true, failing: false, books: true })), { text: "", bad: false });
  assert.deepEqual(fr(() => Ohara.indexerNotes({ on: false, failing: true, books: false })), { text: "désactivé dans Prowlarr, en panne, pas de catégorie Livres", bad: true });
  assert.deepEqual(fr(() => Ohara.indexerNotes({ on: true, failing: false, books: false })), { text: "pas de catégorie Livres", bad: false });
});

test("a volume's name in the language chosen", () => {
  assert.equal(fr(() => Ohara.volumeName({ number: 5, label: "Tome 5" })), "Tome 5");
  assert.equal(en(() => Ohara.volumeName({ number: 5, label: "Tome 5" })), "Volume 5");
  assert.equal(en(() => Ohara.volumeName({ number: null, label: "Artbook" })), "Artbook");
});

test("what a bay's plaque says", () => {
  const s = { name: "Naruto", follow: true, volumes: Array.from({ length: 72 }, (_, i) => ({ number: i + 1 })) };
  assert.deepEqual(fr(() => Ohara.plaqueText({ series: s, part: 0, parts: 1, span: [1, 72] })), { title: "Naruto", sub: "72 tomes · suivie" });
  const some = { name: "Naruto", follow: false, volumes: [{ done: true }, { done: true }, { pages: 9 }, {}] };
  assert.deepEqual(fr(() => Ohara.plaqueText({ series: some, part: 0, parts: 1, span: [1, 4] })), { title: "Naruto", sub: "2 lus sur 4" });
  assert.deepEqual(fr(() => Ohara.plaqueText({ series: s, part: 1, parts: 2, span: [37, 72] })), { title: "Naruto", sub: "Tomes 37 à 72" });
  assert.deepEqual(en(() => Ohara.plaqueText({ series: { ...s, follow: false }, part: 0, parts: 2, span: [1, 36] })), { title: "Naruto", sub: "Volumes 1 to 36" });
});

test("what is said of the place selected", () => {
  const s = { name: "Naruto" };
  assert.deepEqual(fr(() => Ohara.selectionText({ vol: vol({ number: 12, pages: 180, page: 2 }) }, s)), { title: "Naruto, tome 12", state: "page 3 sur 180" });
  assert.deepEqual(fr(() => Ohara.selectionText({ run: [1, 97] }, s)), { title: "Naruto, tomes 1 à 97", state: "à récupérer" });
  assert.deepEqual(fr(() => Ohara.selectionText({ vol: vol({ number: 19, chapters: [162, 171] }) }, s)).state.split(" · ")[1], "chapitres 162 à 171");
  assert.equal(en(() => Ohara.selectionText({ vol: vol({ number: 2, chapters: [9, 9] }) }, s)).state.split(" · ")[1], "chapter 9");
  assert.deepEqual(en(() => Ohara.selectionText({ gap: 7 }, s)), { title: "Naruto, volume 7", state: "to get" });
});

test("a spine's colours: Robin's reading, else the series' colour", () => {
  assert.deepEqual(Ohara.spineColours({ spine: { edge: "#111111", main: "#222222", accent: "#333333", ink: "#fdf6e6" } }, "#999999"), { edge: "#111111", main: "#222222", accent: "#333333", ink: "#fdf6e6" });
  assert.deepEqual(Ohara.spineColours({ spine: null }, "#999999"), { edge: "#999999", main: "#999999", accent: "#999999", ink: "#fdf6e6" });
});

test("the contents: each series once, A to Z, at its first bay", () => {
  const s = (name) => ({ name });
  const bays = [{ series: s("one piece") }, { series: s("Naruto") }, { series: s("Naruto") }, { series: s("Berserk") }];
  assert.deepEqual(Ohara.contents(bays).map((x) => [x.series.name, x.bay]), [["Berserk", 3], ["Naruto", 1], ["one piece", 0]]);
});

test("everything a spine needs", () => {
  const s = { name: "S", new: 0, volumes: [1, 2] };
  const plain = Ohara.spineDraw(vol({ spine: null, number: 7 }), s, null, "#123456");
  assert.deepEqual(plain, { cls: "vol", vars: { "--c": "#123456", "--edge": "#123456", "--main": "#123456", "--accent": "#123456", "--ink": "#fdf6e6" }, cover: null, height: null, art: null, number: "7" });
  const read = Ohara.spineDraw(vol({ spine: { edge: "#1", main: "#2", accent: "#3", ink: "#4" }, pages: 10, page: 2 }), s, "S/T5.cbz", "#123456");
  assert.equal(read.cover, "/api/cover?vol=S%2FT5.cbz");
  assert.equal(read.art, "/api/crop?vol=S%2FT5.cbz");
  assert.equal(read.height, "86%");
  assert.equal(Ohara.spineDraw(vol({ number: null }), s, null, "#1").number, "");
});

test("what a download is called", () => {
  assert.equal(fr(() => Ohara.downloadName({ kind: "ost", series: "Frieren" })), "Musique de Frieren");
  assert.equal(en(() => Ohara.downloadName({ kind: "ost", series: "Frieren" })), "Music of Frieren");
  assert.equal(fr(() => Ohara.downloadName({ kind: "volumes", series: "Naruto", range: [1, 72] })), "Naruto, tomes 1 à 72");
  assert.equal(fr(() => Ohara.downloadName({ series: "Naruto", range: null })), "Naruto");
});

test("how much of a series is read", () => {
  const s = { volumes: [{ done: true, pages: 9 }, { pages: 9, page: 2 }, {}, {}] };
  assert.deepEqual(Ohara.readCounts(s), { done: 1, started: 1, unread: 2, total: 4 });
  const twice = { volumes: [{ number: 1, file: "1.epub" }, { number: 1, file: "1.pdf", done: true, pages: 9 }, { number: 2, file: "2.epub" }, { number: 2, file: "2.pdf" }] };
  assert.deepEqual(Ohara.readCounts(twice), { done: 1, started: 0, unread: 1, total: 2 }); // an EPUB and a PDF: one tome
  assert.equal(fr(() => I18n.words().progressLine(1, 1, 2)), "1 lu, 1 en cours, 2 à lire");
  assert.equal(fr(() => I18n.words().progressLine(3, 0, 0)), "3 lus");
  assert.equal(en(() => I18n.words().progressLine(0, 2, 1)), "2 started, 1 to read");
});

test("the volumes up to one", () => {
  const vs = [{ id: "a", number: 1 }, { id: "b", number: 2 }, { id: "c", number: 3 }, { id: "x", number: null }];
  const s = { volumes: vs };
  assert.deepEqual(Ohara.upTo(s, vs[1]), ["a", "b"]);
  assert.deepEqual(Ohara.upTo(s, vs[3]), ["a", "b", "c", "x"]);
});

test("the lectern moves on to the next volume once one is finished", () => {
  const vs = [{ id: "S/1", number: 1, readable: true, done: true }, { id: "S/2", number: 2, readable: true, done: false, pages: 0 }];
  const series = [{ name: "S", meta: { color: "#1" }, volumes: vs }];
  const last = { ...vs[0], series: "S", page: 9 };
  assert.deepEqual(Ohara.lecternVolume(last, series), { ...vs[1], page: 0, series: "S", meta: { color: "#1" } });
  assert.equal(Ohara.lecternVolume({ ...last, done: false }, series).id, "S/1");
  assert.equal(Ohara.lecternVolume(null, series), null);
  assert.equal(Ohara.lecternVolume({ ...last, series: "Gone" }, series).id, "S/1");
  const allDone = [{ name: "S", meta: {}, volumes: [vs[0]] }];
  assert.equal(Ohara.lecternVolume(last, allDone).id, "S/1");
});

test("what the card of a place selected on a shelf offers", () => {
  assert.deepEqual(Ohara.selectionActions({ vol: { done: false, pages: 3 } }), ["open", "markRead", "sheet"]);
  assert.deepEqual(Ohara.selectionActions({ vol: { done: true } }), ["open", "markUnread", "sheet"]);
  assert.deepEqual(Ohara.selectionActions({ gap: 4 }), ["sheet"]);
});

test("the back of a series' shelves", () => {
  const s = { meta: { banner: "B.jpg", cover: "C.jpg" }, volumes: [{ id: "S/T02.cbz", number: 2 }] };
  assert.equal(Ohara.decorUrl(s), "B.jpg");
  assert.equal(Ohara.decorUrl({ ...s, decor: "cover" }), "C.jpg");
  assert.equal(Ohara.decorUrl({ ...s, decor: "none" }), null);
  assert.equal(Ohara.decorUrl({ ...s, decor: "vol:S/T02.cbz" }), "/api/cover?vol=S%2FT02.cbz");
  assert.equal(Ohara.decorUrl({ ...s, decor: "url:https://x.org/a.jpg" }), "https://x.org/a.jpg");
  assert.equal(Ohara.decorUrl({ meta: {} }), null);
  assert.deepEqual(Ohara.decorChoices({ ...s, decor: "banner" }), ["banner", "cover", "none"]);
  assert.deepEqual(Ohara.decorChoices({ meta: {}, decor: "url:https://x.org/a.jpg" }), ["none", "url:https://x.org/a.jpg"]);
  assert.deepEqual(Ohara.decorChoices({ meta: {}, kept: 7, decor: "none" }), ["none", "own:7"]);
  assert.deepEqual(Ohara.decorChoices({ meta: {}, kept: 7, decor: "vol:S/T02.cbz" }), ["none", "own:7", "vol:S/T02.cbz"]);
  assert.equal(Ohara.decorUrl({ name: "Fruits Basket", meta: {}, decor: "own:7" }), "/api/decor?series=Fruits%20Basket&v=7");
  assert.equal(fr(() => Ohara.decorName(s, "own:7")), "Ton image");
  assert.equal(fr(() => Ohara.decorName(s, "vol:S/T02.cbz")), "Tome 2");
  assert.equal(fr(() => Ohara.decorName(s, "vol:S/gone.cbz")), "Un tome");
  assert.equal(fr(() => Ohara.decorName(s, "url:https://x.org/a.jpg")), "Image du web");
  assert.equal(en(() => Ohara.decorName(s, "none")), "Bare wood");
});

test("the width a page is asked at", () => {
  assert.equal(Reader.pageWidth(390, 3, false), 1170);
  assert.equal(Reader.pageWidth(1440, 2, true), 1440);
  assert.equal(Reader.pageWidth(1000.5, 1, false), 1001);
});

test("the pages made ready around the one read", () => {
  assert.deepEqual(Reader.around(0, 100, false), [0, 1, 2, 3, 4, 5, 6]);
  assert.deepEqual(Reader.around(10, 100, false), [8, 9, 10, 11, 12, 13, 14, 15, 16]);
  assert.deepEqual(Reader.around(10, 100, true), [7, 8, 9, 10, 11, 12, 13, 14, 15, 16]);
  assert.deepEqual(Reader.around(98, 100, false), [96, 97, 98, 99]);
});

test("a volume's pages fetched from the one read, then those before", () => {
  assert.deepEqual(Reader.wholeOrder(3, 6), [3, 4, 5, 0, 1, 2]);
  assert.deepEqual(Reader.wholeOrder(0, 3), [0, 1, 2]);
  assert.deepEqual(Reader.wholeOrder(0, 0), []);
  assert.equal(Reader.nearEnd(89, 100), false);
  assert.equal(Reader.nearEnd(90, 100), true);
});

test("how far Franky has gone", () => {
  assert.equal(fr(() => Ohara.lighterText({ done: 12, total: 340, saved: 4.2e9 })), "12 tomes sur 340 vus · 4,2 Go gagnés");
  assert.equal(fr(() => Ohara.lighterText({ done: 1, total: 340, saved: 3e6 })), "1 tome sur 340 vu · 3 Mo gagnés");
  assert.equal(fr(() => Ohara.lighterText({ done: 0, total: 340, saved: 0 })), "Aucun des 340 tomes n'est encore passé entre ses mains.");
  assert.equal(en(() => Ohara.lighterText({ done: 2, total: 9, saved: 5e8 })), "2 of 9 volumes seen · 500 MB saved");
});

test("the ailments by series, the library's own apart", () => {
  const list = [{ id: 1, series: "B" }, { id: 2, series: null }, { id: 3, series: "B" }, { id: 4, series: "A" }];
  assert.deepEqual(Ohara.bySeries(list).map(([s, l]) => [s, l.map((a) => a.id)]), [["B", [1, 3]], ["", [2]], ["A", [4]]]);
  assert.deepEqual(Ohara.bySeries([]), []);
});

test("a series' sheet drawn again only when it changed, and not while you are on it", () => {
  const s = { name: "S", volumes: [] };
  assert.equal(Ohara.redrawn(s, "", 0, false), true);
  assert.equal(Ohara.redrawn(s, JSON.stringify(s), 0, false), false); // the same
  assert.equal(Ohara.redrawn({ ...s, follow: true }, JSON.stringify(s), 1, false), false); // an image on its way
  assert.equal(Ohara.redrawn({ ...s, follow: true }, JSON.stringify(s), 0, true), false); // typing
  assert.equal(Ohara.redrawn(undefined, "", 0, false), false);
});

test("the library kept in the browser", () => {
  assert.deepEqual(Ohara.keptLibrary('{"series": [{"name": "S"}], "last": null}'), { series: [{ name: "S" }], last: null });
  assert.equal(Ohara.keptLibrary(null), null);
  assert.equal(Ohara.keptLibrary("{not json"), null);
  assert.equal(Ohara.keptLibrary('{"series": 3}'), null);
  const nobody = { series: [], readers: [{ id: "1" }, { id: "a1" }], reader: null };
  assert.equal(Ohara.keptLibrary(JSON.stringify(nobody)), null);
  assert.equal(Ohara.keptLibrary(JSON.stringify({ ...nobody, reader: "a1" })).reader, "a1");
});

test("a reader: their name, the first one's until renamed, and their badge", () => {
  assert.equal(fr(() => Ohara.readerName({ id: "1", name: "" })), "Premier lecteur");
  assert.equal(en(() => Ohara.readerName({ id: "1", name: "" })), "First reader");
  assert.equal(Ohara.readerName({ id: "a1", name: "Robin" }), "Robin");
  const look = Ohara.readerLook({ id: "a1", name: "élise" });
  assert.equal(look.initial, "É");
  assert.match(look.colour, /^hsl\(\d+, 45%, 42%\)$/);
  assert.equal(Ohara.readerLook({ id: "a1", name: "x" }).colour, look.colour); // the same colour each time
  assert.notEqual(Ohara.readerLook({ id: "b2", name: "x" }).colour, look.colour);
  assert.equal(fr(() => Ohara.readerLook({ id: "1", name: "" })).initial, "P");
});

test("who reads: asked among several, shown in the header once there are two", () => {
  const two = [{ id: "1", name: "" }, { id: "a1", name: "Robin" }];
  assert.deepEqual(Ohara.whoReads({ readers: two, reader: "a1" }), { me: two[1], asked: false });
  assert.deepEqual(Ohara.whoReads({ readers: two, reader: null }), { me: null, asked: true });
  assert.deepEqual(Ohara.whoReads({ readers: [two[0]], reader: "1" }), { me: null, asked: false });
  assert.deepEqual(Ohara.whoReads({ series: [] }), { me: null, asked: false }); // a library kept from before the readers
});

test("the reader's cookie is kept for years, for the whole site", () => {
  assert.equal(Ohara.readerCookie("a b"), "ohara-reader=a%20b; max-age=315360000; path=/; samesite=lax");
});
