#!/usr/bin/env python3
"""Turn a constellation-style artwork (bright dots joined by thin strokes on a
dark ground) into an SVG of circles and lines.

Everything is measured from the pixels; nothing is traced by hand.

    python3 tools/constellation_to_svg.py logo.png -o marihuel/logo.svg

How it works
------------
Nodes   A dot and a stroke are told apart by *shape*, not size: the intensity
        covariance around a stroke is elongated, around a dot it is round.
        That keeps the measure scale-free, so 2px ring dots survive alongside
        fat joint dots. (Measured on the Marihuel artwork: anisotropy median
        0.14 for dots vs 0.81 for strokes.)

Edges   A pair is joined when the dimmest point along the segment is still
        bright. Sampling takes the best pixel across a narrow perpendicular
        band, so a 1px stroke offset does not break the chain. An edge that
        passes within 3px of a third node is dropped, otherwise every collinear
        chain sprouts phantom edges spanning it.

Closing Artwork bends strokes at corners that carry no dot, which a pure
        node-and-edge model cannot express. Leftover ink is fitted with PCA and
        attached, adding a bare vertex only where no node is within reach.

Note: a purely geometric reconstruction from node positions does not work here.
Gabriel / relative-neighbourhood / kNN graphs were measured against the
image-verified edges and peaked at 0.63 precision: a drawing has long
structural edges no proximity rule finds, and near-touching dots on separate
strokes that every proximity rule wrongly joins.
"""
import argparse
import json
import sys

import numpy as np
from PIL import Image

# --- tunables ---------------------------------------------------------------
MEAN_R = 2         # disk-mean radius for the node response
PEAK_THR = 0.40    # minimum response for a node candidate
NMS = 4            # minimum separation between nodes, px
ANISO_MAX = 0.55   # above this a blob is a stroke, not a dot
EDGE_THR = 0.16    # minimum brightness anywhere along a real edge
MAX_LEN = 300.0    # px, longest plausible edge
SHADOW_D = 3.0     # px, an edge grazing a third node this closely is bogus
INK_THR = 0.25     # px above this counts as drawn ink
SNAP = 9.0         # px, residual endpoint this close to a node is that node
MIN_BLOB = 12      # px, smaller leftovers are glow, not strokes


def shift(m, dy, dx):
    return np.roll(np.roll(m, dy, axis=0), dx, axis=1)


def disk_offsets(r):
    return [(dy, dx) for dy in range(-r, r + 1) for dx in range(-r, r + 1)
            if dx * dx + dy * dy <= r * r]


def disk_mean(img, r):
    offs = disk_offsets(r)
    acc = np.zeros_like(img)
    for dy, dx in offs:
        acc += shift(img, dy, dx)
    return acc / len(offs)


def local_max(resp, win):
    m = np.ones_like(resp, dtype=bool)
    for dy in range(-win, win + 1):
        for dx in range(-win, win + 1):
            if dx or dy:
                m &= resp >= shift(resp, dy, dx)
    return m


class Extractor:
    def __init__(self, path):
        self.a = np.asarray(Image.open(path).convert("L"), dtype=np.float64) / 255.0
        self.H, self.W = self.a.shape
        self.yy, self.xx = np.mgrid[0:self.H, 0:self.W]

    # -- nodes ---------------------------------------------------------------
    def moments(self, x, y, r=3):
        """(anisotropy, centroid) of intensity in a window."""
        a, H, W = self.a, self.H, self.W
        xi, yi = int(round(x)), int(round(y))
        y0, y1 = max(0, yi - r), min(H, yi + r + 1)
        x0, x1 = max(0, xi - r), min(W, xi + r + 1)
        p = a[y0:y1, x0:x1]
        gy, gx = np.mgrid[y0:y1, x0:x1]
        s = p.sum()
        if s <= 1e-9:
            return 1.0, (x, y)
        mx, my = (gx * p).sum() / s, (gy * p).sum() / s
        dx, dy = gx - mx, gy - my
        cxx = (p * dx * dx).sum() / s
        cyy = (p * dy * dy).sum() / s
        cxy = (p * dx * dy).sum() / s
        tr, det = cxx + cyy, cxx * cyy - cxy * cxy
        disc = max(0.0, tr * tr / 4 - det) ** 0.5
        l1, l2 = tr / 2 + disc, tr / 2 - disc
        return (1.0 if l1 <= 1e-9 else float((l1 - l2) / l1)), (float(mx), float(my))

    def nodes(self):
        resp = disk_mean(self.a, MEAN_R)
        ys, xs = np.nonzero(local_max(resp, NMS) & (resp > PEAK_THR))
        out = []
        for k in np.argsort(-resp[ys, xs]):
            aniso, c = self.moments(float(xs[k]), float(ys[k]))
            if aniso > ANISO_MAX:
                continue
            if all((c[0] - px) ** 2 + (c[1] - py) ** 2 >= NMS * NMS for px, py in out):
                out.append(c)
        return out

    def radius(self, cx, cy, rmax=9, frac=0.55):
        """Largest r whose whole disk stays bright: the disk *minimum* is used,
        so surrounding glow and attached strokes cannot inflate it."""
        x0, x1 = max(0, int(cx - rmax)), min(self.W, int(cx + rmax) + 1)
        y0, y1 = max(0, int(cy - rmax)), min(self.H, int(cy + rmax) + 1)
        p = self.a[y0:y1, x0:x1]
        d = np.hypot(self.xx[y0:y1, x0:x1] - cx, self.yy[y0:y1, x0:x1] - cy)
        peak = p.max()
        if peak <= 0:
            return 2.0
        best = 1.4
        for r in np.arange(1.0, rmax, 0.5):
            m = d <= r
            if m.any() and p[m].min() >= peak * frac:
                best = float(r)
            else:
                break
        return best

    # -- edges ---------------------------------------------------------------
    def profile(self, p, q, inset_px=5.0, halfwidth=1.6):
        (x0, y0), (x1, y1) = p, q
        dx, dy = x1 - x0, y1 - y0
        L = float(np.hypot(dx, dy))
        if L < 1e-6:
            return 0.0
        inset = min(0.42, inset_px / L)
        nx, ny = -dy / L, dx / L
        worst = 1.0
        for t in np.linspace(inset, 1 - inset, max(8, int(L / 1.2))):
            cx, cy = x0 + dx * t, y0 + dy * t
            best = 0.0
            for o in np.linspace(-halfwidth, halfwidth, 9):
                xx, yy = int(round(cx + nx * o)), int(round(cy + ny * o))
                if 0 <= yy < self.H and 0 <= xx < self.W:
                    best = max(best, self.a[yy, xx])
            worst = min(worst, best)
            if worst <= 0.02:
                break
        return float(worst)

    @staticmethod
    def point_seg(p, u, v):
        vx, vy = v[0] - u[0], v[1] - u[1]
        L2 = vx * vx + vy * vy
        if L2 < 1e-9:
            return 1e9, 0.0
        t = ((p[0] - u[0]) * vx + (p[1] - u[1]) * vy) / L2
        tc = min(1.0, max(0.0, t))
        return float(np.hypot(p[0] - (u[0] + vx * tc), p[1] - (u[1] + vy * tc))), float(t)

    def edges(self, P):
        n = len(P)
        cand = []
        for i in range(n):
            for j in range(i + 1, n):
                L = float(np.hypot(P[i][0] - P[j][0], P[i][1] - P[j][1]))
                if L <= MAX_LEN and self.profile(P[i], P[j]) >= EDGE_THR:
                    cand.append((i, j))
        keep = []
        for (i, j) in cand:
            if not any(
                (lambda dt: 0.05 < dt[1] < 0.95 and dt[0] < SHADOW_D)(
                    self.point_seg(P[k], P[i], P[j]))
                for k in range(n) if k not in (i, j)
            ):
                keep.append((i, j))
        return keep

    # -- residual ------------------------------------------------------------
    def coverage(self, P, E):
        ink = self.a > INK_THR
        cov = np.zeros((self.H, self.W), dtype=bool)

        def disk(cx, cy, r):
            x0, x1 = max(0, int(cx - r) - 1), min(self.W, int(cx + r) + 2)
            y0, y1 = max(0, int(cy - r) - 1), min(self.H, int(cy + r) + 2)
            cov[y0:y1, x0:x1] |= ((self.xx[y0:y1, x0:x1] - cx) ** 2
                                  + (self.yy[y0:y1, x0:x1] - cy) ** 2 <= r * r)

        for (x, y) in P:
            disk(x, y, 6.0)
        for (i, j) in E:
            (x0, y0), (x1, y1) = P[i], P[j]
            L = max(2, int(np.hypot(x1 - x0, y1 - y0)))
            for t in np.linspace(0, 1, L * 2):
                disk(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 2.5)
        return ink, cov

    @staticmethod
    def label(mask):
        H, W = mask.shape
        lab = np.zeros(mask.shape, dtype=np.int32)
        cur = 0
        ys, xs = np.nonzero(mask)
        for sy, sx in zip(ys, xs):
            if lab[sy, sx]:
                continue
            cur += 1
            st = [(sy, sx)]
            lab[sy, sx] = cur
            while st:
                y, x = st.pop()
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx < W and mask[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = cur
                            st.append((ny, nx))
        return lab, cur

    def close_residual(self, P, E, passes=3, verbose=True):
        """Attach leftover strokes, adding bare vertices where the artwork bends
        without a dot. Returns the index where bare vertices start."""
        P = [list(p) for p in P]
        E = [tuple(e) for e in E]
        n_dots = len(P)

        def attach(px, py):
            best, bd = None, 1e9
            for k, (x, y) in enumerate(P):
                d = np.hypot(px - x, py - y)
                if d < bd:
                    best, bd = k, d
            if bd <= SNAP:
                return best
            P.append([float(px), float(py)])
            return len(P) - 1

        for it in range(passes):
            ink, cov = self.coverage(P, E)
            lab, n = self.label(ink & ~cov)
            added = 0
            for i in range(1, n + 1):
                ys, xs = np.nonzero(lab == i)
                if len(ys) < MIN_BLOB:
                    continue
                pts = np.stack([xs, ys], 1).astype(float)
                c = pts.mean(0)
                _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
                t = (pts - c) @ vt[0]
                p0, p1 = c + vt[0] * t.min(), c + vt[0] * t.max()
                if np.hypot(*(p1 - p0)) < 8:
                    continue
                A, B = attach(*p0), attach(*p1)
                if A != B and (A, B) not in E and (B, A) not in E:
                    E.append((A, B))
                    added += 1
            if verbose:
                ink, cov = self.coverage(P, E)
                print(f"  pass {it+1}: +{added} edges, "
                      f"coverage {100*(ink&cov).sum()/ink.sum():.1f}%", file=sys.stderr)
            if not added:
                break
        return P, E, n_dots


def to_svg(P, E, radii, n_dots, size=1000.0, pad=14, label="", stroke=1.6, opacity=.55):
    xs = [p[0] for p in P]
    ys = [p[1] for p in P]
    x0, x1 = min(xs) - pad, max(xs) + pad
    y0, y1 = min(ys) - pad, max(ys) + pad
    w, h = x1 - x0, y1 - y0
    s = size / max(w, h)

    def T(p):
        return (p[0] - x0) * s, (p[1] - y0) * s

    lines = []
    for (i, j) in E:
        ax, ay = T(P[i])
        bx, by = T(P[j])
        lines.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}"/>')
    circles = []
    for k in range(n_dots):
        cx, cy = T(P[k])
        circles.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radii[k]*s:.1f}"/>')

    nl = "\n"
    aria = f' role="img" aria-label="{label}"' if label else ""
    title = f"{nl}  <title>{label}</title>" if label else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w*s:.1f} {h*s:.1f}"{aria}>{title}\n'
            f'  <g fill="none" stroke="currentColor" stroke-width="{stroke}" '
            f'stroke-linecap="round" opacity="{opacity}">\n'
            + nl.join("    " + l for l in lines)
            + '\n  </g>\n  <g fill="currentColor">\n'
            + nl.join("    " + c for c in circles)
            + '\n  </g>\n</svg>\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("image")
    ap.add_argument("-o", "--out", help="SVG path (default: stdout)")
    ap.add_argument("--json", help="also dump the raw graph here")
    ap.add_argument("--label", default="", help="SVG <title> / aria-label")
    ap.add_argument("--no-close", action="store_true",
                    help="skip residual closing (no bare vertices)")
    args = ap.parse_args()

    ex = Extractor(args.image)
    P = ex.nodes()
    print(f"nodes: {len(P)}", file=sys.stderr)
    E = ex.edges(P)
    print(f"edges: {len(E)}", file=sys.stderr)
    n_dots = len(P)
    if not args.no_close:
        P, E, n_dots = ex.close_residual(P, E)
    ink, cov = ex.coverage(P, E)
    print(f"final: {len(P)} nodes ({n_dots} dots + {len(P)-n_dots} bare), "
          f"{len(E)} edges, coverage {100*(ink&cov).sum()/ink.sum():.1f}%", file=sys.stderr)

    radii = [ex.radius(*P[k]) for k in range(n_dots)]
    svg = to_svg(P, E, radii, n_dots, label=args.label)
    if args.out:
        open(args.out, "w").write(svg)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(svg)
    if args.json:
        json.dump({"w": ex.W, "h": ex.H, "dots": n_dots,
                   "nodes": [{"x": round(p[0], 2), "y": round(p[1], 2)} for p in P],
                   "edges": [list(e) for e in E]},
                  open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
