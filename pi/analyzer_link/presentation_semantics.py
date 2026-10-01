"""Classification of Teensy-authored state into display-ready semantics.

Protocol-adjacent, renderer-agnostic, pure: no Tk, no three.js, no I/O. Both the
Tk reference renderer and the web client consume THIS module; neither reinterprets
raw protocol fields itself ([ADR-005](../../docs/adr/ADR-005-pi-rendering-stack-and-presentation-semantics.md) §4).

*** WHY THIS IS NOT CALLED bin_classification ***

The problem is not specific to FFT bins. It is one principle (ADR-005 §5):

    Defined state is not evidence of physical establishment.

A configured route is not a detected connection. An available detector is not a
present jack. A finite float in a RESULT array is not a measurement. Naming this
module for bins would invite exactly the wrong scope; bin classification is one
operation inside the contract, not the contract.

*** THE GOVERNING INVARIANT (ADR-005) ***

    A renderer may transform how authoritative state is displayed, but it may not
    transform uncertainty, absence, or undefined state into asserted measurement,
    connectivity, validity, quality, or advice.

Testable: for any rendered element, name the Teensy-authored field it asserts. If
none exists, the renderer invented it.

*** WHAT THIS MODULE MUST NEVER DO ***

  - Classify from a VALUE. Never compare against -24.0, never call a number
    suspicious. Classification reads METADATA only: NaN-ness, coverage nibbles,
    and which fields the packet carries at all. Inferring the class from the value
    is TODO-29's defect wearing a new label, and it would quietly pre-empt TODO-65.
  - Grade, judge, or advise. The Teensy owns quality, validity and insights
    (ADR-001). This module sorts presentation states; it does not rank them.
  - Manufacture coverage while resampling. See `combine()`.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass

from . import packets, protocol


# =============================================================================
# BIN SEMANTICS
# =============================================================================

class BinClass(enum.Enum):
    """What a renderer is entitled to assert about one frequency location."""

    MEASURED = "MEASURED"
    """A finite value the instrument actually measured. Draw it as data."""

    CLAMPED = "CLAMPED"
    """A real value held at the firmware's saturation rail. The number exists but
    is NOT the measurement. `data_sender.h` is explicit: mark saturation, do not
    plot the rail."""

    UNMEASURED = "UNMEASURED"
    """No measurement exists here. NaN, or no energised source bins (pen-lift).
    Draw NOTHING. Never interpolate across it, never substitute 0."""

    INDETERMINATE = "INDETERMINATE"
    """A value is present, but the authoritative metadata required to classify its
    presentation semantics is absent.

    *** NARROW BY DEFINITION (ADR-005 §6). ***
    This is a statement about MISSING METADATA, never about a suspicious value. It
    is not a general "we aren't sure" bucket and not a fallback for unclassifiable
    input — a NaN is UNMEASURED, a parse failure is an error.

    Its canonical and currently only cause: RESULT carries no per-bin clamp mask
    (TODO-65), so a finite bin cannot be sorted into MEASURED vs CLAMPED. When the
    protocol carries that metadata, these same bins become MEASURED or CLAMPED with
    no change to this contract -- only to the evidence available to it.
    """

    @property
    def is_drawable_as_measurement(self) -> bool:
        """Only MEASURED may reach a curve as data."""
        return self is BinClass.MEASURED


#: Why a location was classified as it was. Metadata provenance, never a value
#: judgement. Carried so a renderer (or a bug report) can say WHICH rule fired.
class Reason(enum.Enum):
    FINITE_WITH_COVERAGE = "finite value, coverage reports it measured"
    NOT_FINITE = "value is NaN or non-finite"
    PEN_LIFT = "coverage valid == 0: no energised source bins"
    SATURATED = "coverage clamped == ratio: every source bin railed"
    NO_CLAMP_METADATA = "packet carries no per-bin clamp mask (TODO-65)"
    NO_SOURCES = "no source location maps here"
    COMBINED = "resolved from several source locations"


@dataclass(frozen=True)
class BinSemantics:
    """One displayable frequency location, classified.

    ``value`` is carried through unchanged even when the class forbids drawing it
    as a measurement — a renderer may still want to report a CLAMPED rail value in
    a readout, and discarding it here would be this module making a presentation
    decision that is not its to make.
    """

    index: int
    value: float
    cls: BinClass
    reason: Reason

    # Provenance under resampling. For a 1:1 classification these are 1/0/0/0.
    source_count: int = 1
    measured_count: int = 0
    clamped_count: int = 0
    unmeasured_count: int = 0
    indeterminate_count: int = 0

    @property
    def coverage(self) -> float:
        """Fraction of contributing source locations that were MEASURED.

        1.0 means fully measured. A renderer may fade, thin or hatch by this, and
        MUST NOT present coverage < 1.0 identically to coverage == 1.0 when the
        difference is visible at all.
        """
        if self.source_count <= 0:
            return 0.0
        return self.measured_count / self.source_count

    @property
    def partial(self) -> bool:
        return self.cls is BinClass.MEASURED and self.measured_count < self.source_count


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


# =============================================================================
# CLASSIFIERS — one per packet type, because their EVIDENCE differs
# =============================================================================

def classify_live(values, coverage) -> tuple[BinSemantics, ...]:
    """Classify LIVE_FRAME bins. Full evidence: per-bin coverage nibbles exist.

    Precedence is deliberate and ordered by what the metadata PROVES, not by
    severity. Pen-lift is checked before saturation: `valid == 0` means no source
    bin was energised, so there was nothing to rail in the first place.
    """
    out: list[BinSemantics] = []
    for i, v in enumerate(values):
        cov = coverage[i] if i < len(coverage) else None

        if cov is not None and cov.pen_lift:
            cls, reason = BinClass.UNMEASURED, Reason.PEN_LIFT
        elif not _finite(v):
            cls, reason = BinClass.UNMEASURED, Reason.NOT_FINITE
        elif cov is not None and cov.saturated:
            cls, reason = BinClass.CLAMPED, Reason.SATURATED
        else:
            cls, reason = BinClass.MEASURED, Reason.FINITE_WITH_COVERAGE

        out.append(BinSemantics(
            index=i, value=v, cls=cls, reason=reason, source_count=1,
            measured_count=1 if cls is BinClass.MEASURED else 0,
            clamped_count=1 if cls is BinClass.CLAMPED else 0,
            unmeasured_count=1 if cls is BinClass.UNMEASURED else 0,
        ))
    return tuple(out)


def classify_result(values) -> tuple[BinSemantics, ...]:
    """Classify RESULT bins. Reduced evidence: there is NO per-bin clamp mask.

    So a finite bin here is INDETERMINATE — not MEASURED. That is not pessimism
    and not a heuristic; it is the honest reading of a packet that does not carry
    the field. See TODO-65.

    *** THE TEMPTATION THIS FUNCTION EXISTS TO REFUSE. ***
    The real 2026-09-27 RESULT's four finite bins all read exactly -24.0 dB, the
    firmware's rail. Comparing against -24.0 would "work" on that fixture and would
    be wrong: it breaks the moment the clamp constant changes, and it cannot tell a
    genuine -24.0 dB measurement from a rail -- which IS the problem. Had those bins
    read -11.3 dB they would be INDETERMINATE too.
    """
    out: list[BinSemantics] = []
    for i, v in enumerate(values):
        if not _finite(v):
            cls, reason = BinClass.UNMEASURED, Reason.NOT_FINITE
        else:
            cls, reason = BinClass.INDETERMINATE, Reason.NO_CLAMP_METADATA
        out.append(BinSemantics(
            index=i, value=v, cls=cls, reason=reason, source_count=1,
            unmeasured_count=1 if cls is BinClass.UNMEASURED else 0,
            indeterminate_count=1 if cls is BinClass.INDETERMINATE else 0,
        ))
    return tuple(out)


def classify_result_with_coverage(values, coverage) -> tuple[BinSemantics, ...]:
    """Forward path for when TODO-65 closes and RESULT carries a clamp mask.

    Present so the renderer contract does not change on that day — only the
    evidence does. Not reachable from today's protocol; `classify_result()` is.
    """
    return classify_live(values, coverage)


# =============================================================================
# RESAMPLING — the rule that keeps a 512-bin array honest on a 48-segment ring
# =============================================================================

def combine(group: list[BinSemantics], *, index: int, value: float) -> BinSemantics:
    """Resolve several source locations into one displayed location.

    *** RESAMPLING MUST NOT MANUFACTURE COVERAGE (ADR-005 §6). ***

    This is not hypothetical. The firmware's own 4:1 decimation already loses a
    distinction: source bins 22-25 are clamped, they land in live bins 5 and 6 as
    `clamped=2, ratio=4`, and because saturation is marked only at
    `clamped == ratio`, a half-clamped group is drawn as DATA rather than a rail
    (TODO-36, 2026-09-30). Both the "4/512 clamped" and "0 of 128 clamped" figures
    are correct; decimation is where the meaning changed. Display-side resampling —
    512 bins onto a 48-segment ring, or onto the waterfall's 96 — has the identical
    hazard, so the rule lives HERE and not in each three.js component.

    Precedence, applied in order:
      1. no sources                         -> UNMEASURED  (nothing maps here)
      2. any source INDETERMINATE           -> INDETERMINATE
      3. every source UNMEASURED            -> UNMEASURED
      4. no MEASURED source, some CLAMPED   -> CLAMPED
      5. otherwise                          -> MEASURED, coverage < 1 recorded

    Rule 2 outranks rule 3: a group containing a present-but-unclassifiable value
    is itself unclassifiable, and must not be reported as simple absence.

    Rule 5 is where coverage is preserved rather than lost. The combined location
    is MEASURED only on the strength of its measured members, and `coverage`
    carries the fraction so a renderer can show partialness instead of silently
    upgrading a sparse group to a confident one.
    """
    n = len(group)
    meas = sum(1 for b in group if b.cls is BinClass.MEASURED)
    clamp = sum(1 for b in group if b.cls is BinClass.CLAMPED)
    unmeas = sum(1 for b in group if b.cls is BinClass.UNMEASURED)
    indet = sum(1 for b in group if b.cls is BinClass.INDETERMINATE)

    if n == 0:
        cls, reason = BinClass.UNMEASURED, Reason.NO_SOURCES
    elif indet:
        cls, reason = BinClass.INDETERMINATE, Reason.NO_CLAMP_METADATA
    elif unmeas == n:
        cls, reason = BinClass.UNMEASURED, Reason.COMBINED
    elif meas == 0 and clamp:
        cls, reason = BinClass.CLAMPED, Reason.COMBINED
    else:
        cls, reason = BinClass.MEASURED, Reason.COMBINED

    return BinSemantics(
        index=index, value=value, cls=cls, reason=reason,
        source_count=n, measured_count=meas, clamped_count=clamp,
        unmeasured_count=unmeas, indeterminate_count=indet,
    )


def resample(bins: tuple[BinSemantics, ...], targets: int,
             *, group_of) -> tuple[BinSemantics, ...]:
    """Map classified source bins onto ``targets`` display locations.

    ``group_of(i) -> int | None`` assigns source bin ``i`` to a target, or drops
    it. The caller owns the frequency mapping (log ring, linear waterfall); this
    function owns only the rule that the mapping cannot invent coverage.

    The representative value of a combined location is the mean of its MEASURED
    members, or NaN when it has none. A mean over clamped or absent members would
    be a fabricated number, so it is not computed.
    """
    buckets: list[list[BinSemantics]] = [[] for _ in range(targets)]
    for i, b in enumerate(bins):
        t = group_of(i)
        if t is not None and 0 <= t < targets:
            buckets[t].append(b)

    out: list[BinSemantics] = []
    for t, grp in enumerate(buckets):
        vals = [b.value for b in grp if b.cls is BinClass.MEASURED]
        value = sum(vals) / len(vals) if vals else float("nan")
        out.append(combine(grp, index=t, value=value))
    return tuple(out)


# =============================================================================
# CENSUS
# =============================================================================

@dataclass(frozen=True)
class Census:
    """Counts by class, for the honest-status readout both renderers show."""

    elements: int
    measured: int
    clamped: int
    unmeasured: int
    indeterminate: int

    @property
    def drawable(self) -> int:
        return self.measured

    def text(self) -> str:
        parts = [f"{self.elements} bins", f"{self.measured} measured"]
        if self.clamped:
            parts.append(f"{self.clamped} clamped")
        if self.indeterminate:
            parts.append(f"{self.indeterminate} indeterminate")
        parts.append(f"{self.unmeasured} unmeasured")
        return " · ".join(parts)


def census(bins) -> Census:
    return Census(
        elements=len(bins),
        measured=sum(1 for b in bins if b.cls is BinClass.MEASURED),
        clamped=sum(1 for b in bins if b.cls is BinClass.CLAMPED),
        unmeasured=sum(1 for b in bins if b.cls is BinClass.UNMEASURED),
        indeterminate=sum(1 for b in bins if b.cls is BinClass.INDETERMINATE),
    )


# =============================================================================
# ESTABLISHMENT — the same principle, away from FFT bins (ADR-005 §5)
# =============================================================================

class Establishment(enum.Enum):
    """How much a piece of state proves about the physical world."""

    ESTABLISHED = "ESTABLISHED"
    """Physically confirmed by an authoritative observation."""

    DEFINED = "DEFINED"
    """Configured, selected or defined. Says NOTHING about physical connection.
    `route_valid` lives here: the repo router contract states it means the return
    routing configuration is defined, and that its historical name is not grounds
    to reintroduce presence detection."""

    ABSENT = "ABSENT"
    """Authoritatively observed to be absent."""

    UNOBSERVABLE = "UNOBSERVABLE"
    """No detector is fitted, so presence is unknowable. The UI says
    "no detector", never "not present" (TODO-58, ADR-002/003)."""

    @property
    def asserts_connection(self) -> bool:
        return self is Establishment.ESTABLISHED


def route_establishment(return_source) -> Establishment:
    """A return source is ALWAYS selected under ADR-004, so routing is always
    DEFINED and never ESTABLISHED. There is no path to ESTABLISHED here: nothing
    in the packet observes the far end of the cable."""
    if return_source is None:
        return Establishment.UNOBSERVABLE
    return Establishment.DEFINED


def jack_establishment(jack, *, presence_bits, available_bits) -> Establishment:
    """Presence is informational only (ADR-003 §, ADR-004 §3). Availability is
    checked FIRST: reading a presence bit from an unfitted detector is TODO-58's
    defect, and 'not present' is the wrong answer to 'is there a detector'."""
    if not (int(available_bits) & int(jack)):
        return Establishment.UNOBSERVABLE
    return (Establishment.ESTABLISHED if int(presence_bits) & int(jack)
            else Establishment.ABSENT)
