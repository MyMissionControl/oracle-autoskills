---
name: pixel-sprite-generator-pipeline
description: 'Use when building a set of animated pixel-art sprites for a UI: generate grids from shape specs in a resolution-independent design space instead of hand-typing them, and guard the two faults review…'
installer: auto-skill
created_at: 2026-08-28T15:49:01+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'graphics'
content_hash: 17822d3ae54ab196da8045fb80697fb6ea3aadccb739e5d052a739c7dd258b76
---
# Generate a pixel-art sprite set from shape specs (not hand-typed grids)

Use when a UI needs a small set of animated pixel characters/icons drawn as data
(canvas or DOM), and hand-authoring the grids is on the table. Hand-typing dies
at the second revision: one 24x24 sprite with 3 frames is 1,728 cells, and the
grid size is *always* wrong on the first two tries.

## 1. Author in a design space, rasterise into N

Never bake the output resolution into the coordinates.

```python
D = 32          # design units — every shape is written against this
N = 24          # actual grid; the only number that changes
def s(v): return v * N / D
```

Primitives (`ellipse`, `rect`, `triangle`) scale their inputs by `N/D`. Creature
code addresses `D` only — including full-width clears (`rect(0, y, D-1, D-1)`),
which is the one place the two spaces are easy to confuse.

Payoff: "too blocky" → "too smooth" → "just right" costs one integer, not a
re-tune of ~40 coordinates per character.

## 2. Two failure modes that are invisible in review

**Draw order erases limbs.** Anything cut flat with a full-width clear wipes
whatever was painted before it. Legs and necks vanish silently and the sprite
still looks plausible. Draw back-to-front and put everything that must survive
*after* the last clear. Expect to hit this more than once per character.

**Sub-pixel motion rounds away.** A 1-unit bob is `1 * N/D` px. At N=24 that is
0.75 and rounds to nothing, so a 3-frame walk silently becomes 2 frames — it
still animates, so nothing looks broken. Make motion offsets >= 2 design units,
and **assert it in the generator**:

```python
assert len({''.join(rows) for rows in frames}) == FRAMES, \
    f"{name}: only {len(seen)} distinct frames of {FRAMES} — an offset rounded away at N={N}"
```

That assert fires the instant N drops. Without it the regression ships.

## 3. Zones, not colours

Store zone indices ('1'..'5'), never colour values. The renderer looks each
index up in a palette supplied at runtime, so recolouring needs no new asset and
the same grid serves every colour a user picks. Keep the palette's source of
truth on the server if the colours are user-editable; a second copy in the
client bundle drifts the first time anyone tweaks one.

Guard in the test suite, not by eye:
- every frame is exactly `N` rows of `N` legal characters
- every sprite uses **all** zones — a zone drawn nowhere is a colour picker that
  visibly does nothing
- every frame in a cycle is pairwise distinct (adjacent-only is too weak: a
  2-beat limb swap against a 2-beat bob makes frame 0 == frame 2)
- silhouettes are pairwise distinct across the set, if they must be told apart
  when painted the same colour

## 4. Look at it, every round

Emit a PNG contact sheet (all characters x all frames) from the same script and
**actually open it** after every change. A hand-rolled PNG writer is ~15 lines
of `zlib` + `struct` — no image library needed:

```python
raw = b''.join(b'\x00' + b''.join(struct.pack('BBB', *px) for px in row) for row in buf)
chunk = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d))
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) \
      + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
```

Zoom (`cell=10+`) on any character that looks off. Faults found only this way,
never by reading the grid: a nose ellipse fusing with the stroke beneath it into
a black plus sign; two same-coloured ovals reading as one blob; a fill one shade
off its neighbour being invisible no matter how it is drawn (that is a palette
bug, not a drawing bug).

## 5. Ship both halves

Commit the generator next to the generated file, and mark the output
`GENERATED — do not edit by hand` with the exact command to regenerate. The
grids are unreviewable and unmergeable; the shape spec is the real source.

Keep the on-screen size stable across resolution changes by making cell size
inverse to N (`24 x 8` and `32 x 6` are both 192px), so a resolution experiment
never doubles as a layout change.
