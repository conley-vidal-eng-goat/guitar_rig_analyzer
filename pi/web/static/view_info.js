// INFO — link health, build identity, and an honest statement of what this
// interface cannot do.
//
// The last card is the important one. ADR-005's governing invariant is usually
// discussed as a rule about charts, but it applies just as much to controls: a
// button that looks like it arms a capture, on a link that physically cannot
// carry the request, asserts a capability that does not exist. The Tk renderer
// set the precedent — show the limitation, do not hide it behind an absence of
// buttons — and this says it in words rather than leaving the operator to infer
// it from a screen with no controls on it.

import { card, rows, num, text, gap } from "./ui.js";

export function createInfoView(root) {
  return {
    update(f) {
      const link = f.link || null;
      const a = f.authority || {};

      root.innerHTML =
        card("Link", rows([
          ["session", link ? text(link.session, { why: "unknown" }) : gap("no link state")],
          ["freshness", link
            ? (link.stale ? `<span class="warn">STALE</span>`
                          : `<span class="good">UP</span>`)
            : gap("no link state")],
          ["frames received", link ? num(link.frames_in, { digits: 0 }) : gap("—")],
          ["decode errors", link
            ? (link.decode_errors
                ? `<span class="warn">${text(link.decode_errors)}</span>`
                : `<span class="good">0</span>`)
            : gap("—")],
          ["receiver state", link ? text(link.state) : gap("—")],
        ])) +

        card("Frame", rows([
          ["kind", text(f.kind)],
          ["instrument bins", num(f.source_bins, { digits: 0, why: "no frame" })],
          ["presentation bands", num(f.bands, { digits: 0, why: "no frame" })],
          ["firmware", text(a.firmware_version, { why: "carried on RESULT only" })],
        ])) +

        card("What this interface cannot do", `
          <p class="note"><b>This is a display, not a control surface.</b> The
          link from the Pi to the instrument does not exist — the receiver reads
          bytes and has no way to send any. Nothing on any screen arms a capture,
          changes routing, starts a generator or triggers calibration, and
          nothing here should be read as implying otherwise.</p>
          <p class="note"><b>The instrument decides what the measurements mean.</b>
          Validity, quality, calibration state and advisories are authored on the
          Teensy and printed here unchanged. This interface performs geometry,
          colour and layout; it does not grade, average or interpret.</p>
          <p class="note"><b>Absence is shown as absence.</b> A frequency the
          instrument did not measure is drawn as nothing at all — never as a
          zero, never bridged by a line to its neighbours.</p>`);
    },
  };
}
