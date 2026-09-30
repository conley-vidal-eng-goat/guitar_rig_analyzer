"""Launcher.

    # replay the real 1 kHz RESULT capture at wire speed (development)
    python3 -m analyzer_ui --fixture ../ai/evidence/phase10-result-1khz.bin

    # jump straight to the decoded RESULT, deterministic (screenshots, demos)
    python3 -m analyzer_ui --fixture ../ai/evidence/phase10-result-1khz.bin \
        --no-realtime --tab result

    # live, receive-only, on the Pi
    python3 -m analyzer_ui --serial /dev/ttyAMA0

Run from the ``pi/`` directory so ``analyzer_link`` and ``analyzer_ui`` are
importable, or use ``sh pi/run_ui.sh`` which handles that.

There is deliberately no synthetic/demo source. Every pixel traces to a real
captured artifact or the live UART — see sources.py.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from .engine import Engine
from .sources import REAL_LINK_BYTES_PER_SEC, FixtureSource, SerialSource


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="analyzer_ui",
                                description="Guitar Rig Analyzer — Pi UI")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--fixture", metavar="PATH",
                     help="replay a recorded raw capture (.bin)")
    src.add_argument("--serial", metavar="DEV",
                     help="live receive-only UART, e.g. /dev/ttyAMA0")
    p.add_argument("--no-realtime", action="store_true",
                   help="fixture only: deliver the whole file at once")
    p.add_argument("--loop", action="store_true",
                   help="fixture only: restart at the end (replay artifact, "
                        "NOT a reconnect — the session id does not change)")
    p.add_argument("--bytes-per-sec", type=int, default=REAL_LINK_BYTES_PER_SEC,
                   help="fixture pacing (default: the measured link rate)")
    p.add_argument("--tab", choices=("live", "result"), default="live")
    p.add_argument("--windowed", action="store_true",
                   help="do not go fullscreen (desktop development)")
    p.add_argument("--no-stty", action="store_true",
                   help="serial only: skip stty configuration")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.fixture:
        path = pathlib.Path(args.fixture)
        if not path.is_file():
            print(f"no such fixture: {path}", file=sys.stderr)
            return 2
        source = FixtureSource(path, realtime=not args.no_realtime,
                              bytes_per_sec=args.bytes_per_sec,
                              loop=args.loop)
        print(f"replaying {path.name} ({source.total_bytes} B)"
              f"{'' if args.no_realtime else f' at {args.bytes_per_sec} B/s'}")
    else:
        source = SerialSource(args.serial, configure=not args.no_stty)
        print(f"live receive-only on {args.serial}")

    engine = Engine(source)
    if args.no_realtime:
        # Deterministic start: consume everything before the first paint so the
        # UI opens on fully decoded state rather than animating up to it.
        engine.pump()

    from .app import AnalyzerUI      # imported late: needs a display
    ui = AnalyzerUI(engine, fullscreen=not args.windowed, tab=args.tab)
    try:
        ui.run()
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
