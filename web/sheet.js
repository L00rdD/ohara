// A series' sheet: its cover and facts, how much of it is read, the button to read
// on, following, the missing tomes, its music (Brook), and every volume with what
// can be done with its reading (mark read, read up to here, back to unread), and the
// back of its shelves.
const Sheet = (() => {
  const { $, el, button, bar, api } = UI;
  const W = () => I18n.words();
  const { tomes, describe, readingState, tomesWord, completeText, seriesFacts, nextToRead, readLabel, openUrl, coverUrl, volumeName, tileLook, readCounts, upTo, decorUrl, decorChoices, decorName } = Words;
  let ctx = { reload: () => {}, closeSheet: () => {} };
  let shown = null; // the name of the series on the sheet

  function load() {
    ctx.reload();
  }

  function tomeTile(v) {
    const look = tileLook(v);
    const a = el("a", look.cls);
    a.href = openUrl(v);
    const cv = el("span", "cv");
    if (look.cover) cv.style.backgroundImage = `url("${coverUrl(v.id)}")`;
    if (look.bar !== null) cv.append(bar(look.bar));
    a.append(cv, el("b", "", volumeName(v)), el("small", look.state, readingState(v)));
    return a;
  }

  function followSwitch(s) {
    const sw = el("button", "switch");
    sw.type = "button";
    sw.setAttribute("role", "switch");
    sw.setAttribute("aria-checked", String(s.follow));
    sw.title = W().followHint;
    sw.append(el("span", "knob"), el("span", "", W().followSeries));
    sw.onclick = async () => {
      s.follow = !s.follow;
      sw.setAttribute("aria-checked", String(s.follow));
      await api("/api/follow", { series: s.name, follow: s.follow });
      load();
    };
    return sw;
  }

  function gaps(s) {
    const box = el("div");
    if (s.coming && s.coming.length) box.append(el("p", "note", W().coming(tomesWord(s.coming))));
    if (!s.missing.length) return box;
    box.append(el("p", "note", W().missing(tomesWord(s.missing))));
    const get = button(W().fetchMissing, "button", async () => {
      get.disabled = true;
      get.textContent = W().fetching;
      try {
        get.replaceWith(el("p", "done-note", completeText(await api("/api/complete", { series: s.name }))));
        load();
      } catch (err) {
        get.disabled = false;
        get.textContent = W().fetchMissing;
        box.append(el("p", "error", err.message));
      }
    });
    box.append(get);
    return box;
  }

  // a series' music on its sheet: what Brook did, and a way to ask him or pick another
  function musicBox(s) {
    const box = el("div", "music-box");
    api("/api/music?series=" + encodeURIComponent(s.name)).then((m) => drawMusic(box, s, m), () => {});
    return box;
  }

  function drawMusic(box, s, m) {
    const tracks = m.albums.reduce((n, a) => n + a.tracks.length, 0);
    const said = tracks ? `♪ ${m.albums.length} ${W().albumsTitle.toLowerCase()}, ${W().trackCount(tracks)}` : Music.brookSays(m.status, s.name, W());
    const acts = el("div", "actions");
    if (["none", "notfound", "error"].includes(m.status.state) && !tracks) acts.append(button(W().askBrook, "button", () => askBrook(s, box)));
    acts.append(button(W().otherSoundtrack, "button", () => soundtracks(s, box)));
    box.replaceChildren(el("p", "note", said), acts);
  }

  async function askBrook(s, box) {
    box.replaceChildren(el("p", "note", Music.brookSays({ state: "searching" }, s.name, W())));
    const status = await api("/api/music", { series: s.name });
    box.replaceChildren(el("p", "note", Music.brookSays(status, s.name, W())));
    load();
  }

  // the soundtracks the indexers have for a series, to pick one
  async function soundtracks(s, box) {
    box.replaceChildren(el("p", "note", Music.brookSays({ state: "searching" }, s.name, W())));
    const found = await api("/api/soundtracks?series=" + encodeURIComponent(s.name)).catch(() => []);
    const list = el("ul", "picks");
    list.append(...found.slice(0, 8).map((r) => soundtrackRow(s, box, r)));
    box.replaceChildren(found.length ? list : el("p", "note", Music.brookSays({ state: "notfound" }, s.name, W())));
  }

  function soundtrackRow(s, box, r) {
    const li = el("li");
    const text = el("div");
    text.append(el("span", "", r.title), el("small", "", describe(r)));
    li.append(text, button(W().get, "button", () => pickSoundtrack(s, box, r)));
    return li;
  }

  async function pickSoundtrack(s, box, r) {
    await api("/api/music", { series: s.name, token: r.token });
    box.replaceChildren(el("p", "done-note", Music.brookSays({ state: "downloading" }, s.name, W())));
    load();
  }


  // ---- the reading of the volumes ----
  async function mark(vols, read) {
    await api("/api/read", { vols, read });
    load();
  }

  // a button that asks to be touched twice before it does something that cannot be undone
  function twice(text, action) {
    const b = button(text, "button", () => {
      if (b.dataset.armed) return action();
      b.dataset.armed = "1";
      b.textContent = W().sure;
      setTimeout(() => {
        delete b.dataset.armed;
        b.textContent = text;
      }, 3000);
    });
    return b;
  }

  function progress(s) {
    const c = readCounts(s);
    const box = el("div", "reading");
    box.append(el("p", "note", W().progressLine(c.done, c.started, c.unread)), bar((c.done / c.total) * 100));
    const acts = el("div", "actions");
    const ids = s.volumes.map((v) => v.id);
    if (c.unread || c.started) acts.append(twice(W().allRead, () => mark(ids, true)));
    if (c.done || c.started) acts.append(twice(W().allUnread, () => mark(ids, false)));
    box.append(acts);
    return box;
  }

  // ---- the back of the shelves ----
  async function setDecor(s, decor) {
    await api("/api/decor", { series: s.name, decor });
    load();
  }

  function decorSwatch(s, decor) {
    const b = button("", "decor-pick", () => setDecor(s, decor));
    b.setAttribute("aria-pressed", String((s.decor || "banner") === decor));
    const look = el("span", "swatch");
    const url = decorUrl(s, decor);
    if (url) look.style.backgroundImage = `url("${url}")`;
    b.append(look, el("small", "", decorName(s, decor)));
    return b;
  }

  // the decors to pick from, and a link to an image of one's own
  function decorBox(s) {
    const box = el("div", "decor-box");
    const picks = el("div", "decor-picks");
    picks.append(...decorChoices(s).map((d) => decorSwatch(s, d)));
    const link = el("form", "decor-link");
    const input = el("input");
    input.type = "url";
    input.required = true;
    input.placeholder = W().decorLinkHint;
    const ok = button(W().ok, "button", null);
    ok.type = "submit";
    link.append(input, ok);
    link.onsubmit = (e) => {
      e.preventDefault();
      setDecor(s, "url:" + input.value.trim()).catch((err) => link.append(el("p", "error", err.message)));
    };
    link.hidden = true;
    const more = button(W().decorLink, "button", () => {
      more.hidden = true;
      link.hidden = false;
      input.focus();
    });
    box.append(el("h3", "", W().decorTitle), picks, more, link, el("p", "note", W().decorVolHint));
    return box;
  }

  // a volume with its ⋯ menu: mark read, read up to here, back to unread, its cover on
  // the back of the shelves
  function tomeWithMenu(v, s) {
    const wrap = el("div", "tome-wrap");
    const menu = el("div", "tome-menu");
    menu.hidden = true;
    if (!v.done) menu.append(button(W().markRead, "", () => mark([v.id], true)));
    menu.append(button(W().readUpTo, "", () => mark(upTo(s, v), true)));
    if (v.done || v.pages) menu.append(button(W().markUnread, "", () => mark([v.id], false)));
    menu.append(button(W().asDecor, "", () => setDecor(s, "vol:" + v.id)));
    const more = button("⋯", "tome-more", () => (menu.hidden = !menu.hidden));
    more.title = more.ariaLabel = W().volumeActions;
    wrap.append(tomeTile(v), more, menu);
    return wrap;
  }

  function draw(s) {
    const sheet = $("series");
    const v = nextToRead(s);
    const read = el("a", "button main", readLabel(v));
    read.href = openUrl(v);
    const head = el("div", "sheet-head");
    const img = el("img");
    img.alt = "";
    img.src = s.meta.cover || coverUrl(s.volumes[0].id);
    const text = el("div");
    const acts = el("div", "actions");
    acts.append(read, followSwitch(s));
    const facts = el("p", "facts");
    facts.append(...seriesFacts(s, s.meta).map((f) => el("span", "", f)));
    text.append(el("h2", "", s.name), facts, acts, progress(s), gaps(s), musicBox(s), decorBox(s));
    head.append(img, text);
    const grid = el("div", "tomes");
    grid.append(...s.volumes.map((x) => tomeWithMenu(x, s)));
    sheet.replaceChildren(button("✕", "round close", () => ((shown = null), ctx.closeSheet(sheet))), head, grid);
    sheet.hidden = false;
  }

  function open(s) {
    shown = s.name;
    draw(s);
  }

  // after the library reloads, the sheet shows the series as it is now
  function refresh(series) {
    if (!shown || $("series").hidden) return;
    const s = series.find((x) => x.name === shown);
    if (s) draw(s);
  }

  return { init: (context) => (ctx = context), open, refresh };
})();
