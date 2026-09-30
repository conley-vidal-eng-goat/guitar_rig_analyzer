"""Byte sources. One interface, two implementations, no fabrication anywhere.

*** THERE IS NO SYNTHETIC SOURCE IN THIS MODULE, DELIBERATELY. ***

Every byte the UI renders comes either from a real captured artifact or from the
live UART. There is no generator, no demo mode and no placeholder waveform — a UI
that can invent plausible-looking measurements is a UI that will eventually show
one to somebody as if it were real. The 2026-09-27 RESULT capture already gives
us a genuinely hard case to render (four finite bins out of 512), which is far
more useful for development than smooth fake data would be.

``FixtureSource`` paces a recorded capture at the rate the real link runs, so the
UI animates the way it will on hardware. ``SerialSource`` reads the tty. Both
hand the application identical bytes, so fixture replay exercises the same code
path as live input — which is the whole point of keeping acquisition out of the
renderer.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import time

# Measured on this project's own hardware: 36 483 B/s at 79 % occupancy of the
# 460 800 baud link (2026-09-26 30 s fixture, 2026-09-29 Run 2 capture).
REAL_LINK_BYTES_PER_SEC = 36_483


class ByteSource:
    """Minimal interface: ``read()`` returns whatever is available, or b''."""

    name: str = "none"
    is_live: bool = False

    def read(self) -> bytes:                      # pragma: no cover - interface
        raise NotImplementedError

    def close(self) -> None:                      # pragma: no cover - interface
        pass

    @property
    def exhausted(self) -> bool:
        return False


class FixtureSource(ByteSource):
    """Replay a recorded capture.

    ``realtime=True`` releases bytes at ``bytes_per_sec`` so the UI sees the same
    cadence as the wire — ~21.5 live frames per second. With ``realtime=False``
    the whole file is delivered on the first read, which is what tests want.

    ``loop=True`` restarts at the beginning on exhaustion. The restart is a
    *replay* artifact, not a reconnect: the session id in the recorded HELLO does
    not change, so the receiver will not see it as a new session. Fine for
    watching the UI, and explicitly not a substitute for a reconnect test.
    """

    is_live = False

    def __init__(self, path: str | os.PathLike, *, realtime: bool = True,
                 bytes_per_sec: int = REAL_LINK_BYTES_PER_SEC,
                 loop: bool = False) -> None:
        self._path = pathlib.Path(path)
        self._data = self._path.read_bytes()
        self._pos = 0
        self._realtime = realtime
        self._bps = max(1, int(bytes_per_sec))
        self._loop = loop
        self._t0 = time.monotonic()
        self.name = f"fixture:{self._path.name}"

    @property
    def total_bytes(self) -> int:
        return len(self._data)

    @property
    def position(self) -> int:
        return self._pos

    @property
    def exhausted(self) -> bool:
        return not self._loop and self._pos >= len(self._data)

    def read(self) -> bytes:
        if self._pos >= len(self._data):
            if not self._loop:
                return b""
            self._pos = 0
            self._t0 = time.monotonic()
        if not self._realtime:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        # How many bytes *should* have been delivered by now.
        due = int((time.monotonic() - self._t0) * self._bps)
        end = min(len(self._data), max(self._pos, due))
        chunk = self._data[self._pos:end]
        self._pos = end
        return chunk

    def close(self) -> None:
        self._data = b""


class SerialSource(ByteSource):
    """Live receive-only UART.

    Receive-only by construction: the file is opened ``O_RDONLY``, so this class
    *cannot* transmit even by accident. The Pi to Teensy direction is physically
    disconnected and adding it is a separate reviewed decision, not a code
    change here.

    ``stty`` is shelled out once rather than reimplemented through ``termios``,
    using the exact line ``pi/tools/capture.sh`` uses — including
    ``min 1 time 0``, which is not cosmetic: ``min 0 time 1`` silently broke a
    30 s capture on 2026-09-26 by letting a no-data read return immediately.
    Here the read is non-blocking anyway, but the settings must still match the
    tool whose captures the fixtures came from.
    """

    is_live = True

    STTY_ARGS = ("460800", "cs8", "-cstopb", "-parenb", "-crtscts", "raw",
                 "-echo", "-echoe", "-echok", "-ixon", "-ixoff", "-icrnl",
                 "-onlcr", "min", "1", "time", "0")

    def __init__(self, device: str = "/dev/ttyAMA0", *,
                 configure: bool = True) -> None:
        self.name = f"serial:{device}"
        self._device = device
        if configure:
            subprocess.run(("stty", "-F", device, *self.STTY_ARGS),
                           check=True, capture_output=True)
        self._fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)

    def read(self) -> bytes:
        out = bytearray()
        while True:
            try:
                chunk = os.read(self._fd, 8192)
            except BlockingIOError:
                break
            except OSError:
                break
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > 1 << 20:      # never let one tick starve the renderer
                break
        return bytes(out)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:                           # pragma: no cover - teardown
            pass
