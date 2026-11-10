// Tests of the rotunda's geometry and bays (web/rotunda.js)
const test = require("node:test");
const assert = require("node:assert");
const R = require("../web/rotunda.js");

test("a small library still makes a room", () => {
  assert.equal(R.bayCount(3), 8);
  assert.equal(R.bayCount(20), 20);
  assert.equal(R.step(8), 45);
});

test("a tighter trunk has a smaller radius", () => {
  assert.ok(R.radius(300, 10, 1) < R.radius(300, 10, 0));
  assert.ok(R.radius(300, 20, 0.5) > R.radius(300, 10, 0.5));
});

test("the bay facing you", () => {
  assert.equal(R.front(0, 8), 0);
  assert.equal(R.front(-45, 8), 1);
  assert.equal(R.front(45, 8), 7);
  assert.equal(R.front(-360 - 90, 8), 2);
});

test("turning to a bay the short way", () => {
  assert.equal(R.rotationFor(1, 0, 8), -45);
  assert.equal(R.rotationFor(7, 0, 8), -315 + 360);
  assert.equal(R.rotationFor(2, -720, 8), -810);
  assert.equal(R.front(R.rotationFor(5, 1234, 8), 8), 5);
});

test("how far a bay is from the front, and how lit", () => {
  assert.equal(R.offset(0, 0, 8), 0);
  assert.equal(R.offset(1, 0, 8), 45);
  assert.equal(R.offset(7, 0, 8), -45);
  assert.equal(R.offset(4, 0, 8), -180);
  assert.equal(R.lit(0, 1), 1);
  assert.ok(R.lit(90, 1) < R.lit(30, 1));
  assert.equal(R.lit(180, 0), 0.22 * 0.6);
  assert.equal(R.visible(100), true);
  assert.equal(R.visible(-150), false);
});

const vol = (n, extra = {}) => ({ id: `S/T${n}.cbz`, number: n, ...extra });

test("a bay holds the volumes and the gaps of the missing ones", () => {
  const s = { volumes: [vol(1), vol(2), vol(5), { id: "S/Artbook.cbz", number: null }], missing: [3, 4] };
  const { shown, before, after } = R.slots(s, null);
  assert.deepEqual(shown.map((x) => x.vol ? x.vol.id : `gap${x.gap}`), ["S/T1.cbz", "S/T2.cbz", "gap3", "gap4", "S/T5.cbz", "S/Artbook.cbz"]);
  assert.equal(before + after, 0);
});

test("missing tomes before the first owned are shown too", () => {
  const s = { volumes: [vol(4)], missing: [1, 2, 3] };
  assert.deepEqual(R.slots(s, null).shown.map((x) => x.gap || x.vol.number), [1, 2, 3, 4]);
});

test("a long run of missing tomes stands as one place", () => {
  const s = { volumes: [vol(98), vol(100)], missing: [...Array.from({ length: 97 }, (_, i) => i + 1), 99] };
  const { shown } = R.slots(s, "S/T98.cbz");
  assert.deepEqual(shown.map((x) => (x.run ? `${x.run[0]}-${x.run[1]}` : x.gap ? `gap${x.gap}` : x.vol.number)), ["1-97", 98, "gap99", 100]);
  assert.deepEqual(R.shelves(shown, "S/T98.cbz").map((r) => r.length), [4, 0, 0]);
});

test("a long series shows a window around the volume being read", () => {
  const vols = Array.from({ length: 100 }, (_, i) => vol(i + 1));
  const { shown, before, after } = R.slots({ volumes: vols, missing: [] }, "S/T60.cbz");
  assert.equal(shown.length, 36 - 4);
  assert.ok(shown.some((x) => x.vol.id === "S/T60.cbz"));
  assert.equal(before + shown.length + after, 100);
  assert.ok(before > 40);
  const atEnd = R.slots({ volumes: vols, missing: [] }, "S/T100.cbz");
  assert.equal(atEnd.after, 0);
  assert.equal(atEnd.shown.length, 32);
  const fromStart = R.slots({ volumes: vols, missing: [] }, null);
  assert.equal(fromStart.before, 0);
});

test("shelves: twelve places each, the face-out volume taking five", () => {
  const shown = Array.from({ length: 14 }, (_, i) => ({ vol: vol(i + 1) }));
  const rows = R.shelves(shown, "S/T2.cbz");
  assert.deepEqual(rows.map((r) => r.length), [8, 6, 0]);
  assert.deepEqual(R.shelves([], null).map((r) => r.length), [0, 0, 0]);
  const many = Array.from({ length: 40 }, (_, i) => ({ vol: vol(i + 1) }));
  assert.equal(R.shelves(many, null)[2].length, 16);
});

test("a colour for every series", () => {
  assert.equal(R.colour("One Piece", "#e4ae5d"), "#e4ae5d");
  assert.match(R.colour("One Piece", null), /^hsl\(\d+, 38%, 38%\)$/);
  assert.equal(R.colour("Naruto"), R.colour("Naruto"));
});
