// Ohara's reader: one volume, page by page or two pages side by side, left to right.
// A click on the right half turns to the next page, on the left half back to the
// previous one. The bars show with the corner button, and while the mouse moves unless
// the button in the bottom bar has turned that off.
// The page reached is saved on the server, so another device picks it up. Pages come
// at the width of the screen; once a volume opens, all its pages come in the
// background and stay in memory, so turning a page does not wait on the network. A
// page shows only once it is whole, the one before stays until then.
const Reader = (() => {
  // ---- pure page arithmetic (tested in node) ----

  // The pages shown together from page p: the cover alone, then pairs 1-2, 3-4…
  function spread(p, count, double) {
    if (!double || p === 0) return [p];
    const first = p % 2 === 1 ? p : p - 1;
    return first + 1 < count ? [first, first + 1] : [first];
  }

  // The first page after the spread holding p; count when it was the last
  function after(p, count, double) {
    const s = spread(p, count, double);
    return Math.min(s[s.length - 1] + 1, count);
  }

  function before(p, count, double) {
    const s = spread(p, count, double);
    return s[0] === 0 ? 0 : spread(s[0] - 1, count, double)[0];
  }

  // Where a click lands, from its place across the screen (0 to 1)
  const zone = (x) => (x < 0.5 ? "prev" : "next");

  // The width in pixels a page is shown at: the window's, half of it for two pages
  const pageWidth = (w, ratio, double) => Math.ceil((w * ratio) / (double ? 2 : 1));

  // The pages to have ready around p: two before, six after the spread shown
  function around(p, count, double) {
    const from = Math.max(0, spread(p, count, double)[0] - 2);
    const to = Math.min(count, after(p, count, double) + 6);
    return Array.from({ length: to - from }, (_, i) => from + i);
  }

  // The order a volume's pages are fetched in: from p to the end, then those before
  const wholeOrder = (p, count) => Array.from({ length: count }, (_, i) => (p + i) % count);

  // Whether to get the next volume ready: within the last ten pages
  const nearEnd = (p, count) => p >= count - 10;

  // Whether a pointer moving shows the bars: a mouse, when the bars follow it
  const peeks = (pointerType, follow) => follow === "on" && pointerType === "mouse";

  if (typeof document === "undefined") return { spread, after, before, zone, pageWidth, around, wholeOrder, nearEnd, peeks };

  // ---- the page ----
  const $ = (id) => document.getElementById(id);
  let vid = new URLSearchParams(location.search).get("vol");
  const pref = (key, fallback) => localStorage.getItem("ohara-" + key) || fallback;
  const settings = {
    double: pref("mode", innerWidth > innerHeight * 1.2 ? "double" : "single") === "double",
    fit: pref("fit", "height"),
    peek: pref("peek", "on"),
  };
  let info = null;
  let page = 0;
  let saveTimer = null;

  let width = 0;
  const pageUrl = (id, n) => `/api/page?vol=${encodeURIComponent(id)}&n=${n}&w=${width}`;

  // ---- the volume, kept in memory: every page fetched once, as an object URL ----
  let kept = new Map();
  let fetching = new AbortController();
  function fetchPage(n) {
    if (!kept.has(n)) {
      const map = kept;
      const got = fetch(pageUrl(vid, n), { signal: fetching.signal })
        .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(r.status))))
        .then((b) => URL.createObjectURL(b));
      got.catch(() => map.get(n) === got && map.delete(n)); // asked again when needed
      map.set(n, got);
    }
    return kept.get(n);
  }

  // all the pages of the volume, two at a time, from the page read on; the pages to
  // show go first, as they are asked for directly
  async function fetchAll() {
    const ctl = fetching;
    const order = wholeOrder(page, info.count);
    let i = 0;
    const one = async () => {
      while (i < order.length && fetching === ctl) await fetchPage(order[i++]).catch(() => {});
    };
    await Promise.all([one(), one()]);
  }

  // a new volume, or pages of another width: what was kept goes
  function forget() {
    fetching.abort();
    for (const got of kept.values()) got.then((url) => URL.revokeObjectURL(url), () => {});
    kept = new Map();
    fetching = new AbortController();
    ready = new Map();
    width = pageWidth(innerWidth, devicePixelRatio || 1, settings.double);
  }

  // the next volume, near the end of this one: the server makes its pages, and its
  // first ones wait in the browser's cache
  let readied = null;
  function readyNext() {
    if (!info.next || readied === info.next || !nearEnd(page, info.count)) return;
    readied = info.next;
    fetch(`/api/pages?vol=${encodeURIComponent(info.next)}&w=${width}`)
      .then(() => [0, 1, 2].forEach((n) => fetch(pageUrl(info.next, n)).catch(() => {})))
      .catch(() => {});
  }

  // the pages decoded, ready to show: those around the page read
  let ready = new Map();
  function image(n) {
    if (!ready.has(n)) {
      const img = Object.assign(new Image(), { alt: `Page ${n + 1}` });
      img.whole = fetchPage(n)
        .then((url) => {
          img.src = url;
          return img.decode();
        })
        .catch(() => {});
      ready.set(n, img);
    }
    return ready.get(n);
  }
  function getAhead() {
    const keep = new Set(around(page, info.count, settings.double));
    for (const n of ready.keys()) if (!keep.has(n)) ready.delete(n);
    for (const n of keep) image(n);
  }

  // the spread is shown once its pages are whole; meanwhile the one before stays, with
  // a thin line at the top when it takes a while
  let drawing = 0;
  async function draw() {
    const stage = $("stage");
    const turn = ++drawing;
    const shown = spread(page, info.count, settings.double);
    const imgs = shown.map(image);
    const slow = setTimeout(() => stage.classList.add("waiting"), 250);
    await Promise.all(imgs.map((i) => i.whole));
    clearTimeout(slow);
    if (turn !== drawing) return;
    stage.classList.remove("waiting");
    stage.dataset.fit = settings.fit;
    stage.replaceChildren(...imgs);
    stage.scrollTo(0, 0);
    getAhead();
    readyNext();
  }

  function say() {
    const shown = spread(page, info.count, settings.double);
    $("count").textContent = `${shown.map((n) => n + 1).join("-")} / ${info.count}`;
    $("slider").value = page + 1;
    const w = I18n.words();
    $("mode").textContent = settings.double ? w.twoPages : w.onePage;
    $("fit").textContent = settings.fit === "height" ? w.fitHeight : w.fitWidth;
    $("peek").textContent = settings.peek === "on" ? w.peekOn : w.peekOff;
  }

  function save(done) {
    clearTimeout(saveTimer);
    const at = done ? info.count - 1 : page;
    saveTimer = setTimeout(() => {
      fetch("/api/progress", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vol: vid, page: at, count: info.count }) });
    }, done ? 0 : 800);
  }

  function go(n) {
    $("end").hidden = true;
    page = Math.max(0, Math.min(n, info.count - 1));
    say();
    save();
    return draw();
  }

  function next() {
    const n = after(page, info.count, settings.double);
    if (n >= info.count) return end();
    go(n);
  }

  const prev = () => ($("end").hidden ? go(before(page, info.count, settings.double)) : go(page));

  function end() {
    save(true);
    const nv = $("next-volume");
    nv.hidden = !info.next;
    if (info.next) nv.href = "/read?vol=" + encodeURIComponent(info.next);
    $("end").hidden = false;
  }

  // "Tome 5", "Volume 5", "Chapter 5" in the interface's language, or the file's name
  function volumeTitle(v) {
    const w = I18n.words();
    if (!v.number) return v.label;
    const said = v.chapter ? w.chapters(v.number, v.number) : w.volume(v.number);
    return said.charAt(0).toUpperCase() + said.slice(1);
  }

  // a volume opens in the same page, so the music goes on from one volume to the next
  async function openVolume(id) {
    vid = id;
    forget();
    const r = await fetch(`/api/pages?vol=${encodeURIComponent(vid)}&w=${width}`);
    if (r.status === 401) return location.replace("/"); // who reads is asked in the library
    info = await r.json();
    document.title = `${info.series} · ${volumeTitle(info)}`;
    $("title").textContent = document.title;
    $("back").href = $("end-back").href = "/#" + encodeURIComponent(info.series);
    $("slider").max = info.count;
    if (typeof Player !== "undefined") Player.open(info.series);
    await go(info.page >= info.count - 1 ? 0 : info.page);
    fetchAll();
  }

  // the bars: shown by the corner button, or for a few seconds while the mouse moves
  // if they follow it
  let barsTimer = null;
  const toggleBars = () => document.body.classList.toggle("bars");
  function peekBars(e) {
    if (!peeks(e.pointerType, settings.peek)) return;
    document.body.classList.add("bars");
    clearTimeout(barsTimer);
    if (!e.target.closest(".bar")) barsTimer = setTimeout(() => document.body.classList.remove("bars"), 2500);
  }

  // whether the bars follow the mouse; they stay up while their own button is clicked
  function followMouse() {
    settings.peek = settings.peek === "on" ? "off" : "on";
    localStorage.setItem("ohara-peek", settings.peek);
    clearTimeout(barsTimer);
    say();
  }

  function setting(key, value) {
    settings[key] = value;
    localStorage.setItem("ohara-" + (key === "double" ? "mode" : key), key === "double" ? (value ? "double" : "single") : value);
    if (key !== "double") return go(page);
    forget();
    go(page).then(fetchAll);
  }

  function keys(e) {
    const k = { ArrowLeft: prev, ArrowRight: next, " ": next, PageDown: next, PageUp: prev, Escape: () => (location.href = $("back").href) }[e.key];
    if (!k) return;
    e.preventDefault();
    k();
  }

  async function start() {
    for (const e of document.querySelectorAll("[data-w]")) e.textContent = I18n.words()[e.dataset.w];
    document.documentElement.lang = I18n.get();
    $("menu").title = I18n.words().menu;
    $("next-volume").onclick = (e) => {
      e.preventDefault();
      history.replaceState(null, "", $("next-volume").href);
      openVolume(info.next);
    };
    $("slider").oninput = (e) => go(+e.target.value - 1);
    $("stage").onclick = (e) => (zone(e.clientX / innerWidth) === "next" ? next() : prev());
    $("menu").onclick = toggleBars;
    addEventListener("pointermove", peekBars);
    $("mode").onclick = () => setting("double", !settings.double);
    $("fit").onclick = () => setting("fit", settings.fit === "height" ? "width" : "height");
    $("peek").onclick = followMouse;
    $("end-stay").onclick = () => go(page);
    addEventListener("keydown", keys);
    await openVolume(vid);
  }

  start();
  return { spread, after, before, zone, pageWidth, around };
})();

if (typeof module !== "undefined") module.exports = Reader;
