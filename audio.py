# -*- coding: utf-8 -*-
"""効果音（波形から作る）・BGM（music.py）・声（voice.py、任意）を混ぜて、動画の音を作る。"""
import math, wave
import numpy as np
import music

SR = 44100
BGM_LUFS = -20.0    # BGM だけの大きさ（効果音より控えめに）
MIX_LUFS = -15.0    # 仕上がりの大きさ（YouTube の基準 -14 より少し小さめ）


def env(n, att, dec):
    e = np.ones(n); a = max(1, int(att * SR)); e[:a] = np.linspace(0, 1, a)
    return e * np.exp(-np.arange(n) / (dec * SR))


class Sfx:
    """名前 → 効果音の波形"""

    def __init__(self, seed=7):
        self.rng = np.random.default_rng(seed)

    def noise(self, n):
        return self.rng.standard_normal(n)

    def swoosh(self, dur=0.35):
        n = int(max(0.2, dur) * SR); x = self.noise(n)
        x = np.convolve(x, np.ones(24) / 24, mode="same")
        x = x - np.convolve(x, np.ones(300) / 300, mode="same")
        return x * np.sin(np.linspace(0, math.pi, n)) ** 2 * 3.0

    def pop(self, f=880, dur=0.09):
        n = int(dur * SR); tt = np.arange(n) / SR
        return np.sin(2 * math.pi * f * tt) * env(n, 0.002, 0.025)

    def tick(self):
        n = int(0.05 * SR); tt = np.arange(n) / SR
        return (np.sin(2 * math.pi * 2100 * tt) * 0.7 + self.noise(n) * 0.3) * env(n, 0.0005, 0.008)

    def tone(self, f, dur, dec, harm=0.25):
        n = int(dur * SR); tt = np.arange(n) / SR
        return (np.sin(2 * math.pi * f * tt) + harm * np.sin(4 * math.pi * f * tt)) * env(n, 0.004, dec)

    def chime(self):
        a = self.tone(1046.5, 0.5, 0.18)
        b = self.tone(1568.0, 0.7, 0.25)
        out = np.zeros(int(0.12 * SR) + len(b)); out[:len(a)] += a; out[int(0.12 * SR):] += b
        return out

    def sparkle(self):
        out = np.zeros(int(0.5 * SR))
        for k, f in enumerate((2093.0, 2637.0, 3136.0, 4186.0)):
            s = self.tone(f, 0.25, 0.06, 0.0)
            i = int(k * 0.05 * SR); out[i:i + len(s)] += s * (0.8 - 0.12 * k)
        return out

    def endchord(self):
        out = np.zeros(int(1.0 * SR))
        for f in (523.25, 659.25, 783.99):
            out += self.tone(f, 1.0, 0.35, 0.1)
        return out

    def scratch(self, dur, lo, hi, rate, grit):
        """書く音（チョーク＝高めでざらざら、ペン＝やわらかいサラサラ）"""
        n = int(max(0.05, dur) * SR); tt = np.arange(n) / SR
        x = music.fft_filter(self.noise(n), SR, lo=lo, hi=hi, order=2)
        x /= max(1e-9, np.abs(x).max())
        # 1画ずつ書くような強弱（不規則なリズム）
        strokes = np.zeros(n)
        t = 0.0
        while t < dur:
            L = self.rng.uniform(0.05, 0.14) * 8 / rate
            i0, i1 = int(t * SR), int(min(dur, t + L) * SR)
            if i1 > i0:
                strokes[i0:i1] = np.sin(np.linspace(0, math.pi, i1 - i0)) ** 0.6 * self.rng.uniform(0.6, 1.0)
            t += L + self.rng.uniform(0.01, 0.05)
        g = 1 + grit * (self.noise(n) > 1.6)
        fade = np.minimum(1, np.minimum(tt / 0.01, (dur - tt) / 0.03).clip(0))
        return x * strokes * g * fade

    def chalk(self, dur): return self.scratch(dur, 1800, 7000, 9, 1.5) * 0.9
    def pen(self, dur): return self.scratch(dur, 1200, 5200, 7, 0.0) * 0.6

    def tap(self):
        n = int(0.12 * SR); tt = np.arange(n) / SR
        body = np.sin(2 * math.pi * 180 * tt) * env(n, 0.001, 0.03)
        click = music.fft_filter(self.noise(n), SR, lo=1500, order=1) * env(n, 0.0003, 0.006)
        return body * 0.8 + click * 0.6

    def eraser(self, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        x = music.fft_filter(self.noise(n), SR, lo=300, hi=2500, order=2)
        x /= max(1e-9, np.abs(x).max())
        am = 0.55 + 0.45 * np.abs(np.sin(2 * math.pi * 2.2 * tt))
        return x * am * np.sin(np.linspace(0, math.pi, n)) ** 0.5

    def flip(self, dur):
        n = int(dur * SR); tt = np.arange(n) / SR
        x = music.fft_filter(self.noise(n), SR, lo=600, hi=6000, order=1)
        x /= max(1e-9, np.abs(x).max())
        e = np.exp(-((tt - dur * 0.55) / (dur * 0.28)) ** 2)
        thup = np.zeros(n); k = int(0.08 * SR); i = int(dur * 0.85 * SR)
        thup[i:i + k] = np.sin(2 * math.pi * 120 * np.arange(min(k, n - i)) / SR) * np.exp(-np.arange(min(k, n - i)) / (0.02 * SR))
        return x * e * 0.8 + thup * 0.5

    def stick(self):
        n = int(0.15 * SR)
        x = music.fft_filter(self.noise(n), SR, lo=400, hi=3000, order=1)
        x /= max(1e-9, np.abs(x).max())
        return x * env(n, 0.002, 0.03)

    def make(self, name, dur, write_kind):
        if name.startswith("pop"):
            return self.pop((783.99, 987.77, 1174.66)[int(name[3:] or 0) % 3])   # ソ・シ・レ（BGMの和音に合わせる）
        if name == "write":
            return self.chalk(dur) if write_kind == "chalk" else self.pen(dur)
        if name == "circle":
            return (self.chalk(dur) if write_kind == "chalk" else self.pen(dur)) * 1.1
        if name in ("swoosh", "eraser", "flip"):
            return getattr(self, name)(dur or 0.35)
        return getattr(self, name)()


def duck_env(x, depth, att=0.005, rel=0.15, thresh=0.5):
    hop = int(att * SR)
    nf = (len(x) + hop - 1) // hop
    pk = np.array([np.abs(x[i * hop:(i + 1) * hop]).max(initial=0.0) for i in range(nf)])
    a = np.exp(-hop / SR / rel)
    env_, cur = np.zeros(nf), 0.0
    for i in range(nf):
        cur = max(pk[i], a * cur); env_[i] = cur
    g = 1.0 - depth * np.clip(env_ / thresh, 0.0, 1.0)
    return np.interp(np.arange(len(x)) / hop, np.arange(nf) + 0.5, g)


def build(look, path, dur, times, bgm=True, voices=()):
    """look.sounds() の効果音、BGM、声を混ぜて path（wav）に書く"""
    sx = Sfx(7)
    n = int(SR * dur)
    buf = np.zeros(n + SR * 2)
    for name, t0, gain, d in look.sounds():
        sig = sx.make(name, d, getattr(look, "write_kind", "pen"))
        i = int(max(0.0, t0) * SR)
        if t0 < 0:
            sig = sig[int(-t0 * SR):]
        m = min(len(sig), len(buf) - i)
        buf[i:i + m] += sig[:m] * gain
    sfx = buf[:n]
    sfx = sfx / max(1e-9, np.abs(sfx).max()) * 0.8
    vo = np.zeros(n)
    for t0, x in voices:
        i = int(t0 * SR); m = min(len(x), n - i)
        if m > 0:
            vo[i:i + m] += x[:m]
    if voices:
        vo = vo / max(1e-9, np.abs(vo).max()) * 0.9
        sfx = sfx * 0.7                                   # 声があるときは効果音を少し控えめに
    if bgm:
        ml, mr = music.build_music(SR, dur, times["count0"], times["reveal"], times["ticks"], mix=getattr(look, "bgm_mix", None))
        duck = duck_env(sfx, 0.45)                        # 効果音が鳴るあいだは、BGMを少し下げる
        if voices:
            duck = duck * duck_env(vo, 0.6, rel=0.25, thresh=0.3)
        ml, mr = ml * duck, mr * duck
        g = 10 ** ((BGM_LUFS - (3 if voices else 0) - music.loudness(ml, mr, SR)) / 20)
        left, right = sfx + vo + ml * g, sfx + vo + mr * g
    else:
        left, right = sfx + vo, sfx + vo
    g = 10 ** ((MIX_LUFS - music.loudness(left, right, SR)) / 20)
    left, right = music.limit(left * g, right * g, SR)
    pcm = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
