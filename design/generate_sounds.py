#!/usr/bin/env python3
"""Synthesize every SayMy sound from scratch (no samples, no copyright): python3 design/generate_sounds.py

Savanna  kalimba tines + plucked adungu-style strings on a pentatonic scale. Warm, short, recognisable.
Quiet    soft sine bells, lower volume, shorter. For libraries, classrooms and night use.
Classic  plain beeps. Familiar and unmistakable.
Output: config/includes.chroot/usr/share/saymy/sounds/<Pack>/<event>.wav  (22.05 kHz, mono, 16 bit)
Needs numpy at build time only; the OS itself only plays the finished files.
"""
import wave
from pathlib import Path

import numpy as np

SR = 22050
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config/includes.chroot/usr/share/saymy/sounds"
NOTES = {"C": 0, "D": 2, "E": 4, "G": 7, "A": 9}


def hz(name: str) -> float:
    """C4 / E5 / A3 ... pentatonic note names to frequency."""
    semis = NOTES[name[0]] + 12 * (int(name[1]) - 4) - 9
    return 440.0 * 2 ** (semis / 12)


# ------------------------------------------------------------------ instruments
def t_axis(dur):
    return np.arange(int(SR * dur)) / SR


def kalimba(f, dur=1.0):
    t = t_axis(dur)
    tone = np.sin(2 * np.pi * f * t) + 0.28 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 6) + 0.16 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t * 15)
    env = np.exp(-t * 4.2) * np.minimum(1, t / 0.002)
    click = np.random.default_rng(int(f)).standard_normal(len(t)) * np.exp(-t * 400) * 0.10
    return (tone * env + click) * 0.6


def adungu(f, dur=1.2):
    """Karplus-Strong plucked string: a short burst of noise circulating through a delay line that slowly loses brightness."""
    n = int(SR * dur)
    period = max(2, int(round(SR / f)))
    rng = np.random.default_rng(int(f * 7))
    x = np.arange(period) / period
    pluck = 0.2                                            # plucked a fifth of the way along the string, like a harp
    buf = np.where(x < pluck, x / pluck, (1 - x) / (1 - pluck))
    buf = buf - buf.mean() + rng.normal(0, 0.01, period)   # triangular pluck shape: strong low harmonics, warm
    out = np.empty(n)
    for i in range(n):
        j = i % period
        out[i] = buf[j]
        buf[j] = 0.5 * (buf[j] + buf[(j + 1) % period]) * 0.9965
    out *= np.minimum(1, np.arange(n) / (SR * 0.003))
    return out * 0.9


def bell(f, dur=0.8):
    t = t_axis(dur)
    return (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t * 8)) * np.exp(-t * 6) * np.minimum(1, t / 0.004) * 0.5


def beep(f, dur=0.12):
    t = t_axis(dur)
    return np.sin(2 * np.pi * f * t) * np.minimum(1, t / 0.004) * np.minimum(1, (dur - t) / 0.01) * 0.5


PACKS = {
    "Savanna": {"k": kalimba, "a": adungu, "gain": 1.0, "stretch": 1.0},
    "Quiet": {"k": bell, "a": bell, "gain": 0.55, "stretch": 0.8},
    "Classic": {"k": beep, "a": beep, "gain": 0.8, "stretch": 0.7},
}

# (time offset in seconds, instrument 'k'/'a', note, duration, loudness)
EVENTS = {
    "login": [(0.0, "a", "C3", 1.8, 0.55), (0.15, "k", "E4", 1.0, 0.7), (0.35, "k", "G4", 1.0, 0.7), (0.55, "k", "C5", 1.0, 0.75), (0.80, "k", "E5", 1.1, 0.8)],
    "logout": [(0.0, "a", "C5", 1.1, 0.7), (0.30, "a", "G4", 1.1, 0.7), (0.60, "a", "E4", 1.1, 0.65), (0.90, "a", "C4", 1.4, 0.7)],
    "notify": [(0.0, "k", "G5", 0.6, 0.7), (0.12, "k", "C6", 0.7, 0.8)],
    "tick": [(0.0, "k", "E6", 0.2, 0.45)],
    "critical": [(0.0, "a", "E3", 0.5, 0.9), (0.22, "a", "E3", 0.5, 0.9), (0.44, "a", "E3", 0.7, 0.95)],
    "power-cut": [(0.0, "a", "A4", 1.0, 0.7), (0.28, "a", "E4", 1.0, 0.7), (0.56, "a", "C4", 1.3, 0.75)],
    "power-back": [(0.0, "k", "C4", 0.9, 0.7), (0.18, "k", "G4", 0.9, 0.7), (0.36, "k", "C5", 0.9, 0.75), (0.54, "k", "E5", 1.1, 0.8)],
    "battery-low": [(0.0, "k", "D5", 0.6, 0.6), (0.30, "k", "D5", 0.7, 0.6)],
    "received": [(0.0, "k", "E5", 0.5, 0.7), (0.10, "k", "G5", 0.5, 0.7), (0.20, "k", "C6", 0.7, 0.8)],
    "update-done": [(0.0, "a", "C3", 1.4, 0.5), (0.0, "k", "C5", 0.8, 0.7), (0.12, "k", "E5", 0.8, 0.7), (0.24, "k", "G5", 0.8, 0.75), (0.36, "k", "C6", 0.9, 0.8), (0.50, "k", "E6", 1.1, 0.8)],
    "error": [(0.0, "a", "C3", 0.45, 0.8), (0.18, "a", "C3", 0.6, 0.8)],
}


def compose(pack: dict, notes: list) -> np.ndarray:
    stretch = pack["stretch"]
    end = max(off * stretch + dur * stretch for off, _, _, dur, _ in notes)
    mix = np.zeros(int(SR * (end + 0.15)))
    for off, inst, name, dur, vel in notes:
        voice = pack[inst](hz(name), dur * stretch)
        start = int(SR * off * stretch)
        mix[start:start + len(voice)] += voice * vel
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.85 * pack["gain"]
    fade = int(SR * 0.02)
    mix[-fade:] *= np.linspace(1, 0, fade)                  # no click at the end
    head = int(SR * 0.004)
    mix[:head] *= np.linspace(0, 1, head)                   # none at the start either
    return mix


def write_wav(path: Path, samples: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())


def main():
    total = 0
    for name, pack in PACKS.items():
        for event, notes in EVENTS.items():
            p = OUT / name / f"{event}.wav"
            write_wav(p, compose(pack, notes))
            total += p.stat().st_size
    print(f"{len(PACKS) * len(EVENTS)} sounds, {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
