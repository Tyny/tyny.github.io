#!/usr/bin/env python3
"""Generate the Lawal W as a constellation: dots along the outline of the mark.

    python3 tools/w_logo.py -o lawal/logo.svg
    python3 tools/w_logo.py --spacing 30 --label "Lawal"

Provenance
----------
The polygons below were measured from Lawal_Iso_w_rojo.png (1000x1000), not
traced by hand:

  1. The ink splits into two connected components: the W stroke (27801px) and
     a detached ▽ at the upper right (6076px). Both belong to the mark — with
     the ▽ included the bounding box is 364px wide, matching the ▽-only logos
     in the same family exactly.
  2. Each boundary was walked (Moore tracing) and reduced with Douglas-Peucker,
     which settled on 8 and 3 vertices respectively, stable across every
     tolerance from 1.0 to 3.0 px.
  3. Each edge was then re-fitted at sub-pixel accuracy: the anti-aliased
     coverage was scanned along the edge normal, the 50% crossing taken as the
     true edge position, and a total-least-squares line fitted through those
     samples. Corners are the intersections of consecutive lines.

Fidelity against the source pixels: IoU 98.76% for the W, 98.16% for the ▽.
The residual is a one-pixel fringe along the edges, symmetric (for the W: 173px
of model outside the source, 173px of source outside the model) — anti-aliasing,
not shape error. Mean edge displacement is about 0.17px.
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

# The detached ▽ at the upper right, part of the same mark.
TRI_POLY = [
    (558.000, 394.000),
    (681.000, 394.000),
    (622.584, 490.551),
]

SHAPES = [W_POLY, TRI_POLY]

RED = "#dd5769"          # Lawal red, sampled from the source PNG
DOT_R = 15.0             # dot radius, in output viewBox units
STROKE = 4.0
PAD = 40.0               # margin around the mark, output units
SIZE = 1000.0            # output viewBox is SIZE wide


def normalise(shapes, size=SIZE, pad=PAD):
    """Fit every shape to a viewBox of the given width on one shared transform,
    so the parts keep their relative placement."""
    xs = [p[0] for poly in shapes for p in poly]
    ys = [p[1] for poly in shapes for p in poly]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0, max(ys) - y0
    s = (size - 2 * pad) / w
    out = [[((x - x0) * s + pad, (y - y0) * s + pad) for (x, y) in poly]
           for poly in shapes]
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
    shapes, vw, vh = normalise(SHAPES)
    dots, segs = [], []
    for poly in shapes:
        d, s = place_dots(poly, spacing)
        dots += d
        segs += s
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

    shapes, vw, vh = normalise(SHAPES)
    ndots = corners = 0
    per = 0.0
    for poly in shapes:
        d, _ = place_dots(poly, args.spacing)
        ndots += len(d)
        corners += len(poly)
        per += sum(math.hypot(poly[(i + 1) % len(poly)][0] - poly[i][0],
                              poly[(i + 1) % len(poly)][1] - poly[i][1])
                   for i in range(len(poly)))
    print(f"viewBox {vw:.0f}x{vh:.0f}, {len(shapes)} shapes, perimeter {per:.0f}, "
          f"{ndots} dots ({corners} corners + {ndots-corners} on edges)", file=sys.stderr)

    svg = to_svg(args.spacing, args.label, args.color)
    if args.out:
        open(args.out, "w").write(svg)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(svg)


if __name__ == "__main__":
    main()
