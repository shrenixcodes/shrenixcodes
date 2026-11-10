"""Secondary animation: a visual voice-activity scope, drawn in ASCII.

A mouth opens and closes on the left; on the right its mouth-aspect-ratio trace
scrolls past two thresholds, and a hysteresis state machine (separate start and
end thresholds, each with a hold time) turns it into speech_start / speech_end
events. The input is a synthetic, periodic signal, not recorded data, and the
image says so. The state machine runs for two loops before recording, so the
recorded loop starts in exactly the state it ends in.

    python scripts/animations/generate_ascii_secondary.py   # writes assets/animations/ascii-secondary.{gif,png}
"""
import argparse
import math
import os

import numpy as np

from asciikit import Atlas, Palette, save_gif, scanlines, star, type_layer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GLYPHS = "".join(map(chr, range(32, 127))) + "·→●○"
RAMP = " .:icoO0@"
EDGES = r".,'`-_|/\()<>^~=:;+"
SUB = 4  # signal samples per frame
START, END, START_HOLD, END_HOLD, ALPHA = .45, .24, .16, .55, .3  # thresholds, holds in seconds, EMA


# ---------------------------------------------------------------- signal
def smooth_window(x, a, b, edge=.04):
    up = np.clip((x - a) / edge, 0, 1)
    down = np.clip((b - x) / edge, 0, 1)
    w = np.minimum(up, down)
    return w * w * (3 - 2 * w)


def mar_signal(n):
    """Mouth aspect ratio over one loop of n samples; every term is periodic in the loop."""
    x = np.arange(n) / n
    base = .10 + .025 * np.sin(2 * np.pi * 3 * x) + .015 * np.sin(2 * np.pi * 7 * x + 1)
    envelope = smooth_window(x, .12, .40) + smooth_window(x, .56, .82)
    syllables = (.5 + .5 * np.sin(2 * np.pi * 14 * x)) ** 1.5
    return base + envelope * (.30 + .30 * syllables)


def run_state_machine(raw, seconds):
    """EMA + hysteresis over three loops; returns the third loop's EMA, state and events."""
    n = len(raw)
    hold_start = int(round(START_HOLD / seconds * n))
    hold_end = int(round(END_HOLD / seconds * n))
    ema, speaking, above, below = raw[0], False, 0, 0
    trace, state, events = [], [], []
    for i in range(3 * n):
        ema = ALPHA * raw[i % n] + (1 - ALPHA) * ema
        above = above + 1 if ema > START else 0
        below = below + 1 if ema < END else 0
        if not speaking and above >= hold_start:
            speaking = True
            if i >= 2 * n:
                events.append((i - 2 * n, "speech_start", ema))
        elif speaking and below >= hold_end:
            speaking = False
            if i >= 2 * n:
                events.append((i - 2 * n, "speech_end", ema))
        if i >= 2 * n:
            trace.append(ema)
            state.append(speaking)
    return np.array(trace), np.array(state), events


# ---------------------------------------------------------------- drawing
def smoothstep(e0, e1, x):
    k = np.clip((x - e0) / (e1 - e0), 0, 1)
    return k * k * (3 - 2 * k)


def mouth(w, h, opening):
    """Lips around a dark opening, lit from above; (h, w) in 0..1."""
    ys, xs = np.mgrid[0:h, 0:w]
    u = (xs + .5) / w * 2 - 1
    v = 1 - (ys + .5) / h * 2
    u, v = u * 1.12, v * .62  # lips fill the box rather than a thin strip
    span = np.clip(1 - u * u, 0, 1)
    half = opening / 2 * span ** .7
    upper = half + .30 * span ** .85 - .07 * np.exp(-(u / .14) ** 2)  # cupid's bow
    lower = -(half + .34 * span ** .8)
    soft = .035
    lips = smoothstep(-soft, soft, upper - v) * smoothstep(-soft, soft, v - lower)
    inside = smoothstep(-soft, soft, half - np.abs(v))
    lip = lips * (1 - inside)
    # upper lip brightest along the opening, lower lip catches the light on its top edge
    shade = np.where(v > 0, .55 + .35 * (1 - (v - half) / (upper - half + 1e-6)),
                     .75 + .25 * (v - lower) / (np.abs(lower) + 1e-6))
    teeth = inside * smoothstep(half - .05, half - .01, v) * (opening > .08) * .45
    return np.clip(lip * np.clip(shade, .35, 1) + teeth, 0, 1)


def polyline(w, h, xs, ys, width=1.2):
    """Anti-aliased polyline into a (h, w) image."""
    img = np.zeros((h, w))
    gy, gx = np.mgrid[0:h, 0:w]
    for (x0, y0), (x1, y1) in zip(zip(xs[:-1], ys[:-1]), zip(xs[1:], ys[1:])):
        lo, hi = int(max(0, min(x0, x1) - 3)), int(min(w, max(x0, x1) + 4))
        px, py = gx[:, lo:hi], gy[:, lo:hi]
        dx, dy = x1 - x0, y1 - y0
        L = dx * dx + dy * dy or 1
        k = np.clip(((px - x0) * dx + (py - y0) * dy) / L, 0, 1)
        d = np.hypot(px - (x0 + k * dx), py - (y0 + k * dy))
        img[:, lo:hi] = np.maximum(img[:, lo:hi], np.clip(width - d + .5, 0, 1))
    return img


# ---------------------------------------------------------------- frames
def build(args):
    W, H = args.width, args.height
    fine = Atlas(size=9, glyphs=GLYPHS)
    mono = fine.font_path
    pal = Palette(steps=16, accents=["#ff2a2a"])
    n = int(round(args.fps * args.seconds))
    raw = mar_signal(n * SUB)
    trace, state, events = run_state_machine(raw, args.seconds)

    # mouth box and plot box, in pixels
    mx0, my0, mcols, mrows = 28, 52, 40, 12
    px0, py0, pcols, prows = 268, 46, 76, 13
    vmax = .8

    frames, stills = [], []
    for f in range(n):
        g = np.zeros((H, W))
        now = f * SUB  # newest sample shown

        # mouth
        m = mouth(mcols * fine.sx * 2, mrows * fine.sy * 2, raw[now] * .55)
        m = m.reshape(mrows * fine.sy, 2, mcols * fine.sx, 2).mean(axis=(1, 3))
        mi, mm = fine.match_hybrid(m, mrows, mcols, RAMP, EDGES, edge_threshold=.3, contrast=1.6)
        ml = np.where(mi > 0, np.ceil(np.clip(.25 + mm * 1.5, 0, 1) * 6) / 6, 0)
        mg = fine.compose(mi, ml)
        g[my0:my0 + mg.shape[0], mx0:mx0 + mg.shape[1]] = mg

        # trace: the last half loop of samples, newest on the right
        span = len(trace) // 2
        order = (np.arange(span) + now + 1 - span) % len(trace)
        vals, live = trace[order], state[order]
        sw, sh = pcols * fine.sx, prows * fine.sy
        xs = np.linspace(0, sw - 1, len(vals))
        ys = (1 - np.clip(vals / vmax, 0, 1)) * (sh - 2) + 1
        line = polyline(sw * 2, sh * 2, xs * 2, ys * 2, width=1.6)
        line = line.reshape(sh, 2, sw, 2).mean(axis=(1, 3))
        li, lm = fine.match_hybrid(line, prows, pcols, " .:", EDGES, edge_threshold=.2, contrast=1.8)
        lg = fine.compose(li, np.where(li > 0, .95, 0))
        # speaking spans: a faint floor of dots under the trace
        col_live = live[np.linspace(0, len(live) - 1, pcols).astype(int)]
        band = np.zeros((prows, pcols), int)
        band[-1] = np.where(col_live, fine.index("=")[0], fine.index(".")[0])
        lg = np.maximum(lg, fine.compose(band, np.where(col_live, .55, .18)[None].repeat(prows, 0)))
        g[py0:py0 + lg.shape[0], px0:px0 + lg.shape[1]] = np.maximum(g[py0:py0 + lg.shape[0], px0:px0 + lg.shape[1]], lg)

        # thresholds, labels, events
        items = [(28, 14, "visual vad", 11, .85, 2), (132, 14, "lip motion → speech events", 11, .55, 0),
                 (W - 128, 14, "synthetic input", 11, .4, 0),
                 (mx0, py0 + 13 * fine.ch + 8, "mouth roi", 10, .4, 0),
                 (px0, py0 + lg.shape[0] + 8, "mouth aspect ratio · ema · last 3 s", 10, .4, 0)]
        for thr, label, lvl in ((START, "start .45", .55), (END, "end .24", .35)):
            y = py0 + int((1 - thr / vmax) * (lg.shape[0] - 2)) + 1
            g[y, px0:px0 + lg.shape[1]:4] = np.maximum(g[y, px0:px0 + lg.shape[1]:4], lvl)
            items.append((px0 + lg.shape[1] + 6, y - 6, label, 9, lvl + .1, 0))
        past = [e for e in events if e[0] <= now] or [events[-1]] if events else []
        speaking = bool(state[now])
        if past:
            i, name, value = past[-1]
            ago = ((now - i) % len(trace)) / len(trace) * args.seconds
            items.append((W - 300, H - 26, "{:<13} ema {:.2f}   {:4.1f}s ago".format(name, value, ago), 10, .6, 0))
        items.append((46, H - 26, "speaking" if speaking else "idle", 10, .9 if speaking else .45, 0))
        g = np.maximum(g, type_layer(W, H, mono, items))
        g = scanlines(np.clip(g, 0, 1), .2)
        q = pal.quantize(g)
        dot = (34, H - 19)
        if speaking:
            star(q, dot[0], dot[1], 5, pal.accent(0))
        else:
            star(q, dot[0], dot[1], 4, pal.quantize(np.array([.35]))[0])
        frames.append(pal.image(q))
        stills.append(pal.image(q))
    return frames, stills, (W, H)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--width", type=int, default=720)
    ap.add_argument("--height", type=int, default=230)
    ap.add_argument("--fps", type=float, default=10)
    ap.add_argument("--seconds", type=float, default=6)
    ap.add_argument("--still", type=int, default=24, help="frame used for the static PNG")
    ap.add_argument("--out", default=os.path.join(ROOT, "assets", "animations", "ascii-secondary"))
    args = ap.parse_args()

    frames, stills, size = build(args)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    save_gif(frames, args.out + ".gif", args.fps)
    stills[min(args.still, len(stills) - 1)].save(args.out + ".png", optimize=True)
    print("wrote", args.out + ".gif", size, len(frames), "frames",
          "{:.0f} KB".format(os.path.getsize(args.out + ".gif") / 1024))


if __name__ == "__main__":
    main()
