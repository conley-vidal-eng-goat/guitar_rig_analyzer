// Shell: one poll, one visible view, a persistent tab bar.
//
// *** NO MEASUREMENT PATH EXISTS IN THIS FILE OR ANYWHERE UNDER static/. ***
// There is no getUserMedia, no AudioContext, no AnalyserNode, no FFT and no
// arithmetic on measurement values beyond turning a dB into a bar height. The
// only input is /api/frame, which carries bands the Pi has already classified.
//
// *** THIS FILE OWNS THE ONLY NETWORK CALL IN THE CLIENT. ***
// Views receive the decoded frame as an argument and never fetch. One data
// source is what makes "the browser cannot classify" checkable rather than
// merely intended, and test_web_shell.py pins it.

import { createToneView } from "./view_tone.js";
import { createLiveView } from "./view_live.js";
import { createLabView } from "./view_lab.js";
import { createInfoView } from "./view_info.js";
import { esc } from "./ui.js";

const TABS = ["live", "tone", "lab", "info"];
// 200 ms, not 500. Measured on the Pi 2026-10-13 (journal (12)): the transport
// answers /api/frame in 11.1 ms mean / 15.3 ms p90 and sustains 9 req/s with the
// link unperturbed, while the whole kiosk used 11.7% of one core. The 500 ms this
// used to be meant LIVE refreshed twice a second against the Tk UI's twenty, and
// that difference — not any slow code — is what "the web UI feels slower" was.
// 5 Hz costs about 5.5% of one core. It is an intermediate target: if it still
// reads as sluggish, lower it again rather than assuming something is wrong.
const POLL_MS = 200;

const host = (name) => document.querySelector(`.view[data-view="${name}"]`);

const views = {
  live: createLiveView(host("live")),
  tone: createToneView(host("tone")),
  lab: createLabView(host("lab")),
  info: createInfoView(host("info")),
};

const linkDot = document.getElementById("link-dot");
const kindPill = document.getElementById("kind-pill");
const statusText = document.getElementById("status-text");
const statusDetail = document.getElementById("status-detail");

let active = "live";
let frame = null;

// --- navigation --------------------------------------------------------------

function select(name) {
  if (!TABS.includes(name)) return;
  active = name;

  for (const t of TABS) {
    const shown = t === name;
    host(t).hidden = !shown;
    document.querySelector(`.tab[data-tab="${t}"]`)
      .setAttribute("aria-selected", String(shown));

    // An inactive view must not hold the GPU or run a timer. TONE's orbit is
    // the only animated one today, but the contract applies to all of them so
    // a later animated view cannot quietly keep rendering behind another tab.
    const v = views[t];
    if (shown) v.activate?.();
    else v.deactivate?.();
  }

  // Deliver the latest frame immediately: a tab that waits up to POLL_MS to
  // show anything reads as a broken tap on a touchscreen.
  if (frame) views[name].update?.(frame);
}

for (const btn of document.querySelectorAll(".tab")) {
  // `click` is correct here and `touchstart` is not: click is delivered for
  // touch, mouse and keyboard alike, and it does not fire when a finger lands
  // on a tab and then slides off, which is a cancelled tap and not a choice.
  btn.addEventListener("click", () => select(btn.dataset.tab));
}

// --- status strip ------------------------------------------------------------

function renderStatus(f) {
  const link = f.link || null;
  const stale = link ? link.stale : null;

  linkDot.className = "dot " + (!link ? "down" : stale ? "stale" : "up");
  kindPill.textContent = f.kind === "unknown" ? "no frame" : f.kind;
  kindPill.className = "pill " + (f.kind === "live" ? "live"
    : f.kind === "result" ? "result" : "none");

  if (f.kind === "unknown") {
    statusText.textContent = f.reason;
  } else {
    const a = f.authority || {};
    statusText.textContent = f.kind === "live"
      ? `state ${a.measurement_state}`
      : `quality ${a.result_quality}`;
  }

  const bits = [];
  if (link) {
    bits.push(`session ${link.session ?? "UNKNOWN"}`);
    bits.push(stale ? "LINK STALE" : "LINK UP");
    bits.push(`${link.frames_in} frames`);
    if (link.decode_errors) bits.push(`${link.decode_errors} decode errors`);
  } else {
    bits.push("no link state");
  }
  statusDetail.textContent = bits.join("  ·  ");
}

// --- poll --------------------------------------------------------------------

async function poll() {
  try {
    const f = await (await fetch("/api/frame", { cache: "no-store" })).json();
    frame = f;
    renderStatus(f);
    views[active].update?.(f);
    window.__frame = f;                     // for the headless screenshot check
  } catch (e) {
    linkDot.className = "dot down";
    kindPill.textContent = "no frame";
    kindPill.className = "pill none";
    statusText.textContent = `transport error: ${e.message}`;
    statusDetail.textContent = "";
  }
}

// Polling continues while the page is hidden only if something needs it; nothing
// does, so it stops. The Pi is an appliance and a background tab that keeps
// asking is pure heat.
let timer = 0;
function startPolling() {
  if (!timer) timer = setInterval(poll, POLL_MS);
}
function stopPolling() {
  clearInterval(timer);
  timer = 0;
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopPolling();
    views[active].deactivate?.();
  } else {
    views[active].activate?.();
    poll();
    startPolling();
  }
});

select(active);
poll();
startPolling();

export { TABS };
