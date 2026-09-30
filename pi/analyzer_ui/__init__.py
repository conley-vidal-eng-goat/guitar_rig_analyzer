"""Raspberry Pi production UI for the Guitar Rig Analyzer.

ADR-001: the Teensy is the sole measurement authority; this package is
presentation only. It formats Teensy-authored values and never derives a
measurement, a quality grade or an advisory of its own.

Layers, deliberately separated so fixture replay and live UART share one path:

    sources.py   bytes from a recorded artifact or the live tty
    engine.py    bytes -> production FrameScanner -> ReceiverState
    model.py     ReceiverState -> render-ready Snapshot (UNKNOWN preserved)
    plotting.py  pure plot geometry; never interpolates across invalid bins
    app.py       Tk rendering (the only module that imports tkinter)

Everything except app.py is importable and testable without a display.
"""
