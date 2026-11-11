# ascii animations

The animations in `assets/animations/` are rendered here, offline and deterministically.
Nothing in this folder runs in CI.

The hero is an animated SVG (rows of text, one group per frame, switched by CSS) rather
than a GIF: GitHub wraps README GIFs in a player that stays paused for visitors whose
system asks for reduced motion, and SVG images are not wrapped.

```bash
pip install -r scripts/animations/requirements.txt
python scripts/animations/generate_ascii_hero.py        # ascii-hero.svg + .png (add --gif for a GIF)
python scripts/animations/generate_ascii_secondary.py   # ascii-secondary.gif + .png
```

Both accept `--fps`, `--seconds`, `--width`, `--height`, `--still` and `--out`; run with
`--help` for the rest.

| file | what it does |
|---|---|
| `asciikit.py` | glyph atlas, shape-matched and edge-aware glyph mapping, fixed GIF palette, scanlines, crisp type |
| `generate_ascii_hero.py` | a ray-marched sphere carved by a Schwarz P lattice, turning a quarter revolution per loop |
| `generate_ascii_secondary.py` | a visual voice-activity scope: mouth, mouth-aspect-ratio trace, hysteresis events (synthetic input) |

**How the characters are picked.** Each glyph is drawn once and its ink measured in a
2 × 4 grid of sub-cells. Flat regions take a density ramp (`" .:icoO0@"`); cells with
real structure inside them take whichever edge glyph (`/ \ | _ ( ) ...`) has the closest
ink layout. Brightness is quantised to six steps per cell and the palette is fixed
across frames, which keeps glyphs crisp and lets the GIF store only changed regions.

**Seamless loops.** The hero's lattice is symmetric under a quarter turn, so rotating
exactly 90° per loop returns to the first frame. The scope's signal is periodic in the
loop, and its state machine is run for two loops before recording.

**Fonts.** Rendered with Consolas (glyph grid) and Consolas Bold (name). Elsewhere it
falls back to DejaVu Sans Mono, or set `ASCII_FONT=/path/to/mono.ttf`. A different font
gives slightly different glyph choices.
