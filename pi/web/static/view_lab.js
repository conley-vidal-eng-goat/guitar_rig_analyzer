// LAB — the captured measurement, with its provenance and its gaps.
//
// Every value here is Teensy-authored and printed verbatim. Nothing is graded,
// re-graded, averaged or second-guessed (ADR-001, ADR-005 §3).
//
// The "not carried yet" card is not an apology. The protocol already carries
// coherence[], tf_cal_phase_rad[], group_delay_ms[], insights[] and the full
// capture metadata; /api/frame does not forward them yet. Listing them where an
// operator will look is how the gap stays visible instead of being discovered
// later as an apparent absence of measurement.

import { card, rows, num, text, flag, gap } from "./ui.js";

const NOT_CARRIED = [
  ["coherence per bin", "coherence[]"],
  ["phase", "tf_cal_phase_rad[]"],
  ["group delay", "group_delay_ms[]"],
  ["insights (Teensy-authored)", "insights[]"],
  ["estimator / stimulus / window / FFT size", "capture settings"],
  ["clip counts, line-in level", "clip_source_count, clip_return_count"],
  ["calibration provenance, warnings", "calibration_provenance"],
  ["capture timestamps and block range", "timestamp_ms, capture_*_block"],
];

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
          ["calibration", flag(a.calibration_applied, "applied", "NOT calibrated")],
          ["firmware", text(a.firmware_version)],
        ])) +

        card("Coverage", rows([
          ["instrument", text(f.census_source?.text)],
          ["ring (presentation)", text(f.census_bands?.text)],
        ]) + `<p class="note">A finite value in a RESULT is <b>not</b> evidence
          that the bin was measured: the packet carries no per-bin clamp mask, so
          nothing distinguishes a measured value from the firmware's saturation
          rail. Those bins are reported as <i>indeterminate</i> — a statement
          about missing metadata, never about how the number looks.</p>`) +

        card("Not carried by this transport yet", rows(
          NOT_CARRIED.map(([label, field]) => [label, gap(field)])
        ) + `<p class="note">The instrument measures these and the Pi decodes
          them. They are absent from this screen because
          <b>/api/frame does not forward them yet</b>, not because they were not
          measured.</p>`);
    },
  };
}
