"""Write a reproducible pink-noise WAV to use as the A/B stimulus.

    python3 pi/tools/pink_noise.py out.wav [--seconds 600] [--rms-dbfs -18] [--seed 1]

Pink noise (equal energy per octave) energises every analysis band at once and
does not change from one minute to the next, so two rig settings can be compared
against the same input. The file is deterministic for a given seed, so its
sha256 identifies the stimulus exactly.

Mono, 16-bit, 44.1 kHz. Generated with the Voss-McCartney algorithm (16 rows),
standard library only.
"""

import argparse
import math
import random
import struct
import wave

RATE = 44100
ROWS = 16


def pink(n, seed):
    rng = random.Random(seed)
    rows = [rng.uniform(-1, 1) for _ in range(ROWS)]
    total = sum(rows)
    out = []
    for i in range(1, n + 1):
        # Update the row picked by the number of trailing zeros of i.
        k = (i & -i).bit_length() - 1
        if k < ROWS:
            total -= rows[k]
            rows[k] = rng.uniform(-1, 1)
            total += rows[k]
        out.append(total + rng.uniform(-1, 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=600.0)
    ap.add_argument("--rms-dbfs", type=float, default=-18.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    x = pink(int(a.seconds * RATE), a.seed)
    rms = math.sqrt(sum(v * v for v in x) / len(x))
    gain = 10 ** (a.rms_dbfs / 20) / rms
    peak = max(abs(v) for v in x) * gain
    if peak >= 1.0:
        raise SystemExit(f"peak {peak:.2f} would clip; lower --rms-dbfs")

    frames = b"".join(struct.pack("<h", int(round(v * gain * 32767))) for v in x)
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)
    print(f"{a.out}: {a.seconds:.0f} s, RMS {a.rms_dbfs} dBFS, "
          f"peak {20 * math.log10(peak):.1f} dBFS, seed {a.seed}")


if __name__ == "__main__":
    main()
