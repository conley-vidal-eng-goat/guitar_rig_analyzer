#!/usr/bin/env python3
"""
Guitar Rig Analyzer — as-built schematic generator.

Emits every deliverable from one source of truth:
    docs/asbuilt/schematic_overview.svg        one page, the whole signal path
    docs/asbuilt/schematic_1sheet.svg          single-sheet, bench reconstruction
    docs/asbuilt/schematic_sheet1_analog.svg   sheet 1 of 2, power + analog
    docs/asbuilt/schematic_sheet2_digital.svg  sheet 2 of 2, digital + reserved
    docs/asbuilt/schematics.html               a page that shows all four

Circuit source of truth: docs/asbuilt/netlist.md
Run:  python3 tools/gen_schematic.py

TO ADD HARDWARE: see docs/asbuilt/SCHEMATIC_EDITING.md. Short version - update
netlist.md first, write a draw_*() block using the symbol primitives, and call
it from the sheet composers at the bottom.
"""

import os

SANS = "'DejaVu Sans','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'DejaVu Sans Mono',Menlo,Consolas,monospace"

REV   = "2026-10-31"
PROJ  = "Guitar Rig Analyzer"
TITLE = "As-Built Analyzer - Through Amp Out and the Pi Link"
DRAWN = "C. Vidal"

# ---------------------------------------------------------------- interconnect
# header pin, net, direction, function
#   direction: 'r' = toward the codec, 'l' = toward the Teensy,
#              'b' = bidirectional, '' = power/no arrow
#
# Since 2026-09-13 these run through the soldered headers of the native stack
# (netlist.md §16), not the ten flying leads of the 2026-09-07 capture (§4).
#
# NET NAMES ARE CODEC-REFERENCED (SGTL5000 perspective) — see NAMING note in
# draw_digital(). I2S_DIN is the CODEC's data input, fed by the Teensy's
# SAI1_TX_DATA0 on pin 7. I2S_DOUT is the CODEC's data output, read by the
# Teensy's SAI1_RX_DATA0 on pin 8. See the pin notes in config.h. Do not flip
# these without changing netlist.md §4 too.
INTERCONNECT = [
    ("5V",  "+5V",       "",  "header — shield's use of it NYV"),
    ("GND", "GND",       "",  "header — bonds shield and board grounds"),
    ("3V3", "+3V3",      "",  "header — SGTL5000 supply"),
    ("7",   "I2S_DIN",   "r", "Teensy SAI1_TX_DATA0 → codec"),
    ("8",   "I2S_DOUT",  "l", "codec → Teensy SAI1_RX_DATA0"),
    ("18",  "I2C_SDA",   "b", "codec control"),
    ("19",  "I2C_SCL",   "r", "codec control"),
    ("20",  "I2S_LRCLK", "r", "frame clock · 44.1 kHz · 1×Fs"),
    ("21",  "I2S_BCLK",  "r", "bit clock · 2.8224 MHz · 64×Fs"),
    ("23",  "I2S_MCLK",  "r", "master clock · 11.2896 MHz · 256×Fs"),
]

# ---------------------------------------------------------------- reserved
# Phases 6, 7, 8 and 10 and the Amp Out branch have been BUILT - see their draw_*()
# blocks. What remains here is hardware deliberately never built.
# A row leaves this list only when its block exists above, never because a phase
# is "done".
FUTURE_ITEMS = [
    ("JACK_INSTRUMENT detect", "Teensy 16", "none - #11 has no switch contact", "NOT BUILT · ADR-003"),
    ("JACK_RIG_SEND detect",   "Teensy 17", "none",                             "NOT BUILT · ADR-003"),
    ("JACK_RETURN_TS detect",  "Teensy 22", "none",                             "NOT BUILT · ADR-004"),
    ("JACK_RETURN_XLR detect", "Teensy 24", "D2F-01L omitted by decision",      "NOT BUILT · ADR-004"),
    ("RA8875_CS / INT / RESET", "Teensy 10 / 9 / 5", "SPI display (debug only)", "blocked by stack"),
]


class Sheet:
    def __init__(self, w, h, sheet_no, sheet_of, subtitle):
        self.w, self.h = w, h
        self.no, self.of, self.subtitle = sheet_no, sheet_of, subtitle
        self.b = []
        self.ox = self.oy = 0

    def origin(self, x, y):
        self.ox, self.oy = x, y

    def _(self, x, y):
        return x + self.ox, y + self.oy

    def add(self, s):
        self.b.append(s)

    # ---------------------------------------------------------- primitives
    def wire(self, pts):
        p = " ".join(f"{x+self.ox},{y+self.oy}" for x, y in pts)
        self.add(f'<polyline class="w" points="{p}"/>')

    def arrow(self, x, y, d):
        """Filled data-direction arrow on a horizontal wire."""
        if d == "b":
            self.arrow(x, y, "r"); self.arrow(x - 370, y, "l"); return
        pts = (f"{x},{y-5.5} {x+12},{y} {x},{y+5.5}" if d == "r"
               else f"{x},{y-5.5} {x-12},{y} {x},{y+5.5}")
        pts = " ".join(f"{float(a)+self.ox},{float(b)+self.oy}"
                       for a, b in (q.split(",") for q in pts.split()))
        self.add(f'<polygon class="jn" points="{pts}"/>')

    def dashline(self, pts):
        p = " ".join(f"{x+self.ox},{y+self.oy}" for x, y in pts)
        self.add(f'<polyline class="dash" points="{p}"/>')

    def nc(self, x, y):
        """IEEE no-connect cross."""
        self.path(x, y, "M-7 -7 L7 7 M-7 7 L7 -7")

    def junction(self, x, y):
        x, y = self._(x, y)
        self.add(f'<circle class="jn" cx="{x}" cy="{y}" r="3.4"/>')

    def t(self, x, y, s, cls="lbl", anchor="start"):
        x, y = self._(x, y)
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        self.add(f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>')

    def rect(self, x, y, w, h, cls="box", rx=0):
        x, y = self._(x, y)
        self.add(f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>')

    def path(self, x, y, d, cls="sym"):
        x, y = self._(x, y)
        self.add(f'<path class="{cls}" transform="translate({x},{y})" d="{d}"/>')

    # ---------------------------------------------------------- symbols
    def gnd(self, x, y):
        self.path(x, y, "M0 0 V10 M-13 10 H13 M-8 15 H8 M-3 20 H3")

    def pwr(self, x, y, name):
        self.path(x, y, "M0 0 V-14 M-15 -14 H15")
        self.t(x, y - 21, name, "net", "middle")

    def vgnd(self, x, y, name="VGND"):
        self.path(x, y, "M0 0 V-14 M-17 -14 H17 M-17 -18 H17")
        self.t(x, y - 25, name, "net", "middle")

    def res(self, x, y, ref, val, vert=False, lside=True):
        """Centre at (x,y). Returns (pin_a, pin_b): left/right or top/bottom."""
        d = "M-28 0 h12 l4 -9 l8 18 l8 -18 l8 18 l4 -9 h12"
        if vert:
            xx, yy = self._(x, y)
            self.add(f'<path class="sym" transform="translate({xx},{yy}) rotate(90)" d="{d}"/>')
            tx = x - 14 if lside else x + 14
            an = "end" if lside else "start"
            self.t(tx, y - 3, ref, "lbl", an)
            self.t(tx, y + 12, val, "val", an)
            return (x, y - 28), (x, y + 28)
        self.path(x, y, d)
        self.t(x, y - 20, ref, "lbl", "middle")
        self.t(x, y + 28, val, "val", "middle")
        return (x - 28, y), (x + 28, y)

    def cap(self, x, y, ref, val, pol=False, vert=True, lside=True, flip=False):
        if vert:
            d = ("M0 -16 V-5 M-12 -5 H12 M-12 9 Q0 1 12 9 M0 16 V5" if pol
                 else "M0 -16 V-4 M-11 -4 H11 M-11 4 H11 M0 4 V16")
            self.path(x, y, d)
            if pol:
                px = x + 15 if lside else x - 15
                self.t(px, y - 8, "+", "val", "middle")
            tx = x + 16 if not lside else x - 16
            an = "start" if not lside else "end"
            self.t(tx, y - 2, ref, "lbl", an)
            self.t(tx, y + 13, val, "val", an)
            return (x, y - 16), (x, y + 16)
        d = ("M-16 0 H-5 M-5 -12 V12 M9 -12 Q1 0 9 12 M16 0 H5" if pol
             else "M-16 0 H-4 M-4 -11 V11 M4 -11 V11 M4 0 H16")
        if pol and flip:        # + plate on the right, for right-to-left signal
            d = "M16 0 H5 M5 -12 V12 M-9 -12 Q-1 0 -9 12 M-16 0 H-5"
        self.path(x, y, d)
        if pol:
            self.t(x + 15 if flip else x - 10, y - 16, "+", "val", "middle")
        self.t(x, y - 24, ref, "lbl", "middle")
        self.t(x, y + 32, val, "val", "middle")
        return (x - 16, y), (x + 16, y)

    def npn(self, x, y, ref, part=""):
        """NPN BJT, centre (x,y). Returns (base, collector, emitter)."""
        cx, cy = self._(x, y)
        self.add(f'<circle class="sym" cx="{cx}" cy="{cy}" r="27"/>')
        self.path(x, y, "M-46 0 H-14 M-14 -18 V18")
        self.path(x, y, "M-14 -8 L14 -26 M14 -26 V-48")
        self.path(x, y, "M-14 8 L14 26 M14 26 V48")
        self.path(x, y, "M8 22 L0.6 13.1 L-3.1 19 Z", "jn")
        self.t(x - 6, y - 32, ref, "lbl", "end")
        if part:
            self.t(x + 30, y + 52, part, "val")
        return (x - 46, y), (x + 14, y - 48), (x + 14, y + 48)

    def diode(self, x, y, ref, val=""):
        """Vertical, cathode band at TOP. Returns (cathode, anode)."""
        self.path(x, y, "M0 -22 V-8 M-13 -8 H13 M-13 8 L13 8 L0 -8 Z M0 8 V22")
        self.t(x - 18, y - 4, ref, "lbl", "end")
        if val:
            self.t(x - 18, y + 11, val, "val", "end")
        return (x, y - 22), (x, y + 22)

    def relay(self, x, y, ref, name, holes, sub=""):
        """TQ2 pole 1, drawn DE-ENERGISED (COM resting on NC). Coil box
        top-left at (x,y). holes: dict of P/M/NC/COM/NO -> hole label.
        Returns {'P','M','COM','NC','NO'} connection points."""
        self.rect(x, y, 62, 80)
        self.t(x + 31, y + 34, ref, "lbl", "middle")
        self.t(x + 31, y + 52, name, "val", "middle")
        self.t(x + 7, y + 16, "+", "lbl")
        self.wire([(x, y + 18), (x - 18, y + 18)])
        self.wire([(x, y + 62), (x - 18, y + 62)])
        self.t(x - 22, y + 14, f"1 · {holes['P']}", "pin", "end")
        self.t(x - 22, y + 76, f"10 · {holes['M']}", "pin", "end")

        px, py = x + 150, y + 40
        self.dashline([(x + 62, y + 40), (px - 5, py)])
        self.junction(px, py)
        self.wire([(px, py), (px, py + 60)])
        self.wire([(px, py), (px + 68, py - 28)])          # armature, on NC
        self.wire([(px + 70, py - 28), (px + 110, py - 28)])
        self.wire([(px + 70, py + 28), (px + 110, py + 28)])
        self.junction(px + 70, py - 28)
        self.junction(px + 70, py + 28)
        self.t(px + 108, py - 36, f"NC · 2 · {holes['NC']}", "pin", "end")
        self.t(px + 108, py + 46, f"NO · 4 · {holes['NO']}", "pin", "end")
        self.t(px - 6, py + 58, f"COM · 3 · {holes['COM']}", "pin", "end")
        if sub:
            self.t(x + 31, y + 100, sub, "note", "middle")
        return {"P": (x - 18, y + 18), "M": (x - 18, y + 62),
                "COM": (px, py + 60),
                "NC": (px + 110, py - 28), "NO": (px + 110, py + 28)}

    def contacts(self, x, y, flip=False):
        """SPDT contact group alone, de-energised (COM resting on NC). NC and NO
        face the side the signal enters from; COM leaves the other side. (x,y)
        is the NC terminal. Returns {'NC','NO','COM','ARM'}."""
        d = -1 if flip else 1
        nc, no = (x, y), (x, y + 56)
        com = (x + 96 * d, y + 28)
        self.junction(*nc); self.junction(*no); self.junction(*com)
        self.wire([com, (x + 4 * d, y)])                  # armature, on NC
        return {"NC": nc, "NO": no, "COM": com, "ARM": (x + 50 * d, y + 13)}

    def opamp(self, x, y, ref, pin_p, pin_m, pin_o, flip=False):
        """x = left edge, y = centre. + on top. Returns (p, m, out) coords."""
        xx, yy = self._(x, y)
        if flip:                # x = right edge, output on the left
            self.add(f'<polygon class="box" points="{xx},{yy-42} {xx},{yy+42} {xx-74},{yy}"/>')
            self.t(x - 12, y - 16, "+", "lbl", "end")
            self.t(x - 12, y + 26, "−", "lbl", "end")
            self.t(x - 20, y + 5, ref, "lbl", "end")
            self.t(x + 5, y - 26, str(pin_p), "pin")
            self.t(x + 5, y + 34, str(pin_m), "pin")
            self.t(x - 80, y - 8, str(pin_o), "pin", "end")
            return (x, y - 20), (x, y + 20), (x - 74, y)
        self.add(f'<polygon class="box" points="{xx},{yy-42} {xx},{yy+42} {xx+74},{yy}"/>')
        self.t(x + 12, y - 16, "+", "lbl")
        self.t(x + 12, y + 26, "−", "lbl")
        self.t(x + 20, y + 5, ref, "lbl")
        self.t(x - 5, y - 26, str(pin_p), "pin", "end")
        self.t(x - 5, y + 34, str(pin_m), "pin", "end")
        self.t(x + 80, y - 8, str(pin_o), "pin")
        return (x, y - 20), (x, y + 20), (x + 74, y)

    def netlabel(self, x, y, name, side="right"):
        W = 22 + 7.3 * len(name)
        if side == "right":
            pts = f"{x},{y} {x+11},{y-12} {x+W},{y-12} {x+W},{y+12} {x+11},{y+12}"
            tx, an = x + 17, "start"
        else:
            pts = f"{x},{y} {x-11},{y-12} {x-W},{y-12} {x-W},{y+12} {x-11},{y+12}"
            tx, an = x - 17, "end"
        pts = " ".join(f"{float(a)+self.ox},{float(b)+self.oy}"
                       for a, b in (p.split(",") for p in pts.split()))
        self.add(f'<polygon class="tag" points="{pts}"/>')
        self.t(tx, y + 4, name, "net", an)

    def icbox(self, x, y, w, h, ref, name, sub=""):
        self.rect(x, y, w, h)
        self.t(x + w / 2, y + 26, ref, "lbl", "middle")
        self.t(x + w / 2, y + 44, name, "val", "middle")
        if sub:
            self.t(x + w / 2, y + 60, sub, "note", "middle")

    def blockframe(self, x, y, w, h, title):
        self.rect(x, y, w, h, "dash", rx=6)
        self.t(x + 4, y - 9, title, "ttl")

    def connbox(self, x, y, w, h, ref, name, pins, side="right", note=""):
        """pins: list of (label, y_offset). Returns {label: (x,y)}."""
        self.rect(x, y, w, h)
        self.t(x + w / 2, y + 22, ref, "lbl", "middle")
        self.t(x + w / 2, y + 38, name, "val", "middle")
        if note:
            self.t(x + w / 2, y + h + 18, note, "note", "middle")
        out = {}
        for lab, dy in pins:
            py = y + dy
            if side == "right":
                self.wire([(x + w, py), (x + w + 14, py)])
                self.t(x + w - 6, py + 4, lab, "pin", "end")
                out[lab] = (x + w + 14, py)
            else:
                self.wire([(x, py), (x - 14, py)])
                self.t(x + 6, py + 4, lab, "pin")
                out[lab] = (x - 14, py)
        return out

    # ---------------------------------------------------------- frame
    def titleblock(self):
        bw, bh = 620, 150
        bx, by = self.w - 30 - bw, self.h - 30 - bh
        self.origin(0, 0)
        self.rect(bx, by, bw, bh)
        self.wire([(bx, by + 46), (bx + bw, by + 46)])
        self.wire([(bx, by + 100), (bx + bw, by + 100)])
        self.wire([(bx + 400, by + 100), (bx + 400, by + bh)])
        self.t(bx + 14, by + 30, PROJ.upper(), "ttl")
        self.t(bx + 14, by + 70, TITLE, "lbl")
        self.t(bx + 14, by + 90, self.subtitle, "note")
        self.t(bx + 14, by + 122, "SOURCE OF TRUTH", "pin")
        self.t(bx + 14, by + 140, "docs/asbuilt/netlist.md", "val")
        self.t(bx + 414, by + 122, "REV", "pin")
        self.t(bx + 414, by + 140, REV, "val")
        self.t(bx + 524, by + 122, "SHEET", "pin")
        self.t(bx + 524, by + 140, f"{self.no} of {self.of}", "val")
        self.t(bx + bw - 14, by + 30, DRAWN, "val", "end")

    def render(self):
        css = f"""
    .w{{stroke:#111;stroke-width:1.7;fill:none;stroke-linecap:round;stroke-linejoin:round}}
    .sym{{stroke:#111;stroke-width:1.7;fill:none;stroke-linecap:round}}
    .jn{{fill:#111}}
    .box{{stroke:#111;stroke-width:1.7;fill:#fff}}
    .dash{{stroke:#b0b0b0;stroke-width:1.3;fill:none;stroke-dasharray:7 6}}
    .ext{{stroke:#8a8a8a;stroke-width:1.4;fill:#f4f4f2;stroke-dasharray:7 6}}
    .tag{{stroke:#111;stroke-width:1.2;fill:#eef1f4}}
    .lbl{{font:600 13.5px {SANS};fill:#111}}
    .val{{font:12px {MONO};fill:#333}}
    .net{{font:600 12px {MONO};fill:#111}}
    .note{{font:11.5px {SANS};fill:#5a5a5a}}
    .ttl{{font:700 15px {SANS};fill:#111;letter-spacing:.07em}}
    .pin{{font:10.5px {MONO};fill:#666}}
    .gh{{font:12px {SANS};fill:#9a9a9a}}"""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" '
                f'height="{self.h}" viewBox="0 0 {self.w} {self.h}">\n'
                f'<style>{css}</style>\n'
                f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>\n'
                f'<rect class="box" x="18" y="18" width="{self.w-36}" '
                f'height="{self.h-36}" fill="none"/>\n'
                + "\n".join(self.b) + "\n</svg>\n")


# ===================================================================== BLOCKS
def draw_power(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 930, 372, "A — POWER ENTRY, VGND & OPA_BIAS REFERENCES")

    # +5V entry and rail decoupling
    s.pwr(80, 50, "+5V"); s.wire([(80, 50), (80, 110), (180, 110)]); s.junction(80, 110)
    a, b = s.cap(80, 150, "C6", "10µF", pol=True)
    s.wire([(80, 110), a]); s.wire([b, (80, 205)]); s.gnd(80, 205)
    a, b = s.cap(180, 150, "C5", "0.1µF", lside=False)
    s.wire([(180, 110), a]); s.wire([b, (180, 205)]); s.gnd(180, 205)
    s.t(10, 258, "+5V from U2 Dinkle carrier terminal 5V", "note")
    s.t(10, 274, "(carrier internal provenance NYV — X-5)", "note")

    # VGND divider
    s.pwr(360, 50, "+5V")
    a, b = s.res(360, 110, "R4", "10k", vert=True); s.wire([(360, 50), a])
    c, d = s.res(360, 198, "R3", "10k", vert=True); s.wire([b, c])
    s.wire([d, (360, 255)]); s.gnd(360, 255); s.junction(360, 170)
    s.wire([(360, 170), (540, 170)])
    a, b = s.cap(430, 210, "C8", "10µF", pol=True)
    s.wire([(430, 170), a]); s.wire([b, (430, 255)]); s.gnd(430, 255); s.junction(430, 170)
    a, b = s.cap(495, 210, "C7", "0.1µF", lside=False)
    s.wire([(495, 170), a]); s.wire([b, (495, 255)]); s.gnd(495, 255); s.junction(495, 170)
    s.vgnd(540, 170)
    s.t(360, 296, "VGND = 2.50 V (calculated) — BOT_RED rail.", "note", "middle")
    s.t(360, 313, "Live but UNLOADED. NOT connected to GND.", "note", "middle")

    # OPA_BIAS divider
    s.pwr(680, 50, "+5V")
    a, b = s.res(680, 110, "R1", "47k", vert=True); s.wire([(680, 50), a])
    c, d = s.res(680, 198, "R2", "10k", vert=True); s.wire([b, c])
    s.wire([d, (680, 255)]); s.gnd(680, 255); s.junction(680, 170)
    s.wire([(680, 170), (762, 170)])
    a, b = s.cap(740, 210, "C4", "0.1µF", lside=False)
    s.wire([(740, 170), a]); s.wire([b, (740, 255)]); s.gnd(740, 255); s.junction(740, 170)
    s.netlabel(762, 170, "OPA_BIAS")
    s.t(680, 296, "0.877 V calc / 0.874 V meas — Rth 8.25 kΩ", "note", "middle")
    s.t(680, 313, "Biases U1 and, since 2026-09-30, U4.", "note", "middle")


def draw_analog(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 1160, 500, "B — U1 · OPA1642 HIGH-IMPEDANCE BUFFER (SOURCE PATH)")

    j1 = s.connbox(20, 60, 92, 118, "J4", "1/4in IN",
                   [("T", 55), ("S", 108)], "right",
                   "Switchcraft #11")
    s.t(20, 232, "2-conductor jack — NO switch contact, so", "note")
    s.t(20, 248, "presence detect is NOT BUILT (ADR-003).", "note")
    s.t(20, 272, "J4 superseded the J1 3.5 mm breakout as the", "note")
    s.t(20, 288, "guitar input on 2026-09-08.", "note")
    s.t(20, 500, "VALUE PROVENANCE:  C1 read from its marking (BC103 = 10nF).  C2 / C6 / C8 and the 0.1µF ceramics", "note")
    s.t(20, 517, "stated at the bench (reported, not read back).  R1–R4 derived from the measured 0.874 V bias node;", "note")
    s.t(20, 534, "R5 derived from the measured 1 kHz response (0.9848 vs 0.9867 predicted).  See netlist.md §2 and §4a.", "note")
    s.wire([j1["S"], (150, 168), (150, 190)]); s.gnd(150, 190)

    a, b = s.cap(200, 115, "C1", "10nF", vert=False)
    s.wire([j1["T"], a]); s.wire([b, (290, 115)]); s.junction(290, 115)

    c, d = s.res(290, 190, "R5", "100k", vert=True)
    s.wire([(290, 115), c]); s.wire([d, (290, 258), (350, 258)])
    s.netlabel(350, 258, "OPA_BIAS")

    p, m, o = s.opamp(400, 115, "U1A", 3, 2, 1)
    s.wire([(290, 115), (350, 115), (350, 95), p])
    s.wire([o, (528, 115)]); s.junction(528, 115)
    s.wire([(528, 115), (528, 190), (360, 190), (360, 135), m])

    a, b = s.cap(578, 115, "C2", "10µF", pol=True, vert=False)
    s.wire([(528, 115), a]); s.wire([b, (700, 115)]); s.junction(700, 115)

    s.wire([(700, 115), (742, 115)])
    s.netlabel(742, 115, "SOURCE_NODE")
    s.wire([(700, 115), (700, 235), (742, 235)])
    s.netlabel(742, 235, "K1 NC · 56a")
    s.t(700, 285, "col 48 A–E fans out two ways: the permanent", "note")
    s.t(700, 301, "48e → LINE-IN-L tap, and 48e → RELAY_SEND NC.", "note")
    s.t(700, 325, "⚠ J2 (3.5 mm open stub, 48a) was DISCONNECTED", "note")
    s.t(700, 341, "2026-09-21. No conductor remains on col 48.", "note")

    # U1 power pins + W1
    s.icbox(900, 60, 130, 62, "U1", "power pins")
    s.wire([(965, 60), (965, 26)]); s.pwr(965, 26, "+5V")
    s.wire([(965, 122), (965, 158)]); s.gnd(965, 158)
    s.t(1036, 54, "8", "pin"); s.t(1036, 134, "4", "pin")
    s.junction(965, 44)
    s.wire([(965, 44), (1075, 44)])
    a, b = s.cap(1075, 84, "C3", "0.1µF", lside=False)
    s.wire([(1075, 44), a]); s.wire([b, (1075, 128)]); s.gnd(1075, 128)
    s.t(900, 212, "W1: orange jumper, TOP_RED → hole 35h", "note")
    s.t(900, 228, "C3 decoupling via col 34 → 34j → GND", "note")

    # U1B termination
    p, m, o = s.opamp(400, 385, "U1B", 5, 6, 7)
    s.netlabel(316, 365, "OPA_BIAS", "left"); s.wire([(316, 365), p])
    s.wire([o, (528, 385), (528, 448), (360, 448), (360, 405), m])
    s.t(20, 360, "Unused channel B terminated as a", "note")
    s.t(20, 376, "unity follower on OPA_BIAS.", "note")
    s.t(20, 400, "DEVIATION D1: journal 2026-09-05 (4)", "note")
    s.t(20, 416, "specified 100 kΩ in series to pin 5.", "note")
    s.t(20, 432, "As built it is a direct tie. Benign —", "note")
    s.t(20, 448, "JFET input draws pA.", "note")
    s.t(584, 400, "U4 pin 5 shares this node (col 38 F–J), through the single", "note")
    s.t(584, 416, "jumper 38j → 41c. If it lifts, both channel Bs lose bias.", "note")


def draw_digital(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 990, 910,
                 "C — TEENSY ↔ AUDIO SHIELD INTERFACE  (NATIVE STACK)")

    ys, y = {}, 92
    for i, row in enumerate(INTERCONNECT):
        ys[row[0]] = y
        y += 54 if i == 2 else 34

    s.icbox(30, 55, 215, 405, "U2", "Teensy 4.1", "in Dinkle screw carrier")
    s.icbox(690, 55, 235, 515, "U3", "Audio Shield Rev D", "SGTL5000")

    for pin, net, dr, fn in INTERCONNECT:
        yy = ys[pin]
        s.t(239, yy + 4, pin, "pin", "end")
        s.t(696, yy + 4, pin, "pin")
        s.wire([(245, yy), (690, yy)])
        s.t(400, yy - 8, net, "net", "end")
        s.t(410, yy - 8, fn, "note")
        if dr:
            s.arrow(655, yy, dr)

    s.wire([(690, 480), (600, 480)])
    s.netlabel(600, 480, "SOURCE_NODE", "left")
    s.t(696, 484, "LINE IN L", "pin")
    s.t(600, 506, "jumper: breadboard 48e → U3 LINE-IN-L pad", "note", "end")

    s.wire([(690, 545), (600, 545)])
    s.netlabel(600, 545, "RETURN_NODE", "left")
    s.t(696, 549, "LINE IN R", "pin")
    s.t(600, 567, "fed from RELAY_RETURN COM (16a), block F — TS or XLR return", "note", "end")
    s.t(600, 585, "⚠ joint resoldered and new jumper fitted 2026-10-18 (RPT)", "note", "end")

    s.rect(30, 600, 640, 142, "dash", rx=4)
    s.t(42, 620, "PROVENANCE & CONVENTIONS", "lbl")
    s.t(42, 641, "Net names are CODEC-REFERENCED:  I2S_DIN = codec data IN (Teensy 7, SAI1_TX_DATA0);", "note")
    s.t(42, 657, "I2S_DOUT = codec data OUT (Teensy 8, SAI1_RX_DATA0).   See netlist.md §4.", "note")
    s.t(42, 680, "Clocks derive from SAMPLE_RATE 44100. Scope-confirmed on the REPLACED boards:", "note")
    s.t(42, 696, "LRCLK 44.108 kHz · BCLK ~2.82 MHz · MCLK ~11.29 MHz  (journal 2026-09-06 (1))", "note")
    s.t(42, 719, "SGTL5000 identified functionally over I²C, not from its package marking.", "note")
    s.t(42, 735, "The shield's use of the 5V pad is UNVERIFIED. Pin 15 stubs to the unpopulated VOL pad.", "note")

    s.t(30, 774, "THE HEADER STACK IS THE INTERCONNECT, SINCE 2026-09-13:", "lbl")
    s.t(30, 794, "•  Shield → Teensy → carrier, soldered. New boards. No flying leads.", "note")
    s.t(30, 812, "•  Result: 324/324 clean windows, 0 outliers, 26.9 min (TODO-41B)", "note")
    s.t(30, 830, "•  Idle: SOURCE −65.39, RETURN −65.26 dBFS, LINE-IN-L open", "note")
    s.t(30, 848, "•  U2 is I²S MASTER — it generates MCLK / BCLK / LRCLK", "note")
    s.t(560, 794, "⚠  BOARDS AND TOPOLOGY CHANGED TOGETHER.", "note")
    s.t(560, 812, "   \"The stack fixed it\" is NOT established. What is", "note")
    s.t(560, 830, "   established: this assembly does not reproduce the fault.", "note")
    s.t(560, 848, "   The 10-wire capture of 2026-09-07 is netlist.md §4.", "note")


def _driver_and_relay(s, ref_q, ref_r6, ref_r7, ref_d, ref_k, pin, holes, sat):
    """The half both relay blocks share: GPIO → base resistor → BJT → coil.
    Drawn identically because it IS identical — driver #2 is driver #1's
    as-built line shifted left 41 columns (journal 2026-09-17)."""
    s.netlabel(130, 250, f"TEENSY {pin}", "left")
    s.wire([(130, 250), (172, 250)])
    a, b = s.res(200, 250, ref_r6, "1k")
    s.wire([(228, 250), (280, 250)]); s.junction(280, 250)
    c, d = s.res(280, 310, ref_r7, "10k", vert=True)
    s.wire([(280, 250), c]); s.wire([d, (280, 368)]); s.gnd(280, 368)

    base, col, emi = s.npn(380, 250, ref_q, "MMBT3904 · " + holes["q"])
    s.wire([(280, 250), base])
    s.wire([emi, (394, 368)]); s.gnd(394, 368)
    s.wire([col, (394, 172), (470, 172)]); s.junction(470, 172)

    cat, an = s.diode(470, 150, ref_d, "1N4148")
    s.wire([(470, 172), (542, 172)])
    s.junction(470, 128); s.wire([(470, 128), (542, 128)])
    s.wire([(470, 128), (470, 80)]); s.pwr(470, 80, "+5V")

    k = s.relay(560, 110, ref_k, "TQ2-5V", holes)
    s.t(130, 200, holes["drv"], "pin")
    s.t(560, 238, sat, "note", "middle")
    return k


def draw_relay_send(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 1200, 600,
                 "E — RELAY_SEND · K1 · PHASE 6 · breadboard cols 49–59")

    k = _driver_and_relay(s, "Q1", "R6", "R7", "D1", "K1", 14,
                          {"P": "55a", "M": "55f", "NC": "56a",
                           "COM": "57a", "NO": "58a",
                           "drv": "pin 14 → col 53;  R6 col 53 → 51, 0.993 kΩ meas",
                           "q": "C 49 · E 50 · B 51"},
                          "collector 49: 129.1 mV energised / 4.99 V off")

    s.wire([k["NC"], (860, 122)]); s.netlabel(860, 122, "SOURCE_NODE")
    s.wire([k["NO"], (860, 178)]); s.netlabel(860, 178, "U3 LINE OUT L")
    s.wire([k["COM"], (710, 302), (866, 302)])
    j5 = s.connbox(880, 260, 150, 86, "J5", "RIG SEND",
                   [("T", 42), ("S", 68)], "left", "Switchcraft #11")
    s.wire([j5["S"], (846, 328), (846, 366)]); s.gnd(846, 366)
    s.t(846, 396, "sleeve → Audio Shield GND", "note", "middle")

    s.t(0, 412, "pin 14 LOW  = buffer output → Rig Send   (default, and the boot state)", "note")
    s.t(0, 430, "pin 14 HIGH = codec LINE OUT L → Rig Send (monitor / injection path)", "note")
    s.t(0, 458, "Contact map is proven BY STATE, not from the datasheet. 56a↔58a read OPEN in BOTH states,", "note")
    s.t(0, 476, "which is what rules out a welded or make-before-break contact.", "note")
    s.t(0, 494, "Pole 2 (56f / 57f / 58f) is NOT wired and has never been tested — NYV.", "note")
    s.t(0, 522, "⚠ The coil is POLARIZED and was built backwards first: runbook step 7 inverts pins 1 and 10.", "note")
    s.t(0, 540, "Built that way the coil energises normally and the contacts never transfer.", "note")
    s.t(620, 412, "J5 tip lead reseated at 57b on 2026-10-11, the same", "note")
    s.t(620, 430, "strip as COM 57a, after it was found out of the board.", "note")
    s.t(620, 458, "Since the stack, Audio Shield GND and the breadboard", "note")
    s.t(620, 476, "rail are one net. Sleeve → rail 0.2 Ω (MEAS).", "note")


def draw_relay_return(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 1200, 600,
                 "F — RELAY_RETURN · K2 · PHASE 7 · breadboard cols 8–18")

    k = _driver_and_relay(s, "Q2", "R8", "R9", "D2", "K2", 15,
                          {"P": "14a", "M": "14f", "NC": "15a",
                           "COM": "16a", "NO": "17a",
                           "drv": "pin 15 → col 12;  R8 col 12 → 10",
                           "q": "C 8 · E 9 · B 10"},
                          "14f: 4.98 V at rest · coil 4.78 V energised")

    s.wire([k["COM"], (710, 340), (600, 340)])
    s.netlabel(600, 340, "RETURN_NODE", "left")
    s.t(600, 362, "→ U3 LINE IN R  ·  I²S ch 1", "note", "end")
    s.t(600, 378, "→ 16d → 28a → Amp Out, block G", "note", "end")

    j6 = s.connbox(880, 20, 150, 86, "J6", "RIG RTN TS",
                   [("T", 42), ("S", 68)], "left")
    s.wire([k["NC"], (840, 122), (840, 62), j6["T"]])
    s.wire([j6["S"], (858, 88), (858, 100)]); s.gnd(858, 100)

    j7 = s.connbox(880, 136, 150, 116, "J7", "XLR RETURN",
                   [("2", 42), ("1", 72), ("3", 96)], "left")
    s.wire([k["NO"], j7["2"]])
    s.wire([j7["1"], (846, 208), (846, 268)])
    s.wire([j7["3"], (846, 232)]); s.junction(846, 232)
    s.gnd(846, 268)

    s.t(0, 412, "pin 15 LOW  = TS return  → LINE IN R   (default, and the boot state)", "note")
    s.t(0, 430, "pin 15 HIGH = XLR return → LINE IN R", "note")
    s.t(0, 458, "J6 sleeve → GND, 0.9 Ω.  J7 pins 1 AND 3 land on the BREADBOARD TOP_GND rail (pin 1", "note")
    s.t(0, 476, "repaired 2026-10-11). The 33.1 dB between that rail and Audio Shield GND predates the", "note")
    s.t(0, 494, "stack, which bonds them. Risk R5 is historical and has not been re-measured.", "note")
    s.t(0, 522, "J7's detect microswitch (D2F-01L) is NOT BUILT — ADR-004.  Pole 2 (15f / 16f / 17f)", "note")
    s.t(0, 540, "not wired, and K2's own package marking has never been read back — both NYV.", "note")
    s.t(620, 412, "⚠ This driver once stalled in the active region", "note")
    s.t(620, 430, "(collector 3.556 V, emitter 291 mV) and recovered", "note")
    s.t(620, 448, "during reseating. The bad connection was NEVER", "note")
    s.t(620, 466, "identified. If it returns, measure the R8 drop", "note")
    s.t(620, 484, "12a → 10a FIRST, before anything is touched.", "note")


def draw_amp_out(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 1200, 600,
                 "G — AMP OUT · U4 · ANALOG BRANCH OF RETURN_NODE · cols 21–29")

    s.netlabel(150, 115, "RETURN_NODE", "left")
    s.t(150, 145, "16d → 28a", "pin", "end")
    a, b = s.cap(200, 115, "C10", "0.1µF", vert=False)
    s.wire([(150, 115), a]); s.wire([b, (290, 115)]); s.junction(290, 115)
    s.t(200, 166, "28b – 29b", "pin", "middle")

    c, d = s.res(290, 190, "R10", "100k", vert=True)
    s.wire([(290, 115), c]); s.wire([d, (290, 258), (350, 258)])
    s.netlabel(350, 258, "OPA_BIAS")
    s.t(350, 288, "node identity RPT + DERIV", "pin")

    p, m, o = s.opamp(400, 115, "U4A", 3, 2, 1)
    s.wire([(290, 115), (350, 115), (350, 95), p])
    s.wire([o, (528, 115)]); s.junction(528, 115)
    s.wire([(528, 115), (528, 190), (360, 190), (360, 135), m])

    a, b = s.cap(578, 115, "C11", "10µF", pol=True, vert=False)
    s.wire([(528, 115), a]); s.wire([b, (700, 115)]); s.junction(700, 115)
    s.t(578, 166, "+ 24c · − 21c", "pin", "middle")

    c, d = s.res(700, 175, "R11", "100k", vert=True)
    s.wire([(700, 115), c]); s.wire([d, (700, 232)]); s.gnd(700, 232)

    j8 = s.connbox(770, 60, 130, 92, "J8", "AMP OUT",
                   [("T", 55), ("S", 79)], "left", "1/4in · model not recorded")
    s.wire([(700, 115), j8["T"]])
    s.wire([j8["S"], (740, 139), (740, 172)]); s.gnd(740, 172)

    s.icbox(935, 60, 130, 62, "U4", "power pins")
    s.wire([(1000, 60), (1000, 26)]); s.pwr(1000, 26, "+5V")
    s.wire([(1000, 122), (1000, 158)]); s.gnd(1000, 158)
    s.t(1071, 54, "8", "pin"); s.t(1071, 134, "4", "pin")
    s.junction(1000, 44)
    s.wire([(1000, 44), (1095, 44)])
    a, b = s.cap(1095, 84, "C9", "0.1µF", lside=False)
    s.wire([(1095, 44), a]); s.wire([b, (1095, 128)]); s.gnd(1095, 128)
    s.t(935, 212, "C9: col 24 F–J → col 23 F–J → GND", "note")

    p, m, o = s.opamp(400, 385, "U4B", 5, 6, 7)
    s.netlabel(316, 365, "OPA_BIAS", "left"); s.wire([(316, 365), p])
    s.wire([o, (528, 385), (528, 448), (360, 448), (360, 405), m])
    s.t(0, 354, "Unused channel B terminated as a", "note")
    s.t(0, 370, "unity follower. Pin 5 lands on col 38 F–J,", "note")
    s.t(0, 386, "U1's pin 5 node. Pin 7 reads 0.872 V.", "note")

    s.t(600, 300, "U4 pins 1 / 2 / 3: 0.876 V.  J8 tip → sleeve: 0.000 V DC.", "note")
    s.t(600, 318, "A guitar through a real rig gives a strum-correlated waveform at", "note")
    s.t(600, 336, "J8 (2026-10-12), audible in an amp. NOT calibrated, and no J8", "note")
    s.t(600, 354, "amplitude is quotable (TODO-75). Opens: TODO-69 steps 0b, 3, 5.", "note")
    s.t(600, 382, "J8 follows K2. The branch is analog, so the amp signal does", "note")
    s.t(600, 400, "not depend on the codec, the firmware or digital latency.", "note")

    s.t(0, 478, "⚠ HAZARD H-2: col 28 A–E is RETURN_NODE and col 27 A–E is U4 pin 4, GND. They are adjacent.", "note")
    s.t(0, 496, "A one-column slip shorts the selected return to ground.", "note")
    s.t(0, 522, "⚠ C10 was first built on pin 1, the OUTPUT. It passed every DC check, because a coupling cap", "note")
    s.t(0, 540, "blocks DC in either position. Moved 2026-10-12. Predicted leak via OPA_BIAS: TODO-70, unmeasured.", "note")


def draw_pi_link(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 990, 270,
                 "H — RASPBERRY PI 5 LINK · PHASE 10 · RECEIVE-ONLY")
    s.icbox(30, 20, 215, 150, "U2", "Teensy 4.1")
    s.rect(690, 20, 235, 150)
    s.t(913, 62, "Pi 5", "lbl", "end")
    s.t(913, 80, "Raspberry Pi 5", "val", "end")
    s.t(913, 118, "7in Touch Display 2", "note", "end")

    s.wire([(245, 92), (690, 92)]); s.arrow(655, 92, "r")
    s.t(239, 96, "1 · TX1", "pin", "end"); s.t(696, 96, "10 · GPIO15", "pin")
    s.t(300, 84, "PI_LINK_UART", "net"); s.t(410, 84, "460800 baud, /dev/ttyAMA0", "note")

    s.wire([(245, 136), (690, 136)])
    s.t(239, 140, "GND", "pin", "end"); s.t(696, 140, "9 · GND", "pin")
    s.t(300, 128, "GND", "net"); s.t(410, 128, "the only power-domain connection", "note")

    s.wire([(245, 48), (290, 48)]); s.nc(290, 48)
    s.t(239, 52, "0 · RX1", "pin", "end")
    s.wire([(690, 48), (645, 48)]); s.nc(645, 48)
    s.t(696, 52, "8 · GPIO14", "pin")
    s.t(467, 52, "deliberately unconnected", "note", "middle")

    s.t(30, 200, "The Pi physically cannot send to the Teensy. No 3.3 V or 5 V rail is shared; each board keeps its", "note")
    s.t(30, 218, "own supply. Reference capture: 36 481 B/s, zero CRC failures (journal 2026-10-13 (9)).", "note")


def draw_future(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 990, 270,
                 "D — RESERVED, AND HARDWARE DELIBERATELY NOT BUILT")
    s.t(0, 6, "Everything else is BUILT — see blocks E to H. What is left here is not \"pending\": the four jack-detect inputs are", "note")
    s.t(0, 22, "decided against (ADR-003, ADR-004) and nothing lands on those pins. The firmware still defines them in config.h.", "note")
    s.t(0, 56, "NET / FUNCTION", "pin"); s.t(300, 56, "PIN", "pin")
    s.t(430, 56, "PLANNED PART", "pin"); s.t(760, 56, "PHASE", "pin")
    s.wire([(0, 64), (930, 64)])
    yy = 84
    for net, pin, part, phase in FUTURE_ITEMS:
        s.t(0, yy, net, "gh"); s.t(300, yy, pin, "gh")
        s.t(430, yy, part, "gh"); s.t(760, yy, phase, "gh")
        yy += 22


def verification(s, ox, oy):
    """Evidence-tier statement. Identical on every sheet that carries it."""
    s.origin(ox, oy)
    s.t(0, 0, "VERIFICATION", "ttl")
    s.t(0, 28, "TIERS ARE NOT INTERCHANGEABLE. A part's POSITION and its VALUE are separate claims and are tagged separately.", "note")
    s.t(0, 46, "Strip/column assignments are PHYS. Hole-level row letters are RPT (builder-reported), including every coordinate in blocks E to H.", "note")
    s.t(0, 70, "NYV BY DECISION — open on purpose, not by oversight:", "lbl")
    s.t(0, 90, "•  TOP_RED continuity col 5 ↔ col 55 (GAP-5).  A Phase 7 rail check would close it, but top-vs-bottom was never confirmed.", "note")
    s.t(0, 108, "•  Carrier 5V terminal provenance (X-5)  ·  C3/C4/C5/C7 values (A1)  ·  whether Rev D uses the 5V pad (D2).", "note")
    s.t(0, 126, "•  K2's and J7's package markings — never read back.  Pole 2 of both relays — wired to nothing, never tested.", "note")
    s.t(0, 156, "BLOCKS E TO H ARE TRANSCRIBED FROM THE BENCH RECORD, NOT FROM A FRESH INSPECTION.", "lbl")
    s.t(0, 176, "Blocks A and B were captured against the board and photographs on 2026-09-07. E and F were assembled on 2026-09-22 and C, G", "note")
    s.t(0, 194, "and H on 2026-10-31 from ai/journal.md, ai/todo.md and ai/evidence/. Nothing was promoted; see netlist.md §14 and §21.", "note")
    s.t(0, 224, "THIS DRAWING REFLECTS THE PHYSICAL BOARD, NOT docs/breadboard_bringup_v3.md.", "lbl")
    s.t(0, 244, "The runbook carries documented defects in Phase 6 coil polarity, the transistor pin order and the Phase 7 column siting,", "note")
    s.t(0, 262, "and has no phase for Amp Out. Where they conflict, the board governs. Construction complete ≠ signed off ≠ validated —", "note")
    s.t(0, 280, "Phase 9 has not been run, and the instrument is not calibrated.", "note")


def overview(s):
    """The whole signal path on one page. Every part in the analog path is here;
    the relay drivers and the digital side are reduced to labels and boxes. Drawn
    at 1280 wide so it stays readable at that size."""
    s.origin(0, 0)
    s.t(46, 58, "SOURCE PATH — WHAT GOES INTO THE RIG", "ttl")
    s.t(46, 318, "RETURN PATH — WHAT COMES BACK", "ttl")

    # guitar input and U1
    j4 = s.connbox(46, 100, 96, 96, "J4", "GUITAR IN",
                   [("T", 62), ("S", 84)], "right")
    a, b = s.cap(190, 162, "C1", "10nF", vert=False)
    s.wire([j4["T"], a]); s.wire([b, (250, 162)]); s.junction(250, 162)
    s.wire([j4["S"], (172, 184), (172, 210)]); s.gnd(172, 210)
    c, d = s.res(250, 222, "R5", "100k", vert=True)
    s.wire([(250, 162), c]); s.netlabel(d[0], d[1] + 12, "OPA_BIAS"); s.wire([d, (d[0], d[1] + 12)])
    p, m, o = s.opamp(310, 182, "U1A", 3, 2, 1)
    s.wire([(250, 162), p])
    s.wire([o, (412, 182)]); s.junction(412, 182)
    s.wire([(412, 182), (412, 246), (292, 246), (292, 202), m])
    a, b = s.cap(462, 182, "C2", "10µF", pol=True, vert=False)
    s.wire([(412, 182), a]); s.wire([b, (530, 182)]); s.junction(530, 182)
    s.t(538, 172, "SOURCE_NODE", "net")

    # K1
    k1 = s.contacts(650, 182)
    s.wire([(530, 182), k1["NC"]])
    s.t(650, 172, "NC", "pin", "middle"); s.t(650, 256, "NO", "pin", "middle")
    s.t(754, 200, "COM", "pin")
    s.rect(664, 84, 72, 44)
    s.t(700, 103, "K1", "lbl", "middle"); s.t(700, 119, "TQ2-5V", "val", "middle")
    s.dashline([(700, 128), k1["ARM"]])
    s.netlabel(664, 106, "TEENSY 14 · Q1", "left")
    j5 = s.connbox(830, 164, 110, 96, "J5", "RIG SEND",
                   [("T", 46), ("S", 72)], "left")
    s.wire([k1["COM"], j5["T"]])
    s.wire([j5["S"], (806, 236), (806, 262)]); s.gnd(806, 262)

    # the rig
    s.rect(1040, 150, 200, 330, "ext", rx=6)
    s.t(1140, 298, "GUITAR RIG", "lbl", "middle")
    s.t(1140, 318, "device under test", "val", "middle")
    s.t(1140, 336, "external", "note", "middle")
    s.dashline([(940, 210), (1040, 210)])

    # K2
    k2 = s.contacts(780, 366, flip=True)
    s.t(780, 356, "NC", "pin", "middle"); s.t(770, 426, "NO", "pin", "end")
    s.t(676, 384, "COM", "pin", "end")
    s.rect(644, 284, 72, 44)
    s.t(680, 303, "K2", "lbl", "middle"); s.t(680, 319, "TQ2-5V", "val", "middle")
    s.dashline([(680, 328), k2["ARM"]])
    s.netlabel(716, 306, "TEENSY 15 · Q2")
    j6 = s.connbox(830, 330, 110, 76, "J6", "RTN TS",
                   [("T", 36), ("S", 58)], "left")
    j7 = s.connbox(830, 416, 110, 76, "J7", "RTN XLR",
                   [("2", 36), ("1,3", 58)], "left")
    s.wire([j6["T"], k2["NC"]]); s.wire([j7["2"], (780, 452), k2["NO"]])
    s.wire([j6["S"], (800, 388), (800, 496)]); s.gnd(800, 496)
    s.wire([j7["1,3"], (800, 474)]); s.junction(800, 474)
    s.dashline([(940, 366), (1040, 366)]); s.dashline([(940, 452), (1040, 452)])

    # RETURN_NODE, Amp Out, U4
    s.wire([k2["COM"], (610, 394)]); s.junction(610, 394)
    s.t(618, 412, "RETURN_NODE", "net")
    a, b = s.cap(474, 394, "C10", "0.1µF", vert=False)
    s.wire([(610, 394), b]); s.wire([a, (418, 394)]); s.junction(418, 394)
    c, d = s.res(418, 466, "R10", "100k", vert=True, lside=False)
    s.wire([(418, 394), c]); s.wire([d, (418, 506)]); s.netlabel(418, 506, "OPA_BIAS")
    p, m, o = s.opamp(376, 414, "U4A", 3, 2, 1, flip=True)
    s.wire([(418, 394), p])
    s.wire([o, (270, 414)]); s.junction(270, 414)
    s.wire([(270, 414), (270, 482), (392, 482), (392, 434), m])
    a, b = s.cap(226, 414, "C11", "10µF", pol=True, vert=False, flip=True)
    s.wire([(270, 414), b]); s.wire([a, (186, 414)]); s.junction(186, 414)
    c, d = s.res(186, 470, "R11", "100k", vert=True, lside=False)
    s.wire([(186, 414), c]); s.wire([d, (186, 508)]); s.gnd(186, 508)
    j8 = s.connbox(46, 352, 96, 96, "J8", "AMP OUT",
                   [("T", 62), ("S", 84)], "right")
    s.wire([j8["T"], (186, 414)])
    s.wire([j8["S"], (150, 436), (150, 462)]); s.gnd(150, 462)

    # codec, Teensy, Pi
    s.icbox(500, 560, 190, 100, "U3", "SGTL5000 codec", "44.1 kHz stereo")
    for x, y0, name in ((530, 182, "IN L"), (610, 394, "IN R")):
        s.wire([(x, y0), (x, 560)])
        s.t(x, 576 + 66, name, "pin", "middle")
    s.wire([k1["NO"], (570, 238), (570, 560)])
    s.t(570, 642, "OUT L", "pin", "middle")
    s.icbox(780, 568, 150, 84, "U2", "Teensy 4.1", "FFT, peaks, TF")
    s.icbox(1030, 568, 200, 84, "Pi 5", "Raspberry Pi 5", "7in touch display")
    s.wire([(690, 610), (780, 610)]); s.t(735, 602, "I²S", "net", "middle")
    s.arrow(768, 610, "r")
    s.wire([(930, 610), (1030, 610)]); s.t(980, 602, "UART", "net", "middle")
    s.arrow(1018, 610, "r")
    s.t(980, 628, "TX only", "pin", "middle")

    # bias
    s.pwr(100, 590, "+5V")
    a, b = s.res(100, 628, "R1", "47k", vert=True); s.wire([(100, 590), a])
    c, d = s.res(100, 708, "R2", "10k", vert=True); s.wire([b, c]); s.gnd(d[0], d[1])
    s.junction(100, 668); s.wire([(100, 668), (220, 668)])
    a, b = s.cap(170, 700, "C4", "0.1µF", lside=False)
    s.wire([(170, 668), a]); s.junction(170, 668); s.gnd(b[0], b[1])
    s.netlabel(220, 668, "OPA_BIAS")
    s.t(226, 700, "0.874 V measured. On a 5 V", "note")
    s.t(226, 716, "supply the OPA1642 input must", "note")
    s.t(226, 732, "stay below 1.5 V.", "note")

    s.t(440, 692, "U1 and U4 are OPA1642 on +5 V. Their channel B halves are terminated as", "note")
    s.t(440, 708, "followers on OPA_BIAS. Relays are drawn de-energised, the boot state:", "note")
    s.t(440, 724, "buffer → J5 and TS return → U3. U3 is stacked on U2 by soldered headers.", "note")
    s.t(440, 740, "Not calibrated. The effect of Amp Out on the RETURN reading is unmeasured.", "note")
    s.t(960, 692, f"{PROJ.upper()}", "lbl")
    s.t(960, 708, f"As-built overview · Rev {REV}", "note")
    s.t(960, 724, "Evidence for every value:", "note")
    s.t(960, 740, "docs/asbuilt/netlist.md", "val")


# ================================================================== COMPOSERS
OUT = "docs/asbuilt"

SHEETS = [
    ("schematic_overview.svg", "Overview: the whole signal path"),
    ("schematic_1sheet.svg", "Single sheet: bench reconstruction reference"),
    ("schematic_sheet1_analog.svg", "Sheet 1 of 2: power, analog, relays, Amp Out"),
    ("schematic_sheet2_digital.svg", "Sheet 2 of 2: digital, reserved hardware, Pi link"),
]

HTML_HEAD = f"""<!doctype html>
<meta charset="utf-8">
<title>Guitar Rig Analyzer Schematics</title>
<style>
  body{{max-width:1320px;margin:32px auto;padding:0 16px;background:#fff;color:#111;
       font:16px/1.5 'Helvetica Neue',Helvetica,Arial,sans-serif}}
  img{{display:block;width:100%;height:auto;border:1px solid #ddd}}
  h2{{margin:40px 0 12px;font-size:18px}}
</style>
<body>
<h1>Guitar Rig Analyzer as-built schematics</h1>
<p>Rev {REV}. Generated by tools/gen_schematic.py from docs/asbuilt/netlist.md.</p>
"""


def build():
    os.makedirs(OUT, exist_ok=True)
    made = []

    # ---- overview
    s = Sheet(1280, 800, 1, 1, "Whole signal path, one page")
    overview(s)
    p = f"{OUT}/schematic_overview.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- single sheet
    s = Sheet(2320, 3260, 1, 1, "Single-sheet bench reconstruction reference")
    draw_power(s, 90, 110)
    draw_analog(s, 90, 620)
    draw_digital(s, 1300, 110)
    draw_future(s, 1300, 1050)
    draw_pi_link(s, 1300, 1370)
    draw_relay_send(s, 90, 1290)
    draw_relay_return(s, 90, 1960)
    draw_amp_out(s, 90, 2630)
    s.origin(0, 0)
    verification(s, 1300, 1700)
    s.titleblock()
    p = f"{OUT}/schematic_1sheet.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- sheet 1 of 2
    s = Sheet(1360, 3480, 1, 2,
              "Power, references, analog front end, relay routing and Amp Out")
    draw_power(s, 90, 110)
    draw_analog(s, 90, 620)
    draw_relay_send(s, 90, 1290)
    draw_relay_return(s, 90, 1960)
    draw_amp_out(s, 90, 2630)
    s.origin(0, 0)
    s.t(90, 3270, "Continues on sheet 2: SOURCE_NODE → U3 LINE-IN-L; RETURN_NODE → U3 LINE-IN-R; Teensy ↔ Audio Shield; Pi link.", "note")
    s.titleblock()
    p = f"{OUT}/schematic_sheet1_analog.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- sheet 2 of 2
    s = Sheet(1360, 2190, 2, 2, "Digital interface, reserved hardware and the Pi link")
    draw_digital(s, 130, 110)
    draw_future(s, 130, 1050)
    draw_pi_link(s, 130, 1370)
    s.origin(0, 0)
    s.t(130, 1642, "SOURCE_NODE originates on sheet 1 (C2 output, breadboard column 48).", "note")
    s.t(130, 1660, "RETURN_NODE arrives on sheet 1 from RELAY_RETURN COM (16a) — TS or XLR return, operator-selected.", "note")
    verification(s, 130, 1710)
    s.titleblock()
    p = f"{OUT}/schematic_sheet2_digital.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- viewer
    p = f"{OUT}/schematics.html"
    with open(p, "w") as f:
        f.write(HTML_HEAD)
        for name, title in SHEETS:
            f.write(f'<h2>{title}</h2>\n<a href="{name}"><img src="{name}" alt="{title}"></a>\n')
        f.write("</body>\n")
    made.append(p)

    for m in made:
        print(f"  wrote {m}  ({os.path.getsize(m)/1024:.1f} KB)")


if __name__ == "__main__":
    build()
