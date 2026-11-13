// Volumes added by hand: files or folders dropped on the library (on a series' bay or
// its sheet, they go to that series), or chosen from the ＋ in the header. A sheet
// then says where each lot goes: one of the library's series, guessed from its names,
// or a new one; each folder dropped is a lot of its own, so several series come in at
// once. The volumes are then sent one by one, each with its bar.
const Adding = (() => {
  const { $, el, button, bar, api } = typeof UI !== "undefined" ? UI : {};
  const W = () => I18n.words();
  const VOLUME = /\.(cbz|zip|cbr|rar|cb7|7z|pdf|epub)$/i;
  let ctx = { series: () => [], reload: () => {}, closeSheet: () => {} };

  // ---- what was given, in lots ----

  // whether a file is a volume Ohara keeps (not a hidden one, as macOS leaves)
  const isVolume = (name) => VOLUME.test(name) && !name.startsWith(".");

  // the folder a file came in, from its path ("Manga/Frieren/T01.cbz" → "Frieren")
  const folderOf = (path) => (path || "").split("/").slice(-2, -1)[0] || "";

  // the volumes given, in lots by the folder they came in (loose files make one lot),
  // each in the order of its names; items are { file, folder }
  function lots(items) {
    const by = new Map();
    for (const it of items.filter((x) => isVolume(x.file.name))) {
      if (!by.has(it.folder)) by.set(it.folder, []);
      by.get(it.folder).push(it.file);
    }
    const order = (a, b) => a.localeCompare(b, undefined, { numeric: true });
    return [...by].sort(([a], [b]) => order(a, b)).map(([folder, files]) => ({ folder, files: files.sort((a, b) => order(a.name, b.name)) }));
  }

  // the files under an entry of a drop, a folder read through
  async function filesIn(entry, folder) {
    if (entry.isFile) return [{ file: await new Promise((ok, ko) => entry.file(ok, ko)), folder }];
    const reader = entry.createReader();
    const all = [];
    for (let batch; (batch = await new Promise((ok, ko) => reader.readEntries(ok, ko))).length; ) all.push(...batch);
    return (await Promise.all(all.map((e) => filesIn(e, entry.name)))).flat();
  }

  // what a drop holds; its entries are taken before anything is awaited, as the
  // browser forgets them after
  function dropped(dt) {
    const entries = [...(dt.items || [])].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
    if (!entries.length) return Promise.resolve([...dt.files].map((file) => ({ file, folder: "" })));
    return Promise.all(entries.map((e) => filesIn(e, ""))).then((all) => all.flat());
  }

  // ---- the sheet ----

  // where a lot goes: one of the library's series, or a new one, named
  function whereTo(lot, preset) {
    const names = ctx.series().map((s) => s.name);
    const box = el("fieldset", "lot");
    const id = "lot" + Math.random().toString(36).slice(2);
    const pick = el("select");
    pick.append(...names.map((n) => Object.assign(el("option", "", n), { value: n })));
    const name = el("input");
    name.placeholder = W().addNewName;
    const choice = (value, label, field) => {
      const row = el("label", "option");
      const radio = Object.assign(el("input"), { type: "radio", name: id, value });
      field.onfocus = () => (radio.checked = true);
      row.append(radio, el("b", "", label), field);
      return row;
    };
    const known = choice("known", W().addKnown, pick);
    const fresh = choice("new", W().addNew, name);
    known.hidden = !names.length;
    const sure = (where, value) => {
      box.querySelector(`input[value=${where}]`).checked = true;
      if (where === "known") pick.value = value;
      else name.value = value;
    };
    const list = lot.files.map((f) => f.name).join(", ");
    box.append(el("legend", "", lot.folder || W().addLoose(lot.files.length)), el("p", "note lot-files", list), known, fresh);
    if (preset) sure("known", preset);
    else {
      sure("new", "");
      let touched = false; // the guess comes late: it does not undo a choice made
      box.onchange = box.oninput = () => (touched = true);
      api("/api/shelf?name=" + encodeURIComponent(lot.folder || lot.files[0].name)).then((g) => touched || sure(g.known ? "known" : "new", g.name), () => {});
    }
    box.series = () => (box.querySelector("input[value=known]").checked ? pick.value : name.value.trim());
    return box;
  }

  // one volume sent, its bar filling as it goes
  function send(file, series, row) {
    return new Promise((done, failed) => {
      const x = new XMLHttpRequest();
      x.open("POST", `/api/add?series=${encodeURIComponent(series)}&name=${encodeURIComponent(file.name)}`);
      x.upload.onprogress = (e) => e.lengthComputable && row.querySelector("i").style.setProperty("width", (100 * e.loaded / e.total).toFixed(0) + "%");
      x.onload = () => (x.status === 200 ? done(JSON.parse(x.response)) : failed(new Error((JSON.parse(x.response || "{}").error) || x.status)));
      x.onerror = () => failed(new Error(W().addCut));
      x.send(file);
    });
  }

  // every lot sent to its series, one volume after the other; what failed is said
  async function sendAll(boxes, said) {
    let count = 0;
    for (const box of boxes) {
      const series = box.series();
      for (const file of box.lot.files) {
        const row = el("p", "lot-sending");
        row.append(el("span", "", file.name), bar(0));
        said.append(row);
        try {
          await send(file, series, row);
          count++;
          row.classList.add("done");
        } catch (err) {
          row.replaceWith(el("p", "error", W().addFailed(file.name, err.message)));
        }
      }
    }
    said.append(el("p", "done-note", W().addDone(count)));
    ctx.reload();
  }

  // the sheet for the volumes given (or none yet: it lets them be chosen), a series
  // already said when they were dropped on it
  function open(items = [], preset = "") {
    const sheet = $("adding");
    const given = lots(items);
    const boxes = given.map((lot) => Object.assign(whereTo(lot, preset), { lot }));
    const said = el("div", "lot-progress");
    const go = button(W().addGo(given.reduce((n, l) => n + l.files.length, 0)), "button main", () => {
      if (boxes.some((b) => !b.series())) return said.replaceChildren(el("p", "error", W().addNoName));
      go.disabled = true;
      sendAll(boxes, said).finally(() => (go.hidden = true));
    });
    go.hidden = !given.length;
    const skipped = items.length - given.reduce((n, l) => n + l.files.length, 0);
    sheet.replaceChildren(button("✕", "round close", () => ctx.closeSheet(sheet)), el("h2", "", W().addTitle),
      el("p", "note", given.length ? W().addHint : W().addEmpty), ...choosers(preset), ...boxes,
      ...(skipped > 0 ? [el("p", "note", W().addSkipped(skipped))] : []), go, said);
    sheet.hidden = false;
  }

  // the buttons that choose files, or a whole folder, from the computer or the phone
  function choosers(preset) {
    const input = (folder) => {
      const i = Object.assign(el("input"), { type: "file", multiple: true, hidden: true });
      if (folder) i.webkitdirectory = true;
      else i.accept = ".cbz,.zip,.cbr,.rar,.cb7,.7z,.pdf,.epub";
      i.onchange = () => open([...i.files].map((file) => ({ file, folder: folderOf(file.webkitRelativePath) })), preset);
      return i;
    };
    const files = input(false);
    const folder = input(true);
    const acts = el("div", "actions");
    acts.append(button(W().addFiles, "button", () => files.click()), button(W().addFolder, "button", () => folder.click()));
    return [acts, files, folder];
  }

  // ---- dropping ----

  // Files dragged over the page lay a veil that says they can be dropped; dropped on a
  // series' bay or on its sheet, they go to that series.
  function wireDrops() {
    const veil = $("drop-veil");
    let depth = 0;
    const files = (e) => e.dataTransfer && [...e.dataTransfer.types].includes("Files");
    const lift = () => ((depth = 0), (veil.hidden = true));
    addEventListener("dragenter", (e) => files(e) && (depth++, (veil.hidden = false)));
    addEventListener("dragleave", (e) => files(e) && --depth <= 0 && lift());
    addEventListener("dragover", (e) => {
      if (!files(e)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
    });
    addEventListener("drop", (e) => {
      if (!files(e)) return;
      e.preventDefault();
      lift();
      const on = e.target.closest && e.target.closest("[data-series]");
      dropped(e.dataTransfer).then((items) => open(items, on ? on.dataset.series : ""));
    });
  }

  function init(context) {
    ctx = context;
    wireDrops();
  }

  return { isVolume, folderOf, lots, open, init };
})();

if (typeof module !== "undefined") module.exports = Adding;
