---
name: prove-css-paint-order-bug-headless
description: 'Use when a visual CSS defect (background seam, wrong layer on top, ''does not fill the screen'') must be proven from pixels: faithful repro, headless chromium shot, pixel measurement, controls.'
installer: auto-skill
created_at: 2026-08-03T11:12:46+07:00
created_session: 
trigger: reusable-workflow
created_by: subagent:leaderboard-darkmode-investigation
category: frontend
content_hash: 0585a6db29a16e34481abb05ea62caf50fa2d9207d59f025cd7f77abb8e6212c
edited_at: 2026-08-07T09:25:25+07:00
edited_by: skills-mcp
---
# Prove a CSS background / paint-order bug with headless chromium

Use when someone reports a visual defect ("background doesn't fill the screen",
"seam", "grid only shows at the bottom", "wrong layer on top") and you must
prove or refute it from pixels instead of reasoning about CSS in your head.

## 1. Build a faithful static repro, not the whole app

Copy the load-bearing rules **verbatim** out of the real stylesheet (token
block, the `html`/`body` rules, the pseudo-element) into one self-contained
`.html`. Drop framework directives (`@tailwind ...`) and hand-write only the
few utility classes the layout needs. Hardcode the theme attribute on `<html>`.

Then **prove the copy is faithful** — do not trust your own transcription:

```python
real = open('<path>/globals.css').read(); repro = open('repro.html').read()
def block(src, sel):
    i = src.index(sel); return src[i:src.index('}', i) + 1]
for sel in ['html,\nbody {', 'body::before {']:
    print('MATCH' if block(real, sel) in repro else 'DIFFER', sel)
```

Also re-add the framework's reset bits that change geometry (`body{margin:0}`,
`*{box-sizing:border-box}`) or the repro will not match the real page.

## 2. Render

```bash
chromium-browser --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --window-size=1440,1200 --screenshot=OUT.png --virtual-time-budget=2000 file://ABS/repro.html
```

**Snap gotcha:** a snap-packaged chromium has a private `/tmp`, so it silently
renders nothing and fails with `Failed to write file ...: Permission denied`.
Put the html + png under a NON-hidden dir in `$HOME` (the snap `home`
interface excludes dotdirs), render there, copy back to the scratchpad after.

### Geometry numbers, not just pixels

For "these two things are not aligned / not the same size", a screenshot is the
symptom; the numbers are the diagnosis. Append a probe that writes
`getBoundingClientRect()` + `getComputedStyle()` of each suspect **into a DOM
node**, then read it back:

```bash
chromium --headless --disable-gpu --no-sandbox --virtual-time-budget=4000 \
  --dump-dom file://ABS/page.html | grep -o "ZZMARK.*ZZEND"
```

- Use `--headless`, not `--headless=new` — the latter wrote an **empty** dump here.
- `document.title` changes do not survive `--dump-dom`; append a `<div>` instead.
- Pick a marker that cannot appear in minified JS (`||` matched hundreds of
  boolean-or operators before `ZZMARKZZ` worked).
- Print `marginTop/marginBottom` and the **parent's** rect and `align-items`.
  That is what catches the real culprit: a class collision, where a component
  modifier (`class="btn sec"`) also matches a bare layout rule (`.sec {
  margin-bottom: 16px }`) and silently shifts one element. Guard it in a test:
  no button modifier class may also exist as a bare `.cls {` rule.

## 3. Read the PNG, then measure it

Look at the image first (a seam is obvious). Then get numbers — eyeballing
cannot tell a 9/255 delta from a JPEG-ish artifact. If Pillow and ImageMagick
are absent, a ~50-line pure-python PNG reader is enough (`zlib.decompress` +
undo the 5 per-scanline filters; assert `depth == 8 and interlace == 0`).

Sample a **gutter column** no content ever paints into, walk it top to bottom,
and report the first row whose color changes — that row is the seam, and it
equals the height of the box that is overpainting. Sample a span at least one
background-tile wide (e.g. 64px for a 44px grid) above and below the seam: if
the span above is a single uniform color, the layer is fully hidden there.

## 4. Three controls before you blame the fix

- **Determinism:** render the SAME file twice and diff. Any pixel difference
  here is renderer noise and invalidates fix-vs-original diffs.
- **Text antialiasing:** removing an opaque background can make the browser
  drop LCD subpixel text AA, which changes thousands of glyph pixels and looks
  like the fix broke the content. Confirm by re-rendering both with
  `--disable-lcd-text`; if the diff collapses to ~0, it is only an AA flip.
- **Renderer-vs-CSS:** any surprising render (blank frame, missing content)
  gets the same page rendered PRE-fix before you attribute it to the change.
  Identical md5 across pre and post means the renderer, not your CSS.

Scrolled screenshots are the common trap: `--screenshot` after a scroll (JS
`scrollTo`, `#fragment`, `--headless=new` alike) can write a content-free frame
of just the canvas color — same tiny byte count every time, and byte-identical
pre-fix. To verify a scrolled/tall state anyway, render the whole document in
one frame (`--window-size` taller than the content) and check the background is
uniform over the full height. That covers the layout question; viewport-locked
behavior while scrolling is a property of `position: fixed` /
`background-attachment: fixed` and does not need re-proving.

## 5. Prefer the fix that leaves content pixel-identical

Diff fixed-vs-original per region: opaque content boxes must show **0**
differing pixels; only the background region may change. When two fixes both
kill the seam, that diff is the tiebreaker.

## Painting order, the usual root cause

Inside the root stacking context: (1) canvas/root background, (2) negative
z-index descendants, (3) in-flow non-positioned block backgrounds, (5) inline
content, (6) z-index:0/auto positioned, (7) positive z-index. So a
`position:fixed; z-index:-1` decorative layer on `body` paints at step 2 and
`body`'s own opaque background erases it at step 3 — it survives only outside
the body box. Note step 3 also means bumping that layer to `z-index: 0` will
cover every non-positioned card background too, unless the content wrapper
isolates. Safest fix is usually to move the decoration into the background of
the element that was overpainting it, plus a `min-height` so its box reaches
the viewport.
