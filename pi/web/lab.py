"""LAB diagnostics: what the rig did to the signal, computed on the Pi.

*** EVERY NUMBER THE LAB DASHBOARD DRAWS IS COMPUTED HERE, NOT IN THE BROWSER. ***

Same boundary as `payload.py`: the browser receives finished, classified values
and turns them into geometry. It does no logarithm, no sum and no fit. A number
that is not established arrives as `None` with a `why`, never as a zero.

*** WHAT THIS IS, UNDER ADR-005 ***

Descriptive statistics of two Teensy-authored arrays (`fft_source[]`,
`fft_return[]`) and two Teensy-authored scalars (`peak_source_dbfs`,
`peak_return_dbfs`) -- the same kind of quantity as TONE's `gain_db`. They say
WHERE the return differs from the input and BY HOW MUCH. They are deliberately
NOT grades, verdicts or advice: there is no "good", no "muddy", no "rig health"
anywhere in this file, because those are Teensy-owned judgements (ADR-005, the
governing invariant). The instrument's own words stay on the RESULT printer.

*** THE LIMITS, STATED ONCE AND CARRIED TO THE SCREEN ***

  * Bins are `decimateMax` groups ~172 Hz wide (payload.spectrum_geometry). A
    guitar's harmonics are closer together than that below ~1 kHz, so nothing
    here resolves individual harmonics or pitch.
  * Magnitudes only. LIVE_FRAME carries no phase and no coherence, so nothing
    here can tell a rig's linear EQ from what it adds non-linearly in the same
    bin. "Added content" is energy where the INPUT had none -- the part of
    distortion and noise that lands in otherwise-quiet bins.
  * Uncalibrated: dB relative to FFT magnitude 1.0 (payload.SPECTRUM_UNIT).
    Differences between the two channels are meaningful; absolute levels are not
    dBFS.
  * A clipped frame (either `*_clip` flag) is excluded from every running
    statistic. Its spectra are still drawn live, because hiding a frame is not
    the same as it not having happened, but it does not vote.
"""

from __future__ import annotations

import math
from collections import deque

from analyzer_link import presentation_semantics as ps

from . import payload

FIRST_BIN = payload.TONE_FIRST_BIN          # bin 0 spans DC (payload.py)
FLOOR_DB = payload.TONE_FLOOR_DB            # the firmware's energised gate
MIN_BINS = payload.GAIN_MIN_BINS            # fewer and one bin decides a verdict

# Log axis for every LAB chart. 150 Hz is the bottom edge of bin 1; below it is
# DC territory the wire cannot separate (TODO-92), so the axis does not pretend.
AXIS_LO_HZ = 150.0
AXIS_TICKS = (200, 500, 1000, 2000, 5000, 10000, 20000)

# Octave bands for the tonal-balance chart, starting at bin 1's lower edge.
OCTAVE_EDGES = (150.0, 300.0, 600.0, 1200.0, 2400.0, 4800.0, 9600.0, 22050.0)

# Running windows, in instrument frames (~21.6/s, payload.GainMatcher).
EQ_WINDOW = 432             # ~20 s of energised frames
EQ_MIN_FRAMES = 5           # a bin with fewer is "not yet established"
DYN_WINDOW = 400            # peak pairs kept for the dynamics fit
DYN_POINTS_SENT = 240       # of those, drawn
DYN_MIN_POINTS = 20
DYN_MIN_SPAN_DB = 6.0       # input peaks must span this before a slope means anything
IDLE_WINDOW = 216           # ~10 s of silent-input frames
# *** A SILENT FRAME IS NOT YET SILENCE. *** Measured on the Pi 2026-10-18: a
# rig with +8..+18 dB of gain lifts a note's decay back above the gate long after
# the input has fallen below it, and counting those frames read "+30 dB of
# self-noise" that was the guitar's own sustain. Only frames after this many
# consecutive below-gate input frames (~1 s) are counted.
IDLE_SETTLE = 22
# *** A RETURN PEAK AT FULL SCALE IS THE CONVERTER, NOT THE RIG. ***
# Measured on the Pi 2026-10-18: return peaks sat at -0.1 dBFS (median) in 92%
# of played frames, and the "dynamics slope" fitted that ceiling as 0.00. Peaks
# at or above this level are kept on the plot, flagged, and left out of the fit.
NEAR_FS_DBFS = -1.0
SMOOTH_ALPHA = payload.GainMatcher.ALPHA    # same ~0.2 s time constant as TONE's gain
ROLLOFF = 0.85


def _db(b: ps.BinSemantics) -> float | None:
    return payload._db(b)


def _log_x(hz: float, hi: float) -> float:
    """Position on the LAB axis, 0..1. Geometry, decided once, here."""
    hz = min(max(hz, AXIS_LO_HZ), hi)
    return math.log(hz / AXIS_LO_HZ) / math.log(hi / AXIS_LO_HZ)


def _rnd(v, d=2):
    return None if v is None else round(v, d)


def axis(geometry, count: int) -> dict:
    """Bin edges and ticks as 0..1 positions, so the browser needs no log."""
    geo = payload.spectrum_geometry(geometry, count)
    hi = geometry.sample_rate / 2.0
    bins = [{"i": g["i"], "hz": g["hz"],
             "x0": round(_log_x(g["lo_hz"], hi), 4),
             "x1": round(_log_x(g["hi_hz"], hi), 4)}
            for g in geo[FIRST_BIN:]]
    ticks = [{"hz": t, "x": round(_log_x(t, hi), 4),
              "label": f"{t // 1000}k" if t >= 1000 else str(t)}
             for t in AXIS_TICKS if t <= hi]
    return {"lo_hz": AXIS_LO_HZ, "hi_hz": hi, "bins": bins, "ticks": ticks}


# =============================================================================
# ONE FRAME
# =============================================================================

# Per-bin cell class, one character each so a spectrogram row is a short string.
#   B  both channels above the floor -- a level-matched difference exists
#   R  rig-only: return above the floor where the input is not (payload.tone_block)
#   I  input-only: the rig took this bin below the floor
#   q  neither above the floor: quiet, measured
#   u  either channel UNMEASURED: no statement possible
CELL_BOTH, CELL_RIG, CELL_INPUT, CELL_QUIET, CELL_UNMEASURED = "BRIqu"


def _cells(src, ret, shift: float):
    """Classify every analysis bin and give the matched difference where it exists."""
    out = []
    for i in range(FIRST_BIN, len(src)):
        s, r = src[i], ret[i]
        if s.cls is not ps.BinClass.MEASURED or r.cls is not ps.BinClass.MEASURED:
            out.append((CELL_UNMEASURED, None, None, None))
            continue
        s_db, r_db = _db(s), _db(r)
        s_on = s_db is not None and s_db >= FLOOR_DB
        # Same double test as TONE: as received AND after matching.
        r_on = r_db is not None and r_db >= FLOOR_DB and r_db - shift >= FLOOR_DB
        if s_on and r_on:
            out.append((CELL_BOTH, r_db - shift - s_db, s.value, r.value))
        elif r_on:
            out.append((CELL_RIG, None, s.value, r.value))
        elif s_on:
            out.append((CELL_INPUT, None, s.value, r.value))
        else:
            out.append((CELL_QUIET, None, s.value, r.value))
    return out


def _describe(powers_hz: list[tuple[float, float]]) -> dict | None:
    """Centroid, roll-off, tilt and flatness of one channel over a bin set.

    Both channels are described over the SAME set of bins (see `frame_lab`), so
    a difference between them is a difference in the signal, not in which bins
    happened to be counted.
    """
    if len(powers_hz) < MIN_BINS:
        return None
    total = sum(p for _, p in powers_hz)
    if total <= 0.0:
        return None
    centroid = sum(f * p for f, p in powers_hz) / total
    acc, rolloff = 0.0, powers_hz[-1][0]
    for f, p in powers_hz:
        acc += p
        if acc >= ROLLOFF * total:
            rolloff = f
            break
    # Tilt: least-squares slope of level against octave. dB per octave.
    xs = [math.log2(f) for f, _ in powers_hz]
    ys = [10.0 * math.log10(p) for _, p in powers_hz]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    tilt = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx) if sxx > 0 else None
    # Spectral flatness (Wiener entropy): 1 = noise-like, -> 0 = a few strong peaks.
    geo = math.exp(sum(math.log(p) for _, p in powers_hz) / len(powers_hz))
    flat = geo / (total / len(powers_hz))
    shares = [0.0] * (len(OCTAVE_EDGES) - 1)
    for f, p in powers_hz:
        for k in range(len(shares)):
            if OCTAVE_EDGES[k] <= f < OCTAVE_EDGES[k + 1]:
                shares[k] += p
                break
    return {"centroid_hz": centroid, "rolloff_hz": rolloff, "tilt_db_oct": tilt,
            "flatness": flat, "octave_share": [s / total for s in shares]}


def frame_lab(src, ret, geometry, *, shift: float) -> dict:
    """Everything LAB says about ONE frame. No state."""
    cells = _cells(src, ret, shift)
    hzs = [g["hz"] for g in payload.spectrum_geometry(geometry, len(src))]
    F2 = (10.0 ** (FLOOR_DB / 20.0)) ** 2

    # The common set: every measured bin where EITHER channel is energised.
    # Below the floor a value is floored to the floor's power, so a bin the rig
    # removed still pulls the return's centroid the way the ear hears it --
    # toward the bins that remain -- without a log of zero.
    s_set, r_set = [], []
    for k, (c, _, sv, rv) in enumerate(cells):
        if c in (CELL_BOTH, CELL_RIG, CELL_INPUT):
            f = hzs[FIRST_BIN + k]
            s_set.append((f, max(sv * sv, F2)))
            r_set.append((f, max(rv * rv, F2)))
    d_in, d_out = _describe(s_set), _describe(r_set)

    ret_on_power = sum(rv * rv for c, _, sv, rv in cells if c in (CELL_BOTH, CELL_RIG))
    rig_power = sum(rv * rv for c, _, sv, rv in cells if c == CELL_RIG)

    delta = {}
    if d_in and d_out:
        delta = {
            "centroid_cents": 1200.0 * math.log2(d_out["centroid_hz"] / d_in["centroid_hz"]),
            "rolloff_hz": d_out["rolloff_hz"] - d_in["rolloff_hz"],
            "tilt_db_oct": (None if d_in["tilt_db_oct"] is None or d_out["tilt_db_oct"] is None
                            else d_out["tilt_db_oct"] - d_in["tilt_db_oct"]),
            "flatness": d_out["flatness"] - d_in["flatness"],
        }

    def clean(d):
        if d is None:
            return None
        return {k: ([round(x, 4) for x in v] if isinstance(v, list) else _rnd(v, 3))
                for k, v in d.items()}

    return {
        "cells": "".join(c for c, *_ in cells),
        "delta_db": [_rnd(d) for _, d, _, _ in cells],
        "src_db": [_rnd(_db(src[i])) for i in range(FIRST_BIN, len(src))],
        "ret_matched_db": [None if _db(ret[i]) is None else _rnd(_db(ret[i]) - shift)
                           for i in range(FIRST_BIN, len(ret))],
        "input": clean(d_in),
        "return": clean(d_out),
        "delta": {k: _rnd(v, 3) for k, v in delta.items()},
        "common_bins": len(s_set),
        "added_pct": (None if ret_on_power <= 0.0
                      else round(100.0 * rig_power / ret_on_power, 2)),
    }


# =============================================================================
# RUNNING STATISTICS
# =============================================================================

class LabTracker:
    """The running half of LAB. Advances once per NEW instrument frame.

    Like `payload.GainMatcher`, it keys on `output_block_number`, so the number
    of browsers polling cannot change a time constant or double-count a frame.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._last_block = None
        self._eq = deque()                  # per frame: [(k, s2, r2, d), ...]
        self._S: dict[int, float] = {}
        self._R: dict[int, float] = {}
        self._N: dict[int, int] = {}
        self._D: dict[int, float] = {}
        self._D2: dict[int, float] = {}
        self._dyn = deque(maxlen=DYN_WINDOW)
        self._idle = deque(maxlen=IDLE_WINDOW)
        self._silent_run = 0
        self.frames_seen = 0
        self.frames_clipped = 0
        self.smooth: dict[str, float] = {}  # held between strums, like the gain
        self.smooth_live = False
        self.cache_block = None
        self.cache = None

    # -- feeding --------------------------------------------------------------

    def _add_eq(self, entry):
        self._eq.append(entry)
        for k, s2, r2, d in entry:
            self._S[k] = self._S.get(k, 0.0) + s2
            self._R[k] = self._R.get(k, 0.0) + r2
            self._N[k] = self._N.get(k, 0) + 1
            self._D[k] = self._D.get(k, 0.0) + d
            self._D2[k] = self._D2.get(k, 0.0) + d * d
        if len(self._eq) > EQ_WINDOW:
            for k, s2, r2, d in self._eq.popleft():
                self._S[k] -= s2
                self._R[k] -= r2
                self._N[k] -= 1
                self._D[k] -= d
                self._D2[k] -= d * d

    def feed(self, frame: dict, src, ret, authority: dict, *, energised: bool) -> None:
        block = authority.get("output_block_number")
        if block is not None and block == self._last_block:
            return
        self._last_block = block
        self.frames_seen += 1
        if authority.get("source_clip") or authority.get("return_clip"):
            self.frames_clipped += 1
            return

        entry = []
        for k, (c, d) in enumerate(zip(frame["cells"], frame["delta_db"])):
            if c == CELL_BOTH and d is not None:
                i = FIRST_BIN + k
                entry.append((k, src[i].value ** 2, ret[i].value ** 2, d))
        if len(entry) >= MIN_BINS:
            self._add_eq(entry)

        pin, pout = authority.get("peak_source_dbfs"), authority.get("peak_return_dbfs")
        if (energised and isinstance(pin, (int, float)) and isinstance(pout, (int, float))
                and math.isfinite(pin) and math.isfinite(pout)):
            self._dyn.append((pin, pout))

        # Silent input: every analysis bin of the input measured and below the
        # floor. What the return carries then is the rig's own contribution.
        # Smoothed headline descriptors. Advanced only by ENERGISED frames (TONE
        # has a gain verdict), and HELD between strums -- the payload says so.
        # A decay tail with two bins above the gate would otherwise describe the
        # analyser's floor as much as the guitar: every common-set bin below the
        # gate counts at the gate's power (`frame_lab`), and when the strong
        # bins have faded, those dominate.
        pairs = []
        if energised:
            pairs = [("centroid_in", (frame["input"] or {}).get("centroid_hz")),
                     ("centroid_out", (frame["return"] or {}).get("centroid_hz")),
                     ("added_pct", frame["added_pct"])]
            pairs += [(k, frame["delta"].get(k)) for k in
                      ("centroid_cents", "tilt_db_oct", "flatness", "rolloff_hz")]
        for k, v in pairs:
            if v is None:
                continue
            old = self.smooth.get(k)
            self.smooth[k] = v if old is None else old + SMOOTH_ALPHA * (v - old)
        self.smooth_live = bool(pairs) and bool(frame["delta"])

        cells = frame["cells"]
        silent = bool(cells) and all(c in (CELL_QUIET, CELL_RIG) for c in cells)
        self._silent_run = self._silent_run + 1 if silent else 0
        if self._silent_run > IDLE_SETTLE:
            s_sum = sum(src[i].value ** 2 for i in range(FIRST_BIN, len(src)))
            r_sum = sum(ret[i].value ** 2 for i in range(FIRST_BIN, len(ret)))
            if s_sum > 0.0 and r_sum > 0.0:
                self._idle.append((s_sum, r_sum))

    # -- reporting ------------------------------------------------------------

    def eq(self, nbins: int) -> dict:
        """Long-term level-matched EQ: 10log10(sum ret^2 / sum src^2) per bin,
        minus the same ratio over every bin. Power-weighted, like TONE's gain."""
        tot_s = sum(v for v in self._S.values() if v > 0)
        tot_r = sum(v for v in self._R.values() if v > 0)
        if not self._eq or tot_s <= 0 or tot_r <= 0:
            return {"frames": len(self._eq), "gain_db": None,
                    "db": [None] * nbins, "sd": [None] * nbins, "n": [0] * nbins}
        g = 10.0 * math.log10(tot_r / tot_s)
        db, sd, n = [], [], []
        for k in range(nbins):
            cnt = self._N.get(k, 0)
            n.append(cnt)
            if cnt < EQ_MIN_FRAMES or self._S.get(k, 0) <= 0 or self._R.get(k, 0) <= 0:
                db.append(None)
                sd.append(None)
                continue
            db.append(round(10.0 * math.log10(self._R[k] / self._S[k]) - g, 2))
            m = self._D[k] / cnt
            var = max(0.0, self._D2[k] / cnt - m * m)
            sd.append(round(math.sqrt(var), 2))
        return {"frames": len(self._eq), "gain_db": round(g, 2), "db": db, "sd": sd, "n": n}

    def dynamics(self) -> dict:
        pts = list(self._dyn)
        near = sum(1 for _, b in pts if b >= NEAR_FS_DBFS)
        out = {"points": [[round(a, 1), round(b, 1)] for a, b in pts[-DYN_POINTS_SENT:]],
               "n": len(pts), "slope": None, "intercept": None, "r2": None,
               "span_db": None, "why": None, "near_fs_dbfs": NEAR_FS_DBFS,
               "near_fs_pct": round(100.0 * near / len(pts), 1) if pts else None}
        all_n = len(pts)
        pts = [(a, b) for a, b in pts if b < NEAR_FS_DBFS]
        out["n"] = len(pts)
        if len(pts) < DYN_MIN_POINTS and near:
            out["why"] = (f"return at full scale in {out['near_fs_pct']:.0f}% of "
                          f"{all_n} frames — lower the rig's output level")
            return out
        if len(pts) < DYN_MIN_POINTS:
            out["why"] = f"{len(pts)} of {DYN_MIN_POINTS} played frames"
            return out
        xs = [a for a, _ in pts]
        ys = [b for _, b in pts]
        span = max(xs) - min(xs)
        out["span_db"] = round(span, 1)
        if span < DYN_MIN_SPAN_DB:
            out["why"] = f"input peaks span {span:.1f} dB; need {DYN_MIN_SPAN_DB:.0f} dB — vary picking strength"
            return out
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx
        out.update(slope=round(slope, 3), intercept=round(my - slope * mx, 2),
                   r2=round((sxy * sxy) / (sxx * syy), 3) if syy > 0 else None)
        return out

    def idle(self) -> dict:
        if len(self._idle) < MIN_BINS:
            return {"frames": len(self._idle), "excess_db": None, "return_db": None,
                    "why": "mute the strings for 2 s"}
        s = sum(a for a, _ in self._idle)
        r = sum(b for _, b in self._idle)
        return {"frames": len(self._idle),
                "excess_db": round(10.0 * math.log10(r / s), 2),
                "return_db": round(10.0 * math.log10(r / len(self._idle)), 2),
                "why": None}


def lab_block(live, src, ret, geometry, *, shift: float, energised: bool,
              tracker: LabTracker | None, authority: dict) -> dict:
    """The `lab` key of a LIVE payload."""
    t = tracker if tracker is not None else LabTracker()
    block = authority.get("output_block_number")
    # One computation per instrument frame, however many polls ask for it.
    if tracker is not None and block is not None and block == t.cache_block:
        return t.cache
    fr = frame_lab(src, ret, geometry, shift=shift)
    t.feed(fr, src, ret, authority, energised=energised)
    nb = len(src) - FIRST_BIN

    tf = ps.classify_live(live.tf_db, live.coverage)
    tf_vals = [(b.value if b.cls.is_drawable_as_measurement and math.isfinite(b.value)
                else None) for b in tf[FIRST_BIN:]]
    tf_cls = "".join(b.cls.name[0] for b in tf[FIRST_BIN:])   # M / C / U

    out = {
        "block": block,
        "smooth": {k: round(v, 3) for k, v in t.smooth.items()},
        "smooth_held": not t.smooth_live,
        "axis": axis(geometry, len(src)),
        "floor_db": FLOOR_DB,
        "frame": fr,
        "eq": t.eq(nb),
        "dynamics": t.dynamics(),
        "idle": t.idle(),
        "tf": {"db": [_rnd(v) for v in tf_vals], "cls": tf_cls},
        "octave_edges": list(OCTAVE_EDGES),
        "frames_seen": t.frames_seen,
        "frames_clipped": t.frames_clipped,
        "clipped_pct": (round(100.0 * t.frames_clipped / t.frames_seen, 1)
                        if t.frames_seen else None),
        "windows": {"eq": EQ_WINDOW, "dyn": DYN_WINDOW, "idle": IDLE_WINDOW},
    }
    t.cache_block, t.cache = block, out
    return out
