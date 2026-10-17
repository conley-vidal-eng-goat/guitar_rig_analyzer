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
from typing import NamedTuple

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


# =============================================================================
# TONE — input over return, level-matched (2026-10-16)
# =============================================================================
#
# *** TONE NO LONGER DRAWS THE TRANSFER FUNCTION. IT DRAWS THE TWO SIGNALS. ***
#
# The operator's brief: "it should be clear what the input signal looks like and
# what the rig return signal looks like and we can compare them because they
# are on top of each other." So each section of the ring is ONE TRANSMITTED BIN,
# the input's level rises above the ring and the return's level drops below it.
#
# The tf_db ring drew every band at full length on 2026-10-16 (all readings
# were -15..-24 dB against a 12 dB scale), so bar length carried nothing. It
# also held its last value while the source was gated (`tf_persistence_active`)
# and lit the DC bin permanently. Spectra have none of those properties: they
# are the current 46 ms block, every finite bin is a measurement, and their
# level IS the volume.
#
# *** THE RETURN IS DRAWN LEVEL-MATCHED, AND THE MATCH IS STATED AS A NUMBER. ***
#
# A rig that is 22 dB quieter than its input would otherwise draw a return too
# short to compare shape against. So the return is drawn shifted by the
# broadband gain, and the gain itself is shown: the number says "you are losing
# / gaining level", the two shapes say "and this is what happened to the tone".
#
#     gain_db = 10 * log10( sum(ret^2) / sum(src^2) )
#
# summed over the displayed bins where the INPUT is above the floor -- the
# bins where there is something to compare. Power, not mean-of-dB: a bin that
# carries most of the energy should carry most of the verdict.
#
# 🔺 These are `decimateMax` values (the largest of four source bins), so this
# is a ratio of peak-per-group powers, not of true band powers. The same
# reduction is applied to both channels, so the ratio is like-for-like; it is
# still not the TF the measurement core computes, and must not be presented as
# one.
#
# *** THE FLOOR IS THE FIRMWARE'S OWN, NOT A NUMBER CHOSEN HERE. ***
#
# TF_SOURCE_GATE = 0.001 (config.h) is the level the Teensy calls "energised".
# 20*log10(0.001) = -60 dB. Pinned against config.h by
# test_the_tone_floor_is_the_firmware_gate. Below it a bin is still MEASURED --
# it is quiet, not absent (`classify_spectrum`) -- it simply gets no bar.
#
# *** BIN 0 IS NOT ON THE RING. ***
#
# It spans 0-150.73 Hz and contains DC; on 2026-10-16 it read -53 dB with the
# strings muted, which is why C2/C#2 never went dark. LIVE already refuses it.
# Recovering the low strings needs a firmware change (TODO-92, phase 2).

TONE_FIRST_BIN = 1          # bin 0 spans DC
# *** THE RING IS THE RANGE A GUITAR ACTUALLY PLAYS IN (operator, 2026-10-16) ***
# 46 bins (to 8.1 kHz) was the first cut; the operator's objection -- "my
# guitar doesn't go that high" -- matched the data: in every strum frame
# captured that day the input cleared the floor only up to bin 8 (~1.4-1.6
# kHz). Bin 16 ends at 2.91 kHz: every fretted fundamental up to E6 (1.32 kHz)
# plus the 2-3 kHz overtones where a rig's presence and bite changes show.
TONE_LAST_BIN = 16          # 2.73-2.91 kHz
TONE_FLOOR_DB = -60.0       # 20*log10(TF_SOURCE_GATE), config.h
GAIN_MIN_BINS = 3           # fewer than this and one bin decides the verdict

TONE_UNIT_NOTE = (
    "dB relative to FFT magnitude 1.0, uncalibrated. NOT dBFS. Return levels "
    "are also given shifted by gain_db so the two channels share one scale."
)


def _db(b: ps.BinSemantics) -> float | None:
    """Level in dB, or None when there is no finite positive magnitude.

    None covers two different facts, kept apart by the `*_cls` field beside it:
    UNMEASURED (no number) and an exact zero (MEASURED, minus infinity dB).
    """
    if b.cls is not ps.BinClass.MEASURED:
        return None
    v = b.value
    if not (isinstance(v, (int, float)) and math.isfinite(v)) or v <= 0.0:
        return None
    return 20.0 * math.log10(v)


class GainEstimate(NamedTuple):
    """One frame's verdict on the rig's broadband gain.

    Exactly one of three outcomes:
      gain_db set      -- enough bins where BOTH channels clear the floor.
      bound_db set     -- the input clears the floor in enough bins and the
                          return clears it in NONE of them: the return is at
                          least this far down, and nothing more can be said.
      both None        -- not enough input to judge. Silence has no gain.
    """
    gain_db: float | None
    bins: int
    bound_db: float | None


def frame_gain_db(src_spec, ret_spec, *, first: int = TONE_FIRST_BIN,
                  last: int = TONE_LAST_BIN,
                  floor_db: float = TONE_FLOOR_DB) -> GainEstimate:
    """Broadband return/input gain for ONE frame.

    *** ONLY BINS WHERE BOTH CHANNELS CLEAR THE FLOOR DECIDE IT. ***

    The first version summed every bin with input above the floor, whatever the
    return held there. Replayed against the 2026-10-16 strum capture, every
    return bin was -65..-78 dB -- the analyser's own floor -- and the "gain"
    came out as a confident -28 dB that was a ratio of signal to NOISE. Below
    the floor the return channel is not energised; a number built from it says
    nothing about the rig.

    🔺 Consequence, stated rather than hidden: a bin the rig cuts below the floor
    stops contributing, so on a rig with a deep treble cut this is the gain of
    the band that survives, not of the whole input.

    When the return is below the floor everywhere the input is above it, the
    honest output is a BOUND. Each such return bin is under F = 10^(floor/20),
    so the power ratio over those k bins is under k·F² / Σsrc² -- strictly.
    """
    F2 = (10.0 ** (floor_db / 20.0)) ** 2
    num = den = 0.0
    used = 0
    src_only_k = 0
    src_only_den = 0.0
    for i in range(first, min(last, len(src_spec) - 1) + 1):
        s, r = src_spec[i], ret_spec[i]
        s_db = _db(s)
        if s_db is None or s_db < floor_db:
            continue
        if r.cls is not ps.BinClass.MEASURED:
            continue
        r_db = _db(r)
        if r_db is not None and r_db >= floor_db:
            num += r.value * r.value
            den += s.value * s.value
            used += 1
        else:
            src_only_k += 1
            src_only_den += s.value * s.value
    if used >= GAIN_MIN_BINS:
        return GainEstimate(10.0 * math.log10(num / den), used, None)
    if used == 0 and src_only_k >= GAIN_MIN_BINS:
        bound = 10.0 * math.log10(src_only_k * F2 / src_only_den)
        return GainEstimate(None, src_only_k, bound)
    return GainEstimate(None, used, None)


class GainMatcher:
    """Holds and smooths the displayed gain. The ONLY state in the TONE path.

    *** WHY STATE AT ALL ***
    Between strums the input falls below the floor and a frame has no gain.
    Snapping the return back to unmatched there would make every strum's decay
    jump by the rig's gain. So the last established gain is HELD, and the
    payload says it is held.

    *** WHY IT ADVANCES ON THE BLOCK NUMBER, NOT ON THE POLL ***
    Every browser poll calls this. Smoothing per call would make the time
    constant depend on how many clients are open. It advances once per new
    instrument frame (`output_block_number`), so it is a property of the
    signal, not of the audience.

    ALPHA 0.2 per frame at ~21.6 frames/s is a ~0.2 s time constant. Measured
    2026-10-16 while strumming, the per-frame gain moved within ±1.5 dB, so
    this steadies the number without hiding a real change for long.

    A BOUND is never held and never smoothed: it is reported for the frame
    that produced it, and it does not overwrite a gain established earlier.
    """

    ALPHA = 0.2

    def __init__(self) -> None:
        self.gain_db: float | None = None
        self._last_block: int | None = None

    def update(self, est: GainEstimate, block: int | None) -> tuple[float | None, str]:
        """(gain to display and shift by, state). State is one of
        live / held / below_floor / none."""
        fresh = block is None or block != self._last_block
        self._last_block = block
        if est.gain_db is not None:
            if fresh:
                self.gain_db = (est.gain_db if self.gain_db is None
                                else self.gain_db + self.ALPHA * (est.gain_db - self.gain_db))
            return self.gain_db, "live"
        if est.bound_db is not None:
            return None, "below_floor"
        if self.gain_db is None:
            return None, "none"
        return self.gain_db, "held"


def tone_block(src_spec, ret_spec, geometry, *, gain_db: float | None,
               gain_state: str, gain_bins: int,
               gain_bound_db: float | None = None) -> dict:
    """The TONE ring: one entry per displayed bin, both channels, one scale.

    ``gain_db`` is the matched gain to apply (live or held), or None -- then
    the return is drawn unshifted and ``gain_state`` says why ("none", or
    "below_floor" with ``gain_bound_db`` saying how far down it is at least).

    Classification happens HERE, not in the browser (ADR-005): which channel is
    above the floor, and whether a section is RIG-ONLY -- the return carries
    energy (above the floor both as received and level-matched) where the
    input has none. That is the operator's
    "constant noise introduced by the rig", drawn white on the ring.
    """
    geo = spectrum_geometry(geometry, len(src_spec))
    shift = gain_db if gain_db is not None else 0.0
    rnd = lambda v: None if v is None else round(v, 2)

    bins = []
    n_in = n_ret = n_rig = 0
    for i in range(TONE_FIRST_BIN, min(TONE_LAST_BIN, len(src_spec) - 1) + 1):
        s, r = src_spec[i], ret_spec[i]
        s_db, r_db = _db(s), _db(r)
        r_match = None if r_db is None else r_db - shift
        src_on = s_db is not None and s_db >= TONE_FLOOR_DB
        # The return must clear the floor TWICE: as received, and after the
        # shift. Matching alone would lift the analyser's own -77 dB floor into
        # view whenever the rig loses level -- observed 2026-10-16 at -29.6 dB,
        # when all 46 sections lit white with nothing playing. Below the floor
        # as received, the return channel is not energised and there is
        # nothing of the rig's there to compare.
        ret_on = (r_db is not None and r_db >= TONE_FLOOR_DB
                  and r_match >= TONE_FLOOR_DB)
        rig_only = (s.cls is ps.BinClass.MEASURED and not src_on and ret_on)
        n_in += src_on
        n_ret += ret_on
        n_rig += rig_only
        g = geo[i]
        bins.append({
            "i": i, "hz": g["hz"], "lo_hz": g["lo_hz"], "hi_hz": g["hi_hz"],
            "src_cls": s.cls.name, "ret_cls": r.cls.name,
            "src_db": rnd(s_db), "ret_db": rnd(r_db), "ret_matched_db": rnd(r_match),
            "src_on": src_on, "ret_on": ret_on, "rig_only": rig_only,
        })

    return {
        "unit_note": TONE_UNIT_NOTE,
        "floor_db": TONE_FLOOR_DB,
        "first_bin": TONE_FIRST_BIN,
        "last_bin": TONE_LAST_BIN,
        "gain_db": rnd(gain_db),
        "gain_state": gain_state,
        "gain_bins": gain_bins,
        "gain_bound_db": rnd(gain_bound_db),
        "census": {"sections": len(bins), "input_on": n_in,
                   "return_on": n_ret, "rig_only": n_rig},
        "bins": bins,
    }


def live_payload(live, geometry, *, bands: int = RING_BANDS,
                 gain: GainMatcher | None = None) -> dict:
    """A LIVE_FRAME, classified and reduced to the ring.

    Full per-bin coverage exists here, so bands resolve to MEASURED / CLAMPED /
    UNMEASURED and no INDETERMINATE can arise.

    ``gain`` carries the held TONE gain between frames. Without one (tests, a
    single-shot call) the gain is this frame's alone and is never held.
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

    est = frame_gain_db(src_spec, ret_spec)
    matcher = gain if gain is not None else GainMatcher()
    g_db, g_state = matcher.update(est, live.output_block_number)
    tone = tone_block(src_spec, ret_spec, geometry, gain_db=g_db,
                      gain_state=g_state, gain_bins=est.bins,
                      gain_bound_db=est.bound_db)

    return {
        # ADDITIVE: TONE's input-over-return ring. `segments` below is kept,
        # unchanged, for anything that still reads the tf_db ring.
        "tone": tone,
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
