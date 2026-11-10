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
const label = (p) => (p.run ? `${p.run[0]}-${p.run[1]}` : p.gap ? `gap${p.gap}` : p.vol.number || p.vol.id);

test("the places of a series: volumes, then gaps of the missing ones", () => {
  const s = { volumes: [vol(1), vol(2), vol(5), { id: "S/Artbook.cbz", number: null }], missing: [3, 4] };
  assert.deepEqual(R.places(s).map(label), [1, 2, "gap3", "gap4", 5, "S/Artbook.cbz"]);
  assert.deepEqual(R.places({ volumes: [vol(4)], missing: [1, 2, 3] }).map(label), ["gap1", "gap2", "gap3", 4]);
});

test("a long run of missing tomes stands as one place", () => {
  const s = { volumes: [vol(98), vol(100)], missing: [...Array.from({ length: 97 }, (_, i) => i + 1), 99] };
  assert.deepEqual(R.places(s).map(label), ["1-97", 98, "gap99", 100]);
});

test("the room a place takes", () => {
  assert.equal(R.width({ vol: vol(1) }, "S/T1.cbz"), R.FACE);
  assert.equal(R.width({ vol: vol(1) }, null), 1);
  assert.equal(R.width({ run: [1, 9] }, null), 2);
  assert.equal(R.width({ gap: 3 }, null), 1);
});

test("a long series takes as many bays as it needs", () => {
  const s = { name: "A", volumes: Array.from({ length: 100 }, (_, i) => vol(i + 1)), missing: [] };
  const bays = R.wall([s], null);
  assert.equal(bays.length, 3);
  assert.deepEqual(bays.map((b) => b.span), [[1, 36], [37, 72], [73, 100]]);
  assert.deepEqual(bays.map((b) => `${b.part + 1}/${b.parts}`), ["1/3", "2/3", "3/3"]);
  assert.deepEqual(bays[2].rows.map((r) => r.length), [12, 12, 4]);
});

test("the volume being read faces out and takes more room", () => {
  const s = { name: "A", volumes: Array.from({ length: 14 }, (_, i) => vol(i + 1)), missing: [] };
  const [bay] = R.wall([s], "S/T2.cbz");
  assert.deepEqual(bay.rows.map((r) => r.length), [8, 6, 0]);
  assert.equal(R.bayOf(R.wall([s], "S/T2.cbz"), "S/T2.cbz"), 0);
});

test("the wall: series one after the other", () => {
  const a = { name: "A", volumes: Array.from({ length: 40 }, (_, i) => vol(i + 1)), missing: [] };
  const b = { name: "B", volumes: [{ id: "B/T1.cbz", number: 1 }], missing: [] };
  const bays = R.wall([a, b], null);
  assert.deepEqual(bays.map((x) => [x.series.name, x.index, x.part]), [["A", 0, 0], ["A", 0, 1], ["B", 1, 0]]);
  assert.equal(R.bayOf(bays, "B/T1.cbz"), 2);
  assert.equal(R.bayOf(bays, "nowhere"), -1);
  assert.deepEqual(R.fill([], null), [[[], [], []]]);
  assert.equal(R.span([[], [], []]), null);
  assert.deepEqual(R.span([[{ vol: { id: "x", number: null } }]]), null);
});

test("a colour for every series", () => {
  assert.equal(R.colour("One Piece", "#e4ae5d"), "#e4ae5d");
  assert.match(R.colour("One Piece", null), /^hsl\(\d+, 38%, 38%\)$/);
  assert.equal(R.colour("Naruto"), R.colour("Naruto"));
});
