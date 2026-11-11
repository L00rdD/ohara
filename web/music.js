// The music of the reader, its pure parts (tested in node): the ambiences of a
// series (your own, then its albums, then all of it shuffled), which track comes next,
// and how time reads. player.js plays them.
const Music = (() => {
  const REPEATS = ["all", "one", "none"];

  // the ambiences of a series' music: {key, name, kind, tracks: [{id, title}], art}
  function ambiences(music, allName) {
    const byId = new Map();
    for (const a of music.albums) for (const t of a.tracks) byId.set(t.id, t);
    const own = music.moods.map((m) => ({ key: "mood:" + m.name, name: m.name, kind: "mood", art: null, tracks: m.tracks.map((id) => byId.get(id)).filter(Boolean) }));
    const albums = music.albums.map((a) => ({ key: "album:" + a.name, name: a.name, kind: "album", art: a.art, tracks: a.tracks }));
    const all = byId.size > 1 ? [{ key: "all", name: allName, kind: "all", art: null, tracks: [...byId.values()] }] : [];
    return [...own.filter((m) => m.tracks.length), ...albums, ...all];
  }

  // the track after i in a list of n: the same one, the next, back to the first, or none
  function nextIndex(i, n, repeat) {
    if (repeat === "one") return i;
    if (i + 1 < n) return i + 1;
    return repeat === "all" && n ? 0 : null;
  }

  // the track before: back to the start of this one when it has played a few seconds
  const prevIndex = (i, seconds) => (seconds > 3 ? i : Math.max(0, i - 1));

  const nextRepeat = (r) => REPEATS[(REPEATS.indexOf(r) + 1) % REPEATS.length];

  // a copy of the list in a random order (Fisher-Yates)
  function shuffled(list, random = Math.random) {
    const out = [...list];
    for (let i = out.length - 1; i > 0; i--) {
      const j = Math.floor(random() * (i + 1));
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }

  function clock(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    const s = Math.floor(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  // what is said of Brook's work on a series' music, from its status
  function brookSays(status, series, words) {
    const say = { searching: words.brookSearching, downloading: words.brookDownloading, notfound: words.brookNotFound, error: words.brookError }[status.state];
    return say ? say(series) : words.brookNone(series);
  }

  const trackUrl = (id) => "/api/track?id=" + encodeURIComponent(id);
  const artUrl = (id) => (id ? "/api/art?id=" + encodeURIComponent(id) : null);

  // the ambience's tracks with another one added (or taken out), for a mood
  function withTrack(ids, id, add) {
    return add ? (ids.includes(id) ? ids : [...ids, id]) : ids.filter((x) => x !== id);
  }

  // what the ♪ pill says: the track, a way back when it stopped, or just "music"
  function pillLook(current, paused, hasMusic, words) {
    if (!current) return { state: "♪", text: words.music, on: false, hidden: !hasMusic };
    const title = current.tracks[current.index].title;
    return { state: paused ? "▶" : "❚❚", text: paused ? `${words.resumeMusic} · ${title}` : title, on: !paused, hidden: false };
  }

  // where to start again in a series: the ambience and track kept, when they still exist
  function resumePoint(saved, list) {
    const ambience = saved && list.find((a) => a.key === saved.key);
    if (!ambience || !ambience.tracks[saved.index]) return null;
    return { ambience, index: saved.index, time: saved.time || 0, playing: Boolean(saved.playing) };
  }

  // an ambience's button: chosen or not, its cover or a sign of its kind
  function ambienceLook(a, currentKey) {
    return { cls: a.key === currentKey ? "ambience on" : "ambience", art: artUrl(a.art), sign: { mood: "✦", all: "⤨" }[a.kind] || "♪" };
  }

  // the repeat button: its sign, whether it is off, and what it says
  const repeatLook = (repeat, words) => ({ sign: repeat === "one" ? "🔂" : "🔁", off: repeat === "none", title: words.repeats[repeat] });

  return { REPEATS, pillLook, resumePoint, ambienceLook, repeatLook, ambiences, nextIndex, prevIndex, nextRepeat, shuffled, clock, brookSays, trackUrl, artUrl, withTrack };
})();

if (typeof module !== "undefined") module.exports = Music;
