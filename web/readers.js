// The readers: who reads in this browser (a cookie the server reads), asked with
// "Qui lit ?" when it cannot be told, and the readers' part of the settings: switch,
// add, rename, forget. The volumes are shared, where each one is in them is not.
const Readers = (() => {
  const { $, el, button, twice, api } = UI;
  const W = () => I18n.words();
  const { readerName, readerLook, readerCookie, whoReads } = Words;

  // reading as another reader: the page starts again from their library
  function choose(id) {
    document.cookie = readerCookie(id);
    for (const key of ["ohara-library", "ohara-lectern-away"]) localStorage.removeItem(key);
    location.reload();
  }

  function badge(r) {
    const look = readerLook(r);
    const b = el("span", "reader-badge", look.initial);
    b.style.background = look.colour;
    return b;
  }

  // a name to type and a button, for a new reader or a new name
  function nameForm(label, value, done) {
    const form = el("form", "decor-link");
    const input = el("input");
    input.placeholder = W().readerName;
    input.maxLength = 30;
    input.required = true;
    input.value = value;
    const go = button(label, "button main", null);
    go.type = "submit";
    form.append(input, go);
    form.onsubmit = async (e) => {
      e.preventDefault();
      go.disabled = true;
      try {
        await done(input.value);
      } finally {
        go.disabled = false;
      }
    };
    return form;
  }

  // "Qui lit ?": every reader, and a new one
  function ask(list) {
    const box = $("readers");
    const tiles = el("div", "reader-tiles");
    for (const r of list) {
      const t = button("", "reader-tile", () => choose(r.id));
      t.append(badge(r), el("b", "", readerName(r)));
      tiles.append(t);
    }
    const add = nameForm(W().addReader, "", async (name) => choose((await api("/api/readers", { name })).reader));
    box.replaceChildren(el("h2", "", W().whoReads), el("p", "note", W().whoReadsHint), tiles, el("h3", "", W().addReader), add);
    box.hidden = false;
  }

  // the header's badge of who reads, once there is more than one reader; with
  // several and none known, "Qui lit ?"
  function show(lib) {
    const { me, asked } = whoReads(lib);
    if (asked && $("readers").hidden) ask(lib.readers);
    const b = $("open-readers");
    b.hidden = !me;
    if (!me) return;
    b.replaceChildren(badge(me));
    b.title = b.ariaLabel = `${readerName(me)} · ${W().switchReader}`;
    b.onclick = () => ask(lib.readers);
  }

  // the settings' part: each reader (touch to read as them), renamed or forgotten
  function settingsBox() {
    const box = el("div", "readers-box");
    async function forget(id) {
      const left = await api("/api/readers", { id, forget: true });
      if (id === reader) return location.reload(); // forgot oneself: the page asks again
      draw(left);
    }
    let reader = null;
    const draw = (now) => {
      const readers = now.readers;
      reader = now.reader ?? reader;
      const rows = readers.map((r) => {
        const row = el("div", "option reader-row");
        const who = button("", "reader-who", () => r.id !== reader && choose(r.id));
        who.append(badge(r), el("b", "", readerName(r)), el("small", "", r.id === reader ? W().thatsYou : ""));
        const acts = el("span", "reader-acts");
        acts.append(button(W().renameReader, "button quiet", () => row.replaceWith(nameForm(W().renameReader, r.name, async (name) => draw(await api("/api/readers", { id: r.id, name }))))));
        if (readers.length > 1) acts.append(twice(W().forgetReader, () => forget(r.id), "button quiet"));
        row.append(who, acts);
        return row;
      });
      const add = nameForm(W().addReader, "", async (name) => draw({ ...(await api("/api/readers", { name })), reader: null }));
      box.replaceChildren(...rows, add);
    };
    api("/api/readers").then(draw, () => {});
    return box;
  }

  return { ask, show, settingsBox };
})();
