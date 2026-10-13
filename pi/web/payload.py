"""Fixture/live bytes -> display-ready JSON for the web renderer.

*** THIS IS THE AUTHORITY BOUNDARY, AND IT IS DELIBERATELY ON THIS SIDE OF IT. ***

The browser receives bands that are ALREADY CLASSIFIED. It never sees a coverage
nibble, never sees a NaN, never decides what a bin means. That is what keeps
ADR-005's invariant enforceable: a renderer cannot transform absence into asserted
measurement if absence never reaches it as a number.

What the browser is still allowed to do (ADR-005 §7) is geometry: turn a dB value
into a bar height, pick a colour, move a camera, ease a transition. Those are
presentation transforms and they cannot change measurement meaning.

*** WHY A BAND CAN HAVE A CLASS BUT NO VALUE ***

`resample()` averages over MEASURED members only, because a mean that included a
rail or an unclassifiable value would be a number the instrument never produced.
So an INDETERMINATE band reports `value: null` plus its source counts. The honest
statement is "four sources here, none of them establishable", NOT "-24.0 dB".
"""

from __future__ import annotations

import math

from analyzer_link import presentation_semantics as ps

# The committed design's ring: 48 bands, 20 Hz at the bottom, 20 kHz at the top.
RING_BANDS = 48
F_LO = 20.0
F_HI = 20000.0

_LOG_SPAN = math.log10(F_HI / F_LO)


def band_of_hz(hz: float, bands: int = RING_BANDS) -> int | None:
    """Log-frequency band index, or None for anything off the ring.

    DC (bin 0) has no place on a log axis and is dropped rather than folded into
    the lowest band, which would put a 0 Hz value under a "20 Hz" label.
    """
    if not (isinstance(hz, (int, float)) and math.isfinite(hz)) or hz < F_LO or hz > F_HI:
        return None
    t = math.log10(hz / F_LO) / _LOG_SPAN
    return min(int(t * bands), bands - 1)


def _band_hz(index: int, bands: int = RING_BANDS) -> float:
    """Centre frequency of a ring band, for labelling only."""
    return F_LO * (10 ** (_LOG_SPAN * (index + 0.5) / bands))


def _bin_hz(index: int, sample_rate: int, fft_bins: int) -> float:
    return index * (sample_rate / (2.0 * fft_bins))


# =============================================================================
# MAGNITUDE SPECTRA — fft_source[] / fft_return[]
# =============================================================================
#
# *** THE UNIT IS NOT dBFS, AND THE FIRMWARE DOES NOT CLAIM IT IS. ***
#
# Established by reading the firmware, not assumed:
#
#   audio_capture.cpp:693   s_accum_src[k] += s_fft_src.read(k)
#   audio_capture.cpp:99    s_fft_src is an AudioAnalyzeFFT1024
#   audio_capture.cpp:485   windowFunction(AudioWindowHanning1024)
#   audio_capture.cpp:778   fft_source[k] = accum * (1.0 / FFT_AVERAGE_COUNT)
#
# So each value is the mean, over FFT_AVERAGE_COUNT frames, of the Teensy audio
# library's per-bin magnitude, which the library scales to a nominal 0.0-1.0.
#
# **A Hann window is applied.** Its coherent gain is 0.5, so a full-scale sine
# does not read 1.0 in its bin, and the energy is spread across neighbours. The
# mapping from "full-scale input" to "1.0 here" has never been calibrated on this
# instrument, so **1.0 is a reference, not a known full-scale level.**
#
# 🔺 `audio_capture.cpp:332` defines `linearToDbfs()`, which would convert these
# to "dBFS" with a -120.0 floor. **IT HAS NO CALLERS.** Its name is an
# unverified claim and its floor is an invented number; wiring it up would put
# both on screen as though measured. See TODO-81.
#
# The honest label is therefore **dB relative to FFT magnitude 1.0** -- never
# dBFS, and never on the same axis as `peak_source_dbfs`, which is a time-domain
# peak and a different quantity entirely.

SPECTRUM_UNIT = "linear_magnitude"
SPECTRUM_REFERENCE = 1.0
SPECTRUM_REFERENCE_NOTE = (
    "Mean of AudioAnalyzeFFT1024 per-bin magnitudes over FFT_AVERAGE_COUNT "
    "frames, Hann-windowed. Reference 1.0 is the library's nominal full-scale "
    "magnitude and has NOT been calibrated against a full-scale input on this "
    "instrument. This is NOT dBFS and must not share an axis with the "
    "time-domain peak meters."
)


def spectrum_geometry(geometry, count: int) -> list[dict]:
    """The frequency span each TRANSMITTED bin actually covers.

    Spans, not just centres, because the span is what says whether a bin can go
    on a log axis at all. Transmitted bin ``i`` is `decimateMax` over source bins
    ``i*decim .. i*decim+decim-1``, and source bin ``k`` is centred at ``k*df``
    spanning half a bin either side.

    *** BIN 0 CONTAINS DC, AND THAT IS NOT RECOVERABLE. ***
    Its span starts at 0 Hz. Because the firmware decimates by MAXIMUM and does
    not say which source bin won, a large value in bin 0 may be a DC offset or
    may be a real tone near 130 Hz -- nothing on the wire distinguishes them. It
    is flagged rather than dropped here, so the renderer excludes it from a log
    axis knowingly instead of a reader wondering where bin 0 went.
    """
    df = geometry.sample_rate / (2.0 * geometry.fft_bins)
    decim = max(1, int(geometry.decim_ratio))
    out = []
    for i in range(count):
        lo = max(0.0, (i * decim - 0.5) * df)
        hi = (i * decim + decim - 0.5) * df
        out.append({
            "i": i,
            "lo_hz": round(lo, 2),
            "hi_hz": round(hi, 2),
            "hz": round((i * decim + (decim - 1) / 2.0) * df, 2),
            "dc": lo <= 0.0,
        })
    return out


def _spectrum_points(bins) -> list[dict]:
    """One transmitted bin on the wire.

    ``value`` is present only when the bin is drawable as a measurement -- the
    same rule the ring uses. For a spectrum that means every finite bin, because
    a magnitude needs no coverage to be interpretable and zero is a measurement
    of silence (`presentation_semantics.classify_spectrum`).
    """
    return [
        {"cls": b.cls.name,
         "value": (b.value if b.cls.is_drawable_as_measurement
                   and math.isfinite(b.value) else None)}
        for b in bins
    ]


def _segment(b: ps.BinSemantics, bands: int) -> dict:
    """One ring band on the wire.

    ``value`` is present ONLY when the band is drawable as a measurement. For
    every other class it is null -- not 0, not the rail, not a mean. A renderer
    that wants to draw a bar therefore has nothing to draw one from unless the
    contract says it may.
    """
    drawable = b.cls.is_drawable_as_measurement
    value = b.value if (drawable and math.isfinite(b.value)) else None
    return {
        "i": b.index,
        "hz": round(_band_hz(b.index, bands), 1),
        "cls": b.cls.name,
        "value": None if value is None else round(value, 3),
        "coverage": round(b.coverage, 4),
        "sources": b.source_count,
        "counts": {
            "measured": b.measured_count,
            "clamped": b.clamped_count,
            "unmeasured": b.unmeasured_count,
            "indeterminate": b.indeterminate_count,
        },
    }


def _census(c: ps.Census) -> dict:
    return {"elements": c.elements, "measured": c.measured, "clamped": c.clamped,
            "unmeasured": c.unmeasured, "indeterminate": c.indeterminate,
            "text": c.text()}


def _ring(bins, sample_rate: int, fft_bins: int, bands: int):
    def group_of(i: int):
        return band_of_hz(_bin_hz(i, sample_rate, fft_bins), bands)
    return ps.resample(bins, bands, group_of=group_of)


def result_payload(result, geometry, *, bands: int = RING_BANDS) -> dict:
    """A RESULT, classified and reduced to the ring.

    Every finite bin is INDETERMINATE: RESULT carries no per-bin clamp mask
    (TODO-65). That is not pessimism, it is what the packet supports.
    """
    source = ps.classify_result(result.tf_cal_mag_db)
    ring = _ring(source, geometry.sample_rate, geometry.fft_bins, bands)
    return {
        "kind": "result",
        "bands": bands,
        "source_bins": len(source),
        "census_source": _census(ps.census(source)),
        "census_bands": _census(ps.census(ring)),
        "segments": [_segment(b, bands) for b in ring],
        # Teensy-authored, carried verbatim. The browser prints these; it must
        # never compute, re-grade or second-guess any of them (ADR-001).
        "authority": {
            "firmware_version": result.firmware_version,
            "result_valid": result.result_valid,
            "result_quality": result.result_quality.name,
            "n_averages_completed": result.n_averages_completed,
            "mean_coherence": result.mean_coherence,
            "calibration_applied": bool(result.calibration_applied),
        },
    }


def live_payload(live, geometry, *, bands: int = RING_BANDS) -> dict:
    """A LIVE_FRAME, classified and reduced to the ring.

    Full per-bin coverage exists here, so bands resolve to MEASURED / CLAMPED /
    UNMEASURED and no INDETERMINATE can arise.
    """
    source = ps.classify_live(live.tf_db, live.coverage)
    decim = max(1, int(geometry.decim_ratio))

    def group_of(i: int):
        centre = i * decim + (decim - 1) / 2.0
        hz = centre * (geometry.sample_rate / (2.0 * geometry.fft_bins))
        return band_of_hz(hz, bands)

    ring = ps.resample(source, bands, group_of=group_of)

    # The spectra are NOT resampled. They are the transmitted bins, plotted where
    # the instrument put them. A second reduction onto a log axis would leave 21
    # of 48 ring bands with no source bin at all (the transmitted bins are linear
    # at ~172 Hz), and would undo at the display the peak preservation the
    # firmware was careful to put on the wire.
    src_spec = ps.classify_spectrum(live.fft_source)
    ret_spec = ps.classify_spectrum(live.fft_return)

    return {
        "kind": "live",
        "spectra": {
            "unit": SPECTRUM_UNIT,
            "reference": SPECTRUM_REFERENCE,
            "reference_note": SPECTRUM_REFERENCE_NOTE,
            "nyquist_hz": round(geometry.sample_rate / 2.0, 2),
            "geometry": spectrum_geometry(geometry, len(src_spec)),
            "src": _spectrum_points(src_spec),
            "ret": _spectrum_points(ret_spec),
            "census_src": _census(ps.census(src_spec)),
            "census_ret": _census(ps.census(ret_spec)),
        },
        "bands": bands,
        "source_bins": len(source),
        "census_source": _census(ps.census(source)),
        "census_bands": _census(ps.census(ring)),
        "segments": [_segment(b, bands) for b in ring],
        "authority": {
            "peak_source_dbfs": live.peak_source_dbfs,
            "peak_return_dbfs": live.peak_return_dbfs,
            "tf_confidence": live.tf_confidence,
            "tf_clamped_count": live.tf_clamped_count,
            "measurement_state": live.measurement_state.name,
        },
    }
