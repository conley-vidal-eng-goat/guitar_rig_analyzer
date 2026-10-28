"""Compare the states of a Headrush A/B run and say what it is allowed to claim.

    python3 pi/tools/ab_compare.py RUNDIR [--a A1 A2] [--b B1 B2]

RUNDIR holds one LABEL.jsonl per state, written by ab_capture.sh. The default
run is A1 -> B1 -> A2 -> B2: the setting is changed, changed back, and changed
again. Writes RUNDIR/report.md and RUNDIR/delta.svg and prints the verdict.

What is compared is the Teensy's own live transfer function (the 48 classified
bands in /api/frame). Nothing here recomputes it. The input spectrum is used for
one thing only: checking that the input stayed the same while the rig changed.

The run is INVALID, and no difference is claimed, if any of these fail:
  * every frame comes from one Teensy session (a restart breaks the pair);
  * no frame is stale and decode_errors never rises;
  * no frame flags clipping on either channel.

A band counts as changed only if it is MEASURED in at least 90% of the frames of
every state, the change B - A has the same sign in both cycles, and its size is
more than 3x the repeat difference (A2 vs A1, B2 vs B1) and more than 1 dB.
"""

import argparse
import json
import math
import pathlib
import statistics

MEASURED = "MEASURED"
COVER = 0.90          # fraction of frames a band must be MEASURED in
MIN_DB = 1.0          # smallest change worth calling a change
REPEAT_X = 3.0        # change must exceed this multiple of the repeat difference
SRC_GATE = 0.001      # firmware TF_SOURCE_GATE, linear magnitude


def load(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def db(x):
    return 20 * math.log10(x) if x and x > 0 else None


class State:
    def __init__(self, label, frames):
        self.label = label
        self.all = frames
        self.live = [f for f in frames if f.get("kind") == "live"]
        self.results = [f for f in frames if f.get("kind") == "result"]

    def bands(self):
        """band index -> (hz, mean dB, sd dB, n) for bands measured in >= COVER."""
        out = {}
        n = len(self.live)
        if not n:
            return out
        for i in range(len(self.live[0]["segments"])):
            vals = [f["segments"][i]["value"] for f in self.live
                    if f["segments"][i]["cls"] == MEASURED
                    and f["segments"][i]["value"] is not None]
            if len(vals) >= COVER * n:
                sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
                out[i] = (self.live[0]["segments"][i]["hz"],
                          statistics.fmean(vals), sd, len(vals))
        return out

    def src_db(self):
        """input spectrum per bin, mean dB over frames, energised bins only."""
        out = {}
        for k in range(len(self.live[0]["spectra"]["src"])):
            vals = [f["spectra"]["src"][k]["value"] for f in self.live
                    if f["spectra"]["src"][k]["cls"] == MEASURED]
            if vals and statistics.fmean(vals) > SRC_GATE:
                out[k] = db(statistics.fmean(vals))
        return out

    def peak(self, key):
        v = [f["authority"][key] for f in self.live
             if f["authority"].get(key) is not None]
        return max(v) if v else None


def validity(states):
    problems = []
    sessions = {f["link"]["session"] for s in states for f in s.all}
    if len(sessions) != 1:
        problems.append(f"frames come from {len(sessions)} Teensy sessions "
                        f"{sorted(sessions)}; a restart breaks the comparison")
    for s in states:
        if not s.live:
            problems.append(f"{s.label}: no live frames")
            continue
        stale = sum(1 for f in s.all if f["link"]["stale"])
        if stale:
            problems.append(f"{s.label}: {stale} stale frames")
        errs = [f["link"]["decode_errors"] for f in s.all]
        if errs and errs[-1] != errs[0]:
            problems.append(f"{s.label}: decode_errors rose {errs[0]} -> {errs[-1]}")
        clipped = sum(1 for f in s.live
                      if f["authority"]["source_clip"] or f["authority"]["return_clip"])
        if clipped:
            problems.append(f"{s.label}: {clipped} of {len(s.live)} frames clipped")
    errs_all = [f["link"]["decode_errors"] for s in states for f in s.all]
    if errs_all and max(errs_all) != min(errs_all):
        problems.append("decode_errors changed during the run")
    return problems


def compare(a_states, b_states):
    """One row per band measured in every state."""
    maps = [s.bands() for s in a_states + b_states]
    common = sorted(set.intersection(*(set(m) for m in maps)))
    a1, a2, b1, b2 = maps
    rows = []
    for i in common:
        d1 = b1[i][1] - a1[i][1]
        d2 = b2[i][1] - a2[i][1]
        rep = max(abs(a2[i][1] - a1[i][1]), abs(b2[i][1] - b1[i][1]))
        delta = (d1 + d2) / 2
        changed = (d1 * d2 > 0 and min(abs(d1), abs(d2)) > max(REPEAT_X * rep, MIN_DB))
        rows.append(dict(i=i, hz=a1[i][0], a=(a1[i][1] + a2[i][1]) / 2,
                         b=(b1[i][1] + b2[i][1]) / 2, d1=d1, d2=d2,
                         delta=delta, repeat=rep, changed=changed))
    return rows


def source_drift(a_states, b_states):
    sa = [s.src_db() for s in a_states]
    sb = [s.src_db() for s in b_states]
    common = set.intersection(*(set(m) for m in sa + sb))
    if not common:
        return None
    diffs = [abs(statistics.fmean([m[k] for m in sb]) - statistics.fmean([m[k] for m in sa]))
             for k in common]
    return len(common), statistics.median(diffs), max(diffs)


def svg(rows, path):
    if not rows:
        return
    W, H, L, R, T, B = 760, 360, 60, 20, 20, 50
    fmin, fmax = min(r["hz"] for r in rows), max(r["hz"] for r in rows)
    lo = min(min(r["delta"] - r["repeat"] for r in rows), -3)
    hi = max(max(r["delta"] + r["repeat"] for r in rows), 3)

    def x(f):
        return L + (math.log10(f) - math.log10(fmin)) / (math.log10(fmax) - math.log10(fmin) or 1) * (W - L - R)

    def y(v):
        return T + (hi - v) / (hi - lo) * (H - T - B)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui,sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>']
    for v in range(math.ceil(lo), math.floor(hi) + 1):
        if v % 3 == 0:
            out.append(f'<line x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                       f'stroke="{"#888" if v == 0 else "#e5e5e5"}"/>')
            out.append(f'<text x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end" fill="#555">{v:+d}</text>')
    for f in (100, 200, 500, 1000, 2000, 5000, 10000, 20000):
        if fmin <= f <= fmax:
            lab = f"{f//1000}k" if f >= 1000 else str(f)
            out.append(f'<line x1="{x(f):.1f}" x2="{x(f):.1f}" y1="{T}" y2="{H-B}" stroke="#eee"/>')
            out.append(f'<text x="{x(f):.1f}" y="{H-B+16}" text-anchor="middle" fill="#555">{lab}</text>')
    for r in rows:
        out.append(f'<line x1="{x(r["hz"]):.1f}" x2="{x(r["hz"]):.1f}" '
                   f'y1="{y(r["delta"]-r["repeat"]):.1f}" y2="{y(r["delta"]+r["repeat"]):.1f}" '
                   f'stroke="#999" stroke-width="2"/>')
    pts = " ".join(f'{x(r["hz"]):.1f},{y(r["delta"]):.1f}' for r in rows)
    out.append(f'<polyline points="{pts}" fill="none" stroke="#1f6feb" stroke-width="2"/>')
    for r in rows:
        c = "#1f6feb" if r["changed"] else "#fff"
        out.append(f'<circle cx="{x(r["hz"]):.1f}" cy="{y(r["delta"]):.1f}" r="4" '
                   f'fill="{c}" stroke="#1f6feb" stroke-width="1.5"/>')
    out.append(f'<text x="{(L+W-R)/2}" y="{H-12}" text-anchor="middle" fill="#333">'
               f'frequency (Hz, log)</text>')
    out.append(f'<text x="14" y="{(T+H-B)/2}" text-anchor="middle" fill="#333" '
               f'transform="rotate(-90 14 {(T+H-B)/2})">change B − A (dB)</text>')
    out.append("</svg>")
    pathlib.Path(path).write_text("\n".join(out) + "\n")


def fmt(v, nd=1, unit=""):
    return "—" if v is None else f"{v:.{nd}f}{unit}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rundir")
    ap.add_argument("--a", nargs=2, default=["A1", "A2"])
    ap.add_argument("--b", nargs=2, default=["B1", "B2"])
    a = ap.parse_args()
    d = pathlib.Path(a.rundir)

    a_states = [State(l, load(d / f"{l}.jsonl")) for l in a.a]
    b_states = [State(l, load(d / f"{l}.jsonl")) for l in a.b]
    states = [a_states[0], b_states[0], a_states[1], b_states[1]]
    extra = [State(p.stem, load(p)) for p in sorted(d.glob("*.jsonl"))
             if p.stem not in a.a + a.b]

    problems = validity(states)
    no_live = any("no live frames" in p for p in problems)
    rows = [] if no_live else compare(a_states, b_states)
    drift = source_drift(a_states, b_states) if rows else None
    changed = [r for r in rows if r["changed"]]
    session = sorted({f["link"]["session"] for s in states for f in s.all})

    if problems:
        verdict = "INVALID: " + "; ".join(problems)
    elif not rows:
        verdict = "NO COMPARISON: no band was measured in every state"
    elif changed:
        biggest = max(changed, key=lambda r: abs(r["delta"]))
        verdict = (f"CHANGE DETECTED in {len(changed)} of {len(rows)} bands; largest "
                   f"{biggest['delta']:+.1f} dB at {biggest['hz']:.0f} Hz, "
                   f"repeat difference there {biggest['repeat']:.2f} dB")
    else:
        verdict = (f"NO CHANGE DETECTED in {len(rows)} bands "
                   f"(largest {max(abs(r['delta']) for r in rows):.2f} dB)")

    L = ["# A/B comparison", "", f"**Verdict:** {verdict}", "",
         "## Run", "", "| State | Live frames | Result frames | Peak input dBFS | Peak return dBFS |",
         "|---|---|---|---|---|"]
    for s in states + extra:
        L.append(f"| {s.label} | {len(s.live)} | {len(s.results)} | "
                 f"{fmt(s.peak('peak_source_dbfs'))} | {fmt(s.peak('peak_return_dbfs'))} |")
    L += ["", f"Teensy session: {', '.join(map(str, session))}. "
          f"Checks: {'all passed' if not problems else '; '.join(problems)}.", ""]
    if drift:
        n, med, mx = drift
        L += ["## Did the input stay the same?", "",
              f"Input spectrum, A vs B, over {n} energised bins: median difference "
              f"{med:.2f} dB, largest {mx:.2f} dB. The stimulus was not touched, so any "
              "difference here is either noise or return signal leaking into the input "
              "(TODO-70). It does not by itself close TODO-70.", ""]
    if rows:
        L += ["## Per band", "",
              f"{len(rows)} bands measured in all four states. Change = mean(B) − mean(A); "
              "repeat = largest A2−A1 or B2−B1 difference. ✔ = counted as a change "
              f"(same sign both cycles, > {REPEAT_X:g}× repeat and > {MIN_DB:g} dB).", "",
              "| Hz | A dB | B dB | B1−A1 | B2−A2 | Change | Repeat | |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append(f"| {r['hz']:.0f} | {r['a']:.1f} | {r['b']:.1f} | {r['d1']:+.1f} | "
                     f"{r['d2']:+.1f} | {r['delta']:+.1f} | {r['repeat']:.2f} | "
                     f"{'✔' if r['changed'] else ''} |")
        L += ["", "![Change B − A per band, with the repeat difference as error bars](delta.svg)", ""]
    res = [(s.label, s.results[-1]["authority"]) for s in states + extra if s.results]
    if res:
        L += ["## Teensy RESULTs", "", "| State | Valid | Grade | Mean coherence | Valid bins | Averages |",
              "|---|---|---|---|---|---|"]
        for lab, au in res:
            L.append(f"| {lab} | {au.get('result_valid')} | {au.get('result_quality')} | "
                     f"{fmt(au.get('mean_coherence'), 3)} | {fmt(au.get('valid_bin_fraction'), 3)} | "
                     f"{au.get('n_averages_completed')} |")
        L.append("")
    L += ["## What this does not show", "",
          "This is a difference between two settings on one uncalibrated instrument, "
          "minutes apart. It is not a calibrated frequency response of the Headrush, "
          "and dB values are instrument readings, not volts.", ""]
    (d / "report.md").write_text("\n".join(L))
    svg(rows, d / "delta.svg")
    print(verdict)
    print(f"wrote {d/'report.md'}" + (f" and {d/'delta.svg'}" if rows else ""))


if __name__ == "__main__":
    main()
