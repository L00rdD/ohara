// The rotunda's geometry and what each bay holds: pure functions, tested in node.
// The library is the round wall inside the Tree of Knowledge: one bay per series,
// at least MIN_BAYS so that a small library still makes a room.
const Rotunda = (() => {
  const MIN_BAYS = 8;
  const ROWS = 3; // shelves in a bay
  const PER_ROW = 12; // volume slots on a shelf
  const FACE = 3; // slots taken by a volume shown face out

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

  // The slots of a series' bay: its volumes and the gaps of the missing ones,
  // in tome order, as many as fit, around the volume being read (or from the
  // start). A slot is {vol} or {gap: n}; the volume being read stands face out.
  function slots(series, readingId) {
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
    return fit(squeeze(all), readingId);
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

  // keeps the slots that fit in a bay, the one being read in the window
  function fit(all, readingId) {
    const room = ROWS * PER_ROW;
    const width = (s) => (s.vol && s.vol.id === readingId ? FACE : s.run ? 2 : 1);
    let at = all.findIndex((s) => s.vol && s.vol.id === readingId);
    if (at < 0) at = 0;
    let start = Math.max(0, at - Math.floor(room / 3));
    let used = 0;
    let end = start;
    while (end < all.length && used + width(all[end]) <= room) used += width(all[end++]);
    while (start > 0 && used + width(all[start - 1]) <= room) used += width(all[--start]);
    return { shown: all.slice(start, end), before: start, after: all.length - end };
  }

  // splits the slots into shelves, a face-out volume taking FACE places
  function shelves(shown, readingId) {
    const rows = [[]];
    let used = 0;
    for (const s of shown) {
      const w = s.vol && s.vol.id === readingId ? FACE : s.run ? 2 : 1;
      if (used + w > PER_ROW && rows.length < ROWS) {
        rows.push([]);
        used = 0;
      }
      rows[rows.length - 1].push(s);
      used += w;
    }
    while (rows.length < ROWS) rows.push([]);
    return rows;
  }

  // a spine's colour: AniList's colour of the series, or one made from its name
  function colour(name, color) {
    if (color) return color;
    let h = 0;
    for (const c of name) h = (h * 31 + c.charCodeAt(0)) % 360;
    return `hsl(${h}, 38%, 38%)`;
  }

  return { MIN_BAYS, ROWS, PER_ROW, FACE, RUN, squeeze, bayCount, step, radius, front, rotationFor, offset, lit, visible, slots, fit, shelves, colour };
})();

if (typeof module !== "undefined") module.exports = Rotunda;
