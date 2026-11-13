// Between two volumes, one of the series' eyecatches, as between the two halves of an
// episode of the anime: a short video, or an animated drawing (an SVG), put on the
// server in .ohara/eyecatches/<series>/. Each comes in turn, drawn among those not yet
// seen on this device; a series' sheet shows them all, one after the other.
const Eyecatch = (() => {
  // One of a series' eyecatches, drawn by r (0 to 1); none when it has none
  function url(series, names, r) {
    if (!names || !names.length) return null;
    const name = names[Math.min(Math.floor(r * names.length), names.length - 1)];
    return `/api/eyecatch?series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`;
  }

  // The next eyecatch, drawn by r (0 to 1) among those not in seen, and seen with it;
  // once all were seen they come round again, the last one not twice in a row
  function turn(names, seen, r) {
    let left = names.filter((n) => !seen.includes(n));
    if (!left.length) {
      seen = names.length > 1 ? seen.slice(-1) : [];
      left = names.filter((n) => !seen.includes(n));
    }
    const name = left[Math.min(Math.floor(r * left.length), left.length - 1)];
    return { name, seen: [...seen.filter((n) => names.includes(n)), name] };
  }

  // the address of a series' next eyecatch, those seen kept on the device; none when
  // it has none
  function pick(series, names) {
    if (!names || !names.length) return null;
    const key = "ohara-eyecatches-" + series;
    const next = turn(names, JSON.parse(localStorage.getItem(key) || "[]"), Math.random());
    localStorage.setItem(key, JSON.stringify(next.seen));
    return url(series, [next.name], 0);
  }

  // Whether an eyecatch is a drawing rather than a video
  function isDrawing(address) {
    return /\.svg$/i.test(decodeURIComponent(address));
  }

  // a video plays to its end, without sound if the browser will not have it
  function film(video, address) {
    const over = new Promise((done) => (video.onended = video.onerror = done));
    video.hidden = false;
    video.src = address;
    video.play().catch(() => ((video.muted = true), video.play())).catch(() => video.onerror());
    return { over, stop: () => {
      video.pause();
      video.removeAttribute("src");
      video.muted = false;
      video.hidden = true;
    } };
  }

  // an animated drawing has no end of its own: it is given a few seconds
  function sketch(img, address) {
    let timer;
    const over = new Promise((done) => {
      timer = setTimeout(done, 4500);
      img.onerror = done;
    });
    img.hidden = false;
    img.src = address;
    return { over, stop: () => {
      clearTimeout(timer);
      img.removeAttribute("src");
      img.hidden = true;
    } };
  }

  // the eyecatch shown in its box: over once it has played, stopped with stop()
  const show = (box, address) => (isDrawing(address) ? sketch(box.querySelector("img"), address) : film(box.querySelector("video"), address));

  // all of a series' eyecatches over the page, one after the other: a tap goes to the
  // next one, ✕ stops
  async function reel(series, names) {
    const box = document.createElement("div");
    box.className = "eyecatch";
    box.innerHTML = '<video playsinline hidden></video><img alt="" hidden><button class="round close" type="button">✕</button>';
    let stopped = false;
    const done = new Promise((end) => (box.querySelector("button").onclick = (e) => ((stopped = true), e.stopPropagation(), end())));
    document.body.append(box);
    for (let i = 0; i < names.length && !stopped; i++) {
      const shown = show(box, url(series, names, (i + 0.5) / names.length));
      await Promise.race([shown.over, done, new Promise((tap) => (box.onclick = tap))]);
      shown.stop();
    }
    box.remove();
  }

  return { url, turn, pick, isDrawing, show, reel };
})();

if (typeof module !== "undefined") module.exports = Eyecatch;
