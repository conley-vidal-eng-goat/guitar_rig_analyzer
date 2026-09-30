"""Tk renderer — the ONLY module here that imports tkinter.

Target: Raspberry Pi Touch Display 2, verified on this hardware 2026-09-29 as
**720x1280 portrait, transform normal, scale 1.0** (`wlr-randr`, DSI-2,
physical 90x151 mm). Portrait was measured, not assumed; a landscape layout
would have been wrong.

Everything is drawn on one Canvas rather than assembled from widgets. On a fixed
panel that is simpler and gives exact control over a dense instrument layout, and
a few hundred canvas items repainted at 20 Hz is nothing for a Pi 5.

*** WHAT THIS RENDERER WILL NOT DO ***
  - It will not grade quality, decide validity, or write advisories. Those
    arrive from the Teensy and are printed verbatim (ADR-001).
  - It will not join a curve across a bin the instrument did not measure.
    See plotting.segments(); the real RESULT has four finite bins of 512, which
    are contiguous (22-25, ~948-1077 Hz), so it draws as one short span sitting
    on the 1 kHz stimulus rather than a full-width curve.
  - It will not show a control as working when the command path does not exist.
    Pi -> Teensy is physically disconnected, so command buttons render disabled
    and say so.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from analyzer_link import protocol

from . import plotting
from .engine import Engine
from .model import UNKNOWN_TEXT, Snapshot

# --- geometry (portrait 720x1280, measured) ---------------------------------

W, H = 720, 1280
PAD = 16

Y_STATUS = 0
H_STATUS = 96
Y_STATE = Y_STATUS + H_STATUS
H_STATE = 100
Y_LEVELS = Y_STATE + H_STATE
H_LEVELS = 188
Y_PLOT = Y_LEVELS + H_LEVELS
H_PLOT = 476
Y_DETAIL = Y_PLOT + H_PLOT
H_DETAIL = 300
Y_TABS = Y_DETAIL + H_DETAIL
H_TABS = 120

# --- palette ----------------------------------------------------------------

BG = "#0d1117"
PANEL = "#161b22"
EDGE = "#21262d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#58a6ff"
SRC = "#7ee787"
RET = "#f0883e"
BAD = "#f85149"
WARN = "#d29922"
OKGREEN = "#3fb950"
GRID = "#1f242c"

# Level meter range. Chosen to show the whole usable window: the -40 dBFS arm
# threshold and the -0.5 dBFS clip threshold both fall inside it.
LVL_LO, LVL_HI = -90.0, 0.0

# TF magnitude axis. -24 dB is the firmware's clamp rail, so the axis must extend
# below it or a railed curve would sit on the frame edge and look intentional.
TF_LO, TF_HI = -42.0, 12.0

F_LO, F_HI = 20.0, 20000.0


def _f(size: int, bold: bool = False, mono: bool = False):
    fam = "DejaVu Sans Mono" if mono else "DejaVu Sans"
    return tkfont.Font(family=fam, size=size,
                       weight="bold" if bold else "normal")


class AnalyzerUI:
    """The first vertical slice: live view + result view over real telemetry."""

    def __init__(self, engine: Engine, *, fullscreen: bool = True,
                 tab: str = "live", refresh_ms: int = 50) -> None:
        self.engine = engine
        self.tab = tab
        self.refresh_ms = refresh_ms

        self.root = tk.Tk()
        self.root.title("Guitar Rig Analyzer")
        self.root.configure(bg=BG)
        self.root.geometry(f"{W}x{H}")
        if fullscreen:
            self.root.attributes("-fullscreen", True)
            # The desktop icon layer drew over the canvas on this Pi's
            # labwc session; -topmost keeps the instrument in front.
            self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda _e: self.root.destroy())

        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=BG,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_tap)

        self.fonts = {
            "h1": _f(34, True), "h2": _f(22, True), "body": _f(16),
            "small": _f(13), "tiny": _f(11), "mono": _f(14, mono=True),
            "mono_s": _f(12, mono=True), "big": _f(44, True),
            "meter": _f(26, True, mono=True),
        }
        self._hit: list[tuple[int, int, int, int, str]] = []

    # -- input ---------------------------------------------------------------

    def _on_tap(self, ev) -> None:
        for x0, y0, x1, y1, action in self._hit:
            if x0 <= ev.x <= x1 and y0 <= ev.y <= y1:
                if action in ("live", "result"):
                    self.tab = action
                return

    # -- loop ----------------------------------------------------------------

    def run(self) -> None:
        self._tick()
        self.root.mainloop()

    def _tick(self) -> None:
        self.engine.pump()
        try:
            self.redraw(self.engine.snapshot())
        except tk.TclError:                        # pragma: no cover - teardown
            return
        self.root.after(self.refresh_ms, self._tick)

    # -- drawing helpers -----------------------------------------------------

    def _panel(self, y, h, title=None):
        c = self.canvas
        c.create_rectangle(PAD, y + 6, W - PAD, y + h - 6,
                           fill=PANEL, outline=EDGE)
        if title:
            c.create_text(PAD + 14, y + 22, text=title, anchor="w",
                          fill=MUTED, font=self.fonts["small"])

    def _text(self, x, y, s, *, fill=TEXT, font="body", anchor="w"):
        return self.canvas.create_text(x, y, text=s, anchor=anchor, fill=fill,
                                       font=self.fonts[font])

    # -- sections ------------------------------------------------------------

    def _draw_status(self, s: Snapshot) -> None:
        c = self.canvas
        self._panel(Y_STATUS, H_STATUS)
        y = Y_STATUS + 34

        if not s.session_established:
            dot, label = BAD, "NO HELLO — geometry unknown"
        elif s.link_stale:
            dot, label = WARN, "LINK STALE"
        else:
            dot, label = OKGREEN, "LINK UP"
        c.create_oval(PAD + 18, y - 9, PAD + 36, y + 9, fill=dot, outline="")
        self._text(PAD + 48, y, label, fill=TEXT, font="h2")

        src = self.engine.source
        self._text(W - PAD - 14, y, src.name, fill=MUTED, font="small",
                   anchor="e")

        y2 = Y_STATUS + 68
        geo = s.geometry
        geo_txt = (f"{geo.live_bins}/{geo.fft_bins} bins · {geo.decim_ratio}:1 · "
                   f"{geo.sample_rate} Hz" if geo else "geometry UNKNOWN")
        self._text(PAD + 18, y2,
                   f"session {s.session_text}   fw {s.firmware_text}   "
                   f"proto {s.protocol_version if s.protocol_version else UNKNOWN_TEXT}",
                   fill=MUTED, font="mono_s")
        self._text(W - PAD - 14, y2, geo_txt, fill=MUTED, font="mono_s",
                   anchor="e")

    def _draw_state(self, s: Snapshot) -> None:
        c = self.canvas
        # Sticky ABORTED is its own visual state, and it stays until the Teensy
        # says otherwise. TODO-57: the abort latch is authoritative and the Pi
        # must not clear it on its own.
        if s.abort_latched:
            c.create_rectangle(PAD, Y_STATE + 6, W - PAD, Y_STATE + H_STATE - 6,
                               fill="#3d1416", outline=BAD, width=2)
            self._text(PAD + 20, Y_STATE + 40, "ABORTED", fill=BAD, font="big")
            reason = s.abort_reason_text or UNKNOWN_TEXT
            self._text(PAD + 20, Y_STATE + 76,
                       f"{reason}   ·   code {s.abort_reason_code.name}",
                       fill=TEXT, font="body")
            self._text(W - PAD - 20, Y_STATE + 40, "STICKY", fill=BAD,
                       font="small", anchor="e")
            return

        self._panel(Y_STATE, H_STATE)
        known = s.state_known
        colour = TEXT if known else WARN
        self._text(PAD + 20, Y_STATE + 44, s.state_text, fill=colour,
                   font="big")
        note = ("measurement state from the Teensy"
                if known else "no STATE packet yet")
        self._text(PAD + 22, Y_STATE + 78, note, fill=MUTED, font="small")
        self._text(W - PAD - 20, Y_STATE + 44, f"view {s.view.name}",
                   fill=MUTED, font="small", anchor="e")

    def _meter(self, y, label, reading, colour) -> None:
        c = self.canvas
        x0, x1 = PAD + 22, W - PAD - 22
        self._text(x0, y, label, fill=MUTED, font="small")
        self._text(x1, y, reading.text,
                   fill=(BAD if reading.clipping else colour),
                   font="meter", anchor="e")
        by = y + 30
        c.create_rectangle(x0, by, x1, by + 26, fill=BG, outline=EDGE)
        if reading.dbfs is None:
            # UNKNOWN never renders as an empty bar that could read as silence.
            c.create_text((x0 + x1) / 2, by + 13, text="NO DATA",
                          fill=WARN, font=self.fonts["small"])
        else:
            axis = plotting.LinearAxis(LVL_LO, LVL_HI, x0, x1)
            px = axis.clamp_px(reading.dbfs)
            if px > x0:
                c.create_rectangle(x0, by, px, by + 26, fill=colour,
                                   outline="")
            # -40 dBFS arm threshold tick — an operator-relevant landmark.
            tx = axis.to_px(-40.0)
            c.create_line(tx, by - 4, tx, by + 30, fill=MUTED, dash=(2, 3))
        if reading.clipping:
            self._text(x0 + 8, by + 46, "CLIP", fill=BAD, font="small")

    def _draw_levels(self, s: Snapshot) -> None:
        self._panel(Y_LEVELS, H_LEVELS, "INPUT LEVELS (Teensy-measured)")
        self._meter(Y_LEVELS + 46, "SOURCE_NODE", s.source, SRC)
        self._meter(Y_LEVELS + 122, "RETURN_NODE", s.returns, RET)

    # -- the plot ------------------------------------------------------------

    def _plot_frame(self, title, subtitle):
        c = self.canvas
        self._panel(Y_PLOT, H_PLOT, title)
        x0, x1 = PAD + 54, W - PAD - 18
        y0, y1 = Y_PLOT + 46, Y_PLOT + H_PLOT - 86
        c.create_rectangle(x0, y0, x1, y1, fill=BG, outline=EDGE)

        fx = plotting.LogFreqAxis(F_LO, F_HI, x0, x1)
        fy = plotting.LinearAxis(TF_LO, TF_HI, y1, y0)

        for db in range(int(TF_LO), int(TF_HI) + 1, 6):
            py = fy.to_px(db)
            c.create_line(x0, py, x1, py, fill=GRID)
            c.create_text(x0 - 8, py, text=f"{db}", anchor="e", fill=MUTED,
                          font=self.fonts["tiny"])
        for hz, lab in ((100, "100"), (1000, "1k"), (10000, "10k")):
            px = fx.to_px(hz)
            c.create_line(px, y0, px, y1, fill=GRID)
            c.create_text(px, y1 + 8, text=lab, anchor="n", fill=MUTED,
                          font=self.fonts["tiny"])
        c.create_text(x0 - 8, y0 - 14, text="dB", anchor="e", fill=MUTED,
                      font=self.fonts["tiny"])
        if subtitle:
            c.create_text(x1, y0 - 14, text=subtitle, anchor="e", fill=MUTED,
                          font=self.fonts["tiny"])
        return fx, fy, (x0, y0, x1, y1)

    def _draw_curve(self, segs, colour, width=2) -> None:
        c = self.canvas
        for seg in segs:
            if len(seg) == 1:
                # ONE valid bin surrounded by invalid ones. A dot, never a line.
                x, y = seg[0]
                c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=colour,
                              outline="")
            else:
                flat = [v for pt in seg for v in pt]
                c.create_line(*flat, fill=colour, width=width, capstyle="round")

    def _census_line(self, box, cen, extra="") -> None:
        x0, _y0, x1, y1 = box
        txt = (f"{cen['elements']} bins · {cen['finite']} finite · "
               f"{cen['nan']} NaN (not measured)")
        if cen["pos_inf"] or cen["neg_inf"]:
            txt += f" · {cen['pos_inf'] + cen['neg_inf']} Inf — FINDING"
        if extra:
            txt += f" · {extra}"
        self.canvas.create_text(x0, y1 + 32, text=txt, anchor="w",
                                fill=WARN, font=self.fonts["mono_s"])

    def _draw_live_plot(self, s: Snapshot) -> None:
        live, geo = s.live, s.geometry
        conf = (f"confidence {s.tf_confidence * 100:.0f}%"
                if s.tf_confidence is not None else "")
        if s.tf_clamped_count is not None:
            conf += f"   ·   {s.tf_clamped_count}/512 clamped"
        fx, fy, box = self._plot_frame("LIVE TRANSFER FUNCTION", conf)
        if live is None or geo is None:
            self.canvas.create_text((box[0] + box[2]) / 2,
                                    (box[1] + box[3]) / 2,
                                    text="waiting for LIVE_FRAME",
                                    fill=WARN, font=self.fonts["h2"])
            return

        def x_of(i):
            hz = plotting.live_bin_hz(i, geo.sample_rate, geo.fft_bins,
                                      geo.decim_ratio)
            return fx.to_px(hz) if fx.in_range(hz) else None

        lifted = set(plotting.pen_lift_indices(live.coverage))
        clamped_ix = {i for i, cov in enumerate(live.coverage)
                      if cov.ratio and cov.clamped >= cov.ratio}

        def ok(i, _v):
            return i not in lifted and i not in clamped_ix

        segs = plotting.segments(live.tf_db, x_of, fy.clamp_px, plottable=ok)
        self._draw_curve(segs, ACCENT)

        for x, y in plotting.clamped_marks(live.tf_db, live.coverage, x_of,
                                           fy.clamp_px):
            self.canvas.create_line(x - 5, y - 5, x + 5, y + 5, fill=WARN,
                                    width=2)
            self.canvas.create_line(x - 5, y + 5, x + 5, y - 5, fill=WARN,
                                    width=2)

        extra = f"{len(clamped_ix)} clamped · {len(lifted)} lifted"
        self._census_line(box, plotting.census(live.tf_db), extra)

    def _draw_result_plot(self, s: Snapshot) -> None:
        res, geo = s.result, s.geometry
        fx, fy, box = self._plot_frame(
            "RESULT — CALIBRATED MAGNITUDE (512-bin grid)",
            f"{res.n_averages_completed} averages" if res else "")
        if res is None or geo is None:
            self.canvas.create_text((box[0] + box[2]) / 2,
                                    (box[1] + box[3]) / 2,
                                    text="no RESULT received",
                                    fill=MUTED, font=self.fonts["h2"])
            return

        def x_of(i):
            hz = plotting.result_bin_hz(i, geo.sample_rate, geo.fft_bins)
            return fx.to_px(hz) if fx.in_range(hz) else None

        segs = plotting.segments(res.tf_cal_mag_db, x_of, fy.clamp_px)
        self._draw_curve(segs, SRC, width=3)
        self._census_line(box, plotting.census(res.tf_cal_mag_db),
                          f"{len(segs)} span(s)")

        # *** PROTOCOL GAP, stated on the face of the instrument. ***
        # LIVE_FRAME carries per-bin coverage nibbles and a frame-level
        # tf_clamped_count (protocol v2 audit finding L1). RESULT carries
        # NEITHER, so nothing in this packet distinguishes a measured -24.0 dB
        # from the clamp rail. Refusing to say so would reproduce TODO-29 on the
        # RESULT surface, so the plot admits it instead of looking confident.
        rail = [v for v in res.tf_cal_mag_db
                if plotting.is_plottable(v) and abs(v + 24.0) < 0.05]
        if rail:
            live_note = ""
            if s.tf_clamped_count is not None:
                live_note = (f"  live frame reports "
                             f"{s.tf_clamped_count}/512 clamped")
            self.canvas.create_text(
                box[0], box[3] + 54,
                text=(f"all {len(rail)} finite bin(s) sit on the -24.0 dB "
                      f"clamp rail · RESULT carries no per-bin clamp mask, so "
                      f"measured and railed are indistinguishable here"
                      f"{live_note}"),
                anchor="nw", fill=WARN, font=self.fonts["tiny"],
                width=W - 2 * PAD - 60)

    # -- detail panel --------------------------------------------------------

    def _draw_live_detail(self, s: Snapshot) -> None:
        self._panel(Y_DETAIL, H_DETAIL, "SIGNAL ROUTING (Teensy-authored)")
        y = Y_DETAIL + 54
        rs = s.return_source.name if s.return_source else UNKNOWN_TEXT
        self._text(PAD + 22, y, f"Return source:  {rs}", font="h2")
        self._text(PAD + 22, y + 40,
                   s.router_description or UNKNOWN_TEXT, fill=MUTED)
        # ADR-004 / TODO-58: presence is meaningless without availability, and
        # no detector hardware is fitted, so every jack is UNKNOWN by design.
        det = ("detectors: UNKNOWN (no detect hardware fitted)"
               if not s.detectors_available else "detectors: available")
        self._text(PAD + 22, y + 74, det, fill=WARN, font="small")
        self._text(PAD + 22, y + 104,
                   "Route is operator-selected (ADR-004); jack presence never "
                   "selects it.", fill=MUTED, font="tiny")

        st = self.engine.framing_stats
        self._text(PAD + 22, y + 150, "LINK", fill=MUTED, font="small")
        self._text(PAD + 22, y + 180,
                   f"frames ok {st.frames_ok}   CRC fail {st.crc_failures}   "
                   f"decode err {s.decode_errors}",
                   fill=(BAD if st.crc_failures or s.decode_errors else MUTED),
                   font="mono_s")
        self._text(PAD + 22, y + 204,
                   f"discarded {st.bytes_discarded} "
                   f"(lead {st.bytes_discarded_leading}, "
                   f"interior {st.bytes_discarded_interior})",
                   fill=(BAD if st.bytes_discarded_interior else MUTED),
                   font="mono_s")
        for w in s.warnings:
            self._text(PAD + 22, y + 228, w, fill=BAD, font="small")

    def _draw_result_detail(self, s: Snapshot) -> None:
        self._panel(Y_DETAIL, H_DETAIL, "RESULT — TEENSY-AUTHORED VERDICT")
        res = s.result
        if res is None:
            self._text(PAD + 22, Y_DETAIL + 60,
                       "No RESULT has been received on this link.", fill=MUTED)
            return
        y = Y_DETAIL + 44
        qcol = {"INVALID": BAD, "POOR": WARN, "MARGINAL": WARN,
                "GOOD": OKGREEN, "EXCELLENT": OKGREEN}.get(s.quality_text, TEXT)
        # Row 1: the two headline verdicts, pinned to opposite edges so neither
        # can grow into the other (they overlapped in the first render).
        self._text(PAD + 22, y, f"Quality: {s.quality_text}", fill=qcol,
                   font="h2")
        self._text(W - PAD - 22, y, f"valid: {res.result_valid}",
                   fill=TEXT, font="h2", anchor="e")
        # Row 2: one mono line, so spacing is fixed and nothing can collide.
        self._text(PAD + 22, y + 30,
                   f"coherence {res.mean_coherence:.3f}   "
                   f"valid bins {res.valid_bin_fraction * 100:.1f}%   "
                   f"fft {res.fft_size}   clip {res.clip_detected}",
                   fill=MUTED, font="mono_s")
        self._text(PAD + 22, y + 50, f"cal: {s.calibration_text}",
                   fill=(WARN if not res.calibration_applied else MUTED),
                   font="mono_s")
        if s.calibration_warning_names:
            self._text(PAD + 22, y + 68,
                       "warnings: " + ", ".join(s.calibration_warning_names),
                       fill=WARN, font="mono_s")

        # Insights are printed verbatim. The Pi neither writes nor ranks them.
        self._text(PAD + 22, y + 94,
                   f"INSIGHTS ({len(res.insights)}) — authored by the Teensy",
                   fill=MUTED, font="small")
        iy = y + 116
        sev = {"INFO": MUTED, "WARNING": WARN, "ALERT": BAD}
        # 33 px per entry fits all four inside the panel; the first render
        # clipped the fourth, which is the one that says advisories are
        # unavailable — exactly the one you must not lose.
        for ins in res.insights[:4]:
            col = sev.get(ins.severity.name, TEXT)
            self._text(PAD + 22, iy,
                       f"[{ins.severity.name}] {ins.title}", fill=col,
                       font="small")
            # ONE line, truncated rather than wrapped: a two-line detail
            # pushed the next title into it in the first render.
            detail = ins.detail if len(ins.detail) <= 76 else ins.detail[:75] + "…"
            self.canvas.create_text(PAD + 34, iy + 16, text=detail,
                                    anchor="w", fill=MUTED,
                                    font=self.fonts["tiny"])
            iy += 35
        if len(res.insights) > 4:
            self._text(PAD + 22, iy, f"+{len(res.insights) - 4} more",
                       fill=MUTED, font="tiny")

    # -- tabs and disabled commands -----------------------------------------

    def _draw_tabs(self, s: Snapshot) -> None:
        c = self.canvas
        self._hit = []
        c.create_rectangle(0, Y_TABS, W, H, fill=PANEL, outline=EDGE)
        bw, bh, by = 170, 64, Y_TABS + 14
        for i, (key, label) in enumerate((("live", "LIVE"),
                                          ("result", "RESULT"))):
            x = PAD + i * (bw + 12)
            on = self.tab == key
            c.create_rectangle(x, by, x + bw, by + bh,
                               fill=(ACCENT if on else BG),
                               outline=(ACCENT if on else EDGE), width=2)
            c.create_text(x + bw / 2, by + bh / 2, text=label,
                          fill=(BG if on else TEXT), font=self.fonts["h2"])
            self._hit.append((x, by, x + bw, by + bh, key))

        # Commands need a Pi -> Teensy path. There is none: pin 0 and GPIO14 are
        # unconnected by design. Rendering these as live buttons would be a lie,
        # so they are dashed, greyed, and captioned underneath.
        cluster_w = 3 * 56 + 2 * 8
        x = W - PAD - cluster_w
        for label in ("m", "x", "c"):
            c.create_rectangle(x, by, x + 56, by + bh, fill=BG,
                               outline="#30363d", dash=(3, 3))
            c.create_text(x + 28, by + bh / 2, text=label, fill="#484f58",
                          font=self.fonts["h2"])
            x += 64
        c.create_text(W - PAD, by + bh + 10, text="commands disabled",
                      anchor="ne", fill="#484f58", font=self.fonts["tiny"])
        c.create_text(W - PAD, by + bh + 26, text="Pi→Teensy not connected",
                      anchor="ne", fill="#484f58", font=self.fonts["tiny"])

    # -- top level -----------------------------------------------------------

    def redraw(self, s: Snapshot) -> None:
        self.canvas.delete("all")
        self._draw_status(s)
        self._draw_state(s)
        self._draw_levels(s)
        if self.tab == "result":
            self._draw_result_plot(s)
            self._draw_result_detail(s)
        else:
            self._draw_live_plot(s)
            self._draw_live_detail(s)
        self._draw_tabs(s)
