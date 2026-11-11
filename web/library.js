// Ohara's library page: the rotunda inside the Tree of Knowledge (one bay per series),
// the lectern with the volume being read, the lantern of the downloads, a series'
// sheet, the catalogue drawer of the search and the settings. Words and looks come
// from words.js, the rotunda's geometry from rotunda.js.
const Ohara = (() => {
  const W = () => I18n.words();
  const { size, tomes, describe, readingState, eta, downloadState, spans, tomesWord, completeText, seriesFacts, nextToRead, readLabel, openUrl, lanternLevel, spineLook, lecternState, lecternPages, plaqueText, selectionText, lanternFill, tileLook, moteStep, keyAction, indexerNotes, coverUrl, pageUrl, volumeName, contents, spineDraw, downloadName } = Words;

  // ---- the page ----
  const R = Rotunda;
  const { $, el, button, bar, api } = UI;


  let lib = { series: [], downloads: [], last: null };
  let rot = 0;
  let turnedOnce = false;

  // ---- words on the page ----
  function words() {
    for (const e of document.querySelectorAll("[data-w]")) e.textContent = W()[e.dataset.w];
    $("flag").textContent = I18n.get() === "fr" ? "🇫🇷" : "🇬🇧";
    $("flag").title = I18n.get() === "fr" ? "English" : "Français";
    $("open-settings").title = W().settings;
    $("open-contents").title = W().contentsHint;
    $("turn-left").title = W().turnLeft;
    $("turn-right").title = W().turnRight;
    $("search-form").q.placeholder = W().search;
  }

  // ---- the rotunda ----
  // three sizes of screen: phone, tablet, computer
  function bySize(phone, tablet, computer) {
    return (innerWidth >= 900 ? computer : innerWidth >= 500 ? tablet : phone);
  }

  // the wall of bays: every series on as many bays as its tomes need
  let wall = [];
  const readingId = () => (lib.last ? lib.last.id : null);

  function geometry() {
    const bw = bySize(220, 260, 300);
    const count = R.bayCount(wall.length);
    return { bw, count, r: R.radius(bw, count, 0.8), persp: bySize(420, 700, 700) };
  }

  // ---- what is selected on a shelf, said under the lectern ----
  // With a mouse, hovering selects and a click opens; on a touch screen the first
  // touch selects and the second opens.
  function selection() {
    let pointer = "mouse";
    let selected = null;
    function select(key, place, series) {
      selected = key;
      const text = selectionText(place, series);
      $("selection").querySelector("b").textContent = text.title;
      $("selection").querySelector("small").textContent = pointer === "mouse" ? text.state : `${text.state} · ${W().tapAgain}`;
      $("selection").hidden = false;
    }
    function unselect(key) {
      if (selected !== key) return;
      selected = null;
      $("selection").hidden = true;
    }
    // wires a place on a shelf: hover or first touch selects, then open()
    function selectable(node, key, place, series, open) {
      node.onpointerenter = (e) => e.pointerType === "mouse" && select(key, place, series);
      node.onpointerleave = (e) => e.pointerType === "mouse" && unselect(key);
      node.onclick = (e) => {
        e.stopPropagation();
        if (pointer !== "mouse" && selected !== key) return select(key, place, series);
        open();
      };
      return node;
    }
    addEventListener("pointerdown", (e) => (pointer = e.pointerType), true);
    return selectable;
  }
  const selectable = selection();

  // a spine in the style chosen in the settings (see ohara.css: .vol[data-style])
  let spineStyle = "tome";
  function spine(v, s, reading) {
    const d = spineDraw(v, s, reading, R.colour(s.name, s.meta.color));
    const b = selectable(el("button", d.cls), v.id, { vol: v }, s, () => (location.href = openUrl(v)));
    b.type = "button";
    b.dataset.style = spineStyle;
    b.setAttribute("aria-label", `${s.name}, ${volumeName(v)} (${readingState(v)})`);
    for (const [k, value] of Object.entries(d.vars)) b.style.setProperty(k, value);
    const art = el("span", "art");
    b.style.backgroundImage = d.cover ? `url("${d.cover}")` : "";
    b.style.height = d.height || "";
    art.style.backgroundImage = d.art ? `url("${d.art}")` : "";
    b.append(art, el("span", "vt", s.name), el("span", "vn", d.number));
    return b;
  }


  // an empty place on a shelf: a missing tome, or a run of them
  function hole(place, s, i) {
    const cls = place.run ? "gap run" : "gap";
    const node = selectable(el("button", cls, place.run ? `${place.run[0]}–${place.run[1]}` : ""), `${s.name}#${place.run || place.gap}`, place, s, () => openSeries(s, i));
    node.type = "button";
    return node;
  }

  function bay(b, i, g) {
    const deg = R.offset(i, rot, g.count);
    const node = el("div", "bay");
    node.style.setProperty("--a", `${R.angle(i, g.count)}deg`);
    const inner = el("div", "bay-in");
    inner.style.setProperty("--lit", R.lit(deg, 0.6).toFixed(2));
    node.append(inner);
    inner.append(el("span", "lamp"));
    if (!b) {
      inner.append(el("span", "plaque blank", "·"), el("div", "ledge"), el("div", "ledge"), el("div", "ledge"));
      return node;
    }
    // the series' own decor: its AniList banner on the back of the bay, its colour on the plaque
    if (b.series.meta.banner) {
      inner.classList.add("decor");
      inner.style.setProperty("--banner", `url("${b.series.meta.banner}")`);
    }
    inner.style.setProperty("--tint", R.colour(b.series.name, b.series.meta.color));
    const text = plaqueText(b);
    const plaque = button(text.title, "plaque", () => openSeries(b.series, i));
    plaque.append(el("small", "", text.sub));
    inner.append(plaque);
    for (const row of b.rows) {
      const ledge = el("div", "ledge");
      ledge.append(...row.map((p) => (p.vol ? spine(p.vol, b.series, readingId()) : hole(p, b.series, i))));
      inner.append(ledge);
    }
    inner.onclick = () => openSeries(b.series, i);
    return node;
  }

  function drawRotunda() {
    const g = geometry();
    const rotunda = $("rotunda");
    rotunda.style.setProperty("--persp", g.persp + "px");
    const drum = $("drum");
    drum.style.setProperty("--bw", g.bw + "px");
    drum.style.setProperty("--r", g.r.toFixed(0) + "px");
    drum.style.setProperty("--pull", (g.r * 0.96).toFixed(0) + "px");
    drum.style.setProperty("--below", lib.last ? bySize("290px", "320px", "330px") : "120px");
    drum.style.setProperty("--rot", rot + "deg");
    const bays = [];
    for (let i = 0; i < g.count; i++) if (R.visible(R.offset(i, rot, g.count))) bays.push(bay(wall[i], i, g));
    drum.replaceChildren(...bays);
  }

  function turnTo(next) {
    rot = next;
    drawRotunda();
  }
  function turnBy(n) {
    return turnTo(rot + n * R.step(geometry().count));
  }

  function wireRotunda() {
    const rotunda = $("rotunda");
    let x0 = null;
    let r0 = 0;
    let moved = false;
    rotunda.onpointerdown = (e) => {
      x0 = e.clientX;
      r0 = rot;
      moved = false;
    };
    rotunda.onpointermove = (e) => {
      if (x0 === null || Math.abs(e.clientX - x0) < 6) return;
      if (!moved) {
        moved = true;
        rotunda.setPointerCapture(e.pointerId);
        rotunda.classList.add("dragging");
      }
      // dragging to the left brings the bays on the right to you
      rot = r0 - (e.clientX - x0) * 0.25;
      $("drum").style.setProperty("--rot", rot + "deg");
    };
    rotunda.onpointerup = () => {
      if (moved) {
        rotunda.classList.remove("dragging");
        const step = R.step(geometry().count);
        turnTo(Math.round(rot / step) * step);
      }
      x0 = null;
    };
    // a click at the end of a drag does not open anything
    rotunda.addEventListener("click", (e) => moved && e.stopPropagation(), true);
    let wheelAt = 0;
    rotunda.onwheel = (e) => {
      e.preventDefault();
      if (Date.now() - wheelAt < 250) return;
      wheelAt = Date.now();
      turnBy(Math.sign(e.deltaY || e.deltaX));
    };
    $("turn-left").onclick = () => turnBy(-1);
    $("turn-right").onclick = () => turnBy(1);
  }

  // ---- the lectern ----
  function drawLectern() {
    const box = $("lectern");
    const state = lecternState(lib.last, lib.series);
    box.style.setProperty("--lw", bySize(260, 320, 340) + "px");
    box.hidden = state === "hidden";
    if (state === "empty") drawInvitation(box);
    if (state === "reading") drawOpenBook(box, lib.last);
  }

  function drawInvitation(box) {
    const cap = el("span", "caption", W().emptyTitle);
    cap.append(el("small", "", W().emptyText));
    box.replaceChildren(cap, button(W().emptyAction, "action", Search.open), emptyBook(), el("span", "desk"), el("span", "stand"));
  }

  // the volume being read, open on the lectern at the two pages you left it at
  function drawOpenBook(box, v) {
    const cap = el("span", "caption");
    cap.append(el("b", "", v.series), document.createTextNode(", " + W().volume(v.number || v.label)), el("small", "", readingState(v)));
    const book = el("a", "book");
    book.href = openUrl(v);
    book.title = readLabel(v);
    for (const [side, url] of [["l", lecternPages(v)[0]], ["r", lecternPages(v)[1]]]) {
      const page = el("span", "page " + side);
      if (url) page.style.backgroundImage = `url("${url}")`;
      book.append(page);
    }
    book.append(el("span", "mark"));
    box.replaceChildren(cap, book, el("span", "desk"), el("span", "stand"));
  }

  function emptyBook() {
    const book = el("span", "book");
    book.append(el("span", "page l"), el("span", "page r"));
    return book;
  }

  // ---- the lantern ----
  function drawLantern() {
    const n = lib.downloads.length;
    const lantern = $("lantern");
    lantern.classList.toggle("off", !n);
    lantern.title = n ? W().lantern : W().lanternEmpty;
    $("lantern-count").textContent = n || "";
    $("lantern-fill").setAttribute("y", lanternFill(lib.downloads));
    $("lantern-flame").setAttribute("opacity", n ? 1 : 0.15);
    const rows = n ? lib.downloads.map(downloadRow) : [el("p", "", W().lanternEmpty)];
    $("download-list").replaceChildren(...rows);
  }

  function downloadRow(d) {
    const row = el("div", "dl");
    const stop = button(W().cancel, "", async () => {
      stop.disabled = true;
      await api("/api/cancel", { hash: d.hash });
      load();
    });
    const what = downloadName(d);
    row.append(el("b", "", what), el("span", d.state === "error" ? "stuck" : "", downloadState(d)), bar(d.pct), stop);
    return row;
  }

  // ---- a series' sheet ----
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
    if (["none", "notfound"].includes(m.status.state) && !tracks) acts.append(button(W().askBrook, "button", () => askBrook(s, box)));
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



  function openSeries(s, i) {
    const g = geometry();
    if (R.front(rot, g.count) !== i) return turnTo(R.rotationFor(i, rot, g.count));
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
    text.append(el("h2", "", s.name), facts, acts, gaps(s), musicBox(s));
    head.append(img, text);
    const grid = el("div", "tomes");
    grid.append(...s.volumes.map(tomeTile));
    sheet.replaceChildren(button("✕", "round close", () => closeSheet(sheet)), head, grid);
    sheet.hidden = false;
  }
  function closeSheet(sheet) {
    sheet.hidden = true;
    $("rotunda").focus();
  }



  // ---- the contents: every series, A to Z, to go to its bay ----
  function openContents() {
    const box = $("contents");
    if (!box.hidden) return (box.hidden = true);
    const list = contents(wall).map(({ series, bay }) => {
      const row = button("", "entry", () => {
        box.hidden = true;
        turnTo(R.rotationFor(bay, rot, geometry().count));
      });
      const dot = el("span", "dot");
      dot.style.background = R.colour(series.name, series.meta.color);
      row.append(dot, el("b", "", series.name), el("small", "", W().volumes(series.volumes.length)));
      return row;
    });
    box.replaceChildren(el("h4", "", W().contents), ...list);
    box.hidden = false;
  }


  function setLanguage(code) {
    I18n.set(code);
    words();
    draw();
  }

  // ---- dust in the light of the canopy ----
  function motes() {
    const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const c = $("motes");
    const w = (c.width = innerWidth);
    const h = (c.height = innerHeight);
    const g = c.getContext("2d");
    const ps = Array.from({ length: 40 }, () => ({ x: w / 2 + (Math.random() - 0.5) * w * 0.7, y: Math.random() * h, r: Math.random() * 1.6 + 0.4, v: Math.random() * 0.25 + 0.05, p: Math.random() * 6.28 }));
    const frame = (t) => {
      g.clearRect(0, 0, w, h);
      for (const p of ps) {
        const inLight = moteStep(p, w, h, t);
        g.fillStyle = `rgba(255, 226, 170, ${(0.15 + 0.6 * inLight) * 0.6})`;
        g.beginPath();
        g.arc(p.x, p.y, p.r, 0, 6.29);
        g.fill();
      }
      if (!document.hidden) requestAnimationFrame(frame);
    };
    if (!still) requestAnimationFrame(frame);
    document.addEventListener("visibilitychange", () => !document.hidden && !still && requestAnimationFrame(frame));
  }

  // ---- loading ----
  function draw() {
    wall = R.wall(lib.series, readingId());
    if (!turnedOnce && lib.last) {
      // the rotunda opens facing the bay of the volume being read
      const i = R.bayOf(wall, lib.last.id);
      if (i >= 0) rot = R.rotationFor(i, 0, R.bayCount(wall.length));
      turnedOnce = true;
    }
    drawRotunda();
    drawLectern();
    drawLantern();
  }

  let timer = null;
  async function load() {
    try {
      lib = await api("/api/library");
    } catch {
      return;
    }
    draw();
    clearTimeout(timer);
    timer = setTimeout(load, lib.downloads.length ? 5000 : 60000);
  }

  function keys(e) {
    const action = keyAction(e.key, Boolean(e.target.closest("input, textarea")));
    if (!action || (action === "open" && e.target !== $("rotunda"))) return;
    e.preventDefault();
    const front = wall[R.front(rot, geometry().count)];
    const actions = {
      close: closeAll,
      left: () => turnBy(-1),
      right: () => turnBy(1),
      search: Search.open,
      open: () => front && openSeries(front.series, R.front(rot, geometry().count)),
    };
    actions[action]();
  }

  function closeAll() {
    for (const id of ["series", "settings", "search", "downloads", "contents"]) $(id).hidden = true;
    $("lantern").setAttribute("aria-expanded", "false");
  }

  function start() {
    words();
    wireRotunda();
    $("open-search").onclick = Search.open;
    $("flag").onclick = () => setLanguage(I18n.get() === "fr" ? "en" : "fr");
    $("open-settings").onclick = Settings.open;
    Settings.init({ spineStyle: () => spineStyle, setSpineStyle: (style) => ((spineStyle = style), drawRotunda()), setLanguage, closeSheet });
    Search.init({ series: () => lib.series, reload: load });
    $("open-contents").onclick = openContents;
    api("/api/settings").then((st) => {
      spineStyle = st.spines;
      drawRotunda();
    }, () => {});
    $("lantern").onclick = () => {
      const open = $("downloads").hidden;
      $("downloads").hidden = !open;
      $("lantern").setAttribute("aria-expanded", String(open));
    };
    addEventListener("keydown", keys);
    addEventListener("resize", draw);
    motes();
    load();
  }

  return { start };
})();

Ohara.start();
