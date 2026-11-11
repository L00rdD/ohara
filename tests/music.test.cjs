// Tests of the reader's music, its pure parts (web/music.js)
const test = require("node:test");
const assert = require("node:assert");
const M = require("../web/music.js");

const music = {
  albums: [
    { name: "Season 1", art: "F/Season 1/cover.jpg", tracks: [{ id: "a", title: "A" }, { id: "b", title: "B" }] },
    { name: "Season 2", art: null, tracks: [{ id: "c", title: "C" }] },
  ],
  moods: [{ name: "Calme", tracks: ["c", "a", "gone"] }, { name: "Vide", tracks: ["gone"] }],
};

test("the ambiences: yours, the albums, then everything", () => {
  const list = M.ambiences(music, "Tout");
  assert.deepEqual(list.map((a) => [a.key, a.kind, a.tracks.map((t) => t.id).join("")]), [
    ["mood:Calme", "mood", "ca"], ["album:Season 1", "album", "ab"], ["album:Season 2", "album", "c"], ["all", "all", "abc"]]);
  assert.equal(list[1].art, "F/Season 1/cover.jpg");
  assert.deepEqual(M.ambiences({ albums: [{ name: "X", art: null, tracks: [{ id: "x", title: "X" }] }], moods: [] }, "Tout").map((a) => a.key), ["album:X"]);
  assert.deepEqual(M.ambiences({ albums: [], moods: [] }, "Tout"), []);
});

test("which track comes next", () => {
  assert.equal(M.nextIndex(0, 3, "none"), 1);
  assert.equal(M.nextIndex(2, 3, "none"), null);
  assert.equal(M.nextIndex(2, 3, "all"), 0);
  assert.equal(M.nextIndex(1, 3, "one"), 1);
  assert.equal(M.nextIndex(0, 0, "all"), null);
  assert.equal(M.prevIndex(2, 10), 2);
  assert.equal(M.prevIndex(2, 1), 1);
  assert.equal(M.prevIndex(0, 1), 0);
  assert.deepEqual(["all", "one", "none"].map(M.nextRepeat), ["one", "none", "all"]);
});

test("a shuffle keeps every track", () => {
  const list = [1, 2, 3, 4, 5];
  const out = M.shuffled(list, () => 0);
  assert.deepEqual([...out].sort(), list);
  assert.notDeepEqual(out, list);
  assert.deepEqual(list, [1, 2, 3, 4, 5]);
});

test("time and urls", () => {
  assert.equal(M.clock(187.6), "3:07");
  assert.equal(M.clock(NaN), "0:00");
  assert.equal(M.clock(-1), "0:00");
  assert.equal(M.trackUrl("F/S 1/a.mp3"), "/api/track?id=F%2FS%201%2Fa.mp3");
  assert.equal(M.artUrl(null), null);
  assert.equal(M.artUrl("F/c.jpg"), "/api/art?id=F%2Fc.jpg");
});

test("what is said of Brook's work", () => {
  const w = { brookSearching: (s) => `cherche ${s}`, brookDownloading: (s) => `télécharge ${s}`, brookNotFound: (s) => `rien pour ${s}`, brookNone: (s) => `rien encore pour ${s}`, brookError: (s) => `erreur ${s}` };
  assert.equal(M.brookSays({ state: "error" }, "OP", w), "erreur OP");
  assert.equal(M.brookSays({ state: "searching" }, "OP", w), "cherche OP");
  assert.equal(M.brookSays({ state: "downloading" }, "OP", w), "télécharge OP");
  assert.equal(M.brookSays({ state: "notfound" }, "OP", w), "rien pour OP");
  assert.equal(M.brookSays({ state: "none" }, "OP", w), "rien encore pour OP");
});

test("adding and taking a track out of an ambience", () => {
  assert.deepEqual(M.withTrack(["a"], "b", true), ["a", "b"]);
  assert.deepEqual(M.withTrack(["a"], "a", true), ["a"]);
  assert.deepEqual(M.withTrack(["a", "b"], "a", false), ["b"]);
});

const words = { music: "Musique", resumeMusic: "Reprendre", repeats: { all: "tout", one: "un", none: "non" } };
const amb = { key: "album:S1", kind: "album", art: null, tracks: [{ id: "a", title: "A" }, { id: "b", title: "B" }] };

test("what the pill says", () => {
  assert.deepEqual(M.pillLook(null, true, false, words), { state: "♪", text: "Musique", on: false, hidden: true });
  assert.equal(M.pillLook(null, true, true, words).hidden, false);
  const current = { tracks: amb.tracks, index: 1 };
  assert.deepEqual(M.pillLook(current, false, true, words), { state: "❚❚", text: "B", on: true, hidden: false });
  assert.deepEqual(M.pillLook(current, true, true, words), { state: "▶", text: "Reprendre · B", on: false, hidden: false });
});

test("where the music starts again", () => {
  assert.equal(M.resumePoint(null, [amb]), null);
  assert.equal(M.resumePoint({ key: "gone", index: 0 }, [amb]), null);
  assert.equal(M.resumePoint({ key: "album:S1", index: 5 }, [amb]), null);
  assert.deepEqual(M.resumePoint({ key: "album:S1", index: 1, time: 12, playing: 1 }, [amb]), { ambience: amb, index: 1, time: 12, playing: true });
  assert.equal(M.resumePoint({ key: "album:S1", index: 0 }, [amb]).time, 0);
});

test("the look of an ambience and of the repeat button", () => {
  assert.deepEqual(M.ambienceLook(amb, "album:S1"), { cls: "ambience on", art: null, sign: "♪" });
  assert.deepEqual(M.ambienceLook({ ...amb, kind: "mood", art: "x.jpg" }, null), { cls: "ambience", art: "/api/art?id=x.jpg", sign: "✦" });
  assert.equal(M.ambienceLook({ ...amb, kind: "all" }, null).sign, "⤨");
  assert.deepEqual(M.repeatLook("one", words), { sign: "🔂", off: false, title: "un" });
  assert.deepEqual(M.repeatLook("none", words), { sign: "🔁", off: true, title: "non" });
});
