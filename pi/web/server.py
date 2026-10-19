"""Local UI transport: the Pi receiver's state, served to a browser as JSON.

Standard library only, matching the rest of `pi/`. No framework, no build step,
no dependency added.

    python3 -m web.server --fixture ai/evidence/phase10-result-1khz.bin
    python3 -m web.server --serial /dev/ttyAMA0          # designed, NOT proven

*** THE TRANSPORT CARRIES SEMANTICS, NOT RAW ARRAYS. ***

`/api/frame` returns bands that `presentation_semantics` has already classified.
Nothing on this endpoint lets a browser reconstruct a coverage nibble or a NaN, so
the browser cannot classify even if a future contributor wanted it to.

Bound to loopback by default: this is a panel on a Pi, not a service.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from analyzer_ui.engine import Engine
from analyzer_ui.sources import FixtureSource, SerialSource

from . import lab, payload

STATIC = pathlib.Path(__file__).resolve().parent / "static"

_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".json": "application/json"}


class FrameService:
    """Pumps the receiver and renders the current snapshot as a payload.

    One lock around the engine: `pump()` mutates receiver state and the HTTP
    server is threaded, so two concurrent polls must not interleave inside it.
    """

    def __init__(self, engine: Engine, *, prefer: str = "auto") -> None:
        self.engine = engine
        self.prefer = prefer
        self._lock = threading.Lock()
        # TONE's held, smoothed gain. One per instrument stream, not per client;
        # it advances on the block number, so extra pollers do not speed it up.
        self._gain = payload.GainMatcher()
        # LAB's running statistics, under the same rule. A new session is a
        # new instrument stream, so nothing from the last one may carry over.
        self._lab = lab.LabTracker()
        self._lab_session = None

    def frame(self) -> dict:
        with self._lock:
            self.engine.pump()
            snap = self.engine.snapshot()

        geo = snap.geometry
        if geo is None:
            # Before HELLO the Pi does not know the geometry, so it cannot locate
            # any array. It says so rather than guessing one.
            return {"kind": "unknown", "reason": "no HELLO yet: geometry unknown",
                    "segments": [], "bands": payload.RING_BANDS}

        want_result = self.prefer == "result" or (
            self.prefer == "auto" and snap.result is not None)
        if want_result and snap.result is not None:
            out = payload.result_payload(snap.result, geo)
        elif snap.live is not None:
            with self._lock:                # the matcher is shared state
                if snap.session_id != self._lab_session:
                    self._lab.reset()
                    self._lab_session = snap.session_id
                out = payload.live_payload(snap.live, geo, gain=self._gain,
                                           lab=self._lab)
        else:
            return {"kind": "unknown", "reason": "no LIVE_FRAME or RESULT yet",
                    "segments": [], "bands": payload.RING_BANDS}

        out["link"] = {
            "session": snap.session_id,
            "stale": snap.link_stale,
            "frames_in": snap.frames_in,
            "decode_errors": snap.decode_errors,
            "state": snap.state_text,
        }
        return out


def make_handler(service: FrameService):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/frame":
                body = json.dumps(service.frame()).encode()
                self._send(body, "application/json")
                return

            rel = "index.html" if path == "/" else path.lstrip("/")
            target = (STATIC / rel).resolve()
            if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
                self._send(b"not found", "text/plain", 404)
                return
            self._send(target.read_bytes(),
                       _TYPES.get(target.suffix, "application/octet-stream"))

        def log_message(self, *a) -> None:      # quiet; the panel is the output
            pass

    return Handler


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", help="recorded capture to replay")
    src.add_argument("--serial", help="tty, e.g. /dev/ttyAMA0 (NOT runtime-proven)")
    ap.add_argument("--prefer", choices=("auto", "result", "live"), default="auto")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8711)
    ns = ap.parse_args(argv)

    source = (FixtureSource(ns.fixture, realtime=False) if ns.fixture
              else SerialSource(ns.serial))
    service = FrameService(Engine(source), prefer=ns.prefer)
    httpd = ThreadingHTTPServer((ns.host, ns.port), make_handler(service))
    print(f"[web] http://{ns.host}:{ns.port}/   source="
          f"{ns.fixture or ns.serial}  prefer={ns.prefer}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
