# Guitar Rig Analyzer — Breadboard Bring-Up Guide (v3)

**Document version:** 3.0 (2026-06-01) — *LEGO-instruction style. Built around the parts you actually purchased. v3 fixes five critical bugs found in v2: a severed SOURCE tap and inverted relay topology in Phase 7, a stale parts-availability claim in Phase 1, a missing TQ2 pinout in Phase 6, and a draft "Wait — correction:" note in Phase 4. See the v3 changelog at the end of this document.*

**v1** ([breadboard_bringup.md](breadboard_bringup.md)) and **v2** ([breadboard_bringup_v2.md](breadboard_bringup_v2.md)) are kept alongside for cross-reference. v3 supersedes both.

---

## If something feels wrong — read this first

Pin this page to your monitor.

1. **Smell something warm, see smoke, hear buzzing, or feel anything getting hot?** Unplug the USB cable from the Teensy immediately. You will not break anything by unplugging fast. You *might* break something by leaving a fault energised.
2. **Wait 30 seconds**, touch every IC with the back of your finger — if anything is uncomfortably warm, that component is suspect.
3. **Open Appendix A** (Troubleshooting tree) at the back of this doc. Most "it's broken" moments are one of five known patterns.
4. **Never trust a part until you've continuity-tested it.** A new $3 OPA1642 from DigiKey can still be DOA from a static zap during shipping.
5. **Take photos of the breadboard at the end of each phase.** When something stops working in phase 6 that worked in phase 5, the photo is the diff.

You have **5× OPA1642 spares, 100× MMBT3904 spares, 5× TQ2-5V (2 used + 3 spare), and 4× spare Chip Quik adapter boards.** Your first attempt does not have to be perfect.

> **ESD note.** Touch the silicone mat (or any grounded metal — a screw on a wall plate works) before grabbing the OPA1642 or any other IC. Don't shuffle on carpet during the SMD steps. Static you can't feel will quietly degrade a JFET input.

---

## How to use this guide

Each phase looks like this:

1. **Goal** — one sentence.
2. **Parts tray** — a picture and a list of just the parts you need to grab from your bin for *this phase*.
3. **Steps** — numbered. Each step is *one action* + *one mini-diagram* + *one DMM check (if applicable)*.
4. **End-of-phase verify** — the test you run before moving on.
5. **Background** *(skip if you're in a hurry)* — why each piece is there, what it does, common failures.

Treat the steps like LEGO instructions: do them in order, finish each one before reading the next. The background is for when something is confusing or doesn't work — not required reading the first time through.

> **Stop sign convention.** When you see a **[STOP]** row in a verify table, **do not proceed past it** until that check passes. Breadboard work compounds — a quiet fault in phase 2 becomes an unsolvable mystery in phase 6.

---

## What you'll have when you're done

A working **breadboard prototype** of the v0.6 signal-router hardware that will eventually live on a custom PCB. End-state block diagram:

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 240" width="100%" style="max-width:800px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .box { fill: #f6f8fa; stroke: #444; stroke-width: 1.5; }
    .boxpwr { fill: #fff3e0; stroke: #c84; stroke-width: 1.5; }
    .boxbuf { fill: #e3f2fd; stroke: #36c; stroke-width: 1.5; }
    .boxrel { fill: #e8f5e9; stroke: #284; stroke-width: 1.5; }
    .boxjck { fill: #fce4ec; stroke: #a37; stroke-width: 1.5; }
    .sig { stroke: #2962ff; stroke-width: 2; fill: none; }
    .ctl { stroke: #2e7d32; stroke-width: 1.5; fill: none; stroke-dasharray: 4 3; }
    .pwr { stroke: #c62828; stroke-width: 1.5; fill: none; }
  </style>
  <defs>
    <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#222"/>
    </marker>
  </defs>

  <text x="400" y="18" text-anchor="middle" class="lblbig">v2 end-state</text>

  <rect x="20" y="40" width="130" height="50" rx="4" class="boxpwr"/>
  <text x="85" y="62" text-anchor="middle" class="lblbig">POWER</text>
  <text x="85" y="78" text-anchor="middle" class="lbl">+5V, GND, VGND</text>

  <rect x="20" y="140" width="130" height="80" rx="4" class="boxjck"/>
  <text x="85" y="160" text-anchor="middle" class="lblbig">JACKS</text>
  <text x="85" y="178" text-anchor="middle" class="lbl">Switchcraft #11 ×3</text>
  <text x="85" y="194" text-anchor="middle" class="lbl">Neutrik XLR ×1</text>
  <text x="85" y="210" text-anchor="middle" class="lbl">switch contacts → detect</text>

  <rect x="200" y="100" width="130" height="60" rx="4" class="boxbuf"/>
  <text x="265" y="125" text-anchor="middle" class="lblbig">BUFFER</text>
  <text x="265" y="143" text-anchor="middle" class="lbl">OPA1642 ×1</text>
  <text x="265" y="158" text-anchor="middle" class="lbl">unity-gain JFET</text>

  <rect x="380" y="100" width="130" height="60" rx="4" class="boxrel"/>
  <text x="445" y="125" text-anchor="middle" class="lblbig">RELAYS</text>
  <text x="445" y="143" text-anchor="middle" class="lbl">TQ2-5V ×2</text>
  <text x="445" y="158" text-anchor="middle" class="lbl">MMBT3904 drivers</text>

  <rect x="560" y="70" width="120" height="130" rx="4" class="box"/>
  <text x="620" y="92" text-anchor="middle" class="lblbig">Teensy 4.1</text>
  <text x="620" y="110" text-anchor="middle" class="lbl">+ Audio Shield</text>
  <text x="620" y="135" text-anchor="middle" class="lbl">SGTL5000 codec</text>
  <text x="620" y="155" text-anchor="middle" class="lbl">SOURCE / RETURN</text>

  <rect x="700" y="70" width="80" height="130" rx="4" class="box"/>
  <text x="740" y="92" text-anchor="middle" class="lblbig">Pi 5</text>
  <text x="740" y="115" text-anchor="middle" class="lbl">7" touch</text>
  <text x="740" y="135" text-anchor="middle" class="lbl">display</text>
  <text x="740" y="170" text-anchor="middle" class="lbl">UART</text>
  <text x="740" y="186" text-anchor="middle" class="lbl">460800 baud</text>

  <line x1="150" y1="65" x2="200" y2="125" class="pwr"/>
  <line x1="150" y1="65" x2="380" y2="125" class="pwr"/>
  <line x1="150" y1="65" x2="560" y2="125" class="pwr"/>

  <line x1="150" y1="180" x2="200" y2="130" class="sig" marker-end="url(#ar)"/>
  <line x1="330" y1="130" x2="380" y2="130" class="sig" marker-end="url(#ar)"/>
  <line x1="510" y1="130" x2="560" y2="130" class="sig" marker-end="url(#ar)"/>
  <line x1="680" y1="135" x2="700" y2="135" class="ctl" marker-end="url(#ar)"/>
</svg>

This is the **`DISPLAY_TARGET_PI`** build (since you bought the Pi 5 + touch display). The Teensy still owns all DSP and routing; the Pi just renders.

> **⚠️ Corrected 2026-09-11.** This line previously named a flag **`USE_PI_DISPLAY`** that was never implemented anywhere in the firmware — it existed only in this sentence, and the repository was meanwhile building an RA8875 product. That drift is now resolved: the decision is recorded in [docs/adr/ADR-001-display-architecture.md](adr/ADR-001-display-architecture.md) and the real mechanism is the tri-state `DISPLAY_TARGET` in `config.h`:
>
> | Value | Renderer | Use |
> |---|---|---|
> | `DISPLAY_TARGET_PI` | Pi 5 over UART (`Serial1`, pins 0/1) | **production** |
> | `DISPLAY_TARGET_RA8875` | RA8875 800×480 over SPI | debug / fallback only |
> | `DISPLAY_TARGET_NONE` | none | **use this for Phases 1–9** |
>
> **For every phase in this runbook, build with `DISPLAY_TARGET_NONE`.** No display hardware is attached during breadboard bring-up, and `_NONE` compiles out both renderers — which also removes the Adafruit RA8875 library and the RA8875 pin claims from the build entirely. The Pi link is **Phase 10**, at the end, and it is not a prerequisite for anything before it.

---

## Master parts list — what you have on hand

This consolidates your **DigiKey + Mouser + Vilros + Amazon** orders into one place. I've marked which phase each part is used in, so you can lay out a bin per phase.

### Compute / display

| Part | Source | Used in |
|---|---|---|
| PJRC Teensy 4.1 (no pins) ×1 | Amazon | Phase 0 onward |
| Teensy 4 Audio Shield Rev D ×1 | Amazon | Phase 4 onward |
| SanDisk 128GB microSD ×1 | Amazon | Optional (calibration / exports) |
| Raspberry Pi 5 8GB ×1 | Vilros | **Phase 10** + setup |
| Pi 5 Active Cooler ×1 | Vilros | **Phase 10** |
| Pi 27W USB-C PSU ×1 | Vilros | **Phase 10** |
| Pi Touch Display 2 (7") ×1 | Vilros | **Phase 10** |
| Freenove RPi GPIO breakout HAT ×1 | Amazon | **Phase 10** (Pi↔Teensy UART) |
| HiLetgo SSD1309 2.42" OLED ×1 | Amazon | Optional secondary status display |

> **⚠️ Corrected 2026-09-11.** The five Pi parts above were previously marked "Phase 9". **Phase 9 in this document is the validation harness** — it has nothing to do with the Pi, and no phase in v3 ever installed the Pi hardware. It was purchased with nowhere to go. The Pi link is now **Phase 10** (see below). Retrofitting it into Phase 9 would have meant claiming a completed phase covered untested work, which is the status-collapsing mistake `ai/todo.md` exists to prevent.

### Active / semiconductor

| Part | Qty | Source | Used in |
|---|---:|---|---|
| OPA1642AID (SOIC-8) | 5 | DigiKey 296-25614-5-ND | Phase 4 (buffer) |
| MMBT3904 (SOT-23 NPN) | 100 | DigiKey | Phase 6, 7 (relay drivers) |
| **TQ2-5V (non-latching DPDT, 5V) — to buy** | 2 | DK 255-1004-5-ND | Phase 6, 7 (relays) |
| TQ2-L2-5V (latching DPDT — keep for future PCB) | 10 | DigiKey | *Not used in breadboard* — see "About your relays" sidebar |
| 1N4148 DO-35 (through-hole) | 20 | Amazon | Phase 6, 7 (flyback) |
| 74HC138 (SO-16 decoder) | 25 | DigiKey | *Not used in breadboard* — see "About the 74HC138" sidebar |

### Adapters (so SMD parts can live on the breadboard)

| Part | Qty | Source | Used in |
|---|---:|---|---|
| Chip Quik PA0001 SOIC-8 to DIP-8 | 2 | Mouser 910-PA0001 | Phase 0.5 (solder OPA1642 onto this) |
| Chip Quik SIPH06-1 SOT-23 to DIP | 4 | Mouser 910-SIPH06-1 | Phase 0.5 (solder MMBT3904 onto this) |

### Passives — through-hole, for the breadboard

| Part | Qty | Source | Used in |
|---|---:|---|---|
| 10µF / 25V radial electrolytic (Panasonic ECA-1EM100) | 10 | Mouser | Phase 1, 4 (decoupling, VGND, AC coupling) |
| 0.1µF / 50V leaded ceramic (KYOCERA AVX SR205C104KART) | 20 | Mouser | Phase 1, 4 (decoupling) |
| 10nF / 50V leaded ceramic (Vishay K103K10X7RF5UL2) | 10 | Mouser | Phase 4 (input AC coupling) |
| 1nF / 50V leaded C0G (Vishay K102J15C0GF53H5G) | 20 | Mouser | Optional — RC filter calibration in Phase 9 |
| Through-hole resistors (YAGEO MFR-25 series) | various | Mouser | Phases 2–7 |
| └ 47Ω 1% | 40 | | (HF damping if needed) |
| └ 100Ω 1% | 40 | Phase 2 (LED current limit) | |
| └ 1kΩ 1% | 60 | Phase 4 (input divider option) | |
| └ 10kΩ 1% | 60 | Phase 1 (VGND divider), Phase 6/7 (BJT pulldown) | |
| └ 47kΩ 1% | 40 | Reserve | |
| └ 100kΩ 1% | 50 | Phase 4 (input bias, substitute for 1MΩ) | |

### Connectors

| Part | Qty | Source | Used in |
|---|---:|---|---|
| Switchcraft #11 1/4" mono jack | 10 | Amazon | Phase 5, 7 (instrument in, rig send, rig return TS) |
| Neutrik NC3FAH2-0 XLR F/M combo | 2 | Mouser | Phase 8 (XLR return) |
| Phoenix Contact 1715721 2P 5.08mm terminal block | 4 | Mouser + DK | Reserve (PCB output) |
| JST B2B-XH-A 2P 2.5mm header | 10 | DigiKey | Reserve (PCB output) |

### Breadboard / prototyping

| Part | Source | Used in |
|---|---|---|
| BB830 solderless breadboard | Amazon | Phase 0 onward |
| 560pc jumper-wire kit | Amazon | Phase 0 onward |
| WWZMDiB 2.54mm perf board ×54 | Amazon | Reserve (post-breadboard hand-built version) |
| ElectroCookie prototype boards ×6 | Amazon | Reserve |
| Terminal-block breakout for Teensy 4.1 | Amazon | Phase 0 (screw-down access to Teensy pins) |
| Custom Circuit Solutions 16-pin SMD breakouts ×6 | Amazon | Reserve (for 74HC138 on the PCB) |
| Cermant SMD 0402/0603/0805 breakout plates ×50 | Amazon | Reserve (PCB-stage if needed) |

### Tools

| Tool | Source |
|---|---|
| FNIRSI DWS-200 200W soldering station (with F210 + F245 tips) | Amazon |
| Kester 63/37 0.020" no-clean solder | Amazon |
| ENGINEER SS-03 desolder pump | Amazon |
| iFixit precision tweezers | Amazon |
| Klein MM420 auto-ranging TRMS DMM | Amazon |
| KOTTO solder fume extractor | Amazon |
| VECO-T silicone soldering mat (heat-resistant) | Amazon |
| 99.9% IPA, 1 gal | Amazon |
| DIDODI SMT 4-in-1 soldering practice kit | Amazon |

---

## Background — about your relays and the 74HC138

> *Skip this section the first time through. It's here so you know why some parts you ordered aren't in the bring-up path.*

**About your relays.** You ordered **TQ2-L2-5V** ×10. The `-L2` suffix means **dual-coil latching DPDT**. They take a *pulse* on a "set" coil to switch one way, and a pulse on a "reset" coil to switch the other — then they *hold state with zero current*. That's great for production: quieter, lower power, survives brief power glitches. But the firmware in `signal_router.cpp` today drives the relay statically (`digitalWrite(PIN, HIGH/LOW)`), so a latching relay would need both new firmware *and* a second GPIO per relay. For the breadboard, buy **2× TQ2-5V** (non-latching, same family and footprint — DigiKey 255-1004-5-ND). Keep the TQ2-L2 for a future PCB revision; we can revisit the firmware then.

**About the 74HC138.** You ordered 25 of them. The 74HC138 is a **3-to-8 line decoder/demux**. It's not used in the breadboard bring-up — it's there for the PCB phase if you decide to multiplex relay control or jack-detect signals across fewer Teensy pins (3 select lines → 8 outputs). For 2 relays + 4 jack-detect inputs, you don't need it; you have plenty of free GPIOs. Save them.

**About the OLED.** The HiLetgo SSD1309 is a 128×64 monochrome OLED. Not needed for the bring-up. It would make a nice secondary "status badge" display if you ever want one on a hardware front-panel separate from the Pi touchscreen.

---

# Phase 0 — Workspace and inventory

> **Goal:** A clean, well-lit workspace with the Teensy on standby and every part for phases 1–9 sorted into labeled cups or bins.

## Parts tray for this phase

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 200" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 0 — parts tray</text>
  <rect x="20" y="40" width="660" height="140" rx="8" class="tray"/>
  <rect x="40" y="60" width="180" height="50" class="item"/>
  <text x="130" y="80" text-anchor="middle" class="lbl">BB830 breadboard</text>
  <text x="130" y="98" text-anchor="middle" class="lbl">(in original sleeve)</text>
  <rect x="240" y="60" width="180" height="50" class="item"/>
  <text x="330" y="80" text-anchor="middle" class="lbl">Teensy 4.1 (no pins)</text>
  <text x="330" y="98" text-anchor="middle" class="lbl">+ USB cable</text>
  <rect x="440" y="60" width="220" height="50" class="item"/>
  <text x="550" y="80" text-anchor="middle" class="lbl">Teensy terminal-block breakout</text>
  <text x="550" y="98" text-anchor="middle" class="lbl">(screw-down version)</text>
  <rect x="40" y="125" width="180" height="40" class="item"/>
  <text x="130" y="148" text-anchor="middle" class="lbl">Jumper-wire kit (560 pc)</text>
  <rect x="240" y="125" width="180" height="40" class="item"/>
  <text x="330" y="148" text-anchor="middle" class="lbl">Klein MM420 DMM</text>
  <rect x="440" y="125" width="220" height="40" class="item"/>
  <text x="550" y="148" text-anchor="middle" class="lbl">VECO-T silicone mat</text>
</svg>

## Steps

**1. Lay out the silicone mat on a flat surface.** This is your work area for the next 9 phases. Keep food, drinks, and pets away.

**2. Sort your parts into cups.** Use the master parts list above as your guide. Label each cup with the part name + the phase number. Suggested groupings:

- **Cup A — phase 1 power:** 10µF caps (×3), 0.1µF caps (×4), 10K resistors (×2).
- **Cup B — phase 2 LEDs:** any 2 LEDs you have lying around (an old breadboard kit, an old toy), 100Ω resistors (×2).
- **Cup C — phase 4 buffer:** 1× OPA1642AID, 1× Chip Quik PA0001 adapter (still bare), 100K resistors (×2), 10nF ceramic (×2), 10µF electrolytic (×2), 0.1µF ceramic (×2).
- **Cup D — phase 6/7 drivers:** 4× MMBT3904, 4× SIPH06-1 adapters (still bare), 1N4148s (×4), 10K resistors (×4), 100Ω resistors (×4 — base limiters; we'll explain).
- **Cup E — phase 5/7/8 jacks:** 3× Switchcraft #11, 1× Neutrik XLR.

**3. Mount the Teensy on the screw-down breakout.** Push the Teensy 4.1 (no pins) onto the breakout board's pin sockets. The Teensy is *not* on the breadboard — the breakout sits next to it.

**4. Power up the Teensy on USB and confirm it boots.** Open the Arduino IDE Serial Monitor at 115200 baud. You should see `[Main] Guitar Rig Analyzer v0.5.0 ...`. If not, fix that first (see [README.md](../README.md)).

**5. Bridge top + bottom power rails on the BB830 with two short jumpers each side.** Cut 4 short pieces of solid wire — 2 red, 2 black. Bridge the top-red rail to the bottom-red rail (one bridge at column 1, one at column 60). Same for top-blue ↔ bottom-blue.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .br { stroke: #d33; stroke-width: 1.8; fill: none; }
    .bb { stroke: #2962ff; stroke-width: 1.8; fill: none; }
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Step 5 — bridge the rails</text>
  <rect x="40" y="40" width="620" height="100" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="68" x2="650" y2="68" class="railblue"/>
  <line x1="50" y1="115" x2="650" y2="115" class="railblue"/>
  <line x1="50" y1="128" x2="650" y2="128" class="railred"/>
  <path d="M70,55 L70,128" class="br"/>
  <path d="M90,68 L90,115" class="bb"/>
  <path d="M610,55 L610,128" class="br"/>
  <path d="M630,68 L630,115" class="bb"/>
  <text x="350" y="92" text-anchor="middle" class="lbl">two bridges at left, two at right</text>
</svg>

## End-of-phase verify

| **[STOP]** Check | How | Pass |
|---|---|---|
| Top-red ↔ bottom-red bridged | DMM continuity, top-red anywhere to bottom-red anywhere | Beep |
| Top-blue ↔ bottom-blue bridged | Same, on the blue rails | Beep |
| Red and blue rails are NOT shorted to each other | DMM continuity, top-red to top-blue | **No beep** |
| Teensy boots normally | Serial Monitor, 115200 baud | `[Main] Guitar Rig Analyzer v0.5.0 ...` banner |

## Background

The BB830 has *four* independent power rails (two top, two bottom). Each runs the full length of the board. They are **not** connected to each other from the factory — the manufacturer leaves that to you so you can use them as four independent rails if you want. We only need two rails (one +5V and one GND, plus a third VGND coming in Phase 1), so we bridge the top rails to the bottom rails for redundancy. Two bridges per side keeps the rails at the same potential even with the inductance and resistance of long jumper-wire runs.

---

# Phase 0.5 — Solder the SMD adapters

> **Goal:** Turn your SOIC-8 OPA1642 and your SOT-23 MMBT3904s into "DIP-like" parts you can push into the breadboard. You'll solder them onto Chip Quik adapter boards. This is the only phase that requires a soldering iron — every later phase is purely plug-in.

> **First time soldering SMD?** Spend an hour on the **DIDODI SMT practice kit** before touching the OPA1642. Your $3 chip will thank you. Practice on the 0805 resistors and SOIC-8 footprints from the kit until you can do them cleanly without bridging pins.

## Parts tray for this phase

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 220" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 0.5 — parts tray</text>
  <rect x="20" y="40" width="660" height="170" rx="8" class="tray"/>
  <rect x="40" y="60" width="180" height="50" class="item"/>
  <text x="130" y="80" text-anchor="middle" class="lbl">1× OPA1642AID (SOIC-8)</text>
  <text x="130" y="98" text-anchor="middle" class="lbl">"OPA1642" stamped on top</text>
  <rect x="240" y="60" width="180" height="50" class="item"/>
  <text x="330" y="80" text-anchor="middle" class="lbl">1× Chip Quik PA0001</text>
  <text x="330" y="98" text-anchor="middle" class="lbl">SOIC-8 → DIP-8 adapter</text>
  <rect x="440" y="60" width="220" height="50" class="item"/>
  <text x="550" y="80" text-anchor="middle" class="lbl">2× MMBT3904 (SOT-23)</text>
  <text x="550" y="98" text-anchor="middle" class="lbl">tiny black 3-pin chips</text>
  <rect x="40" y="125" width="180" height="40" class="item"/>
  <text x="130" y="148" text-anchor="middle" class="lbl">2× SIPH06-1 SOT-23 adapter</text>
  <rect x="240" y="125" width="180" height="40" class="item"/>
  <text x="330" y="148" text-anchor="middle" class="lbl">Soldering iron + 63/37 solder</text>
  <rect x="440" y="125" width="220" height="40" class="item"/>
  <text x="550" y="148" text-anchor="middle" class="lbl">Flux (in the solder core)</text>
  <rect x="40" y="173" width="320" height="30" class="item"/>
  <text x="200" y="192" text-anchor="middle" class="lbl">iFixit tweezers + IPA + lint-free wipe</text>
  <rect x="380" y="173" width="280" height="30" class="item"/>
  <text x="520" y="192" text-anchor="middle" class="lbl">Fume extractor running</text>
</svg>

## Steps for the OPA1642

**1. Identify pin 1 on the OPA1642.** Look closely at the top of the chip. You'll see a small **circular dimple** or **dot of laser-etched ink** in one corner. That corner is **pin 1**. The pins count anti-clockwise from there when viewed from above.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 200" width="100%" style="max-width:500px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .chip { fill: #222; stroke: #000; stroke-width: 1; }
    .pin { fill: #ccc; stroke: #444; stroke-width: 0.5; }
    .dot { fill: #f0f0f0; }
  </style>
  <text x="250" y="18" text-anchor="middle" class="lblbig">Step 1 — pin 1 dot</text>
  <rect x="170" y="50" width="160" height="80" rx="4" class="chip"/>
  <circle cx="185" cy="65" r="4" class="dot"/>
  <text x="250" y="95" text-anchor="middle" class="lbl" fill="#fff">OPA1642</text>
  <text x="250" y="110" text-anchor="middle" class="lbl" fill="#aaa">AID</text>
  <!-- pins -->
  <rect x="160" y="55" width="10" height="5" class="pin"/>
  <rect x="160" y="73" width="10" height="5" class="pin"/>
  <rect x="160" y="91" width="10" height="5" class="pin"/>
  <rect x="160" y="109" width="10" height="5" class="pin"/>
  <rect x="330" y="55" width="10" height="5" class="pin"/>
  <rect x="330" y="73" width="10" height="5" class="pin"/>
  <rect x="330" y="91" width="10" height="5" class="pin"/>
  <rect x="330" y="109" width="10" height="5" class="pin"/>
  <text x="155" y="60" text-anchor="end" class="lbl">1</text>
  <text x="155" y="78" text-anchor="end" class="lbl">2</text>
  <text x="155" y="96" text-anchor="end" class="lbl">3</text>
  <text x="155" y="114" text-anchor="end" class="lbl">4</text>
  <text x="345" y="60" text-anchor="start" class="lbl">8</text>
  <text x="345" y="78" text-anchor="start" class="lbl">7</text>
  <text x="345" y="96" text-anchor="start" class="lbl">6</text>
  <text x="345" y="114" text-anchor="start" class="lbl">5</text>
  <text x="250" y="160" text-anchor="middle" class="lbl">dot in upper-left = pin 1 in upper-left</text>
  <text x="250" y="175" text-anchor="middle" class="lbl">pins count anti-clockwise from pin 1</text>
</svg>

**2. Look at your PA0001 adapter board.** It has a SOIC-8 footprint on top and a row of DIP-8 holes around the edge. The pin-1 corner of the SOIC footprint is silkscreened with a "1" or a square pad (the other pads are oval).

**3. Pre-tin one corner pad of the SOIC footprint.** Heat the pad, touch solder, lift. You want a small bead — just enough to hold the chip in place.

**4. Place the OPA1642 on the footprint.** Use tweezers. Make sure pin 1 (the dot corner) lines up with pin 1 of the footprint. Press lightly while you reflow the tinned pad to tack it down.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 220" width="100%" style="max-width:600px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .pcb { fill: #1b5e20; stroke: #0a3010; stroke-width: 1; }
    .pad { fill: #ffd54f; stroke: #b8860b; stroke-width: 0.5; }
    .chip { fill: #222; stroke: #000; stroke-width: 1; }
    .dot { fill: #f0f0f0; }
    .arrow { stroke: #d33; stroke-width: 2; fill: none; }
  </style>
  <text x="300" y="18" text-anchor="middle" class="lblbig">Step 4 — place chip, pin 1 over pin 1</text>
  <rect x="180" y="50" width="240" height="160" rx="6" class="pcb"/>
  <!-- SOIC pads -->
  <rect x="220" y="80" width="20" height="6" class="pad"/>
  <rect x="220" y="100" width="20" height="6" class="pad"/>
  <rect x="220" y="120" width="20" height="6" class="pad"/>
  <rect x="220" y="140" width="20" height="6" class="pad"/>
  <rect x="360" y="80" width="20" height="6" class="pad"/>
  <rect x="360" y="100" width="20" height="6" class="pad"/>
  <rect x="360" y="120" width="20" height="6" class="pad"/>
  <rect x="360" y="140" width="20" height="6" class="pad"/>
  <text x="215" y="86" text-anchor="end" class="lbl" fill="#fff">1</text>
  <text x="385" y="86" text-anchor="start" class="lbl" fill="#fff">8</text>
  <!-- chip -->
  <rect x="245" y="75" width="110" height="75" rx="2" class="chip"/>
  <circle cx="255" cy="83" r="3" class="dot"/>
  <!-- arrow showing pin 1 alignment -->
  <path d="M150,80 L210,80" class="arrow" marker-end="url(#a1)"/>
  <defs>
    <marker id="a1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#d33"/>
    </marker>
  </defs>
  <text x="145" y="76" text-anchor="end" class="lbl" fill="#d33">align pin 1 dot</text>
  <text x="145" y="90" text-anchor="end" class="lbl" fill="#d33">with pin 1 pad</text>
</svg>

**5. Solder the diagonally-opposite pin.** Now the chip is held at both corners and can't shift.

**6. Solder the remaining 6 pins.** Touch the iron tip to the *side* of the pad-and-pin joint (not the top — that just transfers heat to the chip body). Touch solder to the opposite side. It'll flow in. Move to the next pin.

**7. Inspect under good light.** Each joint should be a small, shiny *fillet* — a triangle of solder bridging pad to pin. Dull or "grainy" joints mean it didn't get hot enough. Big blobs mean too much solder.

**8. Look for bridges between pins.** Pins are 1.27mm apart on SOIC-8. A bridge looks like a solder *valley* connecting two pins. To fix: re-flow with extra flux, then wick with desoldering braid (or use the SS-03 pump). Do not leave bridges — they short the chip's pins together and can destroy it on power-up.

**9. Clean the flux residue.** Dampen a lint-free wipe with IPA and gently scrub the adapter. The residue should lift off as a brown haze.

**10. Solder the DIP-8 header pins into the outside row of holes.** Most PA0001 boards come with the header pins separate. Push them through from the *opposite* side of the board (so the long pins stick out where they'll plug into the breadboard, and the short pins solder on the side with the SOIC chip).

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 220" width="100%" style="max-width:600px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .pcb { fill: #1b5e20; stroke: #0a3010; stroke-width: 1; }
    .pad { fill: #ffd54f; stroke: #b8860b; stroke-width: 0.5; }
    .chip { fill: #222; stroke: #000; stroke-width: 1; }
    .pin { fill: #888; stroke: #444; stroke-width: 0.5; }
  </style>
  <text x="300" y="18" text-anchor="middle" class="lblbig">Step 10 — DIP header pins, long side DOWN</text>
  <rect x="180" y="50" width="240" height="120" rx="6" class="pcb"/>
  <rect x="245" y="75" width="110" height="60" rx="2" class="chip"/>
  <!-- DIP pins on left -->
  <rect x="190" y="65" width="3" height="6" class="pad"/>
  <rect x="190" y="85" width="3" height="6" class="pad"/>
  <rect x="190" y="105" width="3" height="6" class="pad"/>
  <rect x="190" y="125" width="3" height="6" class="pad"/>
  <!-- pin sticking down -->
  <rect x="190" y="170" width="3" height="30" class="pin"/>
  <rect x="200" y="170" width="3" height="30" class="pin"/>
  <rect x="210" y="170" width="3" height="30" class="pin"/>
  <rect x="220" y="170" width="3" height="30" class="pin"/>
  <text x="200" y="215" text-anchor="middle" class="lbl">long pins ↓ into breadboard</text>
  <rect x="400" y="170" width="3" height="30" class="pin"/>
  <rect x="410" y="170" width="3" height="30" class="pin"/>
  <rect x="420" y="170" width="3" height="30" class="pin"/>
  <rect x="430" y="170" width="3" height="30" class="pin"/>
</svg>

## Steps for the MMBT3904 (×2)

The MMBT3904 is a SOT-23 part — even smaller, with 3 pins. Same technique, more practice.

**11. Identify the pinout.** The MMBT3904 SOT-23 footprint has the *single pin* on one side and *two pins* on the other. Looking at it with the markings up and the single pin to the right:

- Bottom-left pin = **Base (B)**
- Top-left pin = **Collector (C)**
- Right pin = **Emitter (E)**

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 200" width="100%" style="max-width:500px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .chip { fill: #222; stroke: #000; stroke-width: 1; }
    .pin { fill: #ccc; stroke: #444; stroke-width: 0.5; }
  </style>
  <text x="250" y="18" text-anchor="middle" class="lblbig">Step 11 — SOT-23 pinout</text>
  <rect x="200" y="70" width="100" height="60" rx="2" class="chip"/>
  <text x="250" y="105" text-anchor="middle" class="lbl" fill="#fff">3904</text>
  <rect x="190" y="75" width="10" height="6" class="pin"/>
  <text x="180" y="80" text-anchor="end" class="lbl">C (collector)</text>
  <rect x="190" y="120" width="10" height="6" class="pin"/>
  <text x="180" y="125" text-anchor="end" class="lbl">B (base)</text>
  <rect x="300" y="97" width="10" height="6" class="pin"/>
  <text x="320" y="102" text-anchor="start" class="lbl">E (emitter)</text>
  <text x="250" y="160" text-anchor="middle" class="lbl">Marking on top: "1A" or "1AM"</text>
  <text x="250" y="175" text-anchor="middle" class="lbl">— that's the date/lot code, not the part number</text>
</svg>

**12. Look at your SIPH06-1 adapter.** It has a SOT-23 footprint on one face and a short row of DIP-style pin holes. Note the C / B / E silkscreen markings.

**13. Tin one of the SOT-23 pads, place the part, tack it down, then solder the remaining pins.** Same technique as the OPA1642 — just smaller. Steady hands.

**14. Solder DIP header pins into the row of holes.** Same as step 10.

**15. Test continuity from each header pin to the corresponding C/B/E label.** DMM in continuity mode:
- Header pin labeled C ↔ SOT-23 pin C → **beep**
- Header pin labeled B ↔ SOT-23 pin B → **beep**
- Header pin labeled E ↔ SOT-23 pin E → **beep**
- Any two header pins ↔ each other → **no beep** (no shorts)

**16. Repeat for the second MMBT3904.** You need 2 for phases 6 + 7. Solder 2 of the 4 SIPH06-1 adapters you bought; keep 2 as spares.

## End-of-phase verify

| **[STOP]** Check | How | Pass |
|---|---|---|
| OPA1642 adapter — pin 1 to header pin 1 | DMM continuity | Beep |
| OPA1642 adapter — no pin-to-pin shorts (any adjacent pair) | DMM continuity, 1↔2, 2↔3, 3↔4, 5↔6, 6↔7, 7↔8 | **No beep** on any pair |
| MMBT3904 adapter #1 — each of C/B/E reads through | DMM continuity to header pin | Beep |
| MMBT3904 adapter #1 — no C↔B, C↔E, B↔E shorts | DMM continuity on each pair | **No beep** |
| MMBT3904 BJT test (sanity) | DMM in diode mode: red on B, black on C → 0.65–0.75V drop. Red on B, black on E → 0.65–0.75V drop. Any other direction → OL. | All four readings match |
| MMBT3904 adapter #2 — same | | |

## Background — why we tin a corner first

Surface-mount soldering relies on a technique called "tack and stitch": you create one small dab of solder on a corner pad, then re-melt it while pressing the chip in place. That single pin now anchors the chip — both physically and electrically. Once anchored, you solder the diagonally-opposite pin (so the chip can't lift on one side), and only then do you solder the remaining pins. If you try to solder all 8 pins in order from one side, the chip will heat unevenly and "tombstone" — one end lifting off the pad.

**Heat too long on one pin?** SOIC-8 plastic packages can take ~260°C for ~10 seconds without damage. If you're on a pin for more than 5 seconds and the solder still won't flow, the iron temperature is too low (set the FNIRSI to 350°C for leaded solder) or the pad is contaminated (clean with flux + IPA).

**SOT-23 vs SOIC-8 difficulty.** SOT-23 is smaller but has only 3 pins. SOIC-8 has 8 pins on 1.27mm pitch. Most people find SOT-23 *easier* on their first try because each pin is more accessible.

---

# Phase 1 — Power rails (+5V, GND, and a virtual ground)

> **Goal:** Distribute +5V from the Teensy USB to the breadboard, generate a 2.5V virtual ground (VGND) for the op-amp in phase 4, and decouple everything.

> **What changed from v1 (corrected in v3).** You have **5× TLE2426CLP rail-splitter ICs on hand** (Mouser 595-TLE2426CLP, see `parts_inventory.md`). We're *not* using them on the breadboard — they're being saved for the production PCB. The breadboard uses a **two-resistor divider** (10K + 10K) with a 10µF reservoir cap instead, for two reasons: (1) it lets you probe each side of the divider independently with the DMM, which is a more educational debug experience; (2) it preserves all 5 TLE2426s for the final board run, where their lower noise actually matters. If you'd rather use the TLE2426 now, see the substitution note in Appendix B.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 1 — parts tray</text>
  <rect x="20" y="40" width="660" height="110" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="50" class="item"/>
  <text x="140" y="78" text-anchor="middle" class="lbl">2× 10 kΩ resistors</text>
  <text x="140" y="94" text-anchor="middle" class="lbl">(YAGEO MFR-25)</text>
  <rect x="260" y="60" width="200" height="50" class="item"/>
  <text x="360" y="78" text-anchor="middle" class="lbl">3× 10 µF electrolytic</text>
  <text x="360" y="94" text-anchor="middle" class="lbl">(Panasonic ECA-1EM100)</text>
  <rect x="480" y="60" width="180" height="50" class="item"/>
  <text x="570" y="78" text-anchor="middle" class="lbl">4× 0.1 µF ceramic</text>
  <text x="570" y="94" text-anchor="middle" class="lbl">(AVX SR205C104KART)</text>
  <rect x="40" y="120" width="620" height="20" class="item"/>
  <text x="350" y="135" text-anchor="middle" class="lbl">2× short wires (red + black) for VUSB and GND to the breadboard</text>
</svg>

## Steps

**1. Unplug the Teensy from USB.** Everything in phase 1 happens cold.

**2. Run a red wire from Teensy `VUSB` pad → top-red rail.** The VUSB pad on the Teensy 4.1 is at the very edge of the board, near the USB-C connector. Solder a short pin if the breakout doesn't expose VUSB, or use the screw terminal on your Teensy breakout. Tuck the other end of the wire into the top-red rail anywhere near column 1.

**3. Run a black wire from any Teensy `GND` → top-blue rail.** Any GND pin works. Top-blue rail anywhere near column 1.

**4. Place the first decoupling cap on +5V near column 5.** A 10µF electrolytic. The longer leg (the **+** side) goes into the top-red rail; the shorter leg (the **−** side, also marked with a stripe down that side of the cylinder) goes into the top-blue rail.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .cap { fill: #555; stroke: #000; stroke-width: 1; }
    .legred { stroke: #d33; stroke-width: 1.5; }
    .legblk { stroke: #222; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Step 4 — first +5V decoupling cap</text>
  <rect x="40" y="40" width="620" height="100" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <!-- cap body -->
  <circle cx="140" cy="100" r="15" class="cap"/>
  <text x="140" y="104" text-anchor="middle" class="lbl" fill="#fff">10µF</text>
  <text x="170" y="92" class="lbl">+ leg</text>
  <text x="170" y="115" class="lbl">− leg (stripe)</text>
  <line x1="140" y1="85" x2="140" y2="55" class="legred"/>
  <line x1="140" y1="115" x2="140" y2="70" class="legblk"/>
  <text x="80" y="135" class="lbl">column ~5</text>
</svg>

**5. Place a 0.1 µF ceramic cap right next to the electrolytic.** Ceramic caps are not polarized — orientation doesn't matter. Put it at column 7, one leg in top-red, the other in top-blue.

**6. Build the VGND divider in column 15.**
   - Push one leg of a 10 kΩ resistor into the top-red rail; push the other leg into hole `15a`.
   - Push one leg of a second 10 kΩ resistor into hole `15b`; push its other leg into the top-blue rail.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 220" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .res { fill: #fffde7; stroke: #8d6e63; stroke-width: 1; }
    .wire { stroke: #555; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Step 6 — VGND divider (10k / 10k) at column 15</text>
  <rect x="40" y="40" width="620" height="160" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <line x1="50" y1="180" x2="650" y2="180" class="railblue"/>
  <line x1="50" y1="195" x2="650" y2="195" class="railred"/>
  <!-- R1 -->
  <line x1="200" y1="55" x2="200" y2="85" class="wire"/>
  <rect x="190" y="85" width="20" height="40" class="res"/>
  <text x="225" y="108" class="lbl">10k (top)</text>
  <line x1="200" y1="125" x2="200" y2="140" class="wire"/>
  <!-- VGND tap node -->
  <circle cx="200" cy="140" r="3" fill="#f57c00"/>
  <text x="225" y="143" class="lbl" fill="#f57c00">VGND tap (15a/15b column)</text>
  <line x1="200" y1="140" x2="200" y2="150" class="wire"/>
  <!-- R2 -->
  <rect x="190" y="150" width="20" height="40" class="res"/>
  <text x="225" y="173" class="lbl">10k (bottom)</text>
  <line x1="200" y1="190" x2="200" y2="180" class="wire"/>
</svg>

**7. Run a wire from the VGND tap (column 15) to the bottom-red rail.** This *re-purposes the bottom-red rail as VGND.* It's painted red but it's not +5V anymore. **Stick a piece of masking tape on the breadboard right next to the bottom-red rail and write "VGND ~2.5V" on it.**

**8. Place a 10 µF cap from VGND to GND at column 18.** Longer leg (+) into the bottom-red (VGND), shorter leg (−) into the bottom-blue (GND). This is your VGND reservoir — it stabilizes the divider against transient loads from the op-amp.

**9. Place a 0.1 µF ceramic at column 20, also VGND to GND.** For high-frequency decoupling.

## End-of-phase verify

Plug in USB. **Nothing should hum, smoke, or get warm.** Then DMM:

| **[STOP]** Check | DMM probes | Pass |
|---|---|---|
| +5V rail is alive | red → top-red rail, black → top-blue (GND) | 4.85 – 5.10 V DC |
| VGND is ≈ 2.5 V | red → bottom-red rail (the VGND rail), black → top-blue (GND) | 2.40 – 2.60 V DC |
| VGND really is midway | red → top-red, black → VGND. Then red → VGND, black → GND. Both should be within 0.05 V of each other. | Yes |
| GND continuity | continuity, top-blue ↔ bottom-blue at multiple spots | Beep everywhere |
| No power-to-GND shorts | continuity, top-red ↔ top-blue | **No beep** |

## Background

A **virtual ground** is just a stable voltage at the midpoint of your single supply that the analog circuit treats as "zero." The op-amp's inputs and outputs swing symmetrically above and below it — so on a +5V/GND system, an audio signal that wants to swing ±1V will sit between 1.5V and 3.5V (centered on the 2.5V VGND), never touching either rail.

The 10K/10K divider works but has one weakness: its output impedance is 5K (= 10K || 10K). Any current the op-amp pulls or pushes from its bias resistor *to* VGND moves the VGND voltage. We hide this with the 10µF reservoir cap, which "remembers" the right voltage and supplies (or absorbs) transient current from the divider node. For breadboard work this is fine. The final PCB will use a proper rail-splitter IC (TLE2426 or similar) for clean noise performance.

**About the missing 1MΩ.** In phase 4 you'll use 100K as the OPA1642 input-bias resistor instead of 1M (the value v1 of this doc called for). The implication: input impedance to the buffer is ~100K instead of 1M. For most guitar pickups this is *fine* — measurable but minimal high-frequency rolloff. For very high-impedance vintage humbuckers you might notice ~0.5 dB cut at 10kHz. Easy to fix later by chaining 10× 100K resistors in series. Don't worry about it for now.

---

# Phase 2 — GPIO smoke test

> **Goal:** Prove pins 14 and 15 (the eventual relay control pins) can be driven HIGH/LOW from firmware. Use any 2 LEDs you have on hand.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 140" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 2 — parts tray</text>
  <rect x="20" y="40" width="660" height="80" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="50" class="item"/>
  <text x="140" y="80" text-anchor="middle" class="lbl">2× 5mm red LEDs</text>
  <text x="140" y="97" text-anchor="middle" class="lbl">(DIDODI practice kit)</text>
  <rect x="260" y="60" width="200" height="50" class="item"/>
  <text x="360" y="80" text-anchor="middle" class="lbl">2× 100 Ω resistors</text>
  <text x="360" y="97" text-anchor="middle" class="lbl">(safe at 3.3V GPIO drive)</text>
  <rect x="480" y="60" width="180" height="50" class="item"/>
  <text x="570" y="80" text-anchor="middle" class="lbl">2× jumpers to Teensy</text>
</svg>

## Steps

**1. Unplug USB.**

**2. Place LED #1 at column 30.** Long leg (anode, +) in `30a`, short leg (cathode, −) in `33a`.

**3. Jumper LED #1 cathode to GND.** Wire from `33a` to top-blue rail.

**4. Place a 100Ω resistor between LED #1 anode and column 27.** One leg in `30a` (shared with the LED anode through the column strip), the other leg in `27a`.

**5. Jumper from `27a` → Teensy pin 14.**

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 200" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .res { fill: #fffde7; stroke: #8d6e63; stroke-width: 1; }
    .led { fill: #ef5350; stroke: #c62828; stroke-width: 1; }
    .wire { stroke: #2e7d32; stroke-width: 1.5; }
    .wireblk { stroke: #222; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Steps 2–5 — LED #1 path</text>
  <rect x="40" y="40" width="620" height="150" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <line x1="50" y1="170" x2="650" y2="170" class="railblue"/>
  <line x1="50" y1="185" x2="650" y2="185" class="railred"/>
  <rect x="270" y="105" width="40" height="12" class="res"/>
  <text x="290" y="100" text-anchor="middle" class="lbl">100Ω</text>
  <circle cx="350" cy="111" r="8" class="led"/>
  <text x="350" y="135" text-anchor="middle" class="lbl">LED #1</text>
  <line x1="270" y1="111" x2="200" y2="111" class="wire"/>
  <line x1="200" y1="111" x2="200" y2="75" class="wire"/>
  <text x="180" y="95" text-anchor="end" class="lbl" fill="#2e7d32">to Teensy pin 14</text>
  <line x1="358" y1="111" x2="430" y2="111" class="wireblk"/>
  <line x1="430" y1="111" x2="430" y2="170" class="wireblk"/>
  <text x="450" y="135" class="lbl">to GND</text>
</svg>

**6. Repeat steps 2–5 for LED #2 at column 40, wired to Teensy pin 15.**

**7. Add the smoke-test code block to `setup()`.** Open `guitar_rig_analyzer.ino`. Find the end of `setup()` (right before `loop()` starts). Add:

```cpp
// ==== PHASE 2 SMOKE TEST — REMOVE BEFORE PHASE 3 =====
Serial.println("[BringUp] Phase 2 LED smoke test — 5 sec");
pinMode(RELAY_SEND_PIN,   OUTPUT);
pinMode(RELAY_RETURN_PIN, OUTPUT);
for (int i = 0; i < 5; ++i) {
    digitalWrite(RELAY_SEND_PIN,   HIGH);
    digitalWrite(RELAY_RETURN_PIN, LOW);
    delay(500);
    digitalWrite(RELAY_SEND_PIN,   LOW);
    digitalWrite(RELAY_RETURN_PIN, HIGH);
    delay(500);
}
digitalWrite(RELAY_SEND_PIN,   LOW);
digitalWrite(RELAY_RETURN_PIN, LOW);
Serial.println("[BringUp] Phase 2 smoke test done");
// =====================================================
```

**8. Build and flash.**

```bash
arduino-cli compile --fqbn teensy:avr:teensy41 .
arduino-cli upload  --fqbn teensy:avr:teensy41 .
```

**9. Open the Serial monitor at 115200 baud and watch the LEDs.**

## End-of-phase verify

| **[STOP]** Check | Expected |
|---|---|
| Both LEDs alternate at 1 Hz for 5 seconds after every boot | Yes |
| Serial monitor prints the bring-up banner lines | `[BringUp] Phase 2 ...` lines appear |
| After 5 seconds both LEDs go OFF | Yes (pins return to LOW) |
| DMM on pin 14 to GND during the blink | Alternates 0 V ↔ 3.3 V |

**10. Remove the smoke-test block from `setup()`.** Leave the LEDs and resistors on the breadboard — they become diagnostic indicators in phase 6 (in parallel with the relay coils).

## Background

**Why 100Ω?** Teensy 4.1 GPIOs drive ~3.3V. A red LED has a forward voltage of about 2V and a typical operating current of 5–20 mA. Resistor value to set 15 mA: (3.3 − 2.0) / 0.015 = 87Ω. We round up to 100Ω (which gives about 13 mA — perfectly visible, well within the GPIO's ~10 mA continuous rating per pin). The v1 doc called for 330Ω, which is sized for 5V GPIO and gives a slightly dim 4 mA on a 3.3V system — fine but barely visible in a bright room. 100Ω is brighter and still safe.

**Why drive the LED directly from the GPIO?** It's a smoke test for the GPIO itself. In phase 6 we'll move the LED in parallel with the relay coil and let the transistor handle the LED's current too — but for now, GPIO → resistor → LED is the simplest possible end-to-end test.

---

# Phase 3 — Jack-detect (simulated with wire jumpers)

> **Goal:** Confirm the firmware sees four GPIO inputs go LOW when momentarily grounded. No DIP switch needed — a short wire jumper to GND, touched briefly, is enough.

## Parts tray

Just **one black wire**. That's the whole tray.

## Steps

**1. Make sure USB is plugged in and the firmware is running.** No code changes for this phase — `signalRouter_init()` already configures these pins as `INPUT_PULLUP`.

**2. Strip 5 mm off both ends of a 15 cm black jumper wire.** Push one end firmly into the top-blue (GND) rail.

**3. Open the Serial monitor at 115200 baud.** You'll watch for `JACK_CHANGED` events as you tap the free end of the wire against each Teensy pin.

**4. Briefly touch the free end of the jumper to Teensy pin 16 (JACK_INSTRUMENT_PIN). Hold for ~200 ms, then release.**

Expected output:

```
[Main] signalRouter: JACK_CHANGED  (no return, no injection)
```

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .gnd { stroke: #2962ff; stroke-width: 3; fill: none; }
    .pin { fill: #444; stroke: #000; stroke-width: 1; }
    .wire { stroke: #222; stroke-width: 2; fill: none; }
    .tap { fill: #c62828; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Step 4 — tap GND wire to pin 16</text>
  <rect x="450" y="60" width="200" height="80" rx="6" fill="#eef" stroke="#444"/>
  <text x="550" y="85" text-anchor="middle" class="lbl">Teensy 4.1</text>
  <circle cx="500" cy="115" r="6" class="pin"/>
  <text x="510" y="118" class="lbl">pin 16</text>
  <line x1="40" y1="100" x2="200" y2="100" class="gnd"/>
  <text x="100" y="92" class="lbl" fill="#2962ff">GND rail</text>
  <line x1="200" y1="100" x2="490" y2="115" class="wire"/>
  <circle cx="490" cy="115" r="5" class="tap"/>
  <text x="280" y="130" class="lbl">tap briefly, then release</text>
</svg>

**5. Repeat for pins 17, 22, and 24.** One tap per pin. Wait ~1 second between taps to keep the Serial output readable.

| Touch this pin | Expected serial event |
|---|---|
| 16 (Instrument) | `JACK_CHANGED  (no return, no injection)` |
| 17 (Rig Send) | `JACK_CHANGED  (no return, no injection)` |
| 22 (Return TS) | `JACK_CHANGED  (TS return, no injection)` + `ROUTE_CHANGED` |
| 24 (Return XLR) | `JACK_CHANGED  (XLR return, no injection)` + `ROUTE_CHANGED` |

**6. DMM sanity check on one pin while it's NOT being grounded.** Red probe on Teensy pin 16, black on GND. Reading: ~3.3V (the internal pull-up).

## End-of-phase verify

| **[STOP]** Check | Expected |
|---|---|
| Each of pins 16, 17, 22, 24 generates a `JACK_CHANGED` event when momentarily tapped to GND | Yes, all four |
| Pin 22 (TS) or pin 24 (XLR) also generates a `ROUTE_CHANGED` event | Yes |
| DMM on any of these pins with no tap shows ~3.3V (INPUT_PULLUP active) | Yes |
| With pin tapped to GND, DMM shows < 0.1V | Yes |

## Background

**Why active-low (LOW = jack inserted)?** Because the Switchcraft #11 jacks you bought (and most guitar jacks) use a switch contact that closes to ground when the jack is *empty*, opening when a plug is inserted. With `INPUT_PULLUP`, an empty jack would pull the pin LOW (closed-to-tip-to-sleeve-to-GND), and an inserted plug would let the pin float HIGH (pulled up by the internal 50K resistor).

**Wait — that's backwards from what we just tested.** Right. The firmware's *current* convention is "LOW = inserted." That works directly with jacks that have a normally-open switch (the Cliff CL1384 style). For Switchcraft #11s, we'll need a one-line firmware invert in phase 5. We're testing the GPIO + debounce machinery here; we'll fix the sense convention when we wire the real jacks.

---

# Phase 4 — OPA1642 buffer

> **Goal:** Build a unity-gain JFET buffer that takes a high-impedance signal in and presents a low-impedance copy out, AC-coupled at both ends. Drive it with a phone headphone jack as a test source; confirm the live spectrum on the Audio Shield lights up.

> **What changed from v1.** Using 100K input bias (you don't have 1M); using 10nF input coupling (you have these; 1µF was the v1 spec but works similarly with 100K bias — gives a 160 Hz corner; for guitar use we want lower, see "Background"). VGND comes from the resistor divider you built in phase 1.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 180" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 4 — parts tray</text>
  <rect x="20" y="40" width="660" height="130" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="50" class="item"/>
  <text x="140" y="78" text-anchor="middle" class="lbl">1× OPA1642 on PA0001</text>
  <text x="140" y="94" text-anchor="middle" class="lbl">(from phase 0.5)</text>
  <rect x="260" y="60" width="200" height="50" class="item"/>
  <text x="360" y="78" text-anchor="middle" class="lbl">2× 100 kΩ resistors</text>
  <text x="360" y="94" text-anchor="middle" class="lbl">(input bias to VGND)</text>
  <rect x="480" y="60" width="180" height="50" class="item"/>
  <text x="570" y="78" text-anchor="middle" class="lbl">2× 10nF ceramic</text>
  <text x="570" y="94" text-anchor="middle" class="lbl">(input AC coupling)</text>
  <rect x="40" y="120" width="200" height="40" class="item"/>
  <text x="140" y="140" text-anchor="middle" class="lbl">2× 10µF electrolytic (output)</text>
  <rect x="260" y="120" width="200" height="40" class="item"/>
  <text x="360" y="140" text-anchor="middle" class="lbl">1× 0.1µF ceramic (decouple V+)</text>
  <rect x="480" y="120" width="180" height="40" class="item"/>
  <text x="570" y="140" text-anchor="middle" class="lbl">3.5 mm pigtail or test cable</text>
</svg>

## Steps

**1. Unplug USB.**

**2. Place your OPA1642 (on its PA0001 adapter) at columns 35–38, straddling the center gap.** Notch / pin-1 marker on the **left side**. The DIP-8 layout means:

```
        notch
   1 ──┤    ├── 8
   2 ──┤    ├── 7
   3 ──┤    ├── 6
   4 ──┤    ├── 5
```

So in the breadboard at columns 35–38 straddling the gap:
- Pin 1 (output A) → column 35, row e
- Pin 2 (−in A)   → column 36, row e
- Pin 3 (+in A)   → column 37, row e
- Pin 4 (V−)      → column 38, row e
- Pin 5 (+in B)   → column 38, row f
- Pin 6 (−in B)   → column 37, row f
- Pin 7 (out B)   → column 36, row f
- Pin 8 (V+)      → column 35, row f

**3. Wire pin 4 (V−) to GND.** Jumper from `38e` to top-blue rail.

**4. Wire pin 8 (V+) to +5V.** Jumper from `35f` to top-red rail. The IC body sits across rows e–f at the center gap; route the wire down through rows g, h, i to row j (the outermost row on the f-side of the board), then sideways to the top-red rail.

> **BB830 row reminder:** Each terminal strip on the BB830 has 10 rows of holes — `a` through `e` above the center gap, `f` through `j` below it. Row `j` is the outermost on the f-side. The center gap is what splits the IC's two rows of pins.

**5. Place a 0.1 µF decoupling cap *between* pin 8 and the nearest GND rail.** As close to the IC as possible — within 1 cm. One leg in row j next to where you came off pin 8, the other leg into the bottom-blue (GND) rail.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 240" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .railorange { stroke: #f57c00; stroke-width: 3; fill: none; }
    .ic { fill: #e3f2fd; stroke: #333; stroke-width: 1.4; }
    .cap { fill: #fff8e1; stroke: #a08020; stroke-width: 1; }
    .wired { stroke: #d33; stroke-width: 1.5; }
    .wireb { stroke: #2962ff; stroke-width: 1.5; }
    .wireblk { stroke: #222; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Steps 2–5 — OPA1642 + decoupling</text>
  <rect x="40" y="40" width="620" height="180" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <line x1="50" y1="200" x2="650" y2="200" class="railblue"/>
  <line x1="50" y1="215" x2="650" y2="215" class="railorange"/>
  <rect x="330" y="115" width="80" height="40" rx="3" class="ic"/>
  <text x="370" y="138" text-anchor="middle" class="lblbig">OPA1642</text>
  <text x="370" y="105" text-anchor="middle" class="lbl">notch / pin1 ←</text>
  <!-- pin 8 (V+) → +5V -->
  <line x1="338" y1="155" x2="338" y2="180" class="wired"/>
  <line x1="338" y1="180" x2="290" y2="180" class="wired"/>
  <line x1="290" y1="180" x2="290" y2="55" class="wired"/>
  <text x="270" y="180" text-anchor="end" class="lbl" fill="#d33">pin 8 → +5V</text>
  <!-- pin 4 (V−) → GND -->
  <line x1="402" y1="115" x2="402" y2="80" class="wireb"/>
  <line x1="402" y1="80" x2="430" y2="80" class="wireb"/>
  <line x1="430" y1="80" x2="430" y2="70" class="wireb"/>
  <text x="440" y="80" class="lbl" fill="#2962ff">pin 4 → GND</text>
  <!-- decoupling cap -->
  <rect x="446" y="175" width="14" height="20" class="cap"/>
  <text x="468" y="185" class="lbl">0.1µF</text>
  <line x1="453" y1="175" x2="453" y2="155" class="wireblk"/>
  <line x1="453" y1="155" x2="338" y2="155" class="wired" stroke-dasharray="2 2"/>
  <line x1="453" y1="195" x2="453" y2="200" class="wireblk"/>
</svg>

**6. Build the input bias path.** This is what holds pin 3 (+in) at VGND so the op-amp has a defined operating point. Two pieces:
   - Place a **100kΩ resistor** lying horizontally with one leg at `37a` (the pin-3 column on the a–e side) and the other leg at `45a` (a free column 8 spots to the left). The two legs must be in *different* column strips so the resistor actually carries current — same-column legs would short the resistor across one node and do nothing.
   - Add a **jumper from `45a` down to the bottom-red rail (VGND)**.

This puts the resistor between pin 3 and VGND, which biases pin 3 at the midpoint of the supply.

**7. Place the input AC-coupling cap C1 (10 nF ceramic).** One leg at `30a`, the other at `33a`. Then jumper from `33a` to `37a` (so the cap sits between the test-signal input and pin 3 of the op-amp).

**8. The signal-input pad will be column 30.** This is where the 3.5 mm test cable's tip wire will go.

**9. Build the unity-gain feedback.** Pin 1 (output A) needs to connect to pin 2 (−in A). Use a *very short* jumper from `35e` to `36e` — these are adjacent columns on the same side of the IC.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 220" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .railorange { stroke: #f57c00; stroke-width: 3; fill: none; }
    .ic { fill: #e3f2fd; stroke: #333; stroke-width: 1.4; }
    .cap { fill: #fff8e1; stroke: #a08020; stroke-width: 1; }
    .res { fill: #fffde7; stroke: #8d6e63; stroke-width: 1; }
    .wireorange { stroke: #f57c00; stroke-width: 1.5; }
    .wiresig { stroke: #2962ff; stroke-width: 2; }
    .wireblk { stroke: #222; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Steps 6–9 — input bias, AC coupling, feedback</text>
  <rect x="40" y="40" width="620" height="160" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <line x1="50" y1="180" x2="650" y2="180" class="railblue"/>
  <line x1="50" y1="195" x2="650" y2="195" class="railorange"/>
  <rect x="350" y="100" width="80" height="35" rx="3" class="ic"/>
  <text x="390" y="122" text-anchor="middle" class="lblbig">OPA1642</text>
  <!-- C1 input cap -->
  <rect x="240" y="92" width="30" height="10" class="cap"/>
  <text x="255" y="86" text-anchor="middle" class="lbl">C1 10nF</text>
  <!-- signal in -->
  <line x1="180" y1="97" x2="240" y2="97" class="wiresig"/>
  <text x="170" y="92" text-anchor="end" class="lbl" fill="#2962ff">signal in</text>
  <line x1="270" y1="97" x2="390" y2="100" class="wiresig"/>
  <text x="310" y="92" class="lbl" fill="#2962ff">→ pin 3 (+in)</text>
  <!-- R bias -->
  <rect x="475" y="92" width="40" height="10" class="res"/>
  <text x="495" y="86" text-anchor="middle" class="lbl">100K</text>
  <line x1="412" y1="100" x2="475" y2="97" class="wireblk"/>
  <line x1="515" y1="97" x2="540" y2="97" class="wireblk"/>
  <line x1="540" y1="97" x2="540" y2="195" class="wireorange"/>
  <text x="555" y="135" class="lbl" fill="#f57c00">→ VGND</text>
  <!-- feedback -->
  <line x1="358" y1="135" x2="358" y2="150" class="wireblk"/>
  <line x1="358" y1="150" x2="372" y2="150" class="wireblk"/>
  <line x1="372" y1="150" x2="372" y2="135" class="wireblk"/>
  <text x="365" y="170" text-anchor="middle" class="lbl">pin 1 → pin 2</text>
</svg>

**10. Terminate the unused half of the op-amp** so it doesn't oscillate:
   - **Pin 5 (+in B)** → VGND rail. Jumper from `38f` down to the bottom-red rail.
   - **Pin 6 (−in B)** to **pin 7 (out B)** with a short jumper from `37f` to `36f`.

**11. Place the output AC-coupling cap (10 µF electrolytic).** Long leg (+) in `35e` (shares the strip with op-amp pin 1). Short leg (−) in a free column further out, say `48e`.

**12. Run a wire from `48e` to the Audio Shield's LINE-IN-L pad.** Use a **3.5 mm-to-bare-wires breakout cable**: plug it into the Audio Shield's stereo line-in jack, connect the tip (left) wire to `48e`, and the sleeve (ground) wire to the GND rail. This is reversible, can't damage the codec, and is the right choice for breadboard work.

> **Alternative (only if you've done codec-pad soldering before):** Solder a short pigtail directly to the LINE-IN-L silkscreen pad on the Audio Shield Rev D. The pads are 0.1″ through-holes — easier than the OPA1642 you just survived — but the breakout cable is still the right primary path because nothing you do on the breadboard can stress it.

**13. Prepare the test source.** Cut a 3.5 mm stereo plug or use a breakout cable to expose tip / ring / sleeve.
   - **Tip** (left audio) → breadboard column 30 (the C1 input side).
   - **Sleeve** (ground) → top-blue GND rail.
   - **Ring** (right audio) — not used. Tape it off.

## End-of-phase verify

**First — DMM checks before any signal:**

| **[STOP]** Check | DMM probes | Pass |
|---|---|---|
| Pin 8 reads +5V | red on the +5V rail near the IC, black on GND | 4.85–5.10V |
| Pin 4 reads 0V | red on GND-side wire from pin 4, black on GND | < 0.05V |
| Pin 3 (+in) is biased to VGND | red on `37a`, black on GND | 2.45–2.55V |
| Pin 1 (output) tracks pin 3 | red on `35e`, black on GND | 2.45–2.55V (unity-gain follower) |
| C2 output is DC-free | red on `48e`, black on GND | < 50 mV (the cap blocks the 2.5V DC) |

**Then — with a signal:**

Plug a phone into the test cable. Play a song at low volume. Open the Serial monitor. The Teensy's live spectrum should now show **SOURCE_NODE** energized (broadband response moving with the music). The RETURN_NODE column stays silent. Peak-level reading on SOURCE should sit in the −24 to −6 dBFS range with the phone at moderate volume.

## Background

**Why a JFET op-amp?** Guitar pickups are high-impedance (6–250 kΩ). A bipolar-input op-amp has input bias currents in the microamp range, which over time would charge the input coupling cap and drift the operating point. JFET inputs sit at single-digit picoamps — essentially no leakage, the bias point holds indefinitely.

**Why AC coupling on both ends?** The op-amp output sits at 2.5V DC (the VGND reference). The codec line-in expects signals centered on its own internal bias, which is *not* 2.5V. The output coupling cap blocks DC mismatch while passing AC. Same on the input — your phone outputs AC centered on its own ground, which has no idea what our VGND is. Cap blocks DC, passes signal.

**Input AC-coupling corner frequency.** With C1 = 10 nF and the bias resistor (the OPA1642's input plus our 100K bias to VGND), the high-pass corner is roughly 1 / (2π · R · C) ≈ 1 / (2π · 100 000 · 10⁻⁸) ≈ **160 Hz**. That's *high* for guitar (you'll lose the low E string fundamental at 82 Hz). For a real bench measurement you'd want **C1 = 100 nF or 1 µF** for a corner near 16 Hz or 1.6 Hz. For breadboard validation of the routing topology, 160 Hz is fine — you'll still see clear signal above that.

**If you want full bass response on the breadboard**, swap C1 for **1× 0.1µF ceramic** (you have 20 of them) — that gives ~16 Hz corner, well below the guitar range.

**Unused channel termination.** The OPA1642 is a dual op-amp — two independent op-amps in one package. We're only using channel A. If channel B's inputs are left floating, it can oscillate at hundreds of MHz, which radiates back through the power pins and shows up as noise in channel A. Tying +in B to VGND and shorting −in B to out B configures channel B as a stable unity-gain follower of its own bias — the cleanest "do nothing" state.

---

# Phase 5 — First real instrument jack (Switchcraft #11)

> **Goal:** Replace the temporary 3.5 mm test cable with a real 1/4" Switchcraft #11 jack on a flying-lead pigtail, and integrate the jack-detect switch contact with the firmware. Because the Switchcraft #11's switch is **shorted-to-tip when empty, open when inserted**, you'll invert the logic with a one-line firmware define.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 130" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 5 — parts tray</text>
  <rect x="20" y="40" width="660" height="70" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="40" class="item"/>
  <text x="140" y="85" text-anchor="middle" class="lbl">1× Switchcraft #11</text>
  <rect x="260" y="60" width="200" height="40" class="item"/>
  <text x="360" y="85" text-anchor="middle" class="lbl">3× stranded pigtails 15 cm</text>
  <rect x="480" y="60" width="180" height="40" class="item"/>
  <text x="570" y="85" text-anchor="middle" class="lbl">Heat-shrink + iron</text>
</svg>

## Switchcraft #11 terminals

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 220" width="100%" style="max-width:600px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .jack { fill: #f5f5f5; stroke: #444; stroke-width: 1.5; }
    .term { fill: #ffeb3b; stroke: #8d6e63; stroke-width: 1; }
    .wire { stroke: #222; stroke-width: 1.5; fill: none; }
  </style>
  <text x="300" y="20" text-anchor="middle" class="lblbig">Switchcraft #11 — looking at the back</text>
  <rect x="120" y="50" width="220" height="140" rx="8" class="jack"/>
  <circle cx="120" cy="120" r="20" fill="#888" stroke="#444"/>
  <text x="120" y="125" text-anchor="middle" class="lbl" fill="#fff">⌀</text>
  <rect x="325" y="70" width="20" height="20" class="term"/>
  <text x="355" y="85" class="lbl">TIP terminal (signal)</text>
  <rect x="325" y="120" width="20" height="20" class="term"/>
  <text x="355" y="135" class="lbl">SLEEVE terminal (GND)</text>
  <rect x="325" y="170" width="20" height="20" class="term"/>
  <text x="355" y="185" class="lbl">SWITCH terminal</text>
  <text x="355" y="200" class="lbl">— internally shorted to TIP</text>
  <text x="355" y="214" class="lbl">  ONLY when plug is OUT</text>
</svg>

So the switch terminal's behavior is the **opposite** of what the firmware expects:

| State | Switchcraft #11 SWITCH terminal | Firmware wants |
|---|---|---|
| No plug | shorted to TIP terminal | HIGH (not inserted) ✓ matches if we wire TIP to GND but TIP carries signal... so it doesn't ✗ |
| Plug inserted | open (floats) | LOW (inserted) — needs INPUT_PULLUP to pull *down* but it pulls *up* ✗ |

The cleanest fix is a **one-line firmware invert.** Add a `JACK_DETECT_INVERTED` define in `config.h` and XOR the read in `signal_router.cpp`.

## Steps

### Solder the pigtail

**1. Cut three 15 cm pieces of stranded wire.** Different colors are helpful: red = tip, black = sleeve, green = switch.

**2. Strip 5 mm at one end of each wire and tin it.** Brief touch with the iron + a thin coat of solder.

**3. Slide a 1 cm piece of heat-shrink onto each wire** before soldering.

**4. Solder each wire to the corresponding Switchcraft #11 lug.** Hold the wire in tweezers, touch the iron to the lug + wire junction, feed solder. Slide the heat-shrink down and shrink it with the iron's barrel from a short distance.

### Wire into the breadboard

**5. Unplug USB.**

**6. Remove the temporary 3.5 mm cable from phase 4.**

**7. Strip and tin the breadboard end of each pigtail.**

**8. TIP wire → breadboard column 30** (where the test cable's tip was). This is the signal input to the C1 cap from phase 4.

**9. SLEEVE wire → top-blue GND rail.**

**10. SWITCH wire → Teensy pin 16.**

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 200" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .jack { fill: #f5f5f5; stroke: #444; stroke-width: 1.5; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .sig { stroke: #2962ff; stroke-width: 2; }
    .gnd { stroke: #222; stroke-width: 1.5; }
    .ctl { stroke: #2e7d32; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Steps 8–10 — pigtail to breadboard</text>
  <rect x="40" y="50" width="140" height="100" rx="6" class="jack"/>
  <text x="110" y="80" text-anchor="middle" class="lbl">Switchcraft #11</text>
  <text x="110" y="100" text-anchor="middle" class="lbl">TIP / SLV / SW</text>
  <rect x="280" y="50" width="380" height="130" rx="3" class="body"/>
  <line x1="180" y1="80" x2="320" y2="80" class="sig"/>
  <text x="240" y="74" class="lbl" fill="#2962ff">tip → col 30 (C1 input)</text>
  <line x1="180" y1="120" x2="320" y2="120" class="gnd"/>
  <text x="240" y="135" class="lbl">sleeve → GND rail</text>
  <line x1="180" y1="160" x2="320" y2="160" class="ctl"/>
  <line x1="320" y1="160" x2="650" y2="160" class="ctl"/>
  <text x="500" y="155" class="lbl" fill="#2e7d32">switch → Teensy pin 16</text>
</svg>

### Firmware invert

**11. Open `config.h`.** Add this line in the SIGNAL ROUTER section (right after `JACK_RETURN_XLR_PIN`):

```cpp
// Switchcraft #11 jacks have an inverted switch sense.
// 1 = pin reads HIGH when jack inserted; 0 = pin reads LOW when jack inserted.
#define JACK_DETECT_INVERTED   1
```

**12. Open `signal_router.cpp`.** Find the `readJackInserted()` helper (around line 70):

```cpp
static inline bool readJackInserted(uint8_t pin) {
    return (digitalRead(pin) == LOW);
}
```

Change it to:

```cpp
static inline bool readJackInserted(uint8_t pin) {
#if JACK_DETECT_INVERTED
    return (digitalRead(pin) == HIGH);
#else
    return (digitalRead(pin) == LOW);
#endif
}
```

**13. Build + flash + open Serial monitor.**

## End-of-phase verify

| **[STOP]** Check | Expected |
|---|---|
| Boot banner shows `instrument=0` when jack is empty | Yes |
| Insert a dummy 1/4" plug (not connected to anything) | `JACK_CHANGED  (no return, no injection)` and banner now shows `instrument=1` |
| Pull the dummy plug out | `JACK_CHANGED` event again, back to `instrument=0` |
| Plug a guitar in, strum a chord | SOURCE spectrum lights up on the display; peak meter follows the strum |
| Pull the plug — SOURCE spectrum collapses | Yes |

## Background

**Why the invert?** Switchcraft #11 was originally designed for "battery disconnect when unplugged" use — like a stomp-box. With no plug, the switch terminal shorts to the tip terminal (which is also connected to the battery's negative through the circuit), pulling the battery's ground to the chassis ground via the cable's sleeve. Plug in → switch opens → battery (-) disconnected from chassis → circuit powered. That topology is great for stomp boxes but mismatches our use, where we want "switch closed when plug present."

There's an alternative — buy **Cliff CL1384** (make-on-insertion) instead — but you already have 10 Switchcraft #11s, so the one-line firmware change is cheaper. The `JACK_DETECT_INVERTED` define lets a future PCB revision use either jack type without code duplication.

---

# Phase 6 — First relay driver (RELAY_SEND)

> **Goal:** Build the transistor driver + flyback diode + relay coil for RELAY_SEND, energised by Teensy pin 14 going HIGH. Verify the contacts switch with a continuity test. Don't wire signal through the contacts yet — that's phase 7.

> **Wait for the TQ2-5V to arrive before doing this phase.** TQ2-L2-5V (latching) won't work with the current firmware.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 180" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 6 — parts tray</text>
  <rect x="20" y="40" width="660" height="130" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="50" class="item"/>
  <text x="140" y="78" text-anchor="middle" class="lbl">1× TQ2-5V relay</text>
  <text x="140" y="95" text-anchor="middle" class="lbl">(non-latching)</text>
  <rect x="260" y="60" width="200" height="50" class="item"/>
  <text x="360" y="78" text-anchor="middle" class="lbl">1× MMBT3904</text>
  <text x="360" y="95" text-anchor="middle" class="lbl">on SIPH06-1 adapter</text>
  <rect x="480" y="60" width="180" height="50" class="item"/>
  <text x="570" y="78" text-anchor="middle" class="lbl">1× 1N4148 diode</text>
  <text x="570" y="95" text-anchor="middle" class="lbl">(black stripe = cathode)</text>
  <rect x="40" y="120" width="200" height="40" class="item"/>
  <text x="140" y="140" text-anchor="middle" class="lbl">1× 1 kΩ resistor (base)</text>
  <rect x="260" y="120" width="200" height="40" class="item"/>
  <text x="360" y="140" text-anchor="middle" class="lbl">1× 10 kΩ resistor (pulldown)</text>
</svg>

> **Resistor substitutions vs v1.** v1 specced 4.7 kΩ base + 10 kΩ pulldown. With Teensy's 3.3V GPIO, a 1 kΩ base resistor gives the BJT ~2.6 mA of base drive — plenty to saturate it for the TQ2-5V's ~28 mA coil (Panasonic datasheet: 178 Ω coil at 5 V, 140 mW nominal). Stick with 1 kΩ (which you have).

## Steps

**1. Unplug USB.**

**2. Place the MMBT3904 adapter at column 50, straddling the center gap.** The SIPH06-1 carries the SOT-23 to a 3-pin SIL header. Orient the adapter so its silkscreen reads **E – B – C** left-to-right (E nearest column 49, C nearest column 51) and push all three pins firmly into row `e` (a–e half). This means:
   - Emitter (E) → `49e`
   - Base (B) → `50e`
   - Collector (C) → `51e`
   - *Sanity-check with the DMM in continuity mode: probe each header pin back to the SOT-23 pad and confirm it matches the label — you tested this in Phase 0.5.*

**3. 1 kΩ base resistor:** one leg in `50a` (same strip as Base, since column 50 row a–e is one node), the other leg in `45a` (a free column to the left).

**4. Jumper from `45a` → Teensy pin 14.**

**5. 10 kΩ base pulldown:** one leg in `50b` (still on the Base strip), the other leg into the top-blue GND rail. This holds the BJT off when the GPIO is floating (during reset/boot).

**6. Emitter to GND:** jumper from `49a` (Emitter strip) to top-blue GND.

**7. Place the TQ2-5V relay at columns 55–59, straddling the center gap.** Pin 1 (marked with a small triangle, circle, or "1" on the case) goes to `55a`. The TQ2-5V is a 10-pin DIP-form package; pins march down the left side (a–e half) from `55a` through `59a`, then continue up the right side (f–j half) from `59f` through `55f`. Pinout (looking at the top, pin-1 indicator at upper-left), verified against the **Panasonic ASCTB14E datasheet, 2014-07**:

```
       pin-1 indicator
        ↓
  ┌────U────┐
  │ TQ2-5V  │
1 ┤  (top)  ├ 10
2 ┤         ├ 9
3 ┤         ├ 8
4 ┤         ├ 7
5 ┤         ├ 6
  └─────────┘
```

| Pin | Function | Breadboard hole |
|---|---|---|
| 1 | **COIL (−)** | `55a` |
| 2 | **POLE 1 NC** | `56a` |
| 3 | **POLE 1 COM** | `57a` |
| 4 | **POLE 1 NO** | `58a` |
| 5 | (mechanical only — no electrical connection) | `59a` |
| 6 | (mechanical only — no electrical connection) | `59f` |
| 7 | POLE 2 NO (not used in Phase 6) | `58f` |
| 8 | POLE 2 COM (not used in Phase 6) | `57f` |
| 9 | POLE 2 NC (not used in Phase 6) | `56f` |
| 10 | **COIL (+)** | `55f` |

We use POLE 1 only in this phase. POLE 2 is left unconnected.

**8. Wire COIL (−) → collector of the MMBT3904.** Jumper from `55a` (pin 1) to `51b` (Collector strip — same node as `51a`).

**9. Wire COIL (+) → +5V rail.** Jumper from `55f` (pin 10) to the top-red +5V rail.

**10. Place the 1N4148 flyback diode across the coil**, with the **cathode band (the black/silver stripe) toward COIL (+) — pin 10, the +5V side.** One leg in `55a` (pin 1, COIL −), the other (banded) leg in `55f` (pin 10, COIL +). In normal operation the diode is reverse-biased and does nothing; when the GPIO drops low and the coil's magnetic field collapses, the diode forward-biases and dumps the kickback voltage harmlessly into the +5V rail. *Reversed: the diode shorts +5V to GND through the BJT whenever pin 14 goes HIGH. Get this right — a multimeter in diode mode reads ~0.65 V from band-side to non-band-side and OL the other way.*

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 260" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #fafafa; stroke: #888; stroke-width: 1; }
    .railred { stroke: #d33; stroke-width: 3; fill: none; }
    .railblue { stroke: #2962ff; stroke-width: 3; fill: none; }
    .ic { fill: #e8f5e9; stroke: #284; stroke-width: 1.4; }
    .bjt { fill: #ffe082; stroke: #6d4c41; stroke-width: 1; }
    .res { fill: #fffde7; stroke: #8d6e63; stroke-width: 1; }
    .diode { fill: #fafafa; stroke: #333; stroke-width: 1.4; }
    .wirered { stroke: #d33; stroke-width: 1.5; }
    .wireblue { stroke: #2962ff; stroke-width: 1.5; }
    .wiregreen { stroke: #2e7d32; stroke-width: 1.5; }
    .wireblk { stroke: #222; stroke-width: 1.5; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Steps 2–10 — RELAY_SEND driver</text>
  <rect x="40" y="40" width="620" height="200" rx="3" class="body"/>
  <line x1="50" y1="55" x2="650" y2="55" class="railred"/>
  <line x1="50" y1="70" x2="650" y2="70" class="railblue"/>
  <line x1="50" y1="220" x2="650" y2="220" class="railblue"/>

  <rect x="270" y="120" width="60" height="50" class="bjt"/>
  <text x="300" y="148" text-anchor="middle" class="lbl">3904</text>
  <rect x="180" y="138" width="50" height="14" class="res"/>
  <text x="205" y="135" text-anchor="middle" class="lbl">1k base</text>
  <line x1="60" y1="100" x2="60" y2="145" class="wiregreen"/>
  <line x1="60" y1="145" x2="180" y2="145" class="wiregreen"/>
  <text x="100" y="115" class="lbl" fill="#2e7d32">pin 14</text>
  <rect x="245" y="175" width="14" height="40" class="res"/>
  <text x="280" y="200" class="lbl">10k pull</text>
  <line x1="252" y1="175" x2="252" y2="165" class="wireblk"/>
  <line x1="252" y1="165" x2="270" y2="165" class="wireblk"/>
  <line x1="252" y1="215" x2="252" y2="220" class="wireblk"/>
  <line x1="330" y1="170" x2="330" y2="220" class="wireblk"/>

  <rect x="430" y="100" width="100" height="90" class="ic"/>
  <text x="480" y="130" text-anchor="middle" class="lblbig">TQ2-5V</text>
  <text x="480" y="148" text-anchor="middle" class="lbl">coil A/B + contacts</text>

  <line x1="330" y1="125" x2="430" y2="115" class="wireblk"/>
  <text x="350" y="110" class="lbl">C → coil A</text>
  <line x1="530" y1="115" x2="580" y2="115" class="wirered"/>
  <line x1="580" y1="115" x2="580" y2="55" class="wirered"/>
  <text x="585" y="80" class="lbl" fill="#d33">→ +5V</text>

  <polygon points="450,85 460,80 460,90" class="diode"/>
  <line x1="460" y1="80" x2="460" y2="90" class="wireblk"/>
  <line x1="450" y1="85" x2="430" y2="115" class="wireblk"/>
  <line x1="460" y1="85" x2="530" y2="115" class="wireblk"/>
  <text x="465" y="75" class="lbl">flyback 1N4148 (band → +5V)</text>
</svg>

### Firmware: temporary toggle command

**11. Open `guitar_rig_analyzer.ino`.** Find the Serial command switch (around line 438). Add a temporary case:

```cpp
// PHASE 6 BRING-UP — temporary command, remove before phase 7
case 'p': case 'P': {
    static bool s_send_relay = false;
    s_send_relay = !s_send_relay;
    digitalWrite(RELAY_SEND_PIN, s_send_relay ? HIGH : LOW);
    Serial.printf("[BringUp] RELAY_SEND -> %s\n",
                  s_send_relay ? "HIGH (energised)" : "LOW (de-energised)");
    break;
}
```

**12. Build + flash + Serial monitor.**

## End-of-phase verify

Type `p` and `P` alternately at the Serial monitor.

| Action | DMM probes | Expected |
|---|---|---|
| Type `p` (energise) | red on collector (coil A column), black on GND | 0.1–0.3 V (saturated BJT) |
| Same | red on coil B column, black on GND | ~5 V |
| Same | continuity, COM_1 ↔ NO_1 contacts | Beep (relay clicked closed) |
| Same | continuity, COM_1 ↔ NC_1 contacts | Open |
| Type `P` (de-energise) | continuity, COM_1 ↔ NC_1 | Beep (relay clicked back) |
| Same | continuity, COM_1 ↔ NO_1 | Open |
| Listen for a soft "click" each time | | Yes |

**13. Remove the `p`/`P` Serial command** before phase 7.

## Background

**Why a transistor instead of driving the coil directly?** Teensy 4.1 GPIOs are rated for ~10 mA continuous, ~25 mA burst. The TQ2-5V coil draws ~28 mA nominal (5 V / 178 Ω from the Panasonic datasheet; worst-case ~31 mA with coil-resistance tolerance and temperature) — over the continuous limit and close enough to the burst limit that you cannot drive it directly without degrading the GPIO over time. A small NPN BJT (or N-MOSFET) configured as a switch lets the GPIO control a much larger load with negligible GPIO current.

**Why the flyback diode?** Relay coils are inductors (a coil of wire wrapped around a soft-iron core). When you suddenly cut current through an inductor (BJT switches off), the magnetic field collapses and induces a *reverse-polarity voltage spike* — easily 50–100 V on a small relay. That spike will fry the BJT's collector-emitter junction or the BJT's substrate diode. The 1N4148 across the coil clamps the spike to ~+5V plus 0.7V — well below the BJT's 40 V rating.

**Diode polarity.** The cathode (banded end) goes to the *positive* coil terminal. In normal operation the diode is reverse-biased (looks like an open circuit). When the BJT switches off and the coil voltage flips, the diode becomes forward-biased and shunts the energy back into the +5V rail (the supply absorbs the spike).

**Pulldown resistor R4.** During a Teensy reset, GPIOs briefly become inputs (high-impedance). Without R4, the BJT's base would float to whatever voltage was last on the trace — possibly enough to partially turn on the BJT and chatter the relay. The 10 kΩ to GND keeps the BJT firmly off during this window.

---

# Phase 7 — RELAY_RETURN + signal wiring + Rig Send + Rig Return TS

> **Goal:** Duplicate the phase-6 driver for the second relay (pin 15), then wire both relays into the actual signal path. Add the Rig Send and Rig Return TS jacks with their detect contacts.

This is the biggest phase by part count. Take it slow.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 7 — parts tray</text>
  <rect x="20" y="40" width="660" height="110" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="50" class="item"/>
  <text x="140" y="78" text-anchor="middle" class="lbl">1× TQ2-5V relay #2</text>
  <text x="140" y="95" text-anchor="middle" class="lbl">+ 2nd MMBT3904 driver kit</text>
  <rect x="260" y="60" width="200" height="50" class="item"/>
  <text x="360" y="78" text-anchor="middle" class="lbl">2× Switchcraft #11</text>
  <text x="360" y="95" text-anchor="middle" class="lbl">+ pigtails</text>
  <rect x="480" y="60" width="180" height="50" class="item"/>
  <text x="570" y="78" text-anchor="middle" class="lbl">~10 jumper wires</text>
  <text x="570" y="95" text-anchor="middle" class="lbl">(signal routing)</text>
</svg>

## Steps

### Duplicate the driver for RELAY_RETURN

**1. Build a mirror of phase 6 at columns 60–70**, but driven from Teensy **pin 15** instead of 14. All components: MMBT3904 on adapter, 1 kΩ base, 10 kΩ pulldown, TQ2-5V #2, 1N4148 flyback. Verify with the same DMM checks as phase 6 (use a quick temporary `q`/`Q` Serial command to toggle pin 15 if you want — or just lean on `signalRouter_setReturnPreference(XLR)` later to drive it).

### Wire RELAY_SEND into the signal path

> **v3 critical fix.** In v2, step 2 told you to disconnect the buffer→Line-In-L wire and step 3 wired the buffer to RELAY_SEND COM with the Rig Send tip on NC and the codec line-out on NO. That topology has two bugs: (a) it severs the permanent SOURCE_NODE tap that the contract requires for self-monitoring, and (b) when injection mode energises the relay, COM↔NO connects the buffer output directly to the codec's line-out driver (two outputs fighting on one node) while Rig Send floats. v3 keeps the SOURCE tap and re-wires the relay so **Rig Send is on COM** — the standard SPDT-selector pattern.

**2. Leave the existing wire from buffer output (`48e`) to Audio Shield Line-In L *in place*.** This is the permanent SOURCE_NODE tap from Phase 4 — the contract requires it for self-monitoring. Do NOT disconnect it.

**3. Add a second tap (parallel wire) from buffer output (`48e`) → RELAY_SEND NC_1 contact.** The buffer output is now branching to two places: a permanent tap to Line-In L, and a switched feed into the relay.

**4. Wire RELAY_SEND COM_1 contact → the wire that goes to the Rig Send 1/4" jack tip.** (You'll add the Rig Send jack in step 10.) COM is the **switched output** that ends up at the rig.

**5. Wire RELAY_SEND NO_1 contact → Audio Shield Line-Out L pad.** This is the codec generator output. It's only connected to Rig Send when the relay is energised (injection mode).

**Relay-state truth table (RELAY_SEND, pole 1):**

| State | Closed contact | Signal path |
|---|---|---|
| De-energised (LOW, normal play) | COM↔NC | buffer → Rig Send (the rig under test) |
| Energised (HIGH, self-cal) | COM↔NO | codec Line-Out → Rig Send (generator injection) |

Either way, the permanent buffer→Line-In L tap from step 2 keeps SOURCE_NODE alive — that's how the firmware sees what's being sent into the rig regardless of which signal is driving it.

### Wire RELAY_RETURN into the signal path

The return path uses the same SPDT-selector pattern: COM is the destination (codec input), NC is the default source (TS jack), NO is the alternate source (XLR jack from Phase 8).

**6. Wire RELAY_RETURN NC_1 contact → wire that will go to Rig Return TS jack tip.** When RELAY_RETURN is **de-energised (LOW)**, COM↔NC closes — the TS jack feeds the codec.

**7. Wire RELAY_RETURN NO_1 contact → wire that will go to XLR pin 2.** *(Leave the wire un-terminated for now; the XLR comes in phase 8.)* When energised, COM↔NO closes — the XLR feeds the codec.

**8. Wire RELAY_RETURN COM_1 contact → Audio Shield Line-In R pad.** This is the RETURN_NODE — the post-rig measurement point. The codec always sees whichever return source the relay has selected.

### Add the Rig Send + Rig Return TS jacks

**9. Solder pigtails to Jack #2 (Rig Send) and Jack #3 (Rig Return TS).** Same technique as phase 5.

**10. Jack #2 (Rig Send) wiring:**
   - TIP wire → RELAY_SEND **COM_1** contact (the wire you left dangling in step 4).
   - SLEEVE wire → GND rail.
   - SWITCH wire → Teensy pin 17 (JACK_RIG_SEND_PIN).

**11. Jack #3 (Rig Return TS) wiring:**
   - TIP wire → RELAY_RETURN NC_1 contact (from step 6).
   - SLEEVE wire → GND rail.
   - SWITCH wire → Teensy pin 22 (JACK_RETURN_TS_PIN).

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 320" width="100%" style="max-width:800px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .jack { fill: #f5f5f5; stroke: #444; stroke-width: 1.5; }
    .relay { fill: #e8f5e9; stroke: #284; stroke-width: 1.5; }
    .audio { fill: #e3f2fd; stroke: #36c; stroke-width: 1.5; }
    .sig { stroke: #2962ff; stroke-width: 2; fill: none; }
    .arrow { fill: #2962ff; }
  </style>
  <defs>
    <marker id="b" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M0,0 L10,5 L0,10 z" fill="#2962ff"/>
    </marker>
  </defs>
  <text x="400" y="20" text-anchor="middle" class="lblbig">Phase 7 — signal-path map</text>
  <rect x="20" y="60" width="100" height="40" class="jack"/>
  <text x="70" y="84" text-anchor="middle" class="lbl">Instrument In</text>
  <rect x="160" y="60" width="100" height="40" class="audio"/>
  <text x="210" y="84" text-anchor="middle" class="lbl">OPA1642 buffer</text>
  <rect x="300" y="40" width="140" height="80" class="relay"/>
  <text x="370" y="62" text-anchor="middle" class="lbl">RELAY_SEND</text>
  <text x="370" y="80" text-anchor="middle" class="lbl">NC=buffer</text>
  <text x="370" y="96" text-anchor="middle" class="lbl">NO=codec L-out</text>
  <rect x="480" y="60" width="100" height="40" class="jack"/>
  <text x="530" y="84" text-anchor="middle" class="lbl">Rig Send</text>
  <rect x="620" y="60" width="160" height="80" class="jack"/>
  <text x="700" y="100" text-anchor="middle" class="lbl">Rig under test</text>
  <rect x="480" y="200" width="100" height="40" class="jack"/>
  <text x="530" y="224" text-anchor="middle" class="lbl">Rig Return TS</text>
  <rect x="480" y="260" width="100" height="40" class="jack" stroke-dasharray="3 3"/>
  <text x="530" y="284" text-anchor="middle" class="lbl">XLR (phase 8)</text>
  <rect x="300" y="200" width="140" height="80" class="relay"/>
  <text x="370" y="222" text-anchor="middle" class="lbl">RELAY_RETURN</text>
  <text x="370" y="240" text-anchor="middle" class="lbl">NC=TS</text>
  <text x="370" y="256" text-anchor="middle" class="lbl">NO=XLR</text>
  <rect x="160" y="200" width="100" height="40" class="audio"/>
  <text x="210" y="224" text-anchor="middle" class="lbl">codec line-in R</text>
  <line x1="120" y1="80" x2="160" y2="80" class="sig" marker-end="url(#b)"/>
  <line x1="260" y1="80" x2="300" y2="80" class="sig" marker-end="url(#b)"/>
  <line x1="440" y1="80" x2="480" y2="80" class="sig" marker-end="url(#b)"/>
  <line x1="580" y1="80" x2="620" y2="80" class="sig" marker-end="url(#b)"/>
  <line x1="620" y1="120" x2="580" y2="220" class="sig" marker-end="url(#b)"/>
  <line x1="480" y1="220" x2="440" y2="220" class="sig" marker-end="url(#b)"/>
  <line x1="300" y1="220" x2="260" y2="220" class="sig" marker-end="url(#b)"/>
</svg>

## End-of-phase verify

| **[STOP]** Action | Expected |
|---|---|
| Plug a guitar into Instrument In, send → rig, rig → return TS | Live SOURCE + RETURN both light up; transfer-function curve visible |
| Unplug Rig Return TS | `JACK_CHANGED` + `ROUTE_INVALID` |
| Arm a self-cal capture (Serial `k`) | RELAY_SEND audibly clicks during the capture (NO contact engages, codec line-out drives Rig Send) |
| At idle, RELAY_SEND COM↔NC closed | Continuity beep |
| At idle, RELAY_SEND COM↔NO open | No beep |

**[STOP]** **Do not move on until you can pull each plug and see the correct route-state transition.**

## Background

**Signal routing logic in firmware.** With both relays de-energised (default), the path is:
- Instrument In → buffer → RELAY_SEND NC → Rig Send → [rig] → Rig Return TS → RELAY_RETURN NC → codec line-in R.

When the firmware needs to inject the internal generator (for self-calibration or internal-stimulus measurements), `signalRouter_setInjectionEnabled(true)` energises RELAY_SEND, switching its COM from the buffer to the codec line-out. The generator's audio leaves the codec, hits the relay, goes to Rig Send, through the rig, back to Rig Return, and into the codec line-in R.

When a return XLR is preferred over TS, `applyReturnRelay(XLR)` energises RELAY_RETURN, switching its COM from the TS jack's tip to the XLR's pin 2.

The current firmware in `signal_router.cpp` does both of these correctly; you've just connected the wires it expects to drive.

---

# Phase 8 — XLR return

> **Goal:** Add the Neutrik XLR jack as a second return source. Standard XLRs don't have a switch contact, so we use a small mechanical microswitch actuated by the inserted XLR shell.

## Parts tray

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 130" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 12px monospace; fill: #222; }
    .lblbig { font: 14px monospace; fill: #111; font-weight: 700; }
    .tray { fill: #fff9c4; stroke: #555; stroke-width: 1.5; }
    .item { fill: #ffffff; stroke: #444; stroke-width: 1; }
  </style>
  <text x="350" y="20" text-anchor="middle" class="lblbig">Phase 8 — parts tray</text>
  <rect x="20" y="40" width="660" height="70" rx="8" class="tray"/>
  <rect x="40" y="60" width="200" height="40" class="item"/>
  <text x="140" y="85" text-anchor="middle" class="lbl">1× Neutrik NC3FAH2-0</text>
  <rect x="260" y="60" width="200" height="40" class="item"/>
  <text x="360" y="85" text-anchor="middle" class="lbl">3× pigtail wires (15 cm)</text>
  <rect x="480" y="60" width="180" height="40" class="item"/>
  <text x="570" y="85" text-anchor="middle" class="lbl">1× Omron D2F-01L SPDT</text>
</svg>

> **Note about NC3FAH2-0:** Neutrik's NC3FAH2-0 is a **combo XLR/TRS jack** — it accepts both XLR plugs *and* 1/4" TRS plugs in the same hole. Pin layout for the XLR portion: pin 1 = GND, pin 2 = signal (+), pin 3 = signal (−). The TRS portion shares the same pins via internal switching. For our use, treat it as XLR-only — wire pin 2 as the signal hot, leave pin 3 going to GND for now (single-ended use, see note below).

## Steps

**1. Solder pigtails to the XLR jack:**
   - **Black wire → pin 1 (GND)**
   - **Red or yellow wire → pin 2 (signal hot)**
   - **Green or blue wire → pin 3 (signal cold — wire to GND in this single-ended build)**

**2. Mount the XLR jack** next to the TS jacks on whatever you're using as a panel (cardboard, plate, enclosure).

**3. Mount the D2F-01L microswitch** next to the XLR jack so the lever is *pressed by the XLR plug shell as it goes in*. Use double-sided tape, hot glue, or a tiny bracket. Test mechanically before wiring: insert a dummy XLR plug and confirm you can hear/feel the switch click as the lever depresses.

**4. Wire the D2F-01L's three PCB terminals.** Looking at the switch with the lever side up, the three pins are **COM** (the middle pin, usually marked), **NC** (normally-closed), and **NO** (normally-open). The wiring:

   - **COM** → Teensy **pin 24** (JACK_RETURN_XLR_PIN).
   - **NC** → **GND** rail.
   - **NO** → leave **unconnected**.

<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 220" width="100%" style="max-width:700px;background:#ffffff;border:1px solid #ccc;">
  <style>
    .lbl { font: 11px monospace; fill: #222; }
    .lblbig { font: 13px monospace; fill: #111; font-weight: 700; }
    .body { fill: #f5f5f5; stroke: #444; stroke-width: 1.5; }
    .lever { fill: #c0c0c0; stroke: #555; stroke-width: 1; }
    .term { fill: #ffd54f; stroke: #8d6e63; stroke-width: 0.8; }
    .wctl { stroke: #2e7d32; stroke-width: 1.8; fill: none; }
    .wgnd { stroke: #2962ff; stroke-width: 1.8; fill: none; }
  </style>
  <text x="350" y="18" text-anchor="middle" class="lblbig">Step 4 — D2F-01L wiring (lever side up)</text>
  <rect x="220" y="60" width="260" height="80" rx="4" class="body"/>
  <text x="350" y="85" text-anchor="middle" class="lbl">Omron D2F-01L (top view)</text>
  <rect x="100" y="78" width="120" height="14" rx="2" class="lever"/>
  <text x="160" y="73" text-anchor="middle" class="lbl">hinge lever</text>
  <text x="160" y="105" text-anchor="middle" class="lbl">↑ XLR plug presses</text>
  <text x="160" y="118" text-anchor="middle" class="lbl">  this side</text>
  <!-- terminals on bottom -->
  <rect x="245" y="155" width="14" height="14" class="term"/>
  <text x="252" y="183" text-anchor="middle" class="lbl">COM</text>
  <rect x="343" y="155" width="14" height="14" class="term"/>
  <text x="350" y="183" text-anchor="middle" class="lbl">NC</text>
  <rect x="441" y="155" width="14" height="14" class="term"/>
  <text x="448" y="183" text-anchor="middle" class="lbl">NO</text>
  <text x="448" y="198" text-anchor="middle" class="lbl">(unused)</text>
  <!-- wires -->
  <line x1="252" y1="200" x2="252" y2="210" class="wctl"/>
  <line x1="252" y1="210" x2="650" y2="210" class="wctl"/>
  <text x="540" y="205" class="lbl" fill="#2e7d32">→ Teensy pin 24</text>
  <line x1="350" y1="200" x2="350" y2="216" class="wgnd"/>
  <text x="365" y="213" class="lbl" fill="#2962ff">→ GND rail</text>
</svg>

> **Why this wiring works with the inverted firmware logic from Phase 5.** With no plug, the lever is at rest → COM-NC is closed → pin 24 is pulled to GND → reads LOW → firmware (with `JACK_DETECT_INVERTED=1`) interprets that as "**not inserted.**" When the XLR plug goes in and presses the lever, COM-NC opens → INPUT_PULLUP floats pin 24 → reads HIGH → firmware interprets that as "**inserted.**" Both the Switchcraft #11s and this microswitch end up speaking the same sense convention.

**5. Wire XLR pin 1 → GND rail.**

**6. Wire XLR pin 2 → RELAY_RETURN NO_1 contact** (the wire you left dangling at the end of phase 7 step 7).

**7. Wire XLR pin 3 → GND rail** (single-ended use for breadboard only — the PCB will use a proper instrumentation-amp differential input stage).

## End-of-phase verify

| **[STOP]** Check | Expected |
|---|---|
| Plug an XLR cable into the jack; the microswitch's lever depresses | `JACK_CHANGED` event, `ROUTE_CHANGED → XLR return` (assuming TS is also unplugged, or XLR is preferred via `signalRouter_setReturnPreference(XLR)`) |
| Hum into a dynamic mic plugged into the XLR | Live spectrum shows return signal on RETURN_NODE |
| Unplug the XLR | Microswitch lever springs back; route flips back to NONE or TS |

## Background

**Why a microswitch instead of a jack-integrated detect?** Most cheap panel-mount XLRs (including the Neutrik NC3FAH2-0) don't have a built-in switch contact. The professional move is to use a **Neutrik NC3FAV-SW** (a variant with switch contacts) on the PCB, but for the breadboard the microswitch is cheap and works fine.

**Why pin 3 to GND instead of to the inverting input of a differential amp?** A balanced XLR signal carries the audio as `pin 2 − pin 3`. To recover it correctly you need an *instrumentation amplifier* — the standard chip is the **INA1620** (designed specifically for balanced audio). For the breadboard topology proof you can get away with treating XLR as single-ended (pin 2 = signal, pin 3 = ground), losing the common-mode noise rejection that balanced audio is famous for. This is **not** acceptable for the production PCB — note it in your build log so it doesn't sneak into the final design.

---

# Phase 9 — Validation harness

> **Goal:** Use the firmware's built-in 4-test validation suite to qualify the breadboard. Passing this is the sign-off for going to PCB.

## Parts tray

Just the firmware's existing `validation_runAll()`. Optional helpers:
- A Y-split 1/4" TS cable (or two 1/4" plugs + a short wire) — for Test 1.
- A simple resistive pad (2× equal resistors, e.g., 10 kΩ series + 10 kΩ shunt = 6 dB) — for Test 3.
- An RC filter (e.g., 10 kΩ + 10 nF — you have both — = 1.6 kHz corner) — for Test 4.

## Steps

**1. Open Serial monitor at 115200 baud.**

**2. Run validation tests one at a time.** Type each key in sequence:

| Key | Test | Setup | Pass criterion |
|---|---|---|---|
| `1` | Flat loopback | Y-split so Instrument In + Rig Send are joined, and Rig Return TS receives the same node | `tf_db[]` flat within tolerance, 200 Hz – 10 kHz |
| `2` | Channel-swap symmetry | Same physical Y-split; firmware re-binds channels mid-test | Asymmetry within tolerance |
| `3` | Known gain offset | Insert a 6 dB resistive pad on the return path | Measured offset = expected ± tolerance |
| `4` | Known RC filter | Insert RC low-pass on the return path | Slope + `tf_at_2fc` match expected |

**3. Or run them all at once with `v`** — the firmware does a preflight level check first, then steps through all four.

**4. Capture the Serial output** to a text file (Arduino IDE's serial monitor has a "save" button, or you can `pbpaste` it).

> **Heads-up on Test 1's low end.** Phase 4 uses a 10 nF input AC-coupling cap, which combined with the 100 kΩ bias resistor gives an input high-pass corner at ~160 Hz. Test 1's pass band is 200 Hz – 10 kHz, so it'll pass, but if you peek at the raw `tf_db[]` below 300 Hz you'll see extra rolloff. That's the cap, **not** a fault. To get a flat response down to 16 Hz on the breadboard, swap C1 from 10 nF to 0.1 µF (you have 20 of these in the bin).

## Sign-off checklist

Each check is one line you read out loud. Tick each as you confirm.

- [ ] Phase 1: VGND stays at 2.4 – 2.6 V even when relays are clicking.
- [ ] Phase 2: LED smoke test toggles cleanly at boot.
- [ ] Phase 3: All four GPIOs respond to GND taps.
- [ ] Phase 4: Phone test signal visible on SOURCE spectrum.
- [ ] Phase 5: Switchcraft #11 + invert define both work — guitar plays through, detect events fire.
- [ ] Phase 6: TQ2-5V #1 clicks on `p`/`P`; continuity matches expected state.
- [ ] Phase 7: Full route matrix (4 jack combinations) produces correct route description on Serial.
- [ ] Phase 8: XLR + microswitch detect both work end-to-end.
- [ ] Phase 9: `1`, `2`, `3`, `4` all PASS.
- [ ] Phase 10: Pi link — common ground verified, HELLO reports protocol v2, known data renders, **clamped bins marked rather than drawn**, CRC rejection and unknown-packet tolerance demonstrated, reboot recovery demonstrated, and the **T1 acceptance matrix** passed: all four runs recorded, runs 2-4 indistinguishable from the `_NONE` control on `block_ms_*`, and `blocks_skipped = 0` in every run.

When every box is ticked: photograph the entire board, save the serial logs, and update [docs/bench_runbook.md](bench_runbook.md) §8 with the date. The breadboard is signed off and ready to translate into a KiCad schematic.

---

# Phase 10 — Pi 5 display link (UART)

> **Goal:** Prove that the Teensy can hand measurement data to the Raspberry Pi 5 over UART and that the Pi renders it correctly — **tested independently of the analyzer**, using known data, before the two are trusted together.

**Added 2026-09-11.** Authority: [docs/adr/ADR-001-display-architecture.md](adr/ADR-001-display-architecture.md). The Pi 5 is the production renderer; the Teensy keeps all DSP, routing and measurement authority. Every earlier phase in this runbook is built with `DISPLAY_TARGET_NONE` and none of them depend on this one.

## Status: protocol v2 is a freeze candidate — this phase is the thing that freezes it

An audit on 2026-09-11 found 17 findings against the v1 packet layout, five severe, **four of them cases where the firmware computed a verdict and failed to put it on the wire** — including the TF clamp mask, which would have had the Pi plotting a saturation rail as a real measurement. All five are now fixed in **protocol v2** ([docs/pi_link_protocol_audit.md](pi_link_protocol_audit.md)).

One finding is **not** closed, and it is the one this phase exists to settle:

> **T1 — transmission must not perturb acquisition.** The prediction is that a 128-bin live frame occupies ~36.7 ms of wire time against a measured ~46.3 ms audio block period (~79 %). The delivery policy makes that *safe in principle* — a frame that does not fit is dropped, not waited on — but **nobody has measured it.** Until step 8 below produces a number, T1 is arithmetic, not evidence.

A Pi-side parser may be written against v2 now. The format freezes when step 8 passes, because that measurement is the only remaining thing that could force a change to packet sizing or cadence.

## Parts tray for this phase

| Part | Qty | Notes |
|---|---:|---|
| Raspberry Pi 5 8GB | 1 | |
| Pi 5 Active Cooler | 1 | Fit before first boot — the Pi 5 throttles without it |
| Pi 27W USB-C PSU | 1 | Use this one. An underpowered supply on a Pi 5 presents as random corruption, which looks exactly like a UART fault |
| Pi Touch Display 2 (7") | 1 | |
| Freenove RPi GPIO breakout HAT | 1 | Pi↔Teensy UART |
| Jumper wires | 3 | TX, RX, GND |
| microSD for the Pi | 1 | Not the Teensy's card |

## The link

| Teensy | Signal | Pi (BCM) | Notes |
|---|---|---|---|
| pin 1 | `Serial1` TX | GPIO15 / RXD | Teensy transmits, Pi receives |
| pin 0 | `Serial1` RX | GPIO14 / TXD | reserved for future Pi→Teensy control; not used by `data_sender` today |
| GND | ground | GND | **required** — see the stop sign below |

Both boards are 3.3 V logic, so no level shifting is needed. **Do not connect 5 V between the boards.** Each has its own supply; the only power-domain connection is ground.

> **[STOP]** Connect **GND first**, before TX or RX, and confirm continuity with the DMM. A UART link between two separately-powered boards with no common ground will appear to work intermittently and corrupt data in a pattern that looks like a baud-rate or CRC problem. You will spend a day on it. This is the single most common failure in this phase.

> **[STOP]** `Serial1` is pins **0 and 1** and `config.h` reserves them (`PI_LINK_UART_RX_PIN` / `PI_LINK_UART_TX_PIN`). Do not reassign them for anything. TODO-24 already rejected them as display-reset candidates on these grounds.

## Steps

**1. Assemble and boot the Pi alone.** Active Cooler fitted, OS installed, Touch Display 2 working, no Teensy connected. Confirm the touchscreen responds. *Verify:* the Pi boots to a desktop and touch works. Do not proceed with a Pi you have not already seen working by itself.

**2. Wire GND, then TX, then RX.** In that order. *Verify:* continuity Teensy GND ↔ Pi GND.

**3. Build the firmware with `DISPLAY_TARGET_PI`.** One line in `config.h`. The boot banner prints `[Main] Display target: Pi 5 (UART)` — confirm that on USB Serial before looking at the Pi. If it says anything else you are testing the wrong binary.

**4. Observe raw bytes on the Pi before writing any parser.** `stty -F /dev/serial0 460800 raw` then `xxd /dev/serial0 | head`. *Verify:* you can see the `55 AA` sync word recurring at roughly 11 Hz. **Stop here and fix the link if you cannot** — every later problem is easier to diagnose than a physical-layer fault.

**5. Read HELLO before anything else.** On connect the Teensy sends a structured HELLO packet (type `0x06`) carrying `protocol_version`, `live_bins`, `fft_bins`, `decim_ratio`, baud, sample rate, a capability bitmap and the firmware version. *Verify:* `protocol_version == 2`. A receiver that does not check this will eventually misparse a future layout silently.

**6. Bring up the receiver against known data.** Per TODO-36. Acceptance is a **synthetic or recorded** packet stream rendering correctly — not "the analyzer looks right". Real analyzer data as the first test conflates a protocol bug with a measurement bug.

**7. Verify the clamp contract is honoured.** This is the defect that motivated protocol v2, so it gets its own step. With **nothing connected to RETURN_NODE**, the true TF sits far below the −24 dB clamp rail and the firmware rails essentially the whole curve. *Verify:* the Pi does **not** draw a flat −24 dB line as though it were measured — it marks those bins as saturated, and `tf_clamped_count` in the live frame reads near `FFT_BINS`. A renderer that draws the rail has ignored the per-bin clamped nibble, and has reproduced on the Pi the exact defect that printed `1kHz=-24.0dB` in 33 of 33 windows on 2026-09-07.

**8. Demonstrate CRC rejection.** Deliberately corrupt a payload byte in a replayed stream. *Verify:* the Pi discards that packet and resynchronises on the next sync word. It must not render corrupted data and must not wedge.

**9. Demonstrate unknown-packet tolerance.** Inject a synthetic packet with type `0xFE` and a valid length/CRC. *Verify:* the receiver skips `payload_length` bytes and carries on. This is what lets a future packet type be added without a version break.

**10. Demonstrate reboot recovery.** Reset the Teensy while the Pi is receiving. *Verify:* the Pi recovers without being restarted, and re-reads HELLO.

**11. [STOP] Run the T1 acceptance matrix. This is the decisive step of the phase.**

The question is NOT "does UART work". It is one narrow engineering question:

> **Can the presentation transport become unavailable without measurably perturbing the Teensy's audio/measurement timing?**

The firmware carries a harness for exactly this (`timing_probe.{h,cpp}`). Two serial commands: **`t`** starts a measurement window, **`T`** prints a fixed-format `key=value` report. The format is deliberately machine-diffable — run the four configurations, paste each report verbatim into `ai/journal.md`, and diff them rather than eyeballing.

**Run all four under identical window length and identical signal conditions.** A guitar left plugged in and untouched is fine; an inconsistent input is not, because block timing depends on it.

| Run | Build | Condition | Role |
|---|---|---|---|
| **1** | `DISPLAY_TARGET_NONE` | no display hardware | **THE CONTROL.** Every other run is judged against this |
| **2** | `DISPLAY_TARGET_PI` | Pi connected, reader consuming normally | normal operation |
| **3** | `DISPLAY_TARGET_PI` | Pi connected, reader **suspended** (`kill -STOP <pid>`) so the UART backs up and stays full | sustained backpressure |
| **4** | `DISPLAY_TARGET_PI` | TX wire **pulled while a RESULT is draining** (arm a measurement with `m`, yank during delivery) | loss mid-transaction |

Procedure per run: flash → let it settle → press `t` → leave it for the same fixed window (≥60 s; longer is better for the max figures) → press `T` → save the output.

**Metrics the report emits.** The acquisition block is the one that decides pass/fail:

| Key | Must be |
|---|---|
| `block_ms_mean`, `block_ms_max`, `block_ms_spread` | **indistinguishable from run 1** |
| `blocks_skipped`, `skip_events`, `largest_block_gap` | **0 in every run, no exceptions** |
| `loop_us_max` | comparable to run 1 |
| `audio_blocks_high_water` | comparable to run 1 |
| `[Link] Live frames` sent/dropped/streak | drops **expected** in runs 3 and 4 |
| `[Link] Call time` max | microseconds, not milliseconds |
| `[Link] TX room min` | 0 in runs 3/4 — that is the backpressure, correctly absorbed |
| `[Link] Results` abandoned bytes | non-zero in run 4 is correct |

> **⚠️ DO NOT PASS THIS STEP ON A SMALL CALL TIME.** A microsecond-fast `presentation_*()` can still disturb the instrument indirectly — through interrupt load, UART ISR activity, DMA contention, or buffer servicing — and none of that appears in a call-duration figure. **The pass condition is the comparison against run 1.** There is no absolute threshold to argue about; the control run *is* the threshold.
>
> This matters more here than in a typical embedded project: the firmware is built around a single capture owner and a single canonical timebase (the audio block counter), and every time-sensitive operation references it. Perturbing that layer compromises far more than the display.

**Also verify in runs 3 and 4:** the firmware stays fully responsive on USB Serial, and the validation suite (`1`–`4`) still runs and passes with the Pi stalled. A dead renderer must not be able to fail a measurement.

*If block timing degrades in any run:* **stop.** The non-blocking policy has been violated somewhere, and no amount of Pi-side work will fix it. Find the blocking path first — acceptance test B in [the protocol audit](pi_link_protocol_audit.md) is the place to start.

**12. Freeze the transport and record the milestone.** Once runs 2–4 match run 1 on the acquisition metrics with `blocks_skipped = 0` throughout, T1 closes, protocol v2 goes from *schema-frozen, transport-unproven* to fully proven, and the milestone is **v0.6.0 — Pi presentation architecture validated**. Only then start the Pi parser/renderer (TODO-36): at that point it is being built on a transport demonstrated to be physically incapable of stealing timing from the instrument, rather than on a speculative one.

## End-of-phase verify

| Check | Expected | [STOP] |
|---|---|---|
| Common ground | continuity Teensy GND ↔ Pi GND | **[STOP]** |
| Banner | `[Main] Display target: Pi 5 (UART)` | |
| Raw bytes | `55 AA` sync word at ~11 Hz | **[STOP]** |
| HELLO | `protocol_version == 2` | |
| Known data renders | synthetic stream renders correctly | |
| **Clamp contract** | railed bins marked saturated, **not** drawn as −24 dB data | **[STOP]** |
| CRC rejection | corrupted packet discarded, stream resyncs | **[STOP]** |
| Unknown packet type | skipped by length, receiver continues | |
| Reboot recovery | Pi recovers from a Teensy reset unaided | |
| Loop blocking | max call time in **microseconds**, measured | **[STOP]** |
| Block timing with Pi consuming | indistinguishable from `DISPLAY_TARGET_NONE` | **[STOP]** |
| Dead / stalled / yanked Pi | block timing unchanged in all three cases | **[STOP]** |

## Background — why this phase is last, and separate

The Teensy does the hard real-time work and the Pi does presentation. The interface between them is the one place a mistake is expensive in both directions, which is why it gets its own phase with its own acceptance criteria rather than being folded into the validation harness.

The audit that created this phase found the Pi hardware listed in this runbook's parts table as "used in Phase 9" while Phase 9 was the validation harness — the Pi had been bought with nowhere to be installed, and the firmware had a complete, zero-caller UART module pointed at it. That is what an unbuilt phase looks like from the inside: the parts arrive, the code gets written, and nothing ever connects the two.

---

# Appendix A — Troubleshooting decision tree

For every symptom below, follow the arrows until you get to a green ✓ (fixable on the bench) or a red ✗ (probably a dead part — swap from your spares bin and retest).

## Power phase

```
                  VGND DMM reading
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
       0 V             ≈5 V           drifts under load
        │                │                │
        ▼                ▼                ▼
  Both 10K       One 10K shorted    10µF reservoir cap
  resistors      to +5V, or         missing or installed
  open OR one    upper 10K          backwards
  shorted to     removed            ✓ check polarity,
  GND            ✓ swap resistor,   reseat
  ✓ reseat or    re-probe
  swap
```

## GPIO phase (smoke test, jack-detect)

```
                Pin behavior
                     │
   ┌─────────────────┼─────────────────┐
   ▼                 ▼                 ▼
Always LOW       Always HIGH      Bouncy storm of
   │                 │            JACK_CHANGED events
   ▼                 ▼                 │
Stuck-low wire   INPUT_PULLUP          ▼
short to GND     not set in            Dirty contact OR
✓ trace the      firmware, OR          JACK_DEBOUNCE_MS too short
trace, snip      GND-side jumper       ✓ clean lugs with IPA+DeoxIT,
the short        missing               or raise debounce window
                 ✓ check firmware,
                 add jumper
```

## Buffer phase (Phase 4)

```
                 Symptom at SOURCE
                         │
   ┌─────────────┬───────┴───────┬─────────────┐
   ▼             ▼               ▼             ▼
No signal     Pin 3 bias     Pin 1 doesn't  60 Hz hum
   │          ≠ 2.5 V         track pin 3   in spectrum
   ▼             │               │             │
C1 open or       ▼               ▼             ▼
backwards,       100K bias    Feedback wire   GND loop
OR op-amp        resistor     short, OR       ✗ check sleeve
pin 1↔8          open, OR     op-amp dead     wire continuity
swapped          VGND rail       │            back to Teensy
✓ reseat C1,     dead          ▼             GND pin
flip IC          ✓ swap        ✗ swap
                 resistor      OPA1642 from
                 OR re-probe   spares (you
                 VGND          have 4 more)
```

## Relay-driver phase (Phase 6, Phase 7)

```
                Relay symptom
                     │
   ┌─────────────┬───┴────┬─────────────────┐
   ▼             ▼        ▼                 ▼
Never        Always    Chatters         LED tracks but
energises    energised at click         contacts don't
   │             │        │             switch
   ▼             ▼        ▼                 │
Pin 14/15    R4 (10K)  +5V rail            ▼
not          pulldown  sagging:          Counterfeit
toggling     missing   USB can't         relay
(DMM at      ✓ add     supply inrush     ✗ swap from
pin) OR      pulldown  ✓ powered USB     spares (you
BJT base     to GND    hub or wall       have 3 more
resistor               adapter           TQ2-5V)
open
✓ reseat,
re-flash
```

## Jack-detect phase (Phase 5, Phase 8)

```
            Always reads inserted when empty
                        │
                        ▼
            Inversion convention is wrong
            ✓ flip JACK_DETECT_INVERTED
            between 0 and 1 in config.h
```

## Validation phase (Phase 9)

```
        Test 1 (flat loopback) fails below 300 Hz
                        │
                        ▼
                Not a fault — it's
                the 10 nF input cap
                rolling off at 160 Hz
                ✓ swap C1 to 0.1 µF
                for full guitar range
                (or accept it for the
                breadboard sanity check)
```

---

# Appendix B — Parts substitution table

If you ever need to source replacements, here's what works:

| Original (in your bin) | Substitute | Notes |
|---|---|---|
| OPA1642 | OPA1641 (single-channel), TL072 (dual JFET) | Same pinout (TL072 is noisier but works) |
| MMBT3904 SOT-23 | 2N3904 TO-92 | Drop-in if you swap the adapter for direct DIP |
| TQ2-5V | Omron G6K-2P-Y-DC5, G5V-2-DC5 | Pinout differs — verify datasheet |
| 1N4148 DO-35 | 1N914, any small-signal Si diode rated > 100 mA | Drop-in |
| Switchcraft #11 | Switchcraft #12B, Cliff CL1384 (no firmware invert needed for CL1384) | |
| 10K + 10K VGND divider | TLE2426 rail-splitter IC | Cleaner, quieter, ~$2 |

---

---

# Appendix C — v3 changelog

**Critical fixes (would have blocked the build in v2):**

1. **Phase 7 step 2 + relay topology rewritten.** v2 disconnected the buffer→Line-In L tap (severing SOURCE_NODE per `signal_router_contract.md`) AND wired the relay with COM=buffer, NC=Rig Send, NO=codec line-out — which meant in injection mode the buffer output was shorted into the codec's line-out driver while Rig Send floated, delivering no generator signal to the rig. v3 keeps the SOURCE tap permanently in place, adds a parallel feed into the relay's NC contact, and swaps the topology so **COM=Rig Send, NC=buffer, NO=codec line-out** — the standard SPDT-selector pattern.
2. **Phase 1 TLE2426 sidebar.** v2 claimed "you didn't order a TLE2426." v3 corrects this: 5× TLE2426CLP are in stock per `parts_inventory.md:80`. The 10K/10K divider is now framed as an intentional educational choice that saves the TLE2426s for the production PCB.
3. **Phase 6 step 7 TQ2 pinout.** v2 punted to "verify from the datasheet" and left COIL_A / COM_1 / etc. as placeholders. v3 locks in the Panasonic ASCTB14E (2014-07) pin assignments: pins 1 & 10 = coil, pins 2/3/4 = POLE 1 NC/COM/NO, pins 7/8/9 = POLE 2, pins 5 & 6 are mechanical-only.
4. **Phase 4 step 6 thinking-out-loud removed.** v2 contained a "Wait — that puts both legs on the same strip and the resistor accomplishes nothing — Correction:" draft note in the published doc. v3 replaces it with the correct step in one pass.
5. **Phase 6 step 10 diode polarity rewrite.** v2 said "cathode band facing the +5V side" without naming which terminal that is. v3 says **"cathode band toward COIL (+), pin 10, the +5V side"** so it's unambiguous regardless of which reference frame the reader is in.

**Major fixes (anti-Lego patterns):**

6. Phase 6 step 2 SIPH06-1 row mapping committed to single hole positions (`49e` / `50e` / `51e`) instead of "row f or g".
7. Phase 4 step 4 "row j" hop given a 1-line BB830 row legend (`a`–`e` above the gap, `f`–`j` below).
8. Phase 4 step 12 promoted the breakout-cable path to primary; demoted soldered pigtail to alternative for experienced solderers.
9. Phase 5 deleted the "wiring trick to flip the sense" half-promise that v2 introduced but never described.
10. Phase 2 LED source clarified to the DIDODI practice kit (which is already in the parts inventory) instead of "any 2 LEDs lying around."

**Quick wins:**

11. Added a "If something feels wrong — read this first" panic card to the top of the doc (USB unplug, ESD note, spares reassurance).
12. Phase 9 now flags the 160 Hz HPF behavior so a successful test 1 below 300 Hz isn't read as a fault.
13. Appendix A rewritten as ASCII decision trees per phase, with explicit ✓/✗ outcomes.
14. v2's auto-numbered "Figure N: diagram N" captions replaced with descriptive captions when the v3 PDF is rendered (see image alt-text in the markdown source).

**Known gaps still present in v3:**

- The figures are still minimal — block diagrams and parts-tray rectangles. A future v4 should replace them with dense, top-down breadboard-grid images showing every wire/component placement after each step (review's Major #5). This is a multi-day illustration effort and out of scope for v3.
- Macro photos of IC pin-1 marks, Switchcraft #11 lug labels, D2F-01L COM/NC/NO terminals, and SIPH06-1 silkscreen orientation are not included. Replace the ASCII pinout tables with annotated photos in v4.

---

*End of v3 bring-up document. v1 is preserved at [breadboard_bringup.md](breadboard_bringup.md), v2 at [breadboard_bringup_v2.md](breadboard_bringup_v2.md). When phase 9 signs off, update CHANGELOG.md and start the PCB layout.*
