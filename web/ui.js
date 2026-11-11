// Small tools of Ohara's pages: find an element, make one, a button, a gauge, and
// ask the server (JSON in, JSON out, the server's error as the message).
const UI = (() => {
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
  async function api(path, body) {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.status);
    return data;
  }

  return { $, el, button, bar, api };
})();
