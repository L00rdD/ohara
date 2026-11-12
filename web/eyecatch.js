// Between two volumes, one of the series' eyecatches, as between the two halves of an
// episode of the anime: a short video, or an animated drawing (an SVG), put on the
// server in .ohara/eyecatches/<series>/.
const Eyecatch = (() => {
  // One of a series' eyecatches, drawn by r (0 to 1); none when it has none
  function url(series, names, r) {
    if (!names || !names.length) return null;
    const name = names[Math.min(Math.floor(r * names.length), names.length - 1)];
    return `/api/eyecatch?series=${encodeURIComponent(series)}&name=${encodeURIComponent(name)}`;
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

  return { url, isDrawing, show };
})();

if (typeof module !== "undefined") module.exports = Eyecatch;
