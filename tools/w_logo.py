#!/usr/bin/env python3
"""Generate the Lawal W as a constellation: dots along the outline of the mark.

    python3 tools/w_logo.py -o lawal/logo.svg
    python3 tools/w_logo.py --spacing 30 --label "Lawal"

Provenance
----------
The polygon below was measured from Lawal_Iso_w_rojo.png (1000x1000), not
traced by hand:

  1. The largest connected ink component was isolated — the source file also
     carries a detached ▽ to the right of the W, which is excluded.
  2. Its boundary was walked (Moore tracing) and reduced with Douglas-Peucker,
     which settled on 8 vertices across every tolerance from 2.0 to 3.0 px.
  3. Each edge was then re-fitted at sub-pixel accuracy: the anti-aliased
     coverage was scanned along the edge normal, the 50% crossing taken as the
     true edge position, and a total-least-squares line fitted through those
     samples. Corners are the intersections of consecutive lines.

Fidelity of the result against the source pixels: IoU 98.76%, with the residual
being a one-pixel fringe along the edges (symmetric: 173px of the model outside
the source, 173px of the source outside the model) — i.e. anti-aliasing, not
shape error. Mean edge displacement is about 0.17px.
"""
import argparse
import math
import sys

# Sub-pixel vertices in the source image's 1000x1000 frame, clockwise.
W_POLY = [
    (318.000, 394.000),
    (395.000, 394.000),
    (446.854, 474.091),
    (498.119, 394.134),
    (594.148, 536.492),
    (552.435, 606.709),
    (499.230, 524.212),
    (450.109, 603.364),
]

RED = "#dd5769"          # Lawal red, sampled from the source PNG
DOT_R = 15.0             # dot radius, in output viewBox units
STROKE = 4.0
PAD = 40.0               # margin around the mark, output units
SIZE = 1000.0            # output viewBox is SIZE wide


def normalise(poly, size=SIZE, pad=PAD):
    """Fit the polygon to a viewBox of the given width, keeping aspect."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    s = (size - 2 * pad) / w
    out = [((x - min(xs)) * s + pad, (y - min(ys)) * s + pad) for (x, y) in poly]
    return out, size, h * s + 2 * pad


def place_dots(poly, spacing):
    """Corners always get a dot; edges are subdivided as evenly as possible."""
    dots, segs = [], []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        k = max(1, round(L / spacing))
        for s in range(k):
            t0, t1 = s / k, (s + 1) / k
            p = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            q = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            dots.append(p)
            segs.append((p, q))
    return dots, segs


def to_svg(spacing=64.0, label="Lawal", color=RED, dot_r=DOT_R, stroke=STROKE):
    poly, vw, vh = normalise(W_POLY)
    dots, segs = place_dots(poly, spacing)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw:.0f} {vh:.0f}" '
         f'role="img" aria-label="{label}">',
         f'  <title>{label}</title>',
         f'  <g stroke="{color}" stroke-width="{stroke}" fill="none" '
         f'stroke-linecap="round" opacity=".65">']
    for (p, q) in segs:
        o.append(f'    <line x1="{p[0]:.1f}" y1="{p[1]:.1f}" '
                 f'x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
    o += ['  </g>', f'  <g fill="{color}">']
    for (x, y) in dots:
        o.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{dot_r:.0f}"/>')
    o += ['  </g>', '</svg>']
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-o", "--out", help="output SVG (default stdout)")
    ap.add_argument("--spacing", type=float, default=64.0,
                    help="target distance between dots, output units")
    ap.add_argument("--label", default="Lawal")
    ap.add_argument("--color", default=RED)
    args = ap.parse_args()

    poly, vw, vh = normalise(W_POLY)
    dots, _ = place_dots(poly, args.spacing)
    per = sum(math.hypot(poly[(i + 1) % len(poly)][0] - poly[i][0],
                         poly[(i + 1) % len(poly)][1] - poly[i][1])
              for i in range(len(poly)))
    print(f"viewBox {vw:.0f}x{vh:.0f}, perimeter {per:.0f}, "
          f"{len(dots)} dots (8 corners + {len(dots)-8} on edges)", file=sys.stderr)

    svg = to_svg(args.spacing, args.label, args.color)
    if args.out:
        open(args.out, "w").write(svg)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(svg)


if __name__ == "__main__":
    main()
