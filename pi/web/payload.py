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
from analyzer_link import protocol

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


# =============================================================================
# TEENSY-AUTHORED INSIGHTS, CAPTURE PROVENANCE AND CALIBRATION STATE
# =============================================================================
#
# *** EVERYTHING IN THIS SECTION IS FORWARDING, NOT AUTHORSHIP. ***
#
# The Teensy writes the insight text, grades its own severity and decides its
# mode. This file copies those bytes to the browser and does nothing else to
# them -- no re-ranking, no re-wording, no severity inferred from a magnitude,
# no insight synthesised from the arrays. `insights_engine.cpp` is the author
# and `view_lab.js` is a printer (ADR-001, ADR-005 section 3).
#
# The Tk renderer has printed these verbatim since the first result view
# (`analyzer_ui/app.py`); until this commit the web renderer did not carry them
# at all, which made the browser the LESS informative of the two surfaces.
#
# *** AN EMPTY LIST IS A MEASUREMENT. A MISSING ONE CANNOT REACH HERE. ***
#
# `insight_count` is an explicit byte on the wire (`data_sender.h`, RESULT
# layout) and `packets.py` validates the declared count against both
# `insights_max` and the total payload length before building a Result. So a
# decoded Result with `insights == ()` means the instrument authored ZERO
# insights -- a statement -- and a truncated or over-long insight section raises
# DecodeError and never becomes a Result at all. The renderer is therefore
# entitled to say "none authored" and must never say it for missing data,
# because missing data does not arrive.


def _insight_frequency(hz: float) -> float | None:
    """`frequency_hz`, or None when the firmware's broadband sentinel is set.

    *** 0.0 IS NOT A FREQUENCY HERE, AND THE FIRMWARE SAYS SO. ***

      insights_engine.h:115   "Relevant frequency, or 0 if broadband"
      insights_engine.cpp:26  "Broadband insights carry frequency_hz = 0."
      insights_engine.cpp:537 prints the frequency only `if (ins.frequency_hz > 0)`

    Forwarding the raw 0.0 would let a renderer label a broadband quality
    advisory "@ 0 Hz", which is a location the instrument never claimed. Null
    is the same decision the firmware's own printer makes, not a new one.
    """
    if not (isinstance(hz, (int, float)) and math.isfinite(hz)) or hz <= 0.0:
        return None
    return hz


def _insight_magnitude(value: float) -> float | None:
    """The insight's magnitude slot, or None when the not-applicable sentinel is set.

    *** THE WIRE CANNOT DISTINGUISH "NOT APPLICABLE" FROM A TRUE ZERO. ***

    `insights_engine.h:116` reads "Relevant magnitude, or 0 if not applicable",
    so exactly 0.0 is overloaded. That ambiguity is a protocol limitation of the
    same family as TODO-65's missing clamp mask, and it is resolved the way this
    project resolves those: refuse to assert either reading.

    Null is chosen over the raw 0.0 because the two errors are not symmetric.
    Printing "0.0" beside "No calibration applied" asserts a broadband
    measurement that was never taken. Withholding the number loses nothing,
    because **the Teensy restates every magnitude it considers meaningful inside
    its own `detail` string** -- "Broadband mean TF: -24.0 dB." carries the
    -24.0 in prose, and that string is forwarded untouched.
    """
    if not (isinstance(value, (int, float)) and math.isfinite(value)) or value == 0.0:
        return None
    return value


def _insight(ins) -> dict:
    """One insight, forwarded. `title` and `detail` are never edited.

    The firmware's char[64] fields are NUL-padded and may already be truncated
    mid-word by the sender (`data_sender.h`). They are passed on exactly as
    decoded: re-wrapping or completing them would make this file a co-author.
    """
    return {
        "mode": ins.mode.name,
        "severity": ins.severity.name,
        "frequency_hz": _insight_frequency(ins.frequency_hz),
        # *** DELIBERATELY NOT NAMED `magnitude_db`. THE UNIT IS NOT ON THE WIRE. ***
        #
        # The struct field is called `magnitude_db`, and for "Signal level
        # decrease" it really is dB. But `insights_engine.cpp:170` passes
        # `r.mean_coherence` -- a dimensionless 0..1 ratio -- into the same slot
        # for "Measurement quality". The decoded 0.799 on the pinned fixture is
        # that coherence, not 0.799 dB.
        #
        # So the unit is a function of WHICH INSIGHT produced the value, and the
        # wire does not carry it. A payload key ending in `_db` would hand the
        # renderer a unit the instrument never transmitted, and `view_lab.js`
        # would print it in good faith. The only authoritative statement of the
        # unit is the Teensy's own `detail` sentence, which is forwarded intact.
        # Pinned by test_the_magnitude_slot_is_not_always_db.
        "magnitude": _insight_magnitude(ins.magnitude_db),
        "title": ins.title,
        "detail": ins.detail,
    }


def _calibration(result) -> dict:
    """Calibration identity and its warning bits, by name.

    `calibration_applied` is NOT repeated here: it already rides in
    `authority` and has since the first payload. One field, one home.
    """
    bits = int(result.calibration_warnings)
    return {
        "type": result.calibration_type.name,
        "warnings": [w.name for w in protocol.CalibrationWarning if bits & int(w)],
        "provenance": result.calibration_provenance,
    }


def _capture(result) -> dict:
    """The conditions the measurement was taken under, verbatim.

    `line_in_level` is here for the reason `data_sender.h` gives: without it a
    receiver will A/B two captures taken at different input gains and present
    the difference as a rig difference (audit finding R6). None of these is a
    judgement -- they are the settings the instrument recorded about itself.

    `fft_size` is the FFT length actually used and is NOT the array length; the
    spectra are always `fft_bins` long. `packets.py` says so and a renderer that
    confused the two would misreport the resolution.
    """
    return {
        "estimator": result.estimator.name,
        "stimulus": result.stimulus.name,
        "fft_mode": result.fft_mode.name,
        "window_function": result.window_function.name,
        "fft_size": result.fft_size,
        "timestamp_ms": result.timestamp_ms,
        "capture_start_block": result.capture_start_block,
        "capture_end_block": result.capture_end_block,
        "source_node_ch": result.source_node_ch,
        "return_node_ch": result.return_node_ch,
        "line_in_level": result.line_in_level,
        "clip_source_count": result.clip_source_count,
        "clip_return_count": result.clip_return_count,
        "clip_detected": bool(result.clip_detected),
        "generator_active": bool(result.generator_active),
    }


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
        #
        # ADDITIVE ONLY. Every key that was here before this commit is still
        # here, spelled and typed the same way, because `view_tone.js`,
        # `view_live.js` and `fingerprint_split.js` read this object by name.
        "authority": {
            "firmware_version": result.firmware_version,
            "result_valid": result.result_valid,
            "result_quality": result.result_quality.name,
            "n_averages_completed": result.n_averages_completed,
            "mean_coherence": result.mean_coherence,
            "calibration_applied": bool(result.calibration_applied),
            # Sibling of mean_coherence: the Teensy's own count of how much of
            # the analysis band it could establish. 0.0175 on the pinned
            # fixture -- the instrument grading its own coverage as 2%.
            "valid_bin_fraction": result.valid_bin_fraction,
        },
        "capture": _capture(result),
        "calibration": _calibration(result),
        # A LIST, ALWAYS PRESENT. Empty means the instrument authored none.
        "insights": [_insight(i) for i in result.insights],
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
        # ADDITIVE ONLY -- see the note on the RESULT authority block.
        "authority": {
            "peak_source_dbfs": live.peak_source_dbfs,
            "peak_return_dbfs": live.peak_return_dbfs,
            "tf_confidence": live.tf_confidence,
            "tf_clamped_count": live.tf_clamped_count,
            "measurement_state": live.measurement_state.name,
            # Flag bits the receiver has always decoded and the transport has
            # always dropped. A clip is the one live condition that invalidates
            # a reading while the reading still looks plausible, so it belongs
            # beside the peaks it qualifies.
            "source_clip": bool(live.source_clip),
            "return_clip": bool(live.return_clip),
            "tf_persistence_active": bool(live.tf_persistence_active),
            # The audio block counter's low 16 bits -- the ONLY freshness signal
            # on the wire, and not a wall clock. `packets.py`: gaps are dropped
            # frames, which is expected, and must not be rendered as an error.
            "output_block_number": live.output_block_number,
        },
    }
