// Ohara's library page: the rotunda inside the Tree of Knowledge (one bay per series),
// the lectern with the volume being read, the lantern of the downloads, a series'
// sheet, the catalogue drawer of the search and the settings. Words and looks come
// from words.js, the rotunda's geometry from rotunda.js.
const Ohara = (() => {
  const W = () => I18n.words();
  const { size, tomes, describe, readingState, eta, downloadState, spans, tomesWord, completeText, seriesFacts, nextToRead, readLabel, openUrl, lanternLevel, spineLook, lecternState, lecternPages, plaqueText, selectionText, lanternFill, tileLook, moteStep, keyAction, indexerNotes, coverUrl, pageUrl, volumeName } = Words;

  // ---- the page ----
  const R = Rotunda;
  const $ = (id) => document.getElementById(id);
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function button(text, cls, onclick) {
    const b = el("button", cls, text);
    b.type = "button";
    b.onclick = onclick;
    return b;
  }
  function bar(pct) {
    const b = el("span", "bar");
    b.append(el("i"));
    b.firstChild.style.width = Math.round(pct) + "%";
    return b;
  }
  const api = async (path, body) => {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    return data;
  };
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;

  let lib = { series: [], downloads: [], last: null };
  let rot = 0;
  let turnedOnce = false;

  // ---- words on the page ----
  function words() {
    for (const e of document.querySelectorAll("[data-w]")) e.textContent = W()[e.dataset.w];
    $("flag").textContent = I18n.get() === "fr" ? "🇫🇷" : "🇬🇧";
    $("flag").title = I18n.get() === "fr" ? "English" : "Français";
    $("open-settings").title = W().settings;
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

  function spine(v, s, reading) {
    const look = spineLook(v, s, reading);
    const b = selectable(el("button", look.cls), v.id, { vol: v }, s, () => (location.href = openUrl(v)));
    b.type = "button";
    b.setAttribute("aria-label", `${s.name}, ${volumeName(v)} (${readingState(v)})`);
    b.style.setProperty("--c", R.colour(s.name, s.meta.color));
    if (look.cover) b.style.backgroundImage = `url("${coverUrl(v.id)}")`;
    if (look.height) b.style.height = look.height + "%";
    b.append(el("span", "vt", s.name), el("span", "vn", v.number ? String(v.number) : ""));
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
    node.style.setProperty("--a", `${i * R.step(g.count)}deg`);
    const inner = el("div", "bay-in");
    inner.style.setProperty("--lit", R.lit(deg, 0.6).toFixed(2));
    node.append(inner);
    inner.append(el("span", "lamp"));
    if (!b) {
      inner.append(el("span", "plaque blank", "·"), el("div", "ledge"), el("div", "ledge"), el("div", "ledge"));
      return node;
    }
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
    return turnTo(rot - n * R.step(geometry().count));
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
      rot = r0 + (e.clientX - x0) * 0.25;
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
    box.replaceChildren(cap, button(W().emptyAction, "action", openSearch), emptyBook(), el("span", "desk"), el("span", "stand"));
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
    const what = d.range ? `${d.series}, ${tomes(d.range).toLowerCase()}` : d.series;
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
    text.append(el("h2", "", s.name), facts, acts, gaps(s));
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

  // ---- search: the catalogue drawer ----
  let found = [];
  let lastQuery = "";

  function openSearch() {
    $("search").hidden = false;
    $("search-form").q.focus();
  }

  async function getIt(r, g, follow, where) {
    const box = where.closest(".actions") || where.parentNode;
    where.disabled = true;
    try {
      await api("/api/grab", { token: r.token, series: g.name, follow, query: lastQuery });
      box.replaceWith(el("p", "done-note", follow ? W().sentFollow : W().sent));
      load();
    } catch (err) {
      where.disabled = false;
      box.append(el("p", "error", W().sendFailed(err.message)));
    }
  }

  function otherRow(r, g) {
    const li = el("li");
    const text = el("div");
    text.append(el("span", "", r.title), el("small", "", `${tomes(r.range)}, ${describe(r)}`));
    li.append(text, button(W().get, "button", (e) => getIt(r, g, false, e.target)));
    return li;
  }

  function card(g) {
    const best = g.releases[0];
    const c = el("article", "card");
    let pic = el("span", "blank", g.name.slice(0, 1));
    if (g.meta.cover) {
      pic = el("img");
      pic.src = g.meta.cover;
      pic.alt = "";
    }
    const body = el("div");
    const owned = lib.series.find((s) => s.name === g.name);
    const facts = el("p", "facts");
    facts.append(...seriesFacts(owned, g.meta).map((f) => el("span", "", f)));
    const pick = el("p", "pick");
    pick.append(el("strong", "", tomes(best.range)), document.createTextNode(" " + describe(best)));
    const follow = el("button", "switch");
    follow.type = "button";
    follow.setAttribute("role", "switch");
    follow.setAttribute("aria-checked", "true");
    follow.title = W().followHint;
    follow.append(el("span", "knob"), el("span", "", W().followSeries));
    follow.onclick = () => follow.setAttribute("aria-checked", String(follow.getAttribute("aria-checked") !== "true"));
    const acts = el("div", "actions");
    acts.append(button(owned ? W().complete : W().getAll, "button main", (e) => getIt(best, g, follow.getAttribute("aria-checked") === "true", e.target)), follow);
    body.append(el("h3", "", g.name), facts, pick, acts);
    if (g.releases.length > 1) {
      const more = el("details");
      more.append(el("summary", "", W().otherReleases(g.releases.length - 1)));
      const list = el("ul");
      list.append(...g.releases.slice(1).map((r) => otherRow(r, g)));
      more.append(list);
      body.append(more);
    }
    c.append(el("span", "stamp", best.lang), pic, body);
    return c;
  }

  function drawFinds() {
    const all = $("all-languages").checked;
    const shown = found.map((g) => ({ ...g, releases: g.releases.filter((r) => all || r.lang === "FR") })).filter((g) => g.releases.length);
    $("finds").replaceChildren(...shown.map(card));
    if (!shown.length && $("searching").hidden && lastQuery) $("finds").append(el("p", "empty-line", found.length ? W().noFrench : W().noResult));
  }

  async function runSearch(q) {
    lastQuery = q;
    $("search-title").textContent = W().searchTitle(q);
    $("searching").hidden = false;
    $("finds").replaceChildren();
    try {
      found = await api("/api/search?q=" + encodeURIComponent(q));
    } catch (err) {
      found = [];
      $("finds").append(el("p", "empty-line", W().searchFailed(err.message)));
    }
    $("searching").hidden = true;
    drawFinds();
  }

  // ---- settings ----
  async function openSettings() {
    const sheet = $("settings");
    const langs = el("div", "langs");
    for (const [code, label] of [["fr", "🇫🇷 Français"], ["en", "🇬🇧 English"]]) {
      const b = button(label, "button" + (I18n.get() === code ? " main" : ""), () => {
        setLanguage(code);
        openSettings();
      });
      langs.append(b);
    }
    const list = el("div", "", "…");
    sheet.replaceChildren(button("✕", "round close", () => closeSheet(sheet)), el("h2", "", W().settings), el("h3", "", W().language), langs,
      el("h3", "", W().indexers), el("p", "note", W().indexersHint), list);
    const add = el("a", "button", W().addIndexer);
    add.href = `http://${location.hostname}:9696/`;
    add.target = "_blank";
    add.rel = "noopener";
    sheet.append(add);
    sheet.hidden = false;
    try {
      drawIndexers(list, await api("/api/indexers"));
    } catch {
      list.replaceChildren(el("p", "error", W().indexersFailed));
    }
  }

  function drawIndexers(list, all) {
    list.replaceChildren(...all.map((ix) => {
      const row = el("label", "option");
      const box = el("input");
      box.type = "checkbox";
      box.checked = ix.chosen;
      box.onchange = async () => {
        const chosen = [...list.querySelectorAll("input")].filter((b) => b.checked).map((b) => b.dataset.name);
        drawIndexers(list, await api("/api/indexers", { indexers: chosen }));
      };
      box.dataset.name = ix.name;
      const notes = indexerNotes(ix);
      row.append(box, el("b", "", ix.name), el("small", notes.bad ? "bad" : "", notes.text));
      return row;
    }));
  }

  function setLanguage(code) {
    I18n.set(code);
    words();
    draw();
  }

  // ---- dust in the light of the canopy ----
  function motes() {
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
      search: openSearch,
      open: () => front && openSeries(front.series, R.front(rot, geometry().count)),
    };
    actions[action]();
  }

  function closeAll() {
    for (const id of ["series", "settings", "search", "downloads"]) $(id).hidden = true;
    $("lantern").setAttribute("aria-expanded", "false");
  }

  function start() {
    words();
    wireRotunda();
    $("open-search").onclick = openSearch;
    $("close-search").onclick = () => ($("search").hidden = true);
    $("search-form").onsubmit = (e) => {
      e.preventDefault();
      runSearch(e.target.q.value.trim());
    };
    $("all-languages").onchange = drawFinds;
    $("flag").onclick = () => setLanguage(I18n.get() === "fr" ? "en" : "fr");
    $("open-settings").onclick = openSettings;
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
