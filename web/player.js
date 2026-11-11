// The reader's ambient music: the music of the series being read, found by Brook.
// A ♪ pill opens the player: ambiences (yours, the albums, everything shuffled), the
// track playing, its controls, the tracks of the ambience (each can be added to one
// of your ambiences). The choice and the place in the track are kept per series, so
// the music carries on from one volume to the next, and the phone's lock screen
// controls it (Media Session).
const Player = (() => {
  const $ = (id) => document.getElementById(id);
  const W = () => I18n.words();
  const audio = new Audio();
  audio.preload = "metadata";
  let series = null;
  let music = { status: { state: "none" }, albums: [], moods: [] };
  let list = [];
  let current = null; // {key, tracks, index}
  let prefs = { volume: 0.6, repeat: "all" };

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function button(text, cls, onclick, title) {
    const b = el("button", cls, text);
    b.type = "button";
    b.onclick = onclick;
    if (title) b.title = b.ariaLabel = title;
    return b;
  }
  const api = async (path, body) => (await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {})).json();
  const key = () => "ohara-music:" + series;

  // ---- keeping the place, per series ----
  function remember() {
    if (!series || !current) return;
    localStorage.setItem(key(), JSON.stringify({ key: current.key, index: current.index, time: audio.currentTime, playing: !audio.paused }));
    localStorage.setItem("ohara-music-prefs", JSON.stringify(prefs));
  }
  function recall() {
    try {
      prefs = { ...prefs, ...JSON.parse(localStorage.getItem("ohara-music-prefs") || "{}") };
      return JSON.parse(localStorage.getItem(key()) || "null");
    } catch {
      return null;
    }
  }

  // ---- playing ----
  function play(ambience, index, at = 0) {
    const tracks = ambience.kind === "all" && (!current || current.key !== ambience.key) ? Music.shuffled(ambience.tracks) : ambience.tracks;
    current = { key: ambience.key, name: ambience.name, art: ambience.art, tracks, index };
    audio.src = Music.trackUrl(tracks[index].id);
    audio.currentTime = at;
    audio.volume = prefs.volume;
    audio.play().catch(() => drawPill());
    describe();
    draw();
  }
  function step(i) {
    if (i === null || !current) return audio.pause();
    current.index = i;
    audio.src = Music.trackUrl(current.tracks[i].id);
    audio.play().catch(() => {});
    describe();
    draw();
  }
  const forward = () => current && step(Music.nextIndex(current.index, current.tracks.length, prefs.repeat));
  const backward = () => current && step(Music.prevIndex(current.index, audio.currentTime));
  const toggle = () => (audio.paused ? audio.play().catch(() => {}) : audio.pause());

  // the lock screen of a phone shows and controls it
  function describe() {
    if (!("mediaSession" in navigator) || !current) return;
    const art = Music.artUrl(current.art);
    navigator.mediaSession.metadata = new MediaMetadata({ title: current.tracks[current.index].title, artist: series, album: current.name, artwork: art ? [{ src: art }] : [] });
  }
  function wireSession() {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.setActionHandler("play", toggle);
    navigator.mediaSession.setActionHandler("pause", toggle);
    navigator.mediaSession.setActionHandler("nexttrack", forward);
    navigator.mediaSession.setActionHandler("previoustrack", backward);
  }

  // ---- drawing ----
  function drawPill() {
    const pill = $("music-pill");
    const look = Music.pillLook(current, audio.paused, list.length > 0 || music.status.state !== "none", W());
    pill.querySelector(".state").textContent = look.state;
    pill.querySelector(".what").textContent = look.text;
    pill.classList.toggle("on", look.on);
    pill.hidden = look.hidden;
  }

  function nowPlaying() {
    const box = el("div", "now");
    if (!current) return box;
    const t = current.tracks[current.index];
    const seek = el("input", "seek");
    seek.type = "range";
    seek.min = 0;
    seek.max = Math.floor(audio.duration || 0);
    seek.value = Math.floor(audio.currentTime);
    seek.oninput = () => (audio.currentTime = +seek.value);
    const controls = el("div", "controls");
    controls.append(button("⏮", "btn", backward, W().previous), button(audio.paused ? "▶" : "❚❚", "btn main", toggle, W().playPause), button("⏭", "btn", forward, W().nextTrack),
      repeatButton());
    const volume = el("input", "volume");
    volume.type = "range";
    volume.min = 0;
    volume.max = 1;
    volume.step = 0.05;
    volume.value = prefs.volume;
    volume.title = W().volumeLabel;
    volume.oninput = () => {
      prefs.volume = audio.volume = +volume.value;
      remember();
    };
    controls.append(volume);
    box.append(el("b", "", t.title), el("small", "", `${current.name} · ${current.index + 1}/${current.tracks.length}`), seek, el("span", "time", `${Music.clock(audio.currentTime)} / ${Music.clock(audio.duration)}`), controls);
    return box;
  }

  function repeatButton() {
    const look = Music.repeatLook(prefs.repeat, W());
    return button(look.sign, look.off ? "btn off" : "btn", () => {
      prefs.repeat = Music.nextRepeat(prefs.repeat);
      remember();
      draw();
    }, look.title);
  }

  function ambienceButton(a) {
    const look = Music.ambienceLook(a, current && current.key);
    const b = button("", look.cls, () => play(a, 0), a.name);
    const art = el("span", "art", look.art ? "" : look.sign);
    art.style.backgroundImage = look.art ? `url("${look.art}")` : "";
    b.append(art, el("b", "", a.name), el("small", "", W().trackCount(a.tracks.length)));
    return b;
  }

  // the tracks of the ambience playing, each with a way into (or out of) your ambiences
  function trackList() {
    const ol = el("ol", "tracks");
    if (!current) return ol;
    const mood = current.key.startsWith("mood:") ? current.key.slice(5) : null;
    current.tracks.forEach((t, i) => {
      const li = el("li", i === current.index ? "on" : "");
      li.append(button(t.title, "track", () => step(i)));
      li.append(mood ? button("−", "mini", () => saveMood(mood, t.id, false), W().removeFromMood) : button("＋", "mini", () => moodForm(li, t), W().addToMood));
      ol.append(li);
    });
    return ol;
  }

  function moodForm(li, t) {
    const form = el("form", "mood-form");
    const name = el("input");
    name.required = true;
    name.placeholder = W().moodName;
    name.setAttribute("list", "mood-names");
    const names = el("datalist");
    names.id = "mood-names";
    names.append(...music.moods.map((m) => Object.assign(el("option"), { value: m.name })));
    form.append(name, names, button(W().add, "btn main", null));
    form.lastChild.type = "submit";
    form.onsubmit = (e) => {
      e.preventDefault();
      saveMood(name.value, t.id, true);
    };
    li.append(form);
    name.focus();
  }

  async function saveMood(name, id, add) {
    const mood = music.moods.find((m) => m.name === name);
    music = await api("/api/mood", { series, name, tracks: Music.withTrack(mood ? mood.tracks : [], id, add) });
    list = Music.ambiences(music, W().allShuffled);
    draw();
  }

  // when there is no music yet: what Brook is doing, and a way to ask him
  function brookBox() {
    const box = el("div", "brook");
    box.append(el("p", "", Music.brookSays(music.status, series, W())));
    if (["none", "notfound"].includes(music.status.state)) {
      box.append(button(W().askBrook, "btn main", async () => {
        music.status = await api("/api/music", { series });
        draw();
      }));
    }
    return box;
  }

  function draw() {
    drawPill();
    const panel = $("music-panel");
    if (panel.hidden) return;
    const head = el("header", "");
    head.append(el("h3", "", W().music), button("✕", "btn close", () => (panel.hidden = true)));
    panel.replaceChildren(head, ...(list.length ? playerBody() : [brookBox()]));
  }

  function playerBody() {
    const shelf = el("div", "ambiences");
    shelf.append(...list.map(ambienceButton));
    const body = [current ? nowPlaying() : el("p", "intro", W().musicIntro), shelf, trackList()];
    if (current) body.push(button(W().stopMusic, "btn stop", stop));
    return body;
  }

  function tick() {
    const seek = document.querySelector("#music-panel .seek");
    if (!seek) return;
    seek.max = Math.floor(audio.duration || 0);
    if (document.activeElement !== seek) seek.value = Math.floor(audio.currentTime);
    document.querySelector("#music-panel .time").textContent = `${Music.clock(audio.currentTime)} / ${Music.clock(audio.duration)}`;
  }

  function stop() {
    audio.pause();
    current = null;
    localStorage.removeItem(key());
    draw();
  }

  // ---- a series: its music, and where it was left ----
  async function open(name) {
    if (name === series) return;
    if (current) remember();
    audio.pause();
    series = name;
    current = null;
    music = await api("/api/music?series=" + encodeURIComponent(name));
    list = Music.ambiences(music, W().allShuffled);
    resume(Music.resumePoint(recall(), list));
    draw();
  }

  // the music of a series starts again where it was left
  function resume(point) {
    if (!point) return;
    const a = point.ambience;
    current = { key: a.key, name: a.name, art: a.art, tracks: a.tracks, index: point.index };
    audio.src = Music.trackUrl(a.tracks[point.index].id);
    audio.currentTime = point.time;
    audio.volume = prefs.volume;
    if (point.playing) audio.play().catch(() => drawPill());
    describe();
  }

  function start() {
    $("music-pill").onclick = () => {
      $("music-panel").hidden = !$("music-panel").hidden;
      draw();
    };
    audio.onended = forward;
    audio.onplay = audio.onpause = () => {
      remember();
      draw();
    };
    let lastDraw = 0;
    // only the time moves while a track plays: the panel is not drawn again
    audio.ontimeupdate = () => {
      if (Date.now() - lastDraw < 1000) return;
      lastDraw = Date.now();
      remember();
      tick();
    };
    audio.onloadedmetadata = tick;
    addEventListener("pagehide", remember);
    wireSession();
  }

  start();
  return { open };
})();
