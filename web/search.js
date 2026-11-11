// The search: the catalogue drawer of the library, one index card per series with
// the best release picked, its cover and the switch to follow it. library.js tells
// it the series already there and reloads when something is sent.
const Search = (() => {
  const { $, el, button, api } = UI;
  const W = () => I18n.words();
  const { tomes, describe, seriesFacts } = Words;
  let ctx = { series: () => [], reload: () => {} };

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
      ctx.reload();
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
    const owned = ctx.series().find((s) => s.name === g.name);
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

  // library.js gives the series there and a way to reload them
  function init(context) {
    ctx = context;
    $("close-search").onclick = () => ($("search").hidden = true);
    $("search-form").onsubmit = (e) => {
      e.preventDefault();
      runSearch(e.target.q.value.trim());
    };
    $("all-languages").onchange = drawFinds;
  }

  return { init, open: openSearch };
})();
