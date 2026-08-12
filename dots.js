/* Shared dot-size control for the logo pages.
 *
 * Every logo is a constellation of <circle> elements, but each lives in its own
 * viewBox, so raw radii are not comparable between pages. The common unit here
 * is the radius as a fraction of the viewBox HEIGHT, which is the comparable
 * one because every logo is displayed at the same height (80vh).
 *
 * The two ends of the range are the marks as they were authored:
 *   min = Marihuel today (0.380% of height)
 *   max = Lawal today    (2.423% of height)  -- 6.4x larger
 *
 * A page keeps its own relative dot hierarchy: Marihuel's radii were measured
 * from the original artwork and vary per star, and Estres draws its ring
 * smaller than its triangles. Only the page's MEDIAN radius is driven to the
 * target, everything else scales with it.
 *
 * Usage: mark the element containing the <svg>s with data-dots. The control is
 * built and inserted after it. Pages with no circles get no control.
 */
(function () {
  "use strict";

  var MIN_FRAC = 0.00380;      // Marihuel's median dot / its viewBox height
  var MAX_FRAC = 0.024233;     // Lawal's dot / its viewBox height
  var KEY = "tyny:dot-scale";  // shared across the pages

  var host = document.querySelector("[data-dots]");
  if (!host) { return; }

  var groups = [];
  var svgs = host.querySelectorAll("svg");
  for (var s = 0; s < svgs.length; s++) {
    var svg = svgs[s];
    var vb = (svg.getAttribute("viewBox") || "").split(/[\s,]+/);
    var vh = parseFloat(vb[3]);
    var circles = svg.querySelectorAll("circle");
    if (!circles.length || !(vh > 0)) { continue; }
    var base = [];
    for (var i = 0; i < circles.length; i++) {
      base.push(parseFloat(circles[i].getAttribute("r")) || 1);
    }
    var sorted = base.slice().sort(function (a, b) { return a - b; });
    groups.push({
      circles: circles,
      base: base,
      median: sorted[Math.floor(sorted.length / 2)] || 1,
      vh: vh
    });
  }
  if (!groups.length) { return; }   // e.g. a page whose logo does not exist yet

  function fracToT(f) {
    return Math.max(0, Math.min(1, (f - MIN_FRAC) / (MAX_FRAC - MIN_FRAC)));
  }

  function apply(t) {
    var frac = MIN_FRAC + (MAX_FRAC - MIN_FRAC) * t;
    for (var g = 0; g < groups.length; g++) {
      var grp = groups[g];
      var k = (frac * grp.vh) / grp.median;
      for (var i = 0; i < grp.circles.length; i++) {
        grp.circles[i].setAttribute("r", (grp.base[i] * k).toFixed(2));
      }
    }
    return frac;
  }

  // Start where this page already is, so nothing jumps on load; a stored
  // choice from another page wins over that.
  var natural = fracToT(groups[0].median / groups[0].vh);
  var start = natural;
  try {
    var saved = parseFloat(localStorage.getItem(KEY));
    if (saved >= 0 && saved <= 1) { start = saved; }
  } catch (e) { /* storage blocked; fall back to the page's own size */ }

  var ui = document.createElement("div");
  ui.className = "dots-ui";
  var id = "dot-size";
  ui.innerHTML =
    '<label for="' + id + '">puntos</label>' +
    '<input id="' + id + '" type="range" min="0" max="1" step="0.01" ' +
    'aria-label="Tamaño de los puntos">' +
    '<output for="' + id + '"></output>';
  host.parentNode.insertBefore(ui, host.nextSibling);

  var range = ui.querySelector("input");
  var out = ui.querySelector("output");

  function update(t, save) {
    var frac = apply(t);
    out.textContent = (100 * frac).toFixed(2) + "%";
    if (save) {
      try { localStorage.setItem(KEY, String(t)); } catch (e) { /* ignore */ }
    }
  }

  range.value = String(start);
  update(start, false);
  range.addEventListener("input", function () {
    update(parseFloat(range.value), true);
  });

  // Double-click the slider to snap back to the size this page ships with.
  range.addEventListener("dblclick", function () {
    range.value = String(natural);
    update(natural, true);
  });
})();
