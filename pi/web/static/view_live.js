// LIVE — what the instrument is doing right now.
//
// *** THE SPECTRUM IS DELIBERATELY NOT HERE YET. ***
//
// fft_source[] and fft_return[] are decoded by analyzer_link and are NOT on
// /api/frame, because they carry no coverage nibbles — the coverage array
// belongs to tf_db[]. So there is no rule yet for what UNMEASURED means in a
// magnitude spectrum, and inventing one inside a renderer is precisely the
// drift ADR-005 §4 exists to stop. That rule belongs in
// presentation_semantics.py with its own tests and its own review.
//
// Until then this view shows only scalars the Teensy authored and the transport
// already carries, and says plainly what is missing and why. An empty axis
// labelled "spectrum" would be worse than no axis: it would imply the
// instrument measured a flat response.

import { card, rows, meter, num, text, gap } from "./ui.js";

const PENDING_SPECTRUM = `
  <p class="note"><b>Source / return spectrum is not shown yet.</b> The
  instrument measures it and the Pi decodes it, but the transport does not carry
  it: those arrays have no per-bin coverage, so there is no agreed rule for which
  parts of them may be drawn as data.</p>
  <p class="note">Drawing them without that rule would mean the renderer deciding
  what an unmeasured frequency looks like — the one thing it is not allowed to
  decide. The rule is a reviewed change to the shared contract, not a change
  here.</p>`;

export function createLiveView(root) {
  return {
    update(f) {
      if (f.kind === "unknown") {
        root.innerHTML =
          card("No frame", `<p class="note">${text(f.reason)}</p>`) +
          card("Pending", PENDING_SPECTRUM);
        return;
      }

      if (f.kind !== "live") {
        // A RESULT is not a live frame and must not be dressed as one. Peak
        // levels, state and confidence are LIVE_FRAME fields; a RESULT simply
        // does not contain them, and borrowing the last live value would be
        // presenting stale state as current.
        root.innerHTML =
          card("Levels", `
            <p class="note"><b>No live frame.</b> The transport is currently
            carrying a captured RESULT, which does not contain peak levels,
            measurement state or live confidence.</p>
            <p class="note">These appear when the instrument is streaming
            LIVE_FRAME packets. See <b>LAB</b> for the captured result.</p>`) +
          card("Pending", PENDING_SPECTRUM);
        return;
      }

      const a = f.authority || {};
      root.innerHTML =
        card("Levels", [
          meter("SOURCE", a.peak_source_dbfs, "src", "no live frame"),
          meter("RETURN", a.peak_return_dbfs, "ret", "no live frame"),
        ].join("")) +

        card("State", rows([
          ["measurement state", text(a.measurement_state)],
          ["transfer-function confidence",
            typeof a.tf_confidence === "number"
              ? num(a.tf_confidence * 100, { digits: 0, unit: "%" })
              : gap("not reported")],
          ["bins at the clamp rail",
            num(a.tf_clamped_count, { digits: 0, why: "not reported" })],
        ])) +

        card("Coverage", rows([
          ["instrument", text(f.census_source?.text)],
          ["ring (presentation)", text(f.census_bands?.text)],
        ]) + `<p class="note">Two figures, deliberately. The second is this
          interface reducing ${text(f.source_bins)} bins onto
          ${text(f.bands)} bands; it is <b>not</b> the instrument's own
          coverage.</p>`) +

        card("Pending", PENDING_SPECTRUM);
    },
  };
}
