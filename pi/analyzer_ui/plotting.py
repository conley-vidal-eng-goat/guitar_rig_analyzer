"""Plot geometry. Pure arithmetic — no Tk, no I/O, fully unit-testable.

*** THE ONE RULE THIS MODULE EXISTS TO ENFORCE ***

A curve is NEVER drawn across a bin whose value is not a measurement.

The Teensy marks an unenergised bin as NaN and a saturated bin through the
per-bin coverage nibbles. Joining the two finite bins either side of a NaN would
invent a measurement the instrument never made — and it would look more
confident than the real data, which is the worst possible failure for an
instrument display. This is TODO-29's defect on a new surface: on 2026-09-07 a
consumer printed a flat, confident -24.0 dB curve in 33 of 33 windows that was
entirely a clamp rail. Protocol v2 exists to carry the information that stops it.

So ``segments()`` returns a LIST OF POLYLINES, not one polyline. Every
non-plottable bin terminates the current polyline and a new one starts after it.
A lone plottable bin between two NaNs comes back as a one-point polyline, which
the renderer draws as a dot.

MEASURED against the real 2026-09-27 RESULT rather than assumed: its
``tf_cal_mag_db`` has exactly **four** finite bins of 512, and they are
**contiguous — indices 22-25, 947.5 to 1076.7 Hz**, straddling the 1 kHz
stimulus. So the honest picture is ONE four-point span in the right place, not
four scattered dots (an earlier draft of this comment said dots; the fixture
corrected it). ``group_delay_ms`` is finite only at 23-24, because the central
difference needs both neighbours. A 512-point line across any of it would be a
fabrication.

``clamped_marks()`` is the second half of the contract. A clamped bin has a
value, but that value is the rail, not the measurement. It is returned
separately so the renderer can mark saturation instead of plotting it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --- axes -------------------------------------------------------------------

@dataclass(frozen=True)
class LinearAxis:
    """Maps a value range onto a pixel range. ``px_lo`` may exceed ``px_hi``
    (that is how a dB axis gets drawn with larger values higher up)."""
    lo: float
    hi: float
    px_lo: float
    px_hi: float

    def to_px(self, value: float) -> float:
        if self.hi == self.lo:
            return self.px_lo
        t = (value - self.lo) / (self.hi - self.lo)
        return self.px_lo + t * (self.px_hi - self.px_lo)

    def clamp_px(self, value: float) -> float:
        """``to_px`` with the result held inside the pixel range.

        Used for drawing only. A value outside the axis is still a real
        measurement; clipping it to the edge is a *rendering* decision and must
        never be confused with the instrument's own clamp marking.
        """
        px = self.to_px(value)
        lo, hi = sorted((self.px_lo, self.px_hi))
        return min(max(px, lo), hi)


@dataclass(frozen=True)
class LogFreqAxis:
    """Log-frequency axis. Bin 0 is DC and has no place on a log axis, so the
    axis starts at ``f_lo`` and callers skip anything below it."""
    f_lo: float
    f_hi: float
    px_lo: float
    px_hi: float

    def to_px(self, hz: float) -> float:
        if hz <= 0:
            return self.px_lo
        t = ((math.log10(hz) - math.log10(self.f_lo))
             / (math.log10(self.f_hi) - math.log10(self.f_lo)))
        return self.px_lo + t * (self.px_hi - self.px_lo)

    def in_range(self, hz: float) -> bool:
        return self.f_lo <= hz <= self.f_hi


# --- frequency mapping ------------------------------------------------------

def bin_width_hz(sample_rate: int, fft_bins: int) -> float:
    """Hz per FFT bin.

    ``fft_bins`` is the number of USABLE bins (HELLO's ``fft_bins``, 512), which
    is half the transform size, so the width is ``sample_rate / (2*fft_bins)``.
    Derived rather than hard-coded: the geometry comes from HELLO and a receiver
    that hard-codes it is the exact fragility TODO-36 warns about.
    """
    if fft_bins <= 0:
        raise ValueError("fft_bins must be positive")
    return sample_rate / (2.0 * fft_bins)


def result_bin_hz(index: int, sample_rate: int, fft_bins: int) -> float:
    """Centre frequency of a RESULT array element (the canonical 512 grid)."""
    return index * bin_width_hz(sample_rate, fft_bins)


def live_bin_hz(index: int, sample_rate: int, fft_bins: int,
                decim_ratio: int) -> float:
    """Centre frequency of a decimated LIVE_FRAME bin.

    Live bin ``j`` aggregates source bins ``[j*r, j*r + r - 1]``, so its
    representative frequency is the centre of that span, not its first bin.
    Using the first bin would shift the whole curve left by half a group.
    """
    if decim_ratio <= 0:
        raise ValueError("decim_ratio must be positive")
    centre = index * decim_ratio + (decim_ratio - 1) / 2.0
    return centre * bin_width_hz(sample_rate, fft_bins)


# --- the plottability test --------------------------------------------------

def is_plottable(value: float) -> bool:
    """A value is plottable only if it is a real, finite number.

    NaN means the instrument had no measurement for this bin. +/-Inf should be
    unproducible (the firmware guards every log10), so an Inf reaching here is a
    finding, not something to draw — either way it is not plotted.
    """
    return isinstance(value, (int, float)) and math.isfinite(value)


def segments(values, x_of_index, y_of_value, plottable=None) -> list[list]:
    """Split ``values`` into polylines broken at every non-plottable bin.

    ``x_of_index(i) -> float | None``   None drops the bin (e.g. off-axis DC).
    ``y_of_value(v) -> float``          only called for plottable values.
    ``plottable(i, v) -> bool``         optional extra veto, e.g. a clamped bin.

    Returns a list of polylines, each a list of ``(x, y)``. A one-point polyline
    is a legitimate result and means "one isolated valid bin" — draw it as a dot.
    """
    out: list[list] = []
    current: list = []
    for i, v in enumerate(values):
        ok = is_plottable(v)
        if ok and plottable is not None:
            ok = bool(plottable(i, v))
        x = x_of_index(i) if ok else None
        if not ok or x is None:
            if current:
                out.append(current)
                current = []
            continue
        current.append((x, y_of_value(v)))
    if current:
        out.append(current)
    return out


def clamped_marks(values, coverage, x_of_index, y_of_value) -> list:
    """Positions of bins the Teensy reported as SATURATED.

    A clamped bin carries the rail value, not a measurement, so it is returned
    for marking rather than plotting. The wire contract in ``data_sender.h`` is
    explicit: ``clamped == ratio`` means draw a saturation indicator, NOT the
    rail value.
    """
    marks = []
    for i, cov in enumerate(coverage):
        if i >= len(values):
            break
        if cov.ratio and cov.clamped >= cov.ratio:
            v = values[i]
            x = x_of_index(i)
            if x is not None and is_plottable(v):
                marks.append((x, y_of_value(v)))
    return marks


def pen_lift_indices(coverage) -> list[int]:
    """Bins with NO energised source bins — ``valid == 0``.

    ``data_sender.h``: ``valid == 0`` means pen-lift. Reported separately so the
    caller can veto them in ``segments()`` rather than discovering them as NaN.
    """
    return [i for i, cov in enumerate(coverage) if cov.valid == 0]


def census(values) -> dict:
    """Finite / NaN / +Inf / -Inf counts, for the honest-status readout.

    The UI shows this next to every plot so "4 of 512 bins" is visible on the
    face of the instrument rather than buried. Mirrors replay.py's array census
    so the screen and the replay report cannot disagree.
    """
    finite = nan = pos_inf = neg_inf = 0
    for v in values:
        if v != v:
            nan += 1
        elif v == float("inf"):
            pos_inf += 1
        elif v == float("-inf"):
            neg_inf += 1
        else:
            finite += 1
    return {"elements": len(values), "finite": finite, "nan": nan,
            "pos_inf": pos_inf, "neg_inf": neg_inf}
