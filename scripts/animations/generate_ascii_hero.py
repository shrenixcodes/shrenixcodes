"""Hero animation: a lattice sculpture drawn in ASCII beside the name.

The sculpture is a sphere carved by a Schwarz P lattice, ray-marched in NumPy. It
turns a quarter of a revolution per loop; the lattice is symmetric under that turn
and the camera nods on a sine, so the last frame leads straight back into the first. The lower
part of the sculpture dissolves into horizontal signal streaks; a scan band and
two short, fixed glitch events are the only interference.

    python scripts/animations/generate_ascii_hero.py            # writes assets/animations/ascii-hero.{gif,png}
    python scripts/animations/generate_ascii_hero.py --fps 12 --seconds 5

Output is deterministic for a given font, size and configuration.
"""
import argparse
import math
import os

import numpy as np

from asciikit import Atlas, Palette, save_gif, scanlines, star, type_layer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# every printable ASCII character, plus the few symbols the labels use
GLYPHS = "".join(map(chr, range(32, 127))) + "·θ°"
RAMP = " .:icoO0@"  # flat areas: density ramp, dark to bright (rounded glyphs suit the forms)
EDGES = r".,'`-_|/\()<>^~=:;+"  # structured cells: shape-matched against these


# ---------------------------------------------------------------- scene
LATTICE_SCALE, LATTICE_WALL = 4.2, 0.5


def sdf(p, scale=None, wall=None):
    """A sphere carved by a Schwarz P lattice, around a small solid core.

    The P surface (cos x + cos y + cos z) is unchanged by a quarter turn about any axis,
    which is what lets a 90 degree rotation loop seamlessly.
    """
    scale = scale or LATTICE_SCALE
    wall = wall or LATTICE_WALL
    r = np.linalg.norm(p, axis=-1)
    q = p * scale
    field = np.cos(q[..., 0]) + np.cos(q[..., 1]) + np.cos(q[..., 2])
    shell = (np.abs(field) - wall) / (scale * 1.8)
    lattice = np.maximum(r - 1.0, shell)
    return np.minimum(lattice, r - 0.34)


def rot(yaw, pitch):
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    return ry @ rx


def render(w, h, t, aspect):
    """Grayscale render (h, w) in 0..1 of the sculpture at loop time t in [0, 1)."""
    phase = 2 * math.pi * t
    # a quarter turn per loop around the object's own axis, with a gentle nod of the camera
    R = rot(.35 + math.pi / 2 * t, .42 + .05 * math.sin(phase))
    ys, xs = np.mgrid[0:h, 0:w]
    u = (xs + .5) / w * 2 - 1
    v = 1 - (ys + .5) / h * 2
    rd = np.stack([u * aspect, v, np.full_like(u, 2.7)], -1)
    rd /= np.linalg.norm(rd, axis=-1, keepdims=True)
    rd = (rd @ R.T).reshape(-1, 3)
    ro = np.array([0, 0, -3.65]) @ R.T
    light = (np.array([-.5, .6, -.62]) / np.linalg.norm([-.5, .6, -.62])) @ R.T  # fixed to the camera

    dist = np.full(len(rd), 2.0)
    hit = np.zeros(len(rd), bool)
    live = np.ones(len(rd), bool)
    for _ in range(110):
        idx = np.nonzero(live)[0]
        if not len(idx):
            break
        d = sdf(ro + rd[idx] * dist[idx, None])
        dist[idx] += d * 0.8
        done = d < 1e-3
        hit[idx[done]] = True
        live[idx[done | (dist[idx] > 4.6)]] = False

    out = np.zeros(len(rd))
    idx = np.nonzero(hit)[0]
    p = ro + rd[idx] * dist[idx, None]
    n = np.stack([sdf(p + o) - sdf(p - o) for o in np.eye(3) * 2e-3], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9
    diff = np.clip(n @ light, 0, 1)
    rim = (1 - np.clip((n * -rd[idx]).sum(-1), 0, 1)) ** 3
    ao = np.clip(sdf(p + n * .1) / .1, 0, 1)
    r = np.linalg.norm(p, axis=-1)
    core = np.clip((0.40 - r) / 0.08, 0, 1)  # the inner core reads as a lit nucleus
    shade = (0.04 + 1.1 * diff ** 1.2) * (0.15 + 0.85 * ao) + 0.25 * rim * diff + 0.35 * core
    fog = np.exp(-np.clip(dist[idx] - 2.5, 0, None) * 1.6)  # far side sinks into the dark
    out[idx] = np.clip(shade * fog, 0, 1)
    return out.reshape(h, w)


def local_contrast(img, radius=6, amount=1.2):
    """Unsharp mask with a box blur: lifts hole rims and silhouettes before glyph mapping."""
    k = 2 * radius + 1
    pad = np.pad(img, radius, mode="edge")
    c = pad.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    blur = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    return np.clip(img + amount * (img - blur), 0, 1)


def hashrow(n, seed):
    return np.modf(np.sin(np.arange(n) * 12.9898 + seed * 78.233) * 43758.5453)[0] % 1


def dissolve(img, t, start=.70):
    """Lower part of the sculpture smears sideways into thin horizontal streams."""
    h, w = img.shape
    out = img.copy()
    r1, r2 = hashrow(h, 1), hashrow(h, 2)
    for y in range(int(h * start), h):
        k = (y / h - start) / (1 - start)
        shift = int(round(k * k * w * .22 * math.sin(2 * math.pi * (t + r1[y]))))
        row = np.roll(img[y], shift)
        if r2[y] < .3 * k:  # a few rows trail off into faint streaks
            trail = row.copy()
            for x in range(1, w):
                trail[x] = max(row[x], trail[x - 1] * .9)
            row = np.maximum(row, trail * .45)
        out[y] = row * (1 - .55 * k)
    return out


# ---------------------------------------------------------------- frames
def build(args):
    """Two grids share one canvas: 11px type on the left, a finer 9px grid for the sculpture."""
    atlas = Atlas(size=args.font_size, glyphs=GLYPHS)
    fine = Atlas(size=args.sculpture_font_size, glyphs=GLYPHS)
    cols, rows = args.width // atlas.cw, args.height // atlas.ch
    W, H = cols * atlas.cw, rows * atlas.ch
    pal = Palette(steps=16, accents=["#ff2a2a"])

    # sculpture box (pixels) on the right; the left is type and negative space
    bx0, by0 = int(W * .44), 4
    scols, srows = (W - 8 - bx0) // fine.cw, (H - 8) // fine.ch
    sw, sh = scols * fine.sx * 2, srows * fine.sy * 2
    aspect = (scols * fine.cw) / (srows * fine.ch)

    # the name is set as crisp type: it has to read at a glance, the sculpture carries the texture
    left = 4
    bold = atlas.font_path.replace("consola.ttf", "consolab.ttf")
    bold = bold if os.path.exists(bold) else atlas.font_path
    name = type_layer(W, H, bold, [(left * atlas.cw - 2, 4 * atlas.ch, "SHREYAN", 50, 1.0, 3),
                                   (left * atlas.cw - 2, 4 * atlas.ch + 58, "BAG", 50, 1.0, 3)])

    # glitch events: (centre in loop time, half-width, first row, last row as fractions of the box, shift in cells)
    events = [(.21, .02, .30, .38, 3), (.64, .03, .55, .66, -5)]
    n = int(round(args.fps * args.seconds))
    frames, stills = [], []
    for f in range(n):
        t = f / n

        # sculpture layer
        img = render(sw, sh, t, aspect)
        img = img.reshape(sh // 2, 2, sw // 2, 2).mean(axis=(1, 3))
        img = dissolve(local_contrast(img, 6, 1.2), t)
        sidx, mean = fine.match_hybrid(np.clip(img * 1.65, 0, 1), srows, scols, RAMP, EDGES,
                                       edge_threshold=.3, contrast=1.6, gamma=.85)
        # brightness per cell in six steps: crisp glyphs and a small palette
        slvl = np.where(sidx > 0, np.ceil(np.clip(.22 + mean * 1.8, 0, 1) * 6) / 6, 0)
        gs = fine.compose(sidx, slvl)
        # localized glitch: a band of rows jumps sideways, leaving a faint echo where it was
        glitch = None
        for centre, half, fa, fb, shift in events:
            if abs(((t - centre + .5) % 1) - .5) < half:
                ya, yb_ = int(fa * srows) * fine.ch, int(fb * srows) * fine.ch
                band = gs[ya:yb_].copy()
                gs[ya:yb_] = np.maximum(np.roll(band, shift * fine.cw, axis=1) * 1.15, band * .3)
                glitch = (ya, yb_)

        # type layer
        idx = np.zeros((rows, cols), int)
        lvl = np.zeros((rows, cols))
        for r, text, l, indent in [(2, "shrenixcodes", .78, 2),
                                   (20, "ai/ml  ·  backend  ·  real-time systems", .74, 0),
                                   (21, "b.tech cse (ai & ml)  ·  srm ist", .52, 0)]:
            atlas.text_cells(idx, r, left + indent, text)
            lvl[r, left + indent:left + indent + len(text)] = l
        readout = "schwarz-p lattice   θ {:5.1f}°".format(20 + 90 * t)
        atlas.text_cells(idx, rows - 3, left, readout)
        lvl[rows - 3, left:left + len(readout)] = .42
        stamp = "{:03d}/{:03d}".format(f + 1, n)
        atlas.text_cells(idx, rows - 3, left + 36, stamp)
        lvl[rows - 3, left + 36:left + 36 + len(stamp)] = .3

        g = np.maximum(atlas.compose(idx, lvl), name)
        g[by0:by0 + gs.shape[0], bx0:bx0 + gs.shape[1]] = np.maximum(g[by0:by0 + gs.shape[0], bx0:bx0 + gs.shape[1]], gs)

        # a scan band drifting down once per loop shears a few pixel rows
        yb = int(t * H)
        for y in range(max(0, yb - 7), min(H, yb + 7)):
            g[y] = np.roll(g[y], int(round(2 * math.sin((y - yb) * .9)))) * 1.08
        g = scanlines(np.clip(g, 0, 1), .22)

        q = pal.quantize(g)
        star(q, left * atlas.cw + 4, 2 * atlas.ch + atlas.ch // 2, 5.5, pal.accent(0))
        frames.append(pal.image(q))
        if glitch is None:
            stills.append((f, pal.image(q)))
    return frames, stills, (W, H)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=380)
    ap.add_argument("--font-size", type=int, default=11, help="type grid")
    ap.add_argument("--sculpture-font-size", type=int, default=9, help="sculpture grid")
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--still", type=int, default=0, help="frame used for the static PNG")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "animations", "ascii-hero"))
    args = ap.parse_args()

    frames, stills, size = build(args)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    save_gif(frames, args.out + ".gif", args.fps)
    still = dict(stills).get(args.still, stills[0][1])
    still.save(args.out + ".png", optimize=True)
    print("wrote", args.out + ".gif", size, len(frames), "frames",
          "{:.0f} KB".format(os.path.getsize(args.out + ".gif") / 1024))


if __name__ == "__main__":
    main()
