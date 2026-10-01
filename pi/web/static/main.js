// Wiring only: poll the Pi receiver, hand already-classified bands to the scene.
//
// *** NO MEASUREMENT PATH EXISTS IN THIS FILE OR ANYWHERE UNDER static/. ***
// There is no getUserMedia, no AudioContext, no AnalyserNode, no FFT and no
// arithmetic on measurement values beyond turning a dB into a bar height. The
// only input is /api/frame, which carries bands the Pi has already classified.

import { createFingerprint } from "./fingerprint_split.js";

const scene = createFingerprint(document.getElementById("stage"));
const censusEl = document.getElementById("census");
const authorityEl = document.getElementById("authority");

function renderAuthority(f) {
  // Teensy-authored values, printed verbatim. Nothing here is computed.
  const a = f.authority || {};
  const bits = [];
  if (f.kind === "result") {
    bits.push(`quality ${a.result_quality}`,
              `${a.n_averages_completed} averages`,
              `coherence ${Number(a.mean_coherence).toFixed(3)}`,
              a.calibration_applied ? "calibrated" : "NOT calibrated");
  } else if (f.kind === "live") {
    bits.push(`state ${a.measurement_state}`,
              `src ${Number(a.peak_source_dbfs).toFixed(1)} dBFS`,
              `ret ${Number(a.peak_return_dbfs).toFixed(1)} dBFS`,
              `confidence ${(Number(a.tf_confidence) * 100).toFixed(0)}%`);
  }
  if (f.link) bits.push(`session ${f.link.session ?? "UNKNOWN"}`,
                        f.link.stale ? "LINK STALE" : "LINK UP");
  authorityEl.textContent = bits.join("  ·  ");
}

async function poll() {
  try {
    const f = await (await fetch("/api/frame", { cache: "no-store" })).json();
    scene.setSegments(f.segments);
    if (f.kind === "unknown") {
      censusEl.textContent = f.reason;
      authorityEl.textContent = "";
    } else {
      // Both censuses are shown: the reduction to 48 bands is a presentation
      // step and must not be mistaken for the instrument's own coverage.
      censusEl.textContent =
        `source ${f.census_source.text}   →   ring ${f.census_bands.text}`;
      renderAuthority(f);
    }
    window.__frame = f;                       // for the headless screenshot check
  } catch (e) {
    censusEl.textContent = `transport error: ${e.message}`;
  }
}

poll();
setInterval(poll, 500);
