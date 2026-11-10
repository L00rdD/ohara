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
  // the page shown on the lectern: the one you are at
  function lecternPage(v) {
    return v.readable ? pageUrl(v.id, v.page) : null;
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
    spineLook, lecternState, lecternPage, lanternFill, tileLook, moteStep, keyAction, indexerNotes, coverUrl, pageUrl, volumeName };
})();

if (typeof module !== "undefined") module.exports = Words;
