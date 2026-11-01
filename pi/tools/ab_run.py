"""Run the whole Headrush A/B unattended: switch the rig, dwell, capture, arm RESULTs, compare.

    python3 pi/tools/ab_run.py RUNDIR --block Cab --prop CabType --b 0 [--check]

Runs on the Mac. The stimulus is the one thing it does not start: begin the pink
noise (phone or any player, looping, at a level you write down) and the script
waits until the Teensy says the input is energised. Then, for A1 -> B1 -> A2 -> B2:

  1. set the one Headrush parameter over the unit's own REST API, and read it back;
  2. dwell (LIVE's EMA is sticky, docs/ab_headrush_procedure.md §1);
  3. record /api/frame with ab_capture.sh, arming a RESULT with `m` on the Teensy
     USB console partway through so the same file holds LIVE and RESULT frames;
  4. send `x` to return the Teensy to live view.

Then it runs ab_compare.py on RUNDIR. Whatever happens, including Ctrl-C, the
parameter is put back to the value it had when the script started. It never
saves, loads or renames a rig: the Headrush may be holding unsaved edits.

It stops, rather than carrying on, if the Teensy session changes, the link goes
stale, decode errors rise, either channel clips, or a readback disagrees.

--check does every read-only preflight step and exits without touching anything.
"""

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import termios
import threading
import time
import urllib.request

TOOLS = pathlib.Path(__file__).resolve().parent
STATES = ["A1", "B1", "A2", "B2"]
TF_CONFIDENCE_THRESHOLD = 0.10   # firmware config.h, >= 51 of 512 bins energised


def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


class Stop(Exception):
    pass


class Headrush:
    def __init__(self, url, block):
        self.base = url.rstrip("/") + "/api/v1"
        self.path = "/Evil/Engine/Patch/" + block.replace(" ", "_")

    def _req(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        # Retried, because the unit sits on Wi-Fi: on 2026-10-31 one read timed
        # out mid-run and took the script down before it could restore.
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    raw = r.read()
                return json.loads(raw) if raw.strip() else None
            except OSError as e:
                err = e
                time.sleep(2)
        raise Stop(f"Headrush {method} {path} failed 5 times: {err}")

    def props(self):
        return self._req("GET", "/object-properties" + self.path)

    def rig(self):
        return self._req("GET", "/object-properties/Evil/API/Rigs")

    def set(self, prop, value):
        self._req("PUT", "/object-properties" + self.path, {prop: value})
        got = self.props()[prop]
        if got != value:
            raise Stop(f"Headrush readback: {prop} is {got!r}, wanted {value!r}")
        return got


class Console:
    """The Teensy USB console. Everything it prints is appended to a log file."""

    def __init__(self, dev, logpath):
        self.fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attr = termios.tcgetattr(self.fd)
        attr[0] = attr[1] = attr[3] = 0                  # raw: no iflag/oflag/lflag
        attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attr[4] = attr[5] = termios.B115200
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        self.log = open(logpath, "a", buffering=1)
        self.lines = []
        self.lock = threading.Lock()
        self.done = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        buf = b""
        while not self.done:
            try:
                chunk = os.read(self.fd, 4096)
            except BlockingIOError:
                time.sleep(0.02)
                continue
            except OSError:
                return
            buf += chunk
            *whole, buf = buf.split(b"\n")
            for raw in whole:
                line = raw.decode(errors="replace").rstrip("\r")
                self.log.write(f"{time.time():.3f} {line}\n")
                with self.lock:
                    self.lines.append(line)

    def send(self, ch):
        self.log.write(f"{time.time():.3f} >>> {ch}\n")
        os.write(self.fd, ch.encode())

    def mark(self):
        with self.lock:
            return len(self.lines)

    def wait_for(self, start, needles, timeout):
        end = time.time() + timeout
        while time.time() < end:
            with self.lock:
                for line in self.lines[start:]:
                    if any(n in line for n in needles):
                        return line
            time.sleep(0.1)
        return None

    def close(self):
        self.done = True
        os.close(self.fd)
        self.log.close()


# Cut down on the Pi to the fields health() and summary() read: a whole frame is
# ~47 kB, and over a congested Wi-Fi link each poll took seconds.
SLIM = ("import json,sys; f=json.load(sys.stdin); json.dump({"
        "'link': f['link'], 'authority': f.get('authority', {}), "
        "'census_bands': f.get('census_bands', {}), "
        "'segments': [{'sources': s['sources'], 'cls': s['cls']} for s in f.get('segments', [])]"
        "}, sys.stdout)")


def pi_frame(host):
    try:
        out = subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                              "curl -s -m 3 http://127.0.0.1:8711/api/frame | "
                              f'python3 -c "{SLIM}"'],
                             capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise Stop(f"no answer from {host} within 15 s")
    if out.returncode:
        raise Stop(f"cannot read /api/frame from {host}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def health(f, session, errors):
    """The reasons this frame breaks the run, if any."""
    link, au = f["link"], f.get("authority", {})
    bad = []
    if session is not None and link["session"] != session:
        bad.append(f"Teensy session changed {session} -> {link['session']} (restart)")
    if link["stale"]:
        bad.append("link stale")
    if errors is not None and link["decode_errors"] > errors:
        bad.append(f"decode_errors rose {errors} -> {link['decode_errors']}")
    if au.get("source_clip") or au.get("return_clip"):
        bad.append("clipping (source_clip/return_clip): lower the stimulus level")
    return bad


def summary(f):
    au, cb = f.get("authority", {}), f.get("census_bands", {})
    return (f"confidence {au.get('tf_confidence', 0):.0%}, {cb.get('text', '?')}, "
            f"peak in {au.get('peak_source_dbfs', float('nan')):.1f} / "
            f"return {au.get('peak_return_dbfs', float('nan')):.1f} dBFS")


def energised(f):
    # A band with no FFT bin inside it (sources == 0, the low bands) can never be
    # measured, so "energised" means every band that has a bin is MEASURED or CLAMPED.
    dark = [s for s in f["segments"] if s["sources"] and s["cls"] == "UNMEASURED"]
    return (f["authority"].get("tf_confidence", 0) >= TF_CONFIDENCE_THRESHOLD
            and f["census_bands"]["measured"] > 0 and not dark)


def check_running(host, session, errors, when):
    f = pi_frame(host)
    bad = health(f, session, errors)
    if not energised(f):
        bad.append(f"stimulus gone {when} ({summary(f)}): the noise stopped or dropped out")
    if bad:
        raise Stop("; ".join(bad))


def wait_for_stimulus(host, session, errors, timeout):
    log(f"waiting for stimulus: need confidence >= {TF_CONFIDENCE_THRESHOLD:.0%} and "
        "every band with an FFT bin measured, three polls running")
    good, end = 0, time.time() + timeout
    while time.time() < end:
        f = pi_frame(host)
        bad = health(f, session, errors)
        if bad:
            raise Stop("; ".join(bad))
        ok = energised(f)
        good = good + 1 if ok else 0
        log(("  ok  " if ok else "  ... ") + summary(f))
        if good >= 3:
            return f
        time.sleep(2)
    raise Stop("stimulus never energised the input: is the noise playing into J4?")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rundir")
    ap.add_argument("--block", default="Cab", help="Headrush patch object, e.g. Cab, Amp")
    ap.add_argument("--prop", default="CabType", help="the one parameter that changes")
    ap.add_argument("--a", type=json.loads, help="A value (default: the current value)")
    ap.add_argument("--b", type=json.loads, required=True, help="B value")
    ap.add_argument("--live", type=float, default=60, help="seconds of LIVE per state")
    ap.add_argument("--result", type=float, default=20,
                    help="seconds recorded after arming the RESULT")
    ap.add_argument("--dwell", type=float, default=30, help="seconds after each change")
    ap.add_argument("--wait", type=float, default=600, help="seconds to wait for stimulus")
    ap.add_argument("--headrush", default=os.environ.get("HEADRUSH_URL", "http://192.168.87.149"))
    ap.add_argument("--teensy", default="/dev/cu.usbmodem192895301")
    ap.add_argument("--host", default=os.environ.get("GRA_HOST", "conley@guitar-rig-analyzer.local"))
    ap.add_argument("--check", action="store_true", help="preflight only, change nothing")
    a = ap.parse_args()

    run = pathlib.Path(a.rundir)
    if not a.check:
        if any(run.glob("*.jsonl")):
            sys.exit(f"{run} already holds captures; refusing to mix runs")
        run.mkdir(parents=True, exist_ok=True)

    # --- preflight, read-only -------------------------------------------------
    hr = Headrush(a.headrush, a.block)
    rig, before = hr.rig(), hr.props()
    if a.prop not in before:
        sys.exit(f"{a.block} has no property {a.prop!r}")
    orig = before[a.prop]
    a_val = orig if a.a is None else a.a
    log(f"Headrush rig '{rig.get('loadedName')}' (unsaved edits: {rig.get('dirty')}); "
        f"{a.block}.{a.prop} is {orig!r}; A = {a_val!r}, B = {a.b!r}")
    if a_val == a.b:
        sys.exit("A and B are the same value")
    if orig != a_val:
        sys.exit(f"{a.block}.{a.prop} is {orig!r}, not A = {a_val!r}; set it to A first")

    f0 = pi_frame(a.host)
    session, errors = f0["link"]["session"], f0["link"]["decode_errors"]
    log(f"Pi link: session {session}, decode_errors {errors}, state "
        f"{f0['link']['state']}, {summary(f0)}")
    bad = health(f0, None, None)
    if bad:
        sys.exit("; ".join(bad))

    con = Console(a.teensy, os.devnull if a.check else run / "teensy-console.log")
    log(f"Teensy console open on {a.teensy}")
    if a.check:
        con.close()
        log("check passed; nothing was changed")
        return

    manifest = {
        "started": datetime.datetime.now().isoformat(timespec="seconds"),
        "rig": rig.get("loadedName"), "rig_dirty_at_start": rig.get("dirty"),
        "block": a.block, "prop": a.prop, "a": a_val, "b": a.b,
        "block_before": before, "session": session, "decode_errors": errors,
        "timing_s": {"live": a.live, "result": a.result, "dwell": a.dwell},
        "stimulus": "pink noise from an external player, started by hand; "
                    "record the file and level in notes.md",
        "states": [],
    }

    def save():
        (run / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")

    remote = f"/tmp/ab-run-{run.resolve().name}"
    manifest["pi_dir"] = remote
    save()
    try:
        f = wait_for_stimulus(a.host, session, errors, a.wait)
        manifest["stimulus_seen"] = summary(f)
        log(f"stimulus is up; settling {a.dwell:g} s")
        time.sleep(a.dwell)

        for label in STATES:
            value = a_val if label.startswith("A") else a.b
            got = hr.set(a.prop, value)
            log(f"{label}: {a.block}.{a.prop} = {got!r}; dwell {a.dwell:g} s")
            time.sleep(a.dwell)
            check_running(a.host, session, errors, f"before {label}")

            log(f"{label}: recording {a.live:g} s LIVE + {a.result:g} s RESULT")
            cap = subprocess.Popen(["sh", str(TOOLS / "ab_capture.sh"), str(run), label,
                                    str(a.live + a.result)],
                                   env={**os.environ, "AB_REMOTE_DIR": remote})
            time.sleep(a.live)
            mark = con.mark()
            con.send("m")
            line = con.wait_for(mark, ["Quality:", "Could not arm", "abort", "Abort"],
                                a.result - 2)
            log(f"{label}: RESULT -> {line or 'no RESULT line within the window'}")
            if cap.wait() != 0:
                raise Stop(f"ab_capture.sh failed for {label}")
            con.send("x")
            time.sleep(1)
            check_running(a.host, session, errors, f"after {label}")
            manifest["states"].append({"label": label, "value": got,
                                       "result_line": line,
                                       "readback_after": hr.props()[a.prop]})
            save()
    except (Stop, KeyboardInterrupt) as e:
        manifest["stopped"] = str(e) or "interrupted"
        log(f"STOPPED: {manifest['stopped']}")
        con.send("x")
    finally:
        try:
            hr.set(a.prop, orig)
            log(f"restored {a.block}.{a.prop} = {orig!r}")
            manifest["restored"] = orig
        except Exception as e:  # noqa: BLE001 - must be reported, not raised over
            log(f"!!! COULD NOT RESTORE {a.block}.{a.prop} to {orig!r}: {e}")
            manifest["restored"] = None
        manifest["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
        save()
        con.close()
        # One compressed copy of every state, after the bench work is over, so
        # the Wi-Fi's speed can't stretch the time between states.
        log(f"copying the frames back from {a.host}:{remote} (slow on a busy Wi-Fi)")
        fetched = subprocess.call(f"ssh -o BatchMode=yes {a.host} 'tar czf - -C {remote} .'"
                                  f" | tar xzf - -C '{run}'", shell=True)
        for p in sorted(run.glob("*.jsonl")):
            with open(p) as fh:
                log(f"{p}: {sum(1 for _ in fh)} frames")
        if fetched:
            log(f"!!! copy failed; the frames are still on the Pi in {remote}")
            sys.exit(1)

    if "stopped" in manifest:
        sys.exit(1)
    log("comparing")
    sys.exit(subprocess.call([sys.executable, str(TOOLS / "ab_compare.py"), str(run)]))


if __name__ == "__main__":
    main()
