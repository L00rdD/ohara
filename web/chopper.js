// What ails the library (Chopper, the doctor, examines it on the server: see
// chopper.py), each ailment with its remedies to choose from, or to set aside. The
// header's 🩺 opens the list and says how many; a series' sheet shows its own.
const Doctor = (() => {
  const { $, el, button, twice, api } = UI;
  const W = () => I18n.words();
  const said = (w) => w[I18n.get()] || w.en;
  let ctx = { reload: () => {}, closeSheet: () => {} };
  let known = [];

  // the ailments as they are now, and the 🩺's count
  function show(list) {
    const same = JSON.stringify(list) === JSON.stringify(known);
    known = list;
    const count = $("ailments-count");
    count.textContent = list.length || "";
    $("open-ailments").classList.toggle("quiet", !list.length);
    if (!$("ailments").hidden && !same) draw(); // not drawn again for nothing: it would jump
  }

  const refresh = (fresh = false) => api("/api/ailments" + (fresh ? "?fresh=1" : "")).then(show, () => {});

  async function treat(a, i, box) {
    box.classList.add("busy");
    try {
      show((await api("/api/ailments/treat", { id: a.id, remedy: i })).ailments);
      ctx.reload();
    } catch (err) {
      box.classList.remove("busy");
      box.append(el("p", "error", err.message));
    }
  }

  async function setAside(a) {
    show(await api("/api/ailments/dismiss", { id: a.id }));
  }

  function row(a) {
    const box = el("div", "ailment " + a.severity);
    const acts = el("div", "actions");
    a.remedies.forEach((r, i) => {
      const go = () => treat(a, i, box);
      acts.append(r.risky ? twice(said(r.label), go) : button(said(r.label), "button", go));
    });
    acts.append(button(W().setAside, "button quiet", () => setAside(a)));
    box.append(el("p", "", said(a.text)), acts);
    return box;
  }

  // the list, by series, the library's own first
  function draw() {
    const sheet = $("ailments");
    const groups = new Map();
    for (const a of known) groups.set(a.series || "", [...(groups.get(a.series || "") || []), a]);
    const parts = [...groups].map(([series, list]) => {
      const part = el("div", "ailments-of");
      part.append(el("h3", "", series || W().wholeLibrary), ...list.map(row));
      return part;
    });
    sheet.replaceChildren(button("✕", "round close", () => ctx.closeSheet(sheet)), el("h2", "", W().ailmentsTitle), el("p", "note", W().ailmentsHint),
      ...(parts.length ? parts : [el("p", "done-note", W().ailmentsNone)]));
  }

  function open() {
    draw();
    $("ailments").hidden = false;
    refresh(true);
  }

  // a series' own ailments, on its sheet
  function forSeries(name) {
    const box = el("div", "ailments-here");
    box.append(...known.filter((a) => a.series === name).map(row));
    return box;
  }

  return { init: (context) => (ctx = context), open, refresh, forSeries };
})();
