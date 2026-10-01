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
    return {
        "kind": "live",
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
