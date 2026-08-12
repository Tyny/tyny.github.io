#!/usr/bin/env python3
"""Generate the Estres isotype: three ▽ triangles drawn as constellations
inside a 16-sided ring.

    python3 tools/estres_logo.py echo -o out.svg
    python3 tools/estres_logo.py --all --dir /tmp/svgs

Balance
-------
The three triangles are translated so their combined centre of gravity lands
on the ring centre. This matters because a ▽ carries its centroid at 1/3 of
the height from the base, not at the centre of its bounding box, so laying the
triangles out by their boxes leaves the group hanging upward — measured at
62px (6% of the box) for the `echo` arrangement.

Gravity is computed over the *drawn marks* (dots weighted by disc area,
segments by length), not over filled shapes. On these layouts the two
definitions land within 2.4px of each other, so the choice is not critical,
but ink is what the eye actually weighs.

Colours are the Lawal ▽ palette, sampled from the source PNGs.
"""
import argparse
import math
import os
import sys

YELLOW, RED, GREEN = "#ffbe69", "#dd5769", "#468d81"
COLORS = [YELLOW, RED, GREEN]

S = 1000.0            # viewBox side
C = S / 2             # centre
R_RING = S * 0.46     # ring radius
RING_N = 16           # ring sides
RING_DOT_R = 7.0
TRI_DOT_R = 9.0
TRI_STROKE = 2.6
RING_STROKE = 2.4
TRI_RATIO = 286 / 364  # height/width, measured from the source artwork

LAYOUTS = ("echo", "nested", "triad", "convergent", "quartus", "row")

# Each arrangement is named after a constellation.
NAMES = {
    "echo": "Orión",              # three copies stepping in line, like the belt
    "nested": "Corona Austral",   # concentric rings
    "triad": "Triángulo Austral", # three-fold symmetry
    "convergent": "Pavo",         # three blades fanning from a single point
    "quartus": "Retículo",        # a subdivided lattice
    "row": "Sagitta",
}


def tri_points(cx, cy, w, rot=0.0):
    """Vertices of a ▽ of width w centred on its bounding box, rotated by rot."""
    h = w * TRI_RATIO
    out = []
    for (x, y) in [(-w / 2, -h / 2), (w / 2, -h / 2), (0.0, h / 2)]:
        out.append((cx + x * math.cos(rot) - y * math.sin(rot),
                    cy + x * math.sin(rot) + y * math.cos(rot)))
    return out


def subdivide(poly, n):
    """Dots along each edge (corners plus n-1 points) and the segments between."""
    dots, segs = [], []
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]
        for s in range(n):
            t0, t1 = s / n, (s + 1) / n
            p = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            q = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            dots.append(p)
            segs.append((p, q))
    return dots, segs


def ngon(cx, cy, r, n=RING_N, phase=math.pi / RING_N):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n),
             cy + r * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]


def raw_layout(kind):
    """Triangle groups before balancing: [(colour, dots, segs), ...]."""
    groups = []
    if kind == "echo":
        w = S * 0.46
        for i, col in enumerate(COLORS):
            poly = tri_points(C + (i - 1) * S * 0.085, C + (i - 1) * S * 0.055, w)
            groups.append((col,) + subdivide(poly, 3))
    elif kind == "nested":
        for i, col in enumerate(COLORS):
            poly = tri_points(C, C + S * 0.03, S * (0.66 - 0.17 * i))
            groups.append((col,) + subdivide(poly, 4 - i))
    elif kind == "triad":
        w = S * 0.50
        h = w * TRI_RATIO
        # Offset chosen so the three triangles meet exactly, instead of merely
        # nearly. Each pair shares one dot: the 2/3 point of one edge and the
        # 1/3 point of another. Equating those two positions for a pair of
        # triangles 120° apart gives d = h/6 + w·√3/18 — the value at which the
        # near-miss (6.216 units at the old d = 0.11·S) closes to zero.
        d = h / 6 + w * math.sqrt(3) / 18
        for i, col in enumerate(COLORS):
            rot = i * 2 * math.pi / 3
            poly = tri_points(C + d * math.sin(rot), C - d * math.cos(rot), w, rot)
            groups.append((col,) + subdivide(poly, 3))
    elif kind == "convergent":
        # Offset by exactly half the height and the three apexes land on one
        # another at the centre: a single point shared by all three triangles.
        w = S * 0.46
        h = w * TRI_RATIO
        d = h / 2
        for i, col in enumerate(COLORS):
            rot = i * 2 * math.pi / 3
            poly = tri_points(C + d * math.sin(rot), C - d * math.cos(rot), w, rot)
            groups.append((col,) + subdivide(poly, 3))
    elif kind == "quartus":
        # Three half-scale ▽ on the corners of a larger ▽. The gap they leave is
        # a fourth triangle, inverted, that is never drawn. Each pair meets
        # exactly on a midpoint of the parent's edge.
        w = S * 0.66
        h = w * TRI_RATIO
        A = (C - w / 2, C - h / 2)
        B = (C + w / 2, C - h / 2)
        V = (C, C + h / 2)
        mid = lambda p, q: ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        m_ab, m_bv, m_va = mid(A, B), mid(B, V), mid(V, A)
        for col, poly in zip(COLORS, ([A, m_ab, m_va], [m_ab, B, m_bv], [m_va, m_bv, V])):
            groups.append((col,) + subdivide(poly, 2))
    elif kind == "row":
        for i, col in enumerate(COLORS):
            poly = tri_points(C + (i - 1) * S * 0.26, C, S * 0.26)
            groups.append((col,) + subdivide(poly, 2))
    else:
        raise SystemExit(f"unknown layout {kind!r}; pick from {', '.join(LAYOUTS)}")
    return groups


def ink_centroid(groups):
    """Centre of gravity of the drawn marks: dots by disc area, segments by length."""
    sx = sy = sw = 0.0
    dot_w = math.pi * TRI_DOT_R * TRI_DOT_R
    for (_, dots, segs) in groups:
        for (x, y) in dots:
            sx += x * dot_w
            sy += y * dot_w
            sw += dot_w
        for (p, q) in segs:
            w = math.hypot(q[0] - p[0], q[1] - p[1]) * TRI_STROKE
            sx += (p[0] + q[0]) / 2 * w
            sy += (p[1] + q[1]) / 2 * w
            sw += w
    return sx / sw, sy / sw


def balanced(kind):
    """Layout translated so its centre of gravity is the ring centre."""
    groups = raw_layout(kind)
    cx, cy = ink_centroid(groups)
    dx, dy = C - cx, C - cy
    moved = [(col,
              [(x + dx, y + dy) for (x, y) in dots],
              [((p[0] + dx, p[1] + dy), (q[0] + dx, q[1] + dy)) for (p, q) in segs])
             for (col, dots, segs) in groups]
    return moved, (dx, dy)


def max_reach(groups):
    """Farthest drawn point from the centre, dot radius included."""
    return max(math.hypot(x - C, y - C) + TRI_DOT_R
               for (_, dots, _) in groups for (x, y) in dots)


def to_svg(kind, label="Estres", ring_color="currentColor"):
    groups, _ = balanced(kind)
    ring_dots, ring_segs = subdivide(ngon(C, C, R_RING), 1)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S:.0f} {S:.0f}" '
         f'role="img" aria-label="{label}">',
         f'  <title>{label}</title>',
         f'  <g stroke="{ring_color}" stroke-width="{RING_STROKE}" fill="none" opacity=".55">']
    for (p, q) in ring_segs:
        o.append(f'    <line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
    o += ['  </g>', f'  <g fill="{ring_color}">']
    for (x, y) in ring_dots:
        o.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{RING_DOT_R:.0f}"/>')
    o.append('  </g>')
    for (col, dots, segs) in groups:
        o.append(f'  <g stroke="{col}" stroke-width="{TRI_STROKE}" fill="none" opacity=".7">')
        for (p, q) in segs:
            o.append(f'    <line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
        o += ['  </g>', f'  <g fill="{col}">']
        for (x, y) in dots:
            o.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{TRI_DOT_R:.0f}"/>')
        o.append('  </g>')
    o.append('</svg>')
    return "\n".join(o) + "\n"


def report(kind):
    raw = raw_layout(kind)
    rx, ry = ink_centroid(raw)
    groups, (dx, dy) = balanced(kind)
    bx, by = ink_centroid(groups)
    reach = max_reach(groups)
    print(f"{kind:7s} was off {math.hypot(rx-C, ry-C):5.1f}px  shift ({dx:+.1f},{dy:+.1f})  "
          f"residual {math.hypot(bx-C, by-C):.3f}px  "
          f"reach {reach:.0f}/{R_RING:.0f} {'fits' if reach <= R_RING else 'SPILLS'}",
          file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout", nargs="?", choices=LAYOUTS)
    ap.add_argument("--all", action="store_true", help="emit every layout")
    ap.add_argument("-o", "--out", help="output file (single layout, default stdout)")
    ap.add_argument("--dir", help="output directory when using --all")
    ap.add_argument("--label", default="Estres")
    args = ap.parse_args()

    if args.all:
        d = args.dir or "."
        for k in LAYOUTS:
            report(k)
            with open(os.path.join(d, f"estres-{k}.svg"), "w") as f:
                f.write(to_svg(k, args.label))
        print(f"wrote {len(LAYOUTS)} files to {d}", file=sys.stderr)
        return
    if not args.layout:
        ap.error("give a layout name or --all")
    report(args.layout)
    svg = to_svg(args.layout, args.label)
    if args.out:
        open(args.out, "w").write(svg)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(svg)


if __name__ == "__main__":
    main()


# --- the meeting axis ------------------------------------------------------
# Triángulo Austral and Pavo are not two arrangements but two points on one
# continuous family: three ▽ rotated 120° apart, pushed out from the centre by
# a distance d. Because the rotation is fixed per triangle and the figure stays
# centred by symmetry, changing d translates each triangle rigidly — every dot
# of a triangle moves by exactly d·(sin θ, −cos θ). So the whole axis is a
# translation, and a viewer can walk it with three transforms and no recompute.
FAMILY_W = S * 0.46
FAMILY_H = FAMILY_W * TRI_RATIO
FAMILY_DMAX = 207.2                      # farthest that still fits the ring
LANDMARKS = [
    (FAMILY_H / 6 + FAMILY_W * math.sqrt(3) / 18, "Triángulo Austral"),
    (FAMILY_H / 2, "Pavo"),
]


def family_svg(label="Estres", ring_color="currentColor"):
    """The meeting axis as one SVG: each triangle in a group that carries its
    own unit direction, so a slider only has to set three translations."""
    ring_dots, ring_segs = subdivide(ngon(C, C, R_RING), 1)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S:.0f} {S:.0f}" '
         f'role="img" aria-label="{label}" data-family '
         f'data-dmax="{FAMILY_DMAX}" '
         f'data-marks="{";".join(f"{d:.4f},{n}" for d, n in LANDMARKS)}">',
         f'  <title>{label}</title>',
         f'  <g stroke="{ring_color}" stroke-width="{RING_STROKE}" fill="none" opacity=".55">']
    for (p, q) in ring_segs:
        o.append(f'    <line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
    o += ['  </g>', f'  <g fill="{ring_color}">']
    for (x, y) in ring_dots:
        o.append(f'    <circle cx="{x:.1f}" cy="{y:.1f}" r="{RING_DOT_R:.0f}"/>')
    o.append('  </g>')
    for i, col in enumerate(COLORS):
        rot = i * 2 * math.pi / 3
        ux, uy = math.sin(rot), -math.cos(rot)
        poly = tri_points(C, C, FAMILY_W, rot)      # d = 0; the slider adds d·u
        dots, segs = subdivide(poly, 3)
        o.append(f'  <g class="tri" data-ux="{ux:.6f}" data-uy="{uy:.6f}">')
        o.append(f'    <g stroke="{col}" stroke-width="{TRI_STROKE}" fill="none" opacity=".7">')
        for (p, q) in segs:
            o.append(f'      <line x1="{p[0]:.1f}" y1="{p[1]:.1f}" x2="{q[0]:.1f}" y2="{q[1]:.1f}"/>')
        o += ['    </g>', f'    <g fill="{col}">']
        for (x, y) in dots:
            o.append(f'      <circle cx="{x:.1f}" cy="{y:.1f}" r="{TRI_DOT_R:.0f}"/>')
        o += ['    </g>', '  </g>']
    o.append('</svg>')
    return "\n".join(o) + "\n"
