// Ohara's pure parts: the words of the page (in the language chosen, see i18n.js)
// and what each thing looks like, decided from the data. Tested in node; the page
// itself is library.js.
const Words = (() => {
  function W() {
    return (typeof I18n !== "undefined" ? I18n : require("./i18n.js")).words();
  }

  // ---- words (pure, tested in node) ----
  function size(bytes) {
    return (bytes >= 1e9 ? W().gb(bytes / 1e9) : W().mb(Math.max(1, Math.round(bytes / 1e6))));
  }

  function tomes(range) {
    return (range ? W().tomes(range[0], range[1]) : W().tomesUnknown);
  }

  function describe(r) {
    return W().release(W().langs[r.lang], size(r.size), W().speeds[r.speed] || r.speed);
  }

  function readingState(v) {
    if (!v.readable) return W().openInBrowser;
    if (v.done) return W().done;
    if (v.pages) return W().page(v.page + 1, v.pages);
    return v.new ? W().newVol : W().begin;
  }

  function eta(seconds) {
    return (seconds > 0 ? W().left(Math.ceil(seconds / 60)) : "");
  }

  function downloadState(d) {
    if (d.state === "error") return W().stuck(d.error);
    if (d.state === "done") return W().filing;
    if (d.state === "unknown") return W().waiting;
    return [`${d.pct} %`, eta(d.eta)].filter(Boolean).join(", ");
  }

  // [1, 2, 3, 5, 7, 8] → "1 à 3, 5, 7 et 8"
  function spans(numbers) {
    const parts = [];
    for (const n of numbers) {
      const last = parts[parts.length - 1];
      if (last && n === last[1] + 1) last[1] = n;
      else parts.push([n, n]);
    }
    const words = parts.flatMap(([a, b]) => (a === b ? [`${a}`] : b === a + 1 ? [`${a}`, `${b}`] : [`${a} ${W().to} ${b}`]));
    return words.length > 1 ? words.slice(0, -1).join(", ") + ` ${W().and} ` + words[words.length - 1] : words[0] || "";
  }

  function tomesWord(numbers) {
    return `${W().missingWord(numbers.length)} ${spans(numbers)}`;
  }

  function completeText(r) {
    return W().completed(r.sent.length, r.sent.map((x) => tomes(x.range).toLowerCase()).join(", "), r.nowhere.length ? spans(r.nowhere) : "");
  }

  function seriesFacts(s, meta) {
    const out = [];
    if (meta.status) out.push(W().status[meta.status] || meta.status);
    if (meta.volumes) out.push(W().out(meta.volumes));
    if (s) out.push(W().here(s.volumes.length));
    return out;
  }

  // the volume to open from a series: the one being read, the next one not read, the first
  function nextToRead(s) {
    return s.volumes.find((v) => v.readable && v.pages && !v.done) || s.volumes.find((v) => v.readable && !v.done) || s.volumes[0];
  }

  // a volume's name in the language chosen: "Tome 5", "Volume 5", or its file's name
  function volumeName(v) {
    if (!v.number) return v.label;
    const w = W().volume(v.number);
    return w.charAt(0).toUpperCase() + w.slice(1);
  }

  function readLabel(v) {
    const what = W().volume(v.number ? v.number : v.label);
    if (v.done) return `${W().reread} ${what}`;
    return `${v.pages ? W().readOn : W().readFirst} ${what}`;
  }

  function openUrl(v) {
    return (v.readable ? "/read?vol=" : "/api/file?vol=") + encodeURIComponent(v.id);
  }
  function coverUrl(id) {
    return "/api/cover?vol=" + encodeURIComponent(id);
  }
  function pageUrl(id, n) {
    return `/api/page?vol=${encodeURIComponent(id)}&n=${n}`;
  }

  // how much the lantern holds: the mean progress of the downloads, 0 to 1
  function lanternLevel(downloads) {
    return (downloads.length ? downloads.reduce((a, d) => a + d.pct, 0) / downloads.length / 100 : 0);
  }

  // a spine's colours: those Robin read on the volume's cover, else the series' own
  function spineColours(v, colour) {
    const c = v.spine;
    if (c) return { edge: c.edge, main: c.main, accent: c.accent, ink: c.ink };
    return { edge: colour, main: colour, accent: colour, ink: "#fdf6e6" };
  }

  // everything a spine needs to be drawn: classes, CSS variables, images, number
  function spineDraw(v, s, reading, colour) {
    const look = spineLook(v, s, reading);
    const vars = { "--c": colour };
    for (const [k, value] of Object.entries(spineColours(v, colour))) vars["--" + k] = value;
    return {
      cls: look.cls,
      vars,
      cover: look.cover ? coverUrl(v.id) : null,
      height: look.height ? look.height + "%" : null,
      art: v.spine ? `/api/crop?vol=${encodeURIComponent(v.id)}` : null,
      number: v.number ? String(v.number) : "",
    };
  }

  // what a download is called in the lantern: tomes, or a series' music
  function downloadName(d) {
    if (d.kind === "ost") return W().musicDownload(d.series);
    return d.range ? `${d.series}, ${tomes(d.range).toLowerCase()}` : d.series;
  }

  // the bay of a series in the contents: the first one it stands on
  function contents(bays) {
    const seen = new Map();
    bays.forEach((b, i) => !seen.has(b.series.name) && seen.set(b.series.name, { series: b.series, bay: i }));
    return [...seen.values()].sort((a, b) => a.series.name.localeCompare(b.series.name, undefined, { sensitivity: "base", numeric: true }));
  }

  // the look of a volume's spine on the shelf
  function spineLook(v, s, readingId) {
    const face = v.id === readingId;
    const started = Boolean(v.pages) && !v.done;
    // "new" marks volumes added to a series you had, not a whole series just come
    const fresh = v.new && s.new < s.volumes.length;
    const cls = ["vol", face && "face", v.done && "done", fresh && "fresh", started && !face && "marked"].filter(Boolean).join(" ");
    return { cls, cover: face && v.readable, height: started ? 86 + (v.number % 5) : null };
  }

  // what the lectern shows: nothing (a library but nothing read yet), an invitation
  // (an empty library) or the volume being read, open at its page
  function lecternState(last, series) {
    if (last) return "reading";
    return series.length ? "hidden" : "empty";
  }
  // the two pages open on the lectern, as the reader shows them two by two: the
  // cover alone (on the right, facing a blank page), then 1-2, 3-4…
  function lecternPages(v) {
    if (!v.readable) return [null, null];
    if (v.page === 0) return [null, pageUrl(v.id, 0)];
    const first = v.page % 2 ? v.page : v.page - 1;
    const count = v.pages || Infinity;
    return [pageUrl(v.id, first), first + 1 < count ? pageUrl(v.id, first + 1) : null];
  }

  // how much of a series is read: volumes done, started, still to read
  function readCounts(s) {
    const done = s.volumes.filter((v) => v.done).length;
    const started = s.volumes.filter((v) => v.pages && !v.done).length;
    return { done, started, unread: s.volumes.length - done - started, total: s.volumes.length };
  }

  // what a bay's plaque says: the series, how much is read, and which tomes when it
  // takes several bays
  function plaqueText(bay) {
    const s = bay.series;
    const c = readCounts(s);
    const whole = c.done ? W().readOf(c.done, c.total) : W().volumes(c.total);
    const sub = bay.parts > 1 && bay.span ? W().tomes(bay.span[0], bay.span[1]) : whole;
    return { title: s.name, sub: sub + (s.follow && bay.part === 0 ? ` · ${W().followed}` : "") };
  }

  // the volumes of a series up to v (its number, or its place when it has none)
  function upTo(s, v) {
    const at = s.volumes.indexOf(v);
    return s.volumes.filter((x, i) => (v.number && x.number ? x.number <= v.number : i <= at)).map((x) => x.id);
  }

  // the volume the lectern shows: the last one read, or the next one when it is finished
  function lecternVolume(last, series) {
    if (!last || !last.done) return last;
    const s = series.find((x) => x.name === last.series);
    const next = s && s.volumes.find((v) => v.readable && !v.done && (!last.number || !v.number || v.number > last.number));
    return next ? { ...next, page: 0, series: s.name, meta: s.meta } : last;
  }

  // what is said under the lectern of the place selected on a shelf
  function selectionText(place, series) {
    if (place.vol) return { title: `${series.name}, ${volumeName(place.vol).toLowerCase()}`, state: readingState(place.vol) };
    const [a, b] = place.run || [place.gap, place.gap];
    return { title: `${series.name}, ${W().tomes(a, b).toLowerCase()}`, state: W().toGet };
  }

  // what the card of a place selected on a shelf offers: a volume can be read, marked
  // read (or back to unread when it is read) and lead to its series' sheet; a missing
  // tome only to the sheet, where it can be fetched
  function selectionActions(place) {
    if (!place.vol) return ["sheet"];
    return ["open", place.vol.done ? "markUnread" : "markRead", "sheet"];
  }

  // the lantern's glass filled from y 34 (empty) up to y 10 (full); never quite empty while it burns
  function lanternFill(downloads) {
    return 34 - 24 * (downloads.length ? Math.max(0.15, lanternLevel(downloads)) : 0);
  }

  // the look of a volume's tile on a series' sheet
  function tileLook(v) {
    return { cls: v.done ? "tome done" : "tome", cover: v.readable, bar: v.pages && !v.done ? ((v.page + 1) / v.pages) * 100 : null, state: v.new ? "new" : "" };
  }

  // a speck of dust rising in the light; its brightness is how much light it is in
  function moteStep(p, w, h, t) {
    p.y -= p.v;
    p.x += Math.sin(t / 1500 + p.p) * 0.15;
    if (p.y < -5) p.y = h + 5;
    return Math.max(0, 1 - Math.abs(p.x - w / 2) / (w * 0.38)) * (1 - (p.y / h) * 0.6);
  }

  // what is said of an indexer in the settings, and whether it is a problem
  function indexerNotes(ix) {
    const notes = [!ix.on && W().indexerOff, ix.failing && W().indexerFailing, !ix.books && W().indexerNoBooks].filter(Boolean);
    return { text: notes.join(", "), bad: !ix.on || ix.failing };
  }

  // what a key does: in a text field only Escape counts
  function keyAction(key, inField) {
    if (inField) return key === "Escape" ? "close" : null;
    return { Escape: "close", ArrowLeft: "left", ArrowRight: "right", Enter: "open", "/": "search" }[key] || null;
  }

  return { size, tomes, describe, readingState, eta, downloadState, spans, tomesWord, completeText, seriesFacts, nextToRead, readLabel, openUrl, lanternLevel,
    spineLook, lecternState, lecternPages, plaqueText, selectionText, lanternFill, tileLook, moteStep, keyAction, indexerNotes, coverUrl, pageUrl, volumeName, spineColours, contents, spineDraw, downloadName, readCounts, upTo, lecternVolume, selectionActions };
})();

if (typeof module !== "undefined") module.exports = Words;
