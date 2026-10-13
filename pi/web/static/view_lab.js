// LAB — the captured measurement, with its provenance and its gaps.
//
// Every value here is Teensy-authored and printed verbatim. Nothing is graded,
// re-graded, averaged or second-guessed (ADR-001, ADR-005 §3).
//
// *** THIS FILE IS A PRINTER. IT HAS NO OPINIONS. ***
//
// It contains no threshold, no comparison against a limit, no string that
// describes a measurement, and no branch whose condition is a measured value.
// Severity comes from `severity`, never from how large `magnitude` is; the
// explanation of a finding is the Teensy's `detail` sentence and never a
// sentence assembled here. Every branch below tests PRESENCE (is the field
// there?) or CLASS (what did the instrument call it?) — never magnitude.
//
// The one thing this file decides is layout. That is ADR-005 §7's permitted
// transform and the whole of its licence.
//
// *** WHY THE "NOT CARRIED" CARD SURVIVES, SHORTER. ***
//
// It listed eight gaps. Six are closed by the transport commit that precedes
// this one. The three per-bin arrays remain, and `action[]` / `data_quality`
// have been added to it — those two are a FIRMWARE gap, not a transport one
// (data_sender.cpp never writes them and the 138-byte wire entry has no room),
// which the card now says explicitly. Listing a gap where an operator will look
// is how it stays visible instead of being discovered later as an apparent
// absence of measurement.

import { card, rows, num, text, flag, gap, esc } from "./ui.js";

// Still absent, with the reason each one is absent. The two categories are
// different and are labelled differently: a transport gap is Pi work, a
// firmware gap needs a protocol version and a Teensy change.
const NOT_CARRIED = [
  ["coherence per bin", "coherence[] — needs a classification rule first", "transport"],
  ["phase per bin", "tf_cal_phase_rad[]", "transport"],
  ["group delay per bin", "group_delay_ms[]", "transport"],
  ["suggested action per insight", "Insight.action[] — never written by the sender", "firmware"],
  ["per-insight source quality", "Insight.data_quality — never written by the sender", "firmware"],
];

// Severity and mode are rendered with a GLYPH and a WORD as well as a colour.
// The design brief is explicit that colour alone may never carry severity, and
// the panel is read at arm's length where hue is the first thing to go.
const SEVERITY = {
  ALERT:   { glyph: "▲", cls: "sev-alert",   word: "ALERT" },
  WARNING: { glyph: "◆", cls: "sev-warning", word: "WARNING" },
  INFO:    { glyph: "●", cls: "sev-info",    word: "INFO" },
};

const MODE = {
  MEASUREMENT: { cls: "mode-measurement", word: "MEASUREMENT",
                 hint: "a measured fact" },
  ADVISORY:    { cls: "mode-advisory",    word: "ADVISORY",
                 hint: "interpretation" },
};

/** One insight. Every string in it came off the wire and is escaped. */
function insightCard(ins) {
  // An unrecognised enum name is NOT coerced to a default. A renderer that
  // silently showed an unknown severity as INFO would downgrade a warning from
  // a newer firmware into a pleasantry.
  const sev = SEVERITY[ins.severity];
  const mode = MODE[ins.mode];

  const sevHtml = sev
    ? `<span class="badge ${sev.cls}"><span class="badge-glyph"
         aria-hidden="true">${sev.glyph}</span>${esc(sev.word)}</span>`
    : `<span class="badge sev-unknown">${gap(`unknown severity: ${ins.severity}`)}</span>`;

  const modeHtml = mode
    ? `<span class="badge ${mode.cls}">${esc(mode.word)}</span>`
    : `<span class="badge sev-unknown">${gap(`unknown mode: ${ins.mode}`)}</span>`;

  // Shown only when the instrument attached one. `frequency_hz: null` is the
  // firmware's broadband sentinel, decoded at the transport — a broadband
  // finding gets the word "broadband", never "0 Hz".
  const scope = ins.frequency_hz === null || ins.frequency_hz === undefined
    ? `<span class="meta-broadband">broadband</span>`
    : `<span class="meta-freq">${num(ins.frequency_hz, { digits: 0, unit: "Hz" })}</span>`;

  // *** NO UNIT IS APPENDED. *** The struct field is called `magnitude_db`,
  // but insights_engine.cpp:170 passes `mean_coherence` — a dimensionless
  // ratio — into that slot for the quality insight. The unit is a function of
  // which insight produced the value and is NOT on the wire, so the number is
  // printed bare and the unit is left to the Teensy's own detail sentence.
  const magnitude = ins.magnitude === null || ins.magnitude === undefined
    ? ""
    : `<span class="meta-mag">${num(ins.magnitude, { digits: 2 })}
         <span class="meta-unitless">unit not transmitted</span></span>`;

  return `<article class="insight ${sev ? sev.cls : "sev-unknown"}">
    <div class="insight-badges">${sevHtml}${modeHtml}</div>
    <h3 class="insight-title">${esc(ins.title)}</h3>
    <p class="insight-detail">${esc(ins.detail)}</p>
    <div class="insight-meta">${scope}${magnitude}</div>
  </article>`;
}

function insightsSection(insights) {
  // *** EMPTY IS NOT MISSING, AND THE TWO SAY DIFFERENT THINGS. ***
  //
  // `insight_count` is an explicit wire byte and packets.py validates it, so a
  // decoded RESULT with zero insights means the instrument authored none — a
  // statement it is entitled to make. A payload with no `insights` key at all
  // is a transport that did not carry the field, which is not a statement
  // about the measurement and must never be shown as one.
  if (!Array.isArray(insights)) {
    return card("Insights", `<p class="note">${gap(
      "not carried by this transport")}</p>
      <p class="note">The instrument may or may not have authored insights for
      this result. <b>This screen cannot tell</b>, and does not guess.</p>`);
  }

  if (insights.length === 0) {
    return card("Insights", `<p class="note"><b>None authored.</b> The
      instrument completed this result and raised no insight about it. This is
      a statement from the measurement authority, not a gap in the display —
      the packet carried an explicit count of zero.</p>`);
  }

  return card(`Insights — ${insights.length} authored by the instrument`,
    insights.map(insightCard).join("") +
    `<p class="note"><b>Written on the Teensy, printed here unchanged.</b>
     Severity and mode are the instrument's own grading. This interface does not
     rank them, rewrite them, or author any of its own
     (ADR-001, ADR-005 §3).</p>
     <p class="note">Text is cut at 64 bytes by the sender, so a detail may end
     mid-word. It is shown as received rather than completed here.</p>`);
}

function captureSection(c) {
  if (!c) {
    return card("Capture conditions", `<p class="note">${gap(
      "not carried by this transport")}</p>`);
  }
  // Units appear ONLY where the protocol defines one. `fft_size` is a count of
  // points, `line_in_level` is an SGTL5000 index, the blocks are counter
  // values and the channels are indices — none of them is a physical quantity,
  // so none of them gets a suffix.
  return card("Capture conditions", rows([
    ["estimator", text(c.estimator)],
    ["stimulus", text(c.stimulus)],
    ["FFT mode", text(c.fft_mode)],
    ["FFT size", num(c.fft_size, { digits: 0 })],
    ["window", text(c.window_function)],
    ["averages", num(c.n_averages_completed, { digits: 0, why: "see Result" })],
    ["timestamp", num(c.timestamp_ms, { digits: 0, unit: "ms" })],
    ["block range", `${text(c.capture_start_block)} – ${text(c.capture_end_block)}`],
    ["source channel", num(c.source_node_ch, { digits: 0 })],
    ["return channel", num(c.return_node_ch, { digits: 0 })],
    ["line-in level", num(c.line_in_level, { digits: 0 })],
    ["generator", flag(c.generator_active, "active", "not active")],
  ]) + `<p class="note"><b>FFT size is not the array length.</b> It is the
    transform length actually used; the spectra are always on the canonical
    512-bin grid regardless.</p>
    <p class="note"><b>Line-in level is recorded so a comparison stays honest.</b>
    Two captures taken at different input gains will differ for that reason
    alone, and a difference read as a rig difference would be wrong.</p>`);
}

function clippingSection(c) {
  if (!c) return "";
  // Clipping is its own card because it is the one condition that invalidates
  // a result while every number in it still looks plausible.
  const detected = c.clip_detected;
  return card("Clipping", rows([
    ["detected during capture", flag(detected, "YES", "no")],
    ["source clip count", num(c.clip_source_count, { digits: 0 })],
    ["return clip count", num(c.clip_return_count, { digits: 0 })],
  ]) + (detected
    ? `<p class="note"><b>The instrument reported clipping.</b> Values in this
       result were computed from samples that hit the converter's rail.</p>`
    : `<p class="note">The instrument reported no clipping. That is a statement
       about the converter, not a judgement about whether the stimulus was
       adequate.</p>`));
}

function calibrationSection(cal, applied) {
  if (!cal) {
    return card("Calibration", `<p class="note">${gap(
      "not carried by this transport")}</p>`);
  }
  const warnings = Array.isArray(cal.warnings) ? cal.warnings : null;
  const missing = warnings ? warnings.includes("CALIBRATION_MISSING") : false;

  const warnHtml = !warnings
    ? gap("not carried")
    : warnings.length === 0
      ? `<span class="good">none</span>`
      : warnings.map((w) => `<span class="warn-chip">${esc(w)}</span>`).join("");

  return card("Calibration", rows([
    // `type` names the SLOT, not a calibration that ran. Shown next to
    // `applied` because either alone is misleading.
    ["type (slot)", text(cal.type)],
    ["applied to this result", flag(applied, "yes", "NO")],
    ["warnings", warnHtml],
    ["provenance", text(cal.provenance, { why: "not reported" })],
  ]) + (missing
    ? `<p class="note"><b>CALIBRATION_MISSING — no calibration was loaded.</b>
       The transfer function in this result is raw hardware response: the
       instrument's own channel asymmetry is still in it and has not been
       removed. <b>The type above names an empty slot, not a procedure that
       ran.</b></p>`
    : "") + (applied
      ? ""
      : `<p class="note">Nothing in this result has been corrected against a
         reference. No accuracy claim follows from it.</p>`));
}

export function createLabView(root) {
  return {
    update(f) {
      if (f.kind !== "result") {
        root.innerHTML = card("No captured result", `
          <p class="note"><b>Nothing to show.</b> ${text(f.kind === "unknown"
            ? f.reason : "The transport is carrying live frames, not a captured RESULT.")}</p>
          <p class="note">A result appears here when the instrument completes a
          capture.</p>`);
        return;
      }

      const a = f.authority || {};
      const quality = text(a.result_quality);
      const qCls = a.result_quality === "GOOD" ? "good"
        : a.result_quality === "POOR" ? "warn" : "";

      root.innerHTML =
        card("Result", rows([
          ["valid", flag(a.result_valid, "yes", "no")],
          ["quality", `<span class="${qCls}">${quality}</span>`],
          ["averages completed", num(a.n_averages_completed, { digits: 0 })],
          ["mean coherence", num(a.mean_coherence, { digits: 3 })],
          // The instrument's own count of how much of the analysis band it
          // could establish. Printed as the fraction it is, never recomputed
          // here from the ring census — they answer different questions.
          ["valid bins", typeof a.valid_bin_fraction === "number"
            ? num(a.valid_bin_fraction * 100, { digits: 1, unit: "%" })
            : gap("not reported")],
          ["calibration", flag(a.calibration_applied, "applied", "NOT calibrated")],
          ["firmware", text(a.firmware_version)],
        ]) + `<p class="note"><b>Every value on this screen is the
          instrument's.</b> Quality, validity and coverage are graded on the
          Teensy; this interface lays them out and does not assess them.</p>`) +

        insightsSection(f.insights) +

        captureSection(f.capture
          ? { ...f.capture, n_averages_completed: a.n_averages_completed }
          : null) +

        clippingSection(f.capture) +

        calibrationSection(f.calibration, a.calibration_applied) +

        card("Coverage", rows([
          ["instrument", text(f.census_source?.text)],
          ["ring (presentation)", text(f.census_bands?.text)],
        ]) + `<p class="note">A finite value in a RESULT is <b>not</b> evidence
          that the bin was measured: the packet carries no per-bin clamp mask, so
          nothing distinguishes a measured value from the firmware's saturation
          rail. Those bins are reported as <i>indeterminate</i> — a statement
          about missing metadata, never about how the number looks.</p>`) +

        card("Still not carried", rows(
          NOT_CARRIED.map(([label, field, kind]) => [
            label,
            `${gap(field)}<span class="gap-kind gap-${kind}">${esc(kind)}</span>`,
          ])
        ) + `<p class="note"><b>Two different gaps.</b> A <i>transport</i> gap is
          decoded on the Pi and not yet forwarded — Pi work. A <i>firmware</i>
          gap is never written by the sender at all: the insight entry on the
          wire is 138 bytes and all 138 are spent on the fields above it, so
          <b>action and data_quality have no room in the current protocol</b> and
          need a firmware change and a version bump, not a renderer change.</p>
          <p class="note">In every case the instrument measured more than this
          screen shows. The absence is in the link, not in the measurement.</p>`);
    },
  };
}
