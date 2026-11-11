// The settings: the interface's language, the style of spines, the lectern's ribbon,
// Brook, Franky, and where
// to search (Prowlarr's indexers). library.js gives what they change on the page.
const Settings = (() => {
  const { $, el, button, api } = UI;
  const W = () => I18n.words();
  const { indexerNotes, lighterText } = Words;
  let ctx = { spineStyle: () => "tome", setSpineStyle: () => {}, setRibbon: () => {}, setLanguage: () => {}, closeSheet: () => {} };

  async function openSettings() {
    const sheet = $("settings");
    const langs = el("div", "langs");
    for (const [code, label] of [["fr", "🇫🇷 Français"], ["en", "🇬🇧 English"]]) {
      const b = button(label, "button" + (I18n.get() === code ? " main" : ""), () => {
        ctx.setLanguage(code);
        openSettings();
      });
      langs.append(b);
    }
    const list = el("div", "", "…");
    sheet.replaceChildren(button("✕", "round close", () => ctx.closeSheet(sheet)), el("h2", "", W().settings), el("h3", "", W().language), langs,
      el("h3", "", W().spinesTitle), el("p", "note", W().spinesHint), spineChoices(),
      el("h3", "", W().lecternTitle), settingSwitch("ribbon", W().ribbonSetting, (st) => ctx.setRibbon(st.ribbon)),
      el("h3", "", W().music), el("p", "note", W().brookHint), brookSwitch(),
      el("h3", "", W().lighterTitle), el("p", "note", W().frankyHint), ...frankySwitch(),
      indexersBox(list));
    sheet.hidden = false;
    try {
      drawIndexers(list, await api("/api/indexers"));
    } catch {
      list.replaceChildren(el("p", "error", W().indexersFailed));
    }
  }

  // where to search: folded, it is seldom changed
  function indexersBox(list) {
    const box = el("details", "fold");
    const add = el("a", "button", W().addIndexer);
    add.href = `http://${location.hostname}:9696/`;
    add.target = "_blank";
    add.rel = "noopener";
    box.append(el("summary", "", W().indexers), el("p", "note", W().indexersHint), list, add);
    return box;
  }

  // the three styles of spines, each shown with a sample of three spines
  function spineChoices() {
    const box = el("div", "spine-choices");
    for (const [style, [name, hint]] of Object.entries(W().spineStyles)) {
      const b = button("", "spine-choice" + (style === ctx.spineStyle() ? " on" : ""), async () => {
        ctx.setSpineStyle((await api("/api/settings", { spines: style })).spines);
        box.replaceWith(spineChoices());
      });
      const sample = el("span", "sample");
      for (const [n, colour] of [[1, "#c7372f"], [2, "#2f6f9a"], [3, "#e2b23a"]]) {
        const v = el("span", "vol");
        v.dataset.style = style;
        for (const k of ["edge", "main", "accent", "c"]) v.style.setProperty("--" + k, colour);
        v.style.setProperty("--ink", "#fdf6e6");
        v.append(el("span", "art"), el("span", "vt", "Ohara"), el("span", "vn", String(n)));
        sample.append(v);
      }
      b.append(sample, el("b", "", name), el("small", "", hint));
      box.append(b);
    }
    return box;
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

  // a switch for one of the settings that are on or off
  function settingSwitch(key, label, shown = () => {}) {
    const sw = el("button", "switch");
    sw.type = "button";
    sw.setAttribute("role", "switch");
    sw.append(el("span", "knob"), el("span", "", label));
    const show = (st) => {
      sw.setAttribute("aria-checked", String(st[key]));
      shown(st);
    };
    api("/api/settings").then(show, () => {});
    sw.onclick = () => api("/api/settings", { [key]: sw.getAttribute("aria-checked") !== "true" }).then(show);
    return sw;
  }

  const brookSwitch = () => settingSwitch("brook", W().brookSetting);

  // Franky, and how far he has gone through the library
  function frankySwitch() {
    const said = el("p", "note");
    return [settingSwitch("franky", W().frankySetting, (st) => (said.textContent = lighterText(st.lighter))), said];
  }

  return { init: (context) => (ctx = context), open: openSettings };
})();
