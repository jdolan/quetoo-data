#!/usr/bin/env python3
"""
Generates the Quake II item set's weapon sounds.

These are Quetoo's own: each is synthesized, or reshaped and layered from Quetoo's existing weapon
sounds, to the timing and character of its Quake II counterpart. No Quake II audio is read or
mixed in. The Quake II weapon code (GPL) gives the timing: the hyperblaster's 0.1 s cadence, the
chaingun's spin-up and the looping hums. The other Quake II weapons use Quetoo's sounds directly.
The railgun hum is shared by both railguns.

Usage: make_quake2_sounds.py [--data DIR] [--only NAME ...]

DIR is quetoo-data's target/default (by default, relative to this script). Output is 16-bit mono
44.1 kHz WAV, written over target/default/sounds/weapons/. The output is
deterministic: each sound seeds its own random generator.

Requires numpy, scipy and ffmpeg (to read the Quetoo .ogg sources).
"""

import argparse
import os
import subprocess
import sys
import wave
import zlib

import numpy as np
from scipy import signal

SR = 44100

DATA = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'target', 'default'))


# --- I/O ---

def load(path, af=None):
    """Loads a Quetoo sound as mono float at SR, through the ffmpeg audio filter af if given."""
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', os.path.join(DATA, 'sounds', path)] +
                         (['-af', af] if af else []) +
                         ['-ac', '1', '-ar', str(SR), '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64) / 32768.0


def save(path, x):
    path = os.path.join(DATA, 'sounds', path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).round().astype('<i2')
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# --- Primitives ---

def t(n):
    return np.arange(n) / SR


def secs(d):
    return int(round(d * SR))


def rng(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def pitch(x, ratio):
    """Plays x at ratio times its speed: ratio > 1 is higher and shorter."""
    up, down = int(round(1000 / ratio)), 1000
    g = np.gcd(up, down)
    return signal.resample_poly(x, up // g, down // g)


def sos(kind, freq, order=2):
    return signal.butter(order, freq, btype=kind, fs=SR, output='sos')


def lowpass(x, f, order=2):
    return signal.sosfilt(sos('lowpass', f, order), x)


def highpass(x, f, order=2):
    return signal.sosfilt(sos('highpass', f, order), x)


def bandpass(x, lo, hi, order=2):
    return signal.sosfilt(sos('bandpass', (lo, hi), order), x)


def peak_eq(x, f, gain_db, q=1.0):
    """RBJ peaking equalizer."""
    a = 10 ** (gain_db / 40)
    w = 2 * np.pi * f / SR
    alpha = np.sin(w) / (2 * q)
    b = [1 + alpha * a, -2 * np.cos(w), 1 - alpha * a]
    d = [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a]
    return signal.lfilter(b, d, x)


def shelf_high(x, f, gain_db):
    """Boosts or cuts everything above f."""
    g = 10 ** (gain_db / 20) - 1
    return x + g * highpass(x, f)


def shelf_low(x, f, gain_db):
    """Boosts or cuts everything below f."""
    g = 10 ** (gain_db / 20) - 1
    return x + g * lowpass(x, f)


def weight(x, gain_db=5):
    """Gives a weapon its low end."""
    return shelf_low(x, 140, gain_db)


def fit(x, n):
    """Pads or truncates x to n samples."""
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def fade(x, inn=0.0, out=0.0):
    x = x.copy()
    if inn:
        k = min(secs(inn), len(x))
        x[:k] *= np.linspace(0, 1, k)
    if out:
        k = min(secs(out), len(x))
        x[len(x) - k:] *= np.linspace(1, 0, k) ** 2
    return x


def trim(x, dur, out=0.03):
    return fade(fit(x, secs(dur)), out=out)


def decay(x, tau, hold=0.0):
    """Applies an exponential decay of time constant tau after hold seconds."""
    tt = t(len(x))
    return x * np.where(tt < hold, 1.0, np.exp(-(tt - hold) / tau))


def mix(dur, *layers):
    """Mixes (offset seconds, gain, samples) layers into dur seconds."""
    out = np.zeros(secs(dur))
    for offset, gain, x in layers:
        i = secs(offset)
        x = x[:max(0, len(out) - i)]
        out[i:i + len(x)] += gain * x
    return out


def normalize(x, peak=0.97):
    m = np.abs(x).max()
    return x * (peak / m) if m > 0 else x


def drive(x, amount):
    """Soft saturation, for punch."""
    return np.tanh(amount * x) / np.tanh(amount)


def noise(r, dur):
    return r.standard_normal(secs(dur))


def periodic_noise(r, dur, lo, hi):
    """Band-limited noise that loops seamlessly, filtered in the frequency domain."""
    n = secs(dur)
    spec = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(spec, n)


def osc(freq, harmonics=(1.0,), phase=0.0):
    """Additive oscillator following the instantaneous frequency array freq."""
    ph = 2 * np.pi * np.cumsum(freq) / SR + phase
    return sum(a * np.sin((k + 1) * ph) for k, a in enumerate(harmonics))


def clack(r, modes, tau=0.025, dur=0.12, grit=0.5):
    """A short metallic impact: a noise transient exciting a few decaying resonant modes."""
    n = secs(dur)
    tt = t(n)
    body = sum(np.sin(2 * np.pi * f * tt + r.uniform(0, 6.28)) * np.exp(-tt / (tau * (1 + 0.3 * i)))
               for i, f in enumerate(modes))
    click = highpass(r.standard_normal(n), 2000) * np.exp(-tt / 0.004)
    return body / len(modes) + grit * click


# --- Shared parts ---

def reload_tail(path, start=0.66):
    """The reload at the end of a Quetoo shotgun's fire sound, after its blast has died away."""
    return fade(load(path)[secs(start):], inn=0.01)


def resonance(r, dur, f0, peaks, floor=0.4, swell=2.5):
    """A machine's whine, as a recording has it: narrow resonances on the harmonics of f0, each
    (harmonic, gain, bandwidth in Hz), rung by noise over a broadband noise floor. The noise lets each
    resonance drift and flutter on its own. Built in the frequency domain, it loops seamlessly, as does
    the slow swell if dur holds whole cycles of it."""
    n = secs(dur)
    spec = np.fft.rfft(r.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    tone = sum(a / (1 + ((f - h * f0) / (bw / 2)) ** 2) for h, a, bw in peaks)
    rush = np.clip(f / 300, 0, 1) / (1 + (f / 5000) ** 2)
    tone = np.fft.irfft(spec * tone, n)
    rush = np.fft.irfft(spec * rush, n)
    x = normalize(tone) + floor * normalize(rush)
    return x * (0.8 + 0.2 * np.sin(2 * np.pi * swell * t(n)))


def varispeed(x, s):
    """Plays x back at speed s (an array, 1 is normal), as a slowing tape or motor: pitch and swell fall together."""
    pos = np.cumsum(s)
    assert pos[-1] < len(x) - 1, 'source too short'
    return np.interp(pos, np.arange(len(x)), x)


# --- The sounds ---

SOUNDS = {}


def sound(path):
    def register(fn):
        SOUNDS[path] = fn
        return fn
    return register


def machinegun(i):
    def make(r):
        src = load('weapons/machinegun/fire_%d.wav' % (i % 3 + 1))
        x = pitch(src, (1.04, 0.97, 1.08, 1.0, 0.94)[i])
        x = highpass(x, 90)
        x = peak_eq(peak_eq(x, 260, 5, 0.8), 2600, 4, 1.2)
        n = secs(0.31)
        x = fit(x, n) * (0.7 * np.exp(-t(n) / 0.025) + 0.3 * np.exp(-t(n) / 0.12))
        x = normalize(x) + 0.35 * clack(r, (2300, 3900, 6100), tau=0.006, dur=0.31)
        return trim(normalize(drive(normalize(weight(x)), 2.2)), 0.31, out=0.04)
    return make


for _i in range(5):
    sound('weapons/quake2_machinegun/fire_%d.wav' % (_i + 1))(machinegun(_i))


@sound('weapons/quake2_shotgun/fire.wav')
def shotgun(r):
    blast = shelf_high(peak_eq(highpass(load('weapons/shotgun/fire.wav'), 40), 2500, 4, 0.8), 1800, 4)
    blast = decay(fit(blast, secs(0.5)), 0.16, hold=0.05)
    crack = bandpass(noise(r, 0.12), 1500, 6000) * np.exp(-t(secs(0.12)) / 0.025)
    x = normalize(drive(normalize(weight(mix(0.5, (0, 1.0, normalize(blast)), (0, 0.25, crack)))), 1.8))
    tail = reload_tail('weapons/shotgun/fire.wav')
    return trim(mix(0.5 + len(tail) / SR, (0, 1.0, x), (0.48, 1.0, tail)), 0.5 + len(tail) / SR)


@sound('weapons/quake2_supershotgun/fire.wav')
def supershotgun(r):
    # both barrels at once: a long, heavily compressed blast with a deep thud under it
    blast = peak_eq(peak_eq(highpass(load('weapons/supershotgun/fire.wav'), 60), 280, 12, 0.5), 600, 5, 0.8)
    blast = shelf_high(blast, 2500, 2)
    blast = decay(fit(blast, secs(0.68)), 0.4, hold=0.22)
    n = secs(0.5)
    thud = np.sin(2 * np.pi * np.cumsum(80 * (1.6 * np.exp(-t(n) / 0.04) + 1)) / SR) * np.exp(-t(n) / 0.16)
    crack = bandpass(noise(r, 0.15), 1200, 8000) * np.exp(-t(secs(0.15)) / 0.035)
    x = mix(0.68, (0, 1.0, normalize(blast)), (0, 0.45, thud), (0.0, 0.35, crack), (0.012, 0.25, crack))
    x = normalize(drive(normalize(x), 3.0))
    tail = reload_tail('weapons/supershotgun/fire.wav')
    return trim(mix(0.68 + len(tail) / SR, (0, 1.0, x), (0.66, 1.0, tail)), 0.68 + len(tail) / SR)


@sound('weapons/quake2_hyperblaster/fire.wav')
def hyperblaster(r):
    # Quetoo's blaster, a fifth lower and played twice as fast, with a heavier low end
    x = load('weapons/blaster/fire.wav', af='asetrate=%d,aresample=%d,atempo=2.5' % (SR * 0.8, SR))
    x = weight(peak_eq(peak_eq(x, 90, 6, 0.8), 180, 5, 0.9), 4)
    return trim(normalize(drive(normalize(x), 1.3), 0.9), 0.4, out=0.15)


# the scream is the 7th harmonic's resonance, at 3.36 kHz, above a quieter motor. 1.6 s holds whole
# cycles of 480 Hz and of the 2.5 Hz swell, so the hum loops seamlessly
HYPER = dict(f0=480.0, peaks=((1, 0.25, 30), (2, 0.08, 40), (6, 0.12, 60), (7, 1.0, 22), (8, 0.12, 60),
                              (14, 0.05, 80)))


@sound('weapons/quake2_hyperblaster/hum.wav')
def hyperblaster_hum(r):
    return normalize(resonance(r, 1.6, **HYPER), 0.42)


@sound('weapons/quake2_hyperblaster/spindown.wav')
def hyperblaster_spindown(r):
    n = secs(1.0)
    s = 0.3 + 0.7 * np.exp(-t(n) / 0.35)
    x = varispeed(resonance(r, 1.0, **HYPER), s) * np.exp(-t(n) / 0.4)
    return trim(normalize(x, 0.48), 1.0, out=0.15)


def chaingun(r, dur, s):
    """The chaingun's motor and rattling barrels at spin-speed s (an array, 1 is full speed)."""
    n = secs(dur)
    motor = osc(960 * s, (1.0, 0.35, 0.15, 0.05))
    motor = normalize(motor) + 0.6 * normalize(periodic_noise(r, dur, 500, 1500)) * s
    # one clack per barrel passing the stop: 6 barrels at 7.5 revolutions a second at full speed
    clicks = np.zeros(n)
    phase = np.cumsum(45 * s) / SR
    for i in np.nonzero(np.diff(np.floor(phase)) > 0)[0]:
        c = clack(r, (700, 1100, 1500), tau=0.008, dur=0.04, grit=0.05)
        clicks[i:i + len(c)] += c[:n - i]
    return normalize(motor) * 0.7 + normalize(clicks) * 0.5 * np.clip(s, 0, 1) ** 0.5


@sound('weapons/quake2_chaingun/spinup.wav')
def chaingun_spinup(r):
    n = secs(0.95)
    s = 0.15 + 0.85 * (1 - np.exp(-t(n) / 0.3)) / (1 - np.exp(-0.95 / 0.3))
    return fade(normalize(chaingun(r, 0.95, s), 0.67), inn=0.01)


@sound('weapons/quake2_chaingun/hum.wav')
def chaingun_hum(r):
    # 2 s holds whole numbers of clacks and motor cycles, so the loop is seamless
    return normalize(chaingun(r, 2.0, np.ones(secs(2.0))), 0.39)


@sound('weapons/quake2_chaingun/spindown.wav')
def chaingun_spindown(r):
    n = secs(1.72)
    s = np.exp(-t(n) / 0.5)
    x = chaingun(r, 1.72, s) * np.exp(-t(n) / 0.6)
    return trim(normalize(x, 0.59), 1.72, out=0.2)


@sound('weapons/railgun/hum.wav')
def railgun_hum(r):
    # 1.2 s holds whole cycles of every component, so the hum loops seamlessly
    dur = 1.2
    tt = t(secs(dur))
    x = np.sin(2 * np.pi * 80 * tt) + 0.5 * np.sin(2 * np.pi * (97 / dur) * tt) + 0.25 * np.sin(2 * np.pi * 160 * tt)
    x *= 0.85 + 0.15 * np.sin(2 * np.pi * 2.5 * tt)
    x += 0.15 * normalize(periodic_noise(r, dur, 40, 180))
    return normalize(x, 0.5)


def main():
    global DATA
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[1])
    parser.add_argument('--data', default=DATA, help="quetoo-data's target/default")
    parser.add_argument('--only', nargs='*', help='generate only the sounds whose paths contain these')
    args = parser.parse_args()
    DATA = args.data

    for path, make in SOUNDS.items():
        if args.only and not any(o in path for o in args.only):
            continue
        x = make(rng(path))
        save(path, x)
        print('%-48s %.2fs' % (path, len(x) / SR))


if __name__ == '__main__':
    sys.exit(main())
