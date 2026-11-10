"""Small ASCII rendering toolkit shared by the profile animations.

Characters are chosen by shape rather than brightness alone: every glyph is drawn
once, its ink is measured in a grid of sub-cells, and each cell of the source image
takes the glyph whose ink layout is closest. Edges therefore come out as / \\ | _
and friends instead of a stair-step of brightness levels.

The idea of matching glyphs by sub-cell shape is the one described by Alex Harri
("ASCII characters are not pixels") and used by ascii.rest; this is an independent
NumPy implementation.

Dependencies: Pillow, NumPy.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    os.environ.get("ASCII_FONT", ""),
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
]

# space first: it is what an empty cell turns into
DEFAULT_GLYPHS = " .,:;'`-_~=+*^\"!/\\|()<>[]{}ilrsvxzcXA253hMHGS#9B&@08oO"


def find_font(candidates=FONT_CANDIDATES):
    for path in candidates:
        if path and os.path.exists(path):
            return path
    raise SystemExit("no monospace font found; set ASCII_FONT to a .ttf path")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Atlas:
    """Glyph bitmaps of one monospace font at one size, plus their shape vectors."""

    def __init__(self, size=11, glyphs=DEFAULT_GLYPHS, font_path=None, sub=(2, 4)):
        self.font_path = font_path or find_font()
        font = ImageFont.truetype(self.font_path, size)
        ascent, descent = font.getmetrics()
        self.cw = int(round(font.getlength("M")))
        self.ch = ascent + descent
        self.sx, self.sy = sub
        self.glyphs = glyphs
        maps = []
        for c in glyphs:
            im = Image.new("L", (self.cw, self.ch), 0)
            ImageDraw.Draw(im).text((0, 0), c, font=font, fill=255)
            maps.append(np.asarray(im, np.float32) / 255)
        self.bitmaps = np.stack(maps)  # (G, ch, cw)
        self.vectors = self._pool(self.bitmaps)
        self.vectors /= self.vectors.max()

    def _pool(self, maps):
        """Mean ink of each glyph in an sx-by-sy grid of sub-cells."""
        g = maps.shape[0]
        ys = np.linspace(0, self.ch, self.sy + 1).round().astype(int)
        xs = np.linspace(0, self.cw, self.sx + 1).round().astype(int)
        out = np.empty((g, self.sy * self.sx), np.float32)
        for j in range(self.sy):
            for i in range(self.sx):
                out[:, j * self.sx + i] = maps[:, ys[j]:ys[j + 1], xs[i]:xs[i + 1]].mean(axis=(1, 2))
        return out

    def index(self, chars):
        return [self.glyphs.index(c) for c in chars]

    def match(self, src, rows, cols, contrast=1.6, allowed=None):
        """Pick a glyph per cell for a source image of shape (rows*sy, cols*sx) in 0..1.

        contrast pushes each cell's sub-cells away from their mean before matching, which
        favours glyphs that follow edges over flat mid-density fill.
        """
        v = src.reshape(rows, self.sy, cols, self.sx).transpose(0, 2, 1, 3).reshape(rows * cols, -1)
        allowed = range(len(self.glyphs)) if allowed is None else allowed
        return self._match_vectors(v, contrast, list(allowed)).reshape(rows, cols)

    def match_hybrid(self, src, rows, cols, ramp, edges, edge_threshold=.18, contrast=1.8, gamma=1.0):
        """Edge-aware mapping: flat cells take a density ramp, cells with real structure take
        the edge glyph whose shape fits best.

        Returns glyph indices and each cell's mean brightness.
        """
        v = src.reshape(rows, self.sy, cols, self.sx).transpose(0, 2, 1, 3).reshape(rows * cols, -1)
        mean = v.mean(axis=1)
        spread = v.max(axis=1) - v.min(axis=1)
        ramp_idx = np.asarray(self.index(ramp))
        k = np.clip(mean ** gamma * (len(ramp) - 1) + .5, 0, len(ramp) - 1).astype(int)
        out = ramp_idx[k]
        sel = (spread > edge_threshold) & (mean > .04)
        if sel.any():
            out[sel] = self._match_vectors(v[sel], contrast, self.index(edges))
        return out.reshape(rows, cols), mean.reshape(rows, cols)

    def _match_vectors(self, v, contrast, allowed):
        m = v.mean(axis=1, keepdims=True)
        v = np.clip(m + (v - m) * contrast, 0, 1)
        g = self.vectors[allowed]
        d = (v * v).sum(1)[:, None] - 2 * v @ g.T + (g * g).sum(1)[None, :]
        return np.asarray(allowed)[d.argmin(axis=1)]

    def text_cells(self, idx, row, col, text):
        """Write plain text into a glyph-index grid (characters missing from the atlas become spaces)."""
        for k, c in enumerate(text):
            if 0 <= col + k < idx.shape[1]:
                idx[row, col + k] = self.glyphs.index(c) if c in self.glyphs else 0

    def compose(self, idx, level):
        """Glyph grid and per-cell intensity (0..1) -> grayscale image in 0..1."""
        rows, cols = idx.shape
        tiles = self.bitmaps[idx] * level[:, :, None, None]
        return tiles.transpose(0, 2, 1, 3).reshape(rows * self.ch, cols * self.cw)


class Palette:
    """A fixed GIF palette: `steps` tones from background to ink, then any accent colours.

    Using one palette for every frame keeps colours stable and lets the GIF encoder
    store only the pixels that change between frames.
    """

    def __init__(self, bg="#07080b", ink="#eef1f8", steps=16, accents=()):
        b, k = np.array(hex_rgb(bg), float), np.array(hex_rgb(ink), float)
        ramp = [b + (k - b) * (i / (steps - 1)) ** 1.15 for i in range(steps)]
        self.steps = steps
        self.colors = [tuple(int(round(x)) for x in c) for c in ramp] + [hex_rgb(a) for a in accents]
        self.flat = [x for c in self.colors for x in c] + [0] * (768 - 3 * len(self.colors))

    def accent(self, i):
        return self.steps + i

    def quantize(self, gray):
        """0..1 grayscale -> palette indices on the background-to-ink ramp."""
        return np.clip(np.round(gray * (self.steps - 1)), 0, self.steps - 1).astype(np.uint8)

    def image(self, indices):
        im = Image.fromarray(indices, "P")
        im.putpalette(self.flat)
        return im


def save_gif(frames, path, fps):
    """Write palette frames as a looping GIF; Pillow stores each frame as a delta region."""
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=int(round(1000 / fps)),
                   loop=0, disposal=1, optimize=False)


def scanlines(img, strength=0.18):
    """Darken every other pixel row: the fine horizontal texture of an old monitor."""
    out = img.copy()
    out[1::2] *= 1 - strength
    return out


def type_layer(W, H, font_path, items):
    """Crisp text drawn straight onto the canvas: [(x, y, text, size, level, tracking)]."""
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for x, y, text, size, level, tracking in items:
        font = ImageFont.truetype(font_path, size)
        for c in text:
            d.text((x, y), c, font=font, fill=int(255 * level))
            x += font.getlength(c) + tracking
    return np.asarray(im, np.float32) / 255


def star(img, cx, cy, r, value):
    ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    dx, dy = np.abs(xs - cx) / r, np.abs(ys - cy) / r
    img[(np.sqrt(dx) + np.sqrt(dy)) <= 1] = value
