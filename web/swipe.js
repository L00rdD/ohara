// A finger swiping across the reader's pages turns them: to the left forward, as a
// click on the right half does, to the right back.
const Swipe = (() => {
  // Which way a swipe turns, from the finger's travel (pixels) and its time (ms); too
  // short, too slow or mostly up and down (a page being scrolled) turns nothing
  function way(dx, dy, ms) {
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5 || ms > 800) return null;
    return dx < 0 ? "next" : "prev";
  }

  // Swipes on el call turn("next" or "prev"), unless the page is zoomed in to be looked
  // around; justDone(click) says whether a click only follows a swipe, not a tap
  function watch(el, turn) {
    let touch = null;
    let swiped = -1e9;
    el.addEventListener("touchstart", (e) => {
      const zoomed = typeof visualViewport !== "undefined" && visualViewport.scale > 1.05;
      touch = e.touches.length === 1 && !zoomed ? { x: e.touches[0].clientX, y: e.touches[0].clientY, at: e.timeStamp } : null;
    }, { passive: true });
    el.addEventListener("touchend", (e) => {
      const t = e.changedTouches[0];
      const going = touch && way(t.clientX - touch.x, t.clientY - touch.y, e.timeStamp - touch.at);
      touch = null;
      if (!going) return;
      swiped = e.timeStamp;
      turn(going);
    }, { passive: true });
    return { justDone: (click) => click.timeStamp - swiped < 600 };
  }

  return { way, watch };
})();

if (typeof module !== "undefined") module.exports = Swipe;
