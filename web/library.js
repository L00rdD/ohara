// Ohara's library page: the rotunda inside the Tree of Knowledge (one bay per series),
// the lectern with the volume being read, the lantern of the downloads, a series'
// sheet, the catalogue drawer of the search and the settings. Words and looks come
// from words.js, the rotunda's geometry from rotunda.js.
const Ohara = (() => {
  const W = () => I18n.words();
  const { size, tomes, describe, readingState, eta, downloadState, spans, tomesWord, completeText, seriesFacts, nextToRead, readLabel, openUrl, lanternLevel, spineLook, lecternState, lecternPages, plaqueText, selectionText, lanternFill, tileLook, moteStep, keyAction, indexerNotes, coverUrl, pageUrl, volumeName, contents, spineDraw, downloadName, lecternVolume, selectionActions, decorUrl, readCounts } = Words;

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
    $("lectern-back").title = $("lectern-back").ariaLabel = W().lecternBack;
    $("open-ailments").title = W().ailmentsTitle;
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
  // With a mouse, hovering says what is under it. A click or a touch selects: the card
  // under the lectern then says what it is and what can be done with it (read it, mark
  // it read or unread, its series' sheet); a second one on the same place opens it, a
  // click anywhere else lets it go.
  function selection() {
    const card = $("selection");
    let pinned = null;
    function say(place, series) {
      const text = selectionText(place, series);
      card.querySelector("b").textContent = text.title;
      card.querySelector("small").textContent = text.state;
      card.hidden = false;
    }
    function pin(key, place, series, open) {
      pinned = key;
      say(place, series);
      card.querySelector(".picks-row").replaceChildren(...selectionActions(place).map((a) => pick(a, place, series, open)));
      card.classList.add("pinned");
    }
    function unpin() {
      pinned = null;
      card.classList.remove("pinned");
      card.hidden = true;
    }
    function pick(action, place, series, open) {
      const v = place.vol;
      const what = {
        open: [v && readLabel(v), "button main", open],
        markRead: [W().markRead, "button", () => markVolume(v, true)],
        markUnread: [W().markUnread, "button", () => markVolume(v, false)],
        sheet: [W().seriesSheet, "button", () => Sheet.open(series)],
      }[action];
      return button(what[0], what[1], () => {
        unpin();
        what[2]();
      });
    }
    // wires a place on a shelf: hover tells, a first click or touch selects, a second opens
    function selectable(node, key, place, series, open) {
      node.onpointerenter = (e) => e.pointerType === "mouse" && !pinned && say(place, series);
      node.onpointerleave = (e) => e.pointerType === "mouse" && !pinned && (card.hidden = true);
      node.onclick = (e) => {
        e.stopPropagation();
        if (pinned !== key) return pin(key, place, series, open);
        unpin();
        open();
      };
      return node;
    }
    document.addEventListener("click", (e) => pinned && !card.contains(e.target) && unpin());
    return selectable;
  }
  const selectable = selection();

  // a spine in the style chosen in the settings (see ohara.css: .vol[data-style])
  let spineStyle = "tome";
  let ribbon = true; // the bookmark ribbon on the lectern's book, unless taken off in the settings
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
    if (R.members(b).length > 1) sharedBay(b, i, inner);
    else ownBay(b, i, inner);
    return node;
  }

  // a series' own bay (or bays): its decor, its plaque, its tomes
  function ownBay(b, i, inner) {
    // the series' own decor: the image chosen on its sheet (its AniList banner by
    // default) on the back of the bay, its colour on the plaque
    const back = decorUrl(b.series);
    if (back) {
      inner.classList.add("decor");
      inner.style.setProperty("--banner", `url("${back}")`);
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
  }

  // a bay shared by small series: each on its own shelf, its name on a small plaque,
  // its decor behind it
  function sharedBay(b, i, inner) {
    inner.classList.add("shared");
    b.rows.forEach((row, r) => {
      const s = b.shelves[r];
      const ledge = el("div", "ledge");
      if (s) {
        const text = plaqueText({ series: s, part: 0, parts: 1 });
        const label = button(text.title, "shelf-plaque", () => openSeries(s, i));
        label.style.setProperty("--tint", R.colour(s.name, s.meta.color));
        label.append(el("small", "", text.sub));
        const back = decorUrl(s);
        if (back) {
          ledge.classList.add("decor");
          ledge.style.setProperty("--banner", `url("${back}")`);
        }
        ledge.append(label, ...row.map((p) => (p.vol ? spine(p.vol, s, readingId()) : hole(p, s, i))));
        ledge.onclick = () => openSeries(s, i);
      }
      inner.append(ledge);
    });
  }

  function drawRotunda() {
    const g = geometry();
    const rotunda = $("rotunda");
    rotunda.style.setProperty("--persp", g.persp + "px");
    const drum = $("drum");
    drum.style.setProperty("--bw", g.bw + "px");
    drum.style.setProperty("--r", g.r.toFixed(0) + "px");
    drum.style.setProperty("--pull", (g.r * 0.96).toFixed(0) + "px");
    drum.style.setProperty("--below", lecternRoom() + "px");
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
  // It can be put away (its ✕): a button in the corner brings it back, and so does
  // reading another volume.
  const away = () => localStorage.getItem("ohara-lectern-away");
  function drawLectern() {
    const box = $("lectern");
    const shown = lecternVolume(lib.last, lib.series);
    const state = lecternState(shown, lib.series, away());
    box.style.setProperty("--lw", bySize(200, 250, 270) + "px");
    box.hidden = state === "hidden" || state === "away";
    $("lectern-back").hidden = state !== "away";
    if (state === "empty") drawInvitation(box);
    if (state === "reading") drawOpenBook(box, shown);
  }

  // the room the shelves leave under them: the lectern's height, or a little
  function lecternRoom() {
    const box = $("lectern");
    return box.hidden ? 70 : box.offsetHeight + 36;
  }

  function setRibbon(on) {
    ribbon = on;
    drawLectern();
  }

  function putAway(v) {
    localStorage.setItem("ohara-lectern-away", v.id);
    drawLectern();
    drawRotunda();
  }
  function bringBack() {
    localStorage.removeItem("ohara-lectern-away");
    drawLectern();
    drawRotunda();
  }

  // a sheet (a series, the settings) closes with a touch outside it; the header's
  // buttons open their own things
  function closeOutside(e) {
    if (e.target.closest(".top, #selection, .sheet")) return;
    for (const id of ["series", "settings", "ailments"]) if (!$(id).hidden) closeSheet($(id));
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
    if (ribbon) book.append(el("span", "mark"));
    const shut = button("✕", "away", () => putAway(v));
    shut.title = shut.ariaLabel = W().lecternAway;
    box.replaceChildren(cap, book, shut, el("span", "desk"), el("span", "stand"));
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
    const acts = el("div", "dl-acts");
    // tomes that do not come: another release of them, the one given up not taken again
    if (d.kind !== "ost") {
      const other = button(W().anotherRelease, "", async () => {
        other.disabled = true;
        const r = await api("/api/another", { hash: d.hash }).catch((err) => ({ error: err.message }));
        other.replaceWith(el("small", "", r.error || (r.sent.length ? W().anotherSent(r.sent.length) : W().anotherNone)));
        load();
      });
      acts.append(other);
    }
    acts.append(stop);
    row.append(el("b", "", what), el("span", d.state === "error" ? "stuck" : "", downloadState(d)), bar(d.pct), acts);
    return row;
  }

  function openSeries(s, i) {
    const g = geometry();
    if (R.front(rot, g.count) !== i) return turnTo(R.rotationFor(i, rot, g.count));
    Sheet.open(s);
  }
  async function markVolume(v, read) {
    await api("/api/read", { vols: [v.id], read });
    load();
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
      row.append(dot, el("b", "", series.name), el("small", "", W().volumes(readCounts(series).total)));
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
    drawLectern();
    drawRotunda();
    drawLantern();
  }

  let timer = null;
  // The library as the page saw it last, kept in the browser: coming back from the
  // reader, the shelves are drawn at once from it, then from the server's answer.
  const KEPT = "ohara-library";
  let answered = false; // the server's library came: only it is kept
  function fromKept() {
    const kept = Words.keptLibrary(localStorage.getItem(KEPT));
    if (!kept) return; // nothing kept: the server's answer comes anyway
    lib = kept;
    spineStyle = kept.spineStyle || spineStyle;
    ribbon = kept.ribbon ?? ribbon;
    draw();
  }
  function keep() {
    if (!answered) return;
    try {
      localStorage.setItem(KEPT, JSON.stringify({ ...lib, spineStyle, ribbon }));
    } catch {
      // the browser's room is full: nothing kept, nothing lost
    }
  }

  async function load() {
    try {
      lib = await api("/api/library");
    } catch {
      return;
    }
    answered = true;
    keep();
    draw();
    Sheet.refresh(lib.series);
    Doctor.refresh();
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
    for (const id of ["series", "settings", "ailments", "search", "downloads", "contents"]) $(id).hidden = true;
    $("lantern").setAttribute("aria-expanded", "false");
  }

  function start() {
    words();
    wireRotunda();
    $("open-search").onclick = Search.open;
    $("flag").onclick = () => setLanguage(I18n.get() === "fr" ? "en" : "fr");
    $("open-settings").onclick = () => ($("settings").hidden ? Settings.open() : closeSheet($("settings")));
    $("lectern-back").onclick = bringBack;
    $("open-ailments").onclick = () => ($("ailments").hidden ? Doctor.open() : closeSheet($("ailments")));
    Doctor.init({ reload: load, closeSheet });
    addEventListener("pointerdown", closeOutside);
    Settings.init({ spineStyle: () => spineStyle, setSpineStyle: (style) => ((spineStyle = style), drawRotunda()), setRibbon, setLanguage, closeSheet });
    Search.init({ series: () => lib.series, reload: load });
    Sheet.init({ reload: load, closeSheet });
    $("open-contents").onclick = openContents;
    api("/api/settings").then((st) => {
      spineStyle = st.spines;
      ribbon = st.ribbon;
      keep();
      drawRotunda();
      drawLectern();
    }, () => {});
    $("lantern").onclick = () => {
      const open = $("downloads").hidden;
      $("downloads").hidden = !open;
      $("lantern").setAttribute("aria-expanded", String(open));
    };
    addEventListener("keydown", keys);
    addEventListener("resize", draw);
    motes();
    fromKept();
    load();
  }

  return { start };
})();

Ohara.start();
