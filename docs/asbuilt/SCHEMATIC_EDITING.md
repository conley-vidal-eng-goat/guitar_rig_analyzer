# How to update the as-built schematics

**Never hand-edit the `.svg` files — they are generated and will be overwritten.**
Edit [`tools/gen_schematic.py`](../../tools/gen_schematic.py), then:

```
python3 tools/gen_schematic.py
```

One source produces every deliverable, so the versions can never drift apart:

| File | What it is |
|---|---|
| `schematic_overview.svg` | One page — the whole signal path, readable at 1280 px wide. `overview()` draws it by hand, so **a change to the analog path has to be made there too** |
| `schematic_1sheet.svg` | Everything on one sheet — bench reconstruction reference |
| `schematic_sheet1_analog.svg` | Sheet 1 of 2 — power, references, analog front end, relay signal routing, Amp Out |
| `schematic_sheet2_digital.svg` | Sheet 2 of 2 — digital interface, reserved hardware, Pi link |
| `schematics.html` | A page that shows all four. Generated too |

No dependencies beyond the Python standard library.

---

## The three kinds of edit you will actually make

### 1. Change a value or a note

Values live inline in the `draw_*()` functions. To correct a resistor:

```python
a, b = s.res(680, 110, "R1", "47k", vert=True)
#                       ^ref   ^value
```

### 2. Change the Teensy ↔ Audio Shield connections

Edit the `INTERCONNECT` list near the top. Rows render top to bottom in order:

```python
INTERCONNECT = [
    # header pin, net,        direction, function
    ("8",         "I2S_DOUT", "l",       "codec → Teensy SAI1_RX_DATA0"),
]
```

### 3. Promote a block from planned to built

Three steps, and **step zero is `netlist.md`** — see house rule 5.

**Step one — remove the row from `FUTURE_ITEMS`** so it stops appearing in the
reserved block. A row leaves that list only when its `draw_*()` block exists,
**never because a phase is finished.** Hardware decided *against* stays in the
list with a `NOT BUILT` phase, which is why the four jack-detect rows are still
there, and `FUTURE_ITEMS` no longer carries the Pi link now that block H exists.

**Step two — write a `draw_*()` function** and call it from every composer in
`build()` that should carry it. Every block follows the same shape:

```python
def draw_relay_send(s, ox, oy):
    s.origin(ox, oy)                       # all coords below are block-relative
    s.blockframe(-30, -30, 1200, 600, "E — RELAY_SEND · K1 · PHASE 6 · cols 49–59")

    a, b = s.res(200, 250, "R6", "1k")     # returns (left_pin, right_pin)
    s.wire([b, (280, 250)])                # wire() takes a list of points
    s.junction(280, 250)
    s.gnd(280, 368)
    s.netlabel(130, 250, "TEENSY 14", "left")
```

Then in `build()`:

```python
draw_relay_send(s, 90, 1290)               # place at absolute (90, 1290)
```

**Step three — sweep the frozen blocks for statements the new hardware has just
falsified.** This is the step that gets skipped. Adding block F did not only add
a drawing: it made block C's `RETURN_NODE — NOT CONNECTED` callout **wrong**, and
made block B's J2 open stub **wrong**. A new block almost always invalidates
something older, and a drawing that still asserts "not connected" about a driven
input is worse than one that omits it — that is finding **A2** in `netlist.md`,
repeated.

**Blocks E and F are the working template** for anything with a relay, a driver
and panel connectors. `_driver_and_relay()` holds the half the two share, because
driver #2 physically *is* driver #1 shifted left 41 columns. Block G is the template
for a buffer stage.

---

## Symbol reference

Every symbol that has pins **returns its pin coordinates**, so you wire to the
returned tuples rather than recomputing offsets by hand.

| Call | Returns | Notes |
|---|---|---|
| `s.res(x, y, ref, val, vert=False, lside=True)` | `(pin_a, pin_b)` | `(x,y)` is the centre. `lside` puts the label on the left |
| `s.cap(x, y, ref, val, pol=False, vert=True, lside=True, flip=False)` | `(pin_a, pin_b)` | `pol=True` draws a polarised electrolytic with a `+`. `flip=True` puts a horizontal `+` on the right |
| `s.opamp(x, y, ref, pin_p, pin_m, pin_o, flip=False)` | `(p, m, out)` | `x` is the **left edge**, `y` the centre. `+` on top. `flip=True` points it left, and `x` becomes the right edge |
| `s.contacts(x, y, flip=False)` | `{NC, NO, COM, ARM}` | Relay contacts alone, de-energised, for the overview. `(x,y)` is NC. `flip=True` puts COM on the left. `ARM` is where the coil's dashed line lands |
| `s.icbox(x, y, w, h, ref, name, sub="")` | — | Plain rectangular part |
| `s.connbox(x, y, w, h, ref, name, pins, side, note)` | `{label: (x,y)}` | `pins` is `[(label, y_offset), …]`; `side` is which edge the leads leave from |
| `s.npn(x, y, ref, part)` | `(base, collector, emitter)` | Centre at `(x,y)`. `part` prints under the emitter — put the C/E/B hole map there |
| `s.diode(x, y, ref, val)` | `(cathode, anode)` | Vertical, **band at the top**. For a flyback the cathode goes to the +V node |
| `s.relay(x, y, ref, name, holes)` | `{P, M, COM, NC, NO}` | TQ2 pole 1, drawn **de-energised** (COM resting on NC). `(x,y)` is the coil box's top-left. `holes` maps `P/M/NC/COM/NO` to hole labels |
| `s.dashline([(x1,y1), …])` | — | Non-electrical link — the relay's coil-to-armature actuation line |
| `s.wire([(x1,y1), (x2,y2), …])` | — | Orthogonal runs; list every corner |
| `s.junction(x, y)` | — | **Required** at every 3-way connection |
| `s.gnd(x, y)` / `s.pwr(x, y, "+5V")` / `s.vgnd(x, y)` | — | `(x,y)` is the connection point |
| `s.netlabel(x, y, name, side="right")` | — | `side` is where the tag body sits relative to `(x,y)` |
| `s.t(x, y, text, cls, anchor)` | — | Classes: `lbl` `val` `net` `note` `pin` `ttl` `gh` |
| `s.blockframe(x, y, w, h, title)` | — | Dashed functional-block outline |

---

## House rules

1. **Junctions are not optional.** A crossing with no dot means *not connected*.
   Omitting a dot at a real 3-way join makes the drawing wrong, not just untidy.
2. **Prefer net labels to long wires.** `OPA_BIAS` and `SOURCE_NODE` are carried
   by label, not by routing across the sheet. Keep it that way.
3. **Blocks must not overlap.** `build()` places each block at an absolute
   origin; the frames are the true extents. After moving anything, re-render and
   look at it. The composite sheet is the one that breaks first.
   **Long `note` lines are the usual cause of a broken layout** — text has no
   measured width here, so a line that reads fine in the source silently runs out
   through the dashed frame. Keep note lines under ~95 characters at the 1200-wide
   block size, and split rather than shrink.
4. **Keep the schematic honest.** If something is not verified, say so on the
   drawing. The verification note on the single-sheet version and the `NYV`
   callouts exist because the board, not the runbook, is the authority.
5. **The netlist governs.** [`netlist.md`](netlist.md) is the source of truth;
   these drawings are a rendering of it. Update the netlist first.

---

## Which blocks are frozen, and which are transcribed

**Blocks A and B** were captured against the physical board and photographs on
2026-09-07. **Blocks E and F were assembled on 2026-09-22, and blocks C, G and H on
2026-10-31, from `ai/journal.md`, `ai/todo.md` and `ai/evidence/`** — from evidence
already taken, not from a fresh inspection. The drawing says so on its face, in the
VERIFICATION panel, and it must keep saying so. **Do not quietly raise them to the
same standing as A and B**; that is the tier promotion `netlist.md` §9 exists to
prevent.

## Block C changed, and how that went wrong

Block **C** used to document ten flying leads, whose geometry was the fix in journal
2026-09-07 (6). The boards were replaced by a soldered stack on 2026-09-13, and
TODO-41 said to update the drawing afterwards. Nobody did, so for seven weeks the
schematic showed an interconnect that no longer existed, labelled "do not disturb".
The old capture is kept in `netlist.md` §4.

**So: when a phase changes the board, update the netlist and the drawing in that
same session**, and add the change to `netlist.md` §10.0.
