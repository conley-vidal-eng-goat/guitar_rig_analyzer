#!/usr/bin/env python3
"""
Guitar Rig Analyzer — as-built schematic generator.

Emits BOTH deliverables from one source of truth:
    docs/asbuilt/schematic_1sheet.svg          single-sheet, bench reconstruction
    docs/asbuilt/schematic_sheet1_analog.svg   sheet 1 of 2, power + analog
    docs/asbuilt/schematic_sheet2_digital.svg  sheet 2 of 2, digital + future

Circuit source of truth: docs/asbuilt/netlist.md
Run:  python3 tools/gen_schematic.py

TO ADD PHASE 5-9 HARDWARE: see docs/asbuilt/SCHEMATIC_EDITING.md.
Short version - add rows to FUTURE_ITEMS below, then write a draw_*() block
using the symbol primitives and call it from the sheet composers at the bottom.
"""

import os

SANS = "'DejaVu Sans','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = "'DejaVu Sans Mono',Menlo,Consolas,monospace"

REV   = "2026-09-07"
PROJ  = "Guitar Rig Analyzer"
TITLE = "As-Built Breadboard - Known-Good Configuration"
DRAWN = "C. Vidal"

# ---------------------------------------------------------------- interconnect
# colour, carrier screw terminal, U3 pad, net, function
# colour, carrier screw, U3 pad, net, direction, function
#   direction: 'r' = toward the codec, 'l' = toward the Teensy,
#              'b' = bidirectional, '' = power/no arrow
#
# NET NAMES ARE CODEC-REFERENCED (SGTL5000 perspective) — see NAMING note in
# draw_digital(). I2S_DIN is the CODEC's data input, fed by the Teensy's
# SAI1_TX_DATA0 on pin 7. I2S_DOUT is the CODEC's data output, read by the
# Teensy's SAI1_RX_DATA0 on pin 8. Confirmed at config.h:81-85 and
# ai/journal.md:1077. Do not flip these without changing both of those too.
INTERCONNECT = [
    ("green",  "5V",  "5V",   "+5V",       "",  "5V pass-through — shield function NYV"),
    ("purple", "GND", "GND",  "GND",       "",  "shield ground return"),
    ("brown",  "3V3", "3.3V", "+3V3",      "",  "SGTL5000 supply"),
    ("yellow", "7",   "7",    "I2S_DIN",   "r", "Teensy SAI1_TX_DATA0 → codec"),
    ("orange", "8",   "8",    "I2S_DOUT",  "l", "codec → Teensy SAI1_RX_DATA0"),
    ("black",  "18",  "18",   "I2C_SDA",   "b", "codec control"),
    ("orange", "19",  "19",   "I2C_SCL",   "r", "codec control"),
    ("red",    "20",  "20",   "I2S_LRCLK", "r", "frame clock · 44.1 kHz · 1×Fs"),
    ("white",  "21",  "21",   "I2S_BCLK",  "r", "bit clock · 2.8224 MHz · 64×Fs"),
    ("gray",   "23",  "23",   "I2S_MCLK",  "r", "master clock · 11.2896 MHz · 256×Fs"),
]

# ---------------------------------------------------------------- future work
FUTURE_ITEMS = [
    ("RELAY_SEND",    "Teensy 14", "TQ2-5V + MMBT3904 driver", "Phase 6"),
    ("RELAY_RETURN",  "Teensy 15", "TQ2-5V + MMBT3904 driver", "Phase 7"),
    ("JACK_INSTRUMENT", "Teensy 16", "Switchcraft #11 detect", "Phase 5"),
    ("JACK_RIG_SEND",   "Teensy 17", "jack detect",            "Phase 7"),
    ("JACK_RETURN_TS",  "Teensy 22", "jack detect",            "Phase 7"),
    ("JACK_RETURN_XLR", "Teensy 24", "XLR return",             "Phase 8"),
    ("RA8875_CS / INT / RESET", "Teensy 10 / 9 / 5", "SPI display", "deferred"),
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

    def cap(self, x, y, ref, val, pol=False, vert=True, lside=True):
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
        self.path(x, y, d)
        if pol:
            self.t(x - 10, y - 16, "+", "val", "middle")
        self.t(x, y - 24, ref, "lbl", "middle")
        self.t(x, y + 32, val, "val", "middle")
        return (x - 16, y), (x + 16, y)

    def opamp(self, x, y, ref, pin_p, pin_m, pin_o):
        """x = left edge, y = centre. + on top. Returns (p, m, out) coords."""
        xx, yy = self._(x, y)
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


def draw_analog(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 1160, 500, "B — OPA1642 HIGH-IMPEDANCE BUFFER (SOURCE PATH)")

    j1 = s.connbox(20, 60, 92, 118, "J1", "3.5 mm IN",
                   [("T", 55), ("R", 82), ("S", 108)], "right",
                   "tip = white cond.")
    s.t(20, 232, "R — no connect (taped off)", "note")
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

    j2 = s.connbox(654, 235, 92, 105, "J2", "3.5 mm",
                   [("S", 92)], "right", "NOT PLUGGED IN — open stub")
    s.wire([(700, 115), (700, 235)])
    s.t(688, 230, "T", "pin", "end")
    s.wire([j2["S"], (790, 327), (790, 350)]); s.gnd(790, 350)

    s.wire([(700, 115), (742, 115)])
    s.netlabel(742, 115, "SOURCE_NODE")

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


def draw_digital(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 990, 910,
                 "C — TEENSY ↔ AUDIO SHIELD INTERFACE  (FROZEN GEOMETRY — DO NOT DISTURB)")

    ys, y = {}, 92
    for i, row in enumerate(INTERCONNECT):
        ys[row[1]] = y
        y += 54 if i == 2 else 34

    s.icbox(30, 55, 215, 405, "U2", "Teensy 4.1", "Dinkle screw carrier")
    s.icbox(690, 55, 235, 515, "U3", "Audio Shield Rev D", "SGTL5000")

    for colour, screw, pad, net, dr, fn in INTERCONNECT:
        yy = ys[screw]
        s.t(239, yy + 4, screw, "pin", "end")
        s.t(696, yy + 4, pad, "pin")
        s.wire([(245, yy), (690, yy)])
        s.t(400, yy - 8, net, "net", "end")
        s.t(410, yy - 8, f"·  {colour}  —  {fn}", "note")
        if dr:
            s.arrow(655, yy, dr)

    s.wire([(690, 480), (600, 480)])
    s.netlabel(600, 480, "SOURCE_NODE", "left")
    s.t(696, 484, "LINE IN L", "pin")
    s.t(600, 506, "red jumper: breadboard 48e → U3 LINE-IN-L pad", "note", "end")

    s.wire([(690, 545), (658, 545)])
    s.nc(648, 545)
    s.t(696, 549, "LINE IN R", "pin")
    s.t(628, 541, "RETURN_NODE  (I²S ch 1)  —  NOT CONNECTED", "lbl", "end")
    s.t(628, 561, "No conductor is fitted. The −56 dBFS this channel reports", "note", "end")
    s.t(628, 578, "is crosstalk from LINE IN L, not a measurement.", "note", "end")

    s.rect(30, 600, 640, 142, "dash", rx=4)
    s.t(42, 620, "PROVENANCE & CONVENTIONS", "lbl")
    s.t(42, 641, "Net names are CODEC-REFERENCED:  I2S_DIN = codec data IN (Teensy 7, SAI1_TX_DATA0);", "note")
    s.t(42, 657, "I2S_DOUT = codec data OUT (Teensy 8, SAI1_RX_DATA0).   Ref: config.h:81-85", "note")
    s.t(42, 680, "Clocks derived from SAMPLE_RATE 44100 (config.h:208); all three scope-confirmed:", "note")
    s.t(42, 696, "LRCLK 44.108 kHz · BCLK ~2.82 MHz · MCLK ~11.29 MHz  (journal 2026-09-06 (1))", "note")
    s.t(42, 719, "U3 \"Rev D\" read from silkscreen. SGTL5000 identified functionally over I²C, not", "note")
    s.t(42, 735, "from its package marking. The shield's use of the 5V pad is UNVERIFIED.", "note")

    s.t(30, 774, "GEOMETRY IS LOAD-BEARING — this is the fix, not a detail:", "lbl")
    s.t(30, 794, "•  Jumper length ≈ 25–30 mm (was 100–200 mm flying leads)", "note")
    s.t(30, 812, "•  U3 sits ≈ 25 mm above U2, bundle held tight, 1:1 screw → pad", "note")
    s.t(30, 830, "•  Result: 360/360 clean windows, 0 corrupted of 11,520 samples/node", "note")
    s.t(30, 848, "•  U2 is I²S MASTER — it generates MCLK / BCLK / LRCLK", "note")
    s.t(560, 794, "⚠  TWO ORANGE WIRES: pin 8 (I2S_DOUT) and pin 19 (I2C_SCL).", "note")
    s.t(560, 812, "   DOUT is the conductor that caused the corruption fault.", "note")
    s.t(560, 830, "   Do not re-seat this bundle from memory. Risk R3.", "note")


def draw_future(s, ox, oy):
    s.origin(ox, oy)
    s.blockframe(-30, -30, 990, 300,
                 "D — PHASES 5–9: NOT INSTALLED (reserved)")
    s.t(0, 6, "Firmware pin definitions exist in config.h:77-101. NO HARDWARE IS FITTED.", "note")
    s.t(0, 22, "Add each block here as its phase is built, then regenerate.", "note")
    s.t(0, 56, "NET / FUNCTION", "pin"); s.t(300, 56, "PIN", "pin")
    s.t(430, 56, "PLANNED PART", "pin"); s.t(760, 56, "PHASE", "pin")
    s.wire([(0, 64), (930, 64)])
    yy = 84
    for net, pin, part, phase in FUTURE_ITEMS:
        s.t(0, yy, net, "gh"); s.t(300, yy, pin, "gh")
        s.t(430, yy, part, "gh"); s.t(760, yy, phase, "gh")
        yy += 22


# ================================================================== COMPOSERS
OUT = "docs/asbuilt"


def build():
    os.makedirs(OUT, exist_ok=True)
    made = []

    # ---- single sheet
    s = Sheet(2320, 1560, 1, 1, "Single-sheet bench reconstruction reference")
    draw_power(s, 90, 110)
    draw_analog(s, 90, 620)
    draw_digital(s, 1300, 110)
    draw_future(s, 1300, 1050)
    s.origin(0, 0)
    s.t(90, 1230, "VERIFICATION", "ttl")
    s.t(90, 1258, "All connections shown are PHYS (direct physical observation) or PHOTO.", "note")
    s.t(90, 1276, "Hole-level row letters are RPT (builder-reported); strip/column assignments are PHYS.", "note")
    s.t(90, 1294, "NYV by decision: TOP_RED col5-col55 continuity (GAP-5); carrier 5V provenance (X-5).", "note")
    s.t(90, 1318, "THIS DRAWING REFLECTS THE PHYSICAL BOARD, NOT docs/breadboard_bringup_v3.md.", "lbl")
    s.t(90, 1338, "The runbook contains 6 documented defects; where they conflict, the board governs.", "note")
    s.titleblock()
    p = f"{OUT}/schematic_1sheet.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- sheet 1 of 2
    s = Sheet(1360, 1400, 1, 2, "Power, references and analog front end")
    draw_power(s, 90, 110)
    draw_analog(s, 90, 620)
    s.origin(0, 0)
    s.t(90, 1210, "Continues on sheet 2: SOURCE_NODE → U3 LINE-IN-L; Teensy ↔ Audio Shield.", "note")
    s.titleblock()
    p = f"{OUT}/schematic_sheet1_analog.svg"; open(p, "w").write(s.render()); made.append(p)

    # ---- sheet 2 of 2
    s = Sheet(1360, 1620, 2, 2, "Digital interface and reserved future hardware")
    draw_digital(s, 130, 110)
    draw_future(s, 130, 1050)
    s.origin(0, 0)
    s.t(130, 1390, "SOURCE_NODE originates on sheet 1 (C2 output, breadboard column 48).", "note")
    s.titleblock()
    p = f"{OUT}/schematic_sheet2_digital.svg"; open(p, "w").write(s.render()); made.append(p)

    for m in made:
        print(f"  wrote {m}  ({os.path.getsize(m)/1024:.1f} KB)")


if __name__ == "__main__":
    build()
