# How to update the as-built schematics

**Never hand-edit the `.svg` files — they are generated and will be overwritten.**
Edit [`tools/gen_schematic.py`](../../tools/gen_schematic.py), then:

```
python3 tools/gen_schematic.py
```

One source produces all three deliverables, so the single-sheet and two-sheet
versions can never drift apart:

| File | What it is |
|---|---|
| `schematic_1sheet.svg` | Everything on one sheet — bench reconstruction reference |
| `schematic_sheet1_analog.svg` | Sheet 1 of 2 — power, references, analog front end |
| `schematic_sheet2_digital.svg` | Sheet 2 of 2 — digital interface, reserved future hardware |

No dependencies beyond the Python standard library.

---

## The three kinds of edit you will actually make

### 1. Change a value or a note

Values live inline in the `draw_*()` functions. To correct a resistor:

```python
a, b = s.res(680, 110, "R1", "47k", vert=True)
#                       ^ref   ^value
```

### 2. Change the Teensy ↔ Audio Shield wiring

Edit the `INTERCONNECT` list near the top. Rows render top to bottom in order,
and the block auto-sizes:

```python
INTERCONNECT = [
    # colour,  carrier screw, U3 pad, net,        function
    ("orange", "8",           "8",    "I2S_DOUT", "codec → Teensy RX"),
]
```

### 3. Promote a Phase 5–9 block from planned to built

Two steps.

**Step one — remove the row from `FUTURE_ITEMS`** so it stops appearing in the
reserved block.

**Step two — write a `draw_*()` function for the new hardware** and call it from
`build()`. Every block follows the same shape:

```python
def draw_relay_send(s, ox, oy):
    s.origin(ox, oy)                       # all coords below are block-relative
    s.blockframe(-30, -30, 700, 400, "E — RELAY_SEND DRIVER (PHASE 6)")

    a, b = s.res(100, 120, "R6", "1k")     # returns (left_pin, right_pin)
    s.wire([a, (40, 120)])                 # wire() takes a list of points
    s.junction(100, 120)
    s.gnd(100, 260)
    s.netlabel(300, 120, "RELAY_SEND")
```

Then in `build()`:

```python
draw_relay_send(s, 90, 1150)               # place at absolute (90, 1150)
```

---

## Symbol reference

Every symbol that has pins **returns its pin coordinates**, so you wire to the
returned tuples rather than recomputing offsets by hand.

| Call | Returns | Notes |
|---|---|---|
| `s.res(x, y, ref, val, vert=False, lside=True)` | `(pin_a, pin_b)` | `(x,y)` is the centre. `lside` puts the label on the left |
| `s.cap(x, y, ref, val, pol=False, vert=True, lside=True)` | `(pin_a, pin_b)` | `pol=True` draws a polarised electrolytic with a `+` |
| `s.opamp(x, y, ref, pin_p, pin_m, pin_o)` | `(p, m, out)` | `x` is the **left edge**, `y` the centre. `+` on top |
| `s.icbox(x, y, w, h, ref, name, sub="")` | — | Plain rectangular part |
| `s.connbox(x, y, w, h, ref, name, pins, side, note)` | `{label: (x,y)}` | `pins` is `[(label, y_offset), …]` |
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
4. **Keep the schematic honest.** If something is not verified, say so on the
   drawing. The verification note on the single-sheet version and the `NYV`
   callouts exist because the board, not the runbook, is the authority.
5. **The netlist governs.** [`netlist.md`](netlist.md) is the source of truth;
   these drawings are a rendering of it. Update the netlist first.

---

## Frozen content — do not casually redraw

Block **C** documents the Teensy ↔ Audio Shield interconnect, whose *geometry*
is the fix recorded in journal 2026-09-07 (6). The length, bundling and 1:1
mapping annotations are load-bearing engineering content, not decoration. If the
hardware is ever re-seated, the drawing and the netlist both need re-verifying
before they can be trusted again.
