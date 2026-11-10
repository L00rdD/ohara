// The rotunda's geometry and what each bay holds: pure functions, tested in node.
// The library is the round wall inside the Tree of Knowledge: each series on as many
// bays as its tomes need, at least MIN_BAYS so that a small library still makes a room.
const Rotunda = (() => {
  const MIN_BAYS = 8;
  const ROWS = 3; // shelves in a bay
  const PER_ROW = 12; // volume slots on a shelf
  const FACE = 5; // slots taken by a volume shown face out (a 2:3 cover)

  const bayCount = (series) => Math.max(MIN_BAYS, series);
  const step = (count) => 360 / count;

  // the wall's radius for bays of width bw; curve (0 to 1) tightens the trunk
  function radius(bw, count, curve) {
    return bw / 2 / Math.tan((Math.PI / count) * (0.55 + curve / 2));
  }

  // the bay facing you for a rotation of rot degrees
  function front(rot, count) {
    return (((Math.round(-rot / step(count)) % count) + count) % count);
  }

  // the rotation that brings bay i to the front, the shortest way from rot
  function rotationFor(i, rot, count) {
    const target = -i * step(count);
    const turns = Math.round((rot - target) / 360);
    return target + turns * 360;
  }

  // how far bay i is from the front, in degrees (-180 to 180)
  function offset(i, rot, count) {
    return ((((i * step(count) + rot) % 360) + 540) % 360) - 180;
  }

  // how lit a bay is: full in the light, dim on the sides
  const lit = (deg, light = 1) => Math.max(0.22, 1 - Math.abs(deg) / 115) * (0.6 + light * 0.4);

  // only the bays you can see are drawn: within ±110° of the front
  const visible = (deg) => Math.abs(deg) <= 110;

  // The places of a series on the wall: its volumes and the missing ones, in tome
  // order. A place is {vol}, {gap: n}, or {run: [first, last]} for a long run of
  // missing tomes; volumes without a number come last.
  function places(series) {
    const all = [];
    const numbered = series.volumes.filter((v) => v.number);
    const missing = new Set(series.missing || []);
    let last = 0;
    for (const v of series.volumes) last = Math.max(last, v.number || 0);
    const byNumber = new Map(numbered.map((v) => [Math.floor(v.number), v]));
    const first = numbered.length ? Math.floor(Math.min(...numbered.map((v) => v.number))) : 1;
    for (let n = Math.min(first, missing.size ? Math.min(...missing) : first); n <= last; n++) {
      if (byNumber.has(n)) all.push({ vol: byNumber.get(n) });
      else if (missing.has(n)) all.push({ gap: n });
    }
    for (const v of series.volumes) if (!v.number) all.push({ vol: v });
    return squeeze(all);
  }

  // more than RUN missing tomes in a row stand as one empty place: {run: [first, last]}
  const RUN = 4;
  function squeeze(all) {
    const out = [];
    let gaps = [];
    const flush = () => {
      if (gaps.length > RUN) out.push({ run: [gaps[0].gap, gaps[gaps.length - 1].gap] });
      else out.push(...gaps);
      gaps = [];
    };
    for (const s of all) {
      if (s.gap) gaps.push(s);
      else {
        flush();
        out.push(s);
      }
    }
    flush();
    return out;
  }

  // the room a place takes on a shelf: a volume facing out FACE, a run 2, else 1
  const width = (place, readingId) => (place.vol && place.vol.id === readingId ? FACE : place.run ? 2 : 1);

  // splits places into bays of ROWS shelves of PER_ROW, in order: [[row, row, row], …]
  function fill(all, readingId) {
    const bays = [];
    let rows = null;
    let used = 0;
    for (const p of all) {
      const w = width(p, readingId);
      if (!rows || used + w > PER_ROW) {
        if (!rows || rows.length === ROWS) bays.push((rows = []));
        rows.push([]);
        used = 0;
      }
      rows[rows.length - 1].push(p);
      used += w;
    }
    for (const b of bays) while (b.length < ROWS) b.push([]);
    return bays.length ? bays : [[[], [], []]];
  }

  // the first and last tome on a bay's shelves
  function span(rows) {
    const ns = rows.flat().flatMap((p) => (p.run ? p.run : p.gap ? [p.gap] : p.vol.number ? [p.vol.number] : []));
    return ns.length ? [Math.min(...ns), Math.max(...ns)] : null;
  }

  // The wall: every series on as many bays as its tomes need, one after the other.
  // A bay is {series, index (of the series), part, parts, rows, span}.
  function wall(seriesList, readingId) {
    const out = [];
    seriesList.forEach((series, index) => {
      const bays = fill(places(series), readingId);
      bays.forEach((rows, part) => out.push({ series, index, part, parts: bays.length, rows, span: span(rows) }));
    });
    return out;
  }

  // the bay holding a volume, or -1
  const bayOf = (bays, id) => bays.findIndex((b) => b.rows.some((r) => r.some((p) => p.vol && p.vol.id === id)));

  // a spine's colour: AniList's colour of the series, or one made from its name
  function colour(name, color) {
    if (color) return color;
    let h = 0;
    for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h}, 38%, 38%)`;
  }

  return { MIN_BAYS, ROWS, PER_ROW, FACE, RUN, squeeze, bayCount, step, radius, front, rotationFor, offset, lit, visible, places, width, fill, span, wall, bayOf, colour };
})();

if (typeof module !== "undefined") module.exports = Rotunda;
