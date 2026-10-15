# -*- coding: utf-8 -*-
"""動画のBGMを、プログラムだけで作る（音源ファイルは使わない）。

120BPM・ハ長調。動画の流れに合わせて、次のように進む。
  はじめ〜カウントダウン前 ：王道進行（Fmaj7→G→Em7→Am7）の軽いポップ
  カウントダウン（3秒前〜）：リズムを止め、Gsus4→G7 で「ため」。時計の音に合わせて低い「ドン」
  正解の瞬間               ：C（主和音）で解決して、明るいリズムに戻る
  おわり                   ：Fmaj7→C で着地して、ゆっくり小さくなる（くり返し再生でも自然につながる）
"""
import numpy as np

TAU = 2 * np.pi

# 和音ごとの音（MIDIの番号。60＝ド）
CHORDS = {
    "Fmaj7": {"ep": [57, 60, 64], "bass": 41, "arp": [65, 69, 72, 76]},
    "G": {"ep": [55, 59, 62], "bass": 43, "arp": [67, 71, 74, 79]},
    "Em7": {"ep": [55, 59, 62, 64], "bass": 40, "arp": [64, 67, 71, 74]},
    "Am7": {"ep": [55, 60, 64], "bass": 45, "arp": [69, 72, 76, 79]},
    "C": {"ep": [60, 64, 67, 72], "bass": 48, "arp": [72, 76, 79, 84]},
    "G/B": {"ep": [59, 62, 67], "bass": 47, "arp": [71, 74, 79, 83]},
    "Cend": {"ep": [60, 64, 67, 72], "bass": 48, "arp": [72, 76, 79, 84]},
}
PROG_A = ["Fmaj7", "G", "Em7", "Am7"]

# 楽器ごとの音量
G_EP, G_PAD, G_BASS, G_ARP = 0.20, 0.060, 0.24, 0.15
G_KICK, G_CLAP, G_HAT, G_CRASH = 0.40, 0.28, 0.085, 0.08


def hz(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _t(n, sr):
    return np.arange(n) / sr


def fft_filter(x, sr, lo=None, hi=None, order=2):
    """位相のずれない簡単なフィルター（lo より下・hi より上を削る）。"""
    n = len(x)
    size = 1 << max(1, (n - 1).bit_length())
    f = np.fft.rfftfreq(size, 1.0 / sr)
    h = np.ones_like(f)
    if lo:
        h /= np.sqrt(1.0 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    if hi:
        h /= np.sqrt(1.0 + (f / hi) ** (2 * order))
    return np.fft.irfft(np.fft.rfft(x, size) * h, size)[:n]


def shelf(x, sr, f0, db):
    """f0 より上をなめらかに db だけ持ち上げる（スマホのスピーカーでも聞こえやすく）。"""
    n = len(x)
    size = 1 << max(1, (n - 1).bit_length())
    f = np.fft.rfftfreq(size, 1.0 / sr)
    h = 10.0 ** (db / 20.0 / (1.0 + (f0 / np.maximum(f, 1e-3)) ** 2))
    return np.fft.irfft(np.fft.rfft(x, size) * h, size)[:n]


def bell(x, sr, f0, db, octaves=0.7):
    """f0 のまわりだけを db だけ上げ下げする（こもりを取る）。"""
    n = len(x)
    size = 1 << max(1, (n - 1).bit_length())
    f = np.maximum(np.fft.rfftfreq(size, 1.0 / sr), 1e-3)
    h = 10.0 ** (db / 20.0 * np.exp(-np.log2(f / f0) ** 2 / (2 * octaves ** 2)))
    return np.fft.irfft(np.fft.rfft(x, size) * h, size)[:n]


def conv(x, h):
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[: len(x)]


def pan_gains(p):
    a = (p + 1.0) * np.pi / 4.0
    return np.cos(a), np.sin(a)


class Mixer:
    def __init__(self, sr, dur):
        self.sr, self.n = sr, int(sr * dur)
        self.dry = np.zeros((self.n, 2))
        self.send = np.zeros((self.n, 2))

    def add(self, t0, sig, gain=1.0, pan=0.0, rev=0.0):
        i = int(round(t0 * self.sr))
        if i >= self.n or i < 0:
            return
        sig = np.asarray(sig, dtype=float)
        if sig.ndim == 1:
            gl, gr = pan_gains(pan)
            sig = np.stack([sig * gl, sig * gr], axis=1)
        m = min(len(sig), self.n - i)
        self.dry[i:i + m] += sig[:m] * gain
        if rev:
            self.send[i:i + m] += sig[:m] * gain * rev


# ---------- 楽器 ----------
def ep_note(f, dur, sr, vel=1.0):
    """エレピ（FM音源の定番の作り方）。"""
    n = int((dur + 0.6) * sr)
    t = _t(n, sr)
    i1 = (1.4 + 0.6 * vel) * np.exp(-t / 0.6) + 0.25
    body = np.sin(TAU * f * t + i1 * np.sin(TAU * f * t))
    i2 = 1.4 * vel * np.exp(-t / 0.02)
    tine = 0.30 * np.exp(-t / 0.16) * np.sin(TAU * f * t + i2 * np.sin(TAU * 14.0 * f * t))
    amp = (1.0 - np.exp(-t / 0.0015)) * np.exp(-t / 1.5)
    rel = t > dur
    amp[rel] *= np.exp(-(t[rel] - dur) / 0.08)
    return (body + tine) * amp * vel


def ep_chord(notes, dur, sr, vel=0.8, strum=0.007):
    n = int((dur + 0.7) * sr)
    out = np.zeros((n, 2))
    for j, m in enumerate(notes):
        off = int(j * strum * sr)
        for cents, p in ((-4.0, -0.4), (4.0, 0.4)):
            s = ep_note(hz(m) * 2.0 ** (cents / 1200.0), dur, sr, vel)
            gl, gr = pan_gains(p)
            k = min(len(s), n - off)
            out[off:off + k, 0] += s[:k] * gl * 0.6
            out[off:off + k, 1] += s[:k] * gr * 0.6
    return out


def pad_chord(notes, dur, sr, bright=0.35, bright_end=None, attack=0.15, release=0.3, amp_end=1.0):
    """やわらかい持続音。bright を上げると明るく（フィルターが開く感じに）なる。"""
    n = int((dur + release * 5) * sr)
    t = _t(n, sr)
    x = np.clip(t / max(dur, 1e-6), 0.0, 1.0)
    b = bright + ((bright_end if bright_end is not None else bright) - bright) * x
    env = np.minimum(1.0, t / attack) * (1.0 + (amp_end - 1.0) * x)
    rel = t > dur
    env[rel] *= np.exp(-(t[rel] - dur) / release)
    out = np.zeros((n, 2))
    for m in notes:
        f0 = hz(m)
        for cents, ch in ((-7.0, 0), (7.0, 1)):
            f = f0 * 2.0 ** (cents / 1200.0)
            v = np.zeros(n)
            for k in range(1, 10):
                if k * f > 5000:
                    break
                w = (1.0 / k) * np.exp(-(k - 1) * (1.8 - 1.55 * b))
                v += w * np.sin(TAU * k * f * t + 0.9 * k + 0.37 * m)
            out[:, ch] += v
    return out * env[:, None] / max(1, len(notes))


def bass_note(f, dur, sr, vel=1.0):
    n = int((dur + 0.06) * sr)
    t = _t(n, sr)
    y = np.zeros(n)
    for k, a in enumerate((1.0, 0.55, 0.32, 0.2, 0.12, 0.07), start=1):
        y += a * (0.35 + 0.65 * np.exp(-t * (k - 1) * 5.0)) * np.sin(TAU * k * f * t)
    amp = (1.0 - np.exp(-t / 0.003)) * (0.75 + 0.25 * np.exp(-t / 0.12))
    rel = t > dur
    amp[rel] *= np.exp(-(t[rel] - dur) / 0.02)
    return np.tanh(1.3 * y * amp) / np.tanh(1.3) * vel


def marimba(f, sr, vel=1.0):
    n = int(0.9 * sr)
    t = _t(n, sr)
    y = (np.sin(TAU * f * t) * np.exp(-t / 0.30)
         + 0.40 * np.sin(TAU * 3.98 * f * t) * np.exp(-t / 0.05)
         + 0.06 * np.sin(TAU * 9.85 * f * t) * np.exp(-t / 0.016))
    return y * (1.0 - np.exp(-t / 0.0012)) * vel


def kick(sr, rng, vel=1.0):
    n = int(0.4 * sr)
    t = _t(n, sr)
    f = 48.0 + 115.0 * np.exp(-t / 0.03)
    y = np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / 0.17)
    y = np.tanh(1.8 * y) / np.tanh(1.8)
    click = fft_filter(rng.standard_normal(n), sr, lo=2000, order=1) * np.exp(-t / 0.0015) * 0.25
    return (y + click) * vel


def clap(sr, rng, vel=1.0):
    n = int(0.35 * sr)
    t = _t(n, sr)
    noise = fft_filter(rng.standard_normal(n), sr, lo=900, hi=3200, order=2)
    e = np.zeros(n)
    for d in (0.0, 0.010, 0.021):
        m = t >= d
        e[m] += np.exp(-(t[m] - d) / 0.0045)
    e += 0.6 * np.exp(-t / 0.085) * (t >= 0.021)
    y = noise * e
    return y / max(1e-9, np.abs(y).max()) * vel


def hat(sr, rng, vel=1.0, open_=False):
    n = int((0.4 if open_ else 0.09) * sr)
    t = _t(n, sr)
    y = fft_filter(rng.standard_normal(n), sr, lo=7000, hi=14000, order=2) * np.exp(-t / (0.10 if open_ else 0.022))
    return y / max(1e-9, np.abs(y).max()) * vel


def crash(sr, rng, dur=2.2, vel=1.0):
    n = int(dur * sr)
    t = _t(n, sr)
    out = np.zeros((n, 2))
    for ch in range(2):
        y = fft_filter(rng.standard_normal(n), sr, lo=3500, hi=11000, order=1)
        out[:, ch] = y * (1.0 - np.exp(-t / 0.002)) * np.exp(-t / 0.7)
    return out / max(1e-9, np.abs(out).max()) * vel


def riser(sr, rng, dur):
    n = int(dur * sr)
    t = _t(n, sr)
    x = t / dur
    out = np.zeros((n, 2))
    sweep = np.sin(TAU * np.cumsum(300.0 * 2.0 ** (2.0 * x)) / sr) * 0.18
    for ch in range(2):
        y = fft_filter(rng.standard_normal(n), sr, lo=1500, hi=9000, order=1)
        y = y / max(1e-9, np.abs(y).max())
        out[:, ch] = (y + sweep) * x ** 2.2
    return out


def thump(sr):
    n = int(0.3 * sr)
    t = _t(n, sr)
    f = 50.0 + 40.0 * np.exp(-t / 0.04)
    return np.sin(TAU * np.cumsum(f) / sr) * np.exp(-t / 0.12) * (1.0 - np.exp(-t / 0.004))


def reverb_ir(sr, rng, rt60=1.5):
    n = int(sr * rt60)
    t = _t(n, sr)
    irs = []
    for _ in range(2):
        x = fft_filter(rng.standard_normal(n), sr, lo=250, hi=5500, order=1) * np.exp(-6.9 * t / rt60)
        k = int(0.015 * sr)
        x[:k] *= np.linspace(0.0, 1.0, k)
        irs.append(x / np.sqrt(np.sum(x ** 2)))
    return irs


# ---------- 曲の組み立て ----------
def build_music(sr, dur, count0, reveal, ticks, seed=11):
    """BGM（左右2ch、長さ dur 秒）を返す。count0：カウントダウン開始、reveal：正解の瞬間、ticks：時計の音の時刻。"""
    rng = np.random.default_rng(seed)
    mx = Mixer(sr, dur)
    gap = reveal - 0.08  # 正解の直前に一瞬だけ音を止める

    chords = []
    t, k = 0.0, 0
    while t + 1.0 <= count0 - 0.5 + 1e-9:
        chords.append((t, 1.0, PROG_A[k % 4], "A"))
        t += 1.0
        k += 1
    if count0 - t > 0.05:
        chords.append((t, count0 - t, "G", "A"))
    chords += [(reveal, 1.0, "C", "B"), (reveal + 1.0, 1.0, "G/B", "B"), (reveal + 2.0, 1.0, "Am7", "B"),
               (reveal + 3.0, 0.5, "Fmaj7", "B"), (reveal + 3.5, max(0.5, dur - reveal - 3.5), "Cend", "B")]

    for t0, length, name, sec in chords:
        if t0 >= dur:
            continue
        c = CHORDS[name]
        final = name == "Cend"
        # エレピ：頭と「ウラ」で刻む
        mx.add(t0, ep_chord(c["ep"], length if final else length - 0.04, sr, vel=0.85), G_EP, rev=0.35)
        if length >= 1.0 and not final:
            mx.add(t0 + 0.75, ep_chord(c["ep"], 0.18, sr, vel=0.5), G_EP, rev=0.35)
        # パッド
        mx.add(t0, pad_chord(c["ep"], length, sr, bright=0.5, attack=0.12, release=0.25), G_PAD, rev=0.3)
        # ベース
        b = c["bass"]
        if final:
            mx.add(t0, bass_note(hz(b), length - 0.15, sr), G_BASS)
        else:
            mx.add(t0, bass_note(hz(b), min(0.42, length - 0.05), sr), G_BASS)
            if length >= 1.0:
                mx.add(t0 + 0.5, bass_note(hz(b), 0.2, sr, vel=0.7), G_BASS)
                mx.add(t0 + 0.75, bass_note(hz(b + 12), 0.2, sr, vel=0.75), G_BASS)
        # マリンバの分散和音
        arp = c["arp"]
        if final:
            for j, m in enumerate(arp):
                mx.add(t0 + 0.125 * j, marimba(hz(m), sr, 0.8), G_ARP, pan=(-0.3, 0.3)[j % 2], rev=0.4)
        else:
            vel_b = 1.0 if sec == "B" else 0.8
            for dt, idx, v in ((0.0, 0, 0.85), (0.25, 2, 0.55), (0.5, 1, 0.7), (0.75, 3, 0.55)):
                if dt < length - 0.01:
                    mx.add(t0 + dt, marimba(hz(arp[idx]), sr, v * vel_b), G_ARP, pan=(-0.25, 0.25)[idx % 2], rev=0.4)

    # リズム（はじめの部分）
    def groove(t_from, t_to, energy):
        s = t_from
        while s < t_to - 1e-9:
            pos = round((s - t_from) / 0.25) % 4
            if pos == 0:
                mx.add(s, kick(sr, rng, 0.9), G_KICK)
            if pos == 2:
                mx.add(s, clap(sr, rng, 0.45 + 0.25 * energy), G_CLAP, rev=0.25)
                if energy > 0.5:
                    mx.add(s, kick(sr, rng, 0.6), G_KICK)
            if pos in (1, 3):
                mx.add(s, hat(sr, rng, 0.6 + 0.2 * energy, open_=energy > 0.5), G_HAT * (0.8 if energy > 0.5 else 1.0), pan=-0.2)
            else:
                mx.add(s, hat(sr, rng, 0.35), G_HAT, pan=-0.2)
            s += 0.25

    groove(0.0, count0 - 0.5, 0.0)
    # カウントダウンへのつなぎ（小さな連打）
    mx.add(count0 - 0.5, kick(sr, rng, 0.9), G_KICK)
    for j in range(4):
        mx.add(count0 - 0.5 + 0.125 * j, clap(sr, rng, 0.25 + 0.12 * j), G_CLAP, rev=0.25)

    # カウントダウン：Gsus4 → G7 で ため、時計に合わせて「ドン」
    half = (gap - count0) * 0.6
    mx.add(count0, pad_chord([55, 60, 62, 67], half, sr, bright=0.3, bright_end=0.65, attack=0.25, release=0.15, amp_end=1.5), G_PAD * 2.2, rev=0.3)
    mx.add(count0 + half, pad_chord([55, 59, 62, 65], gap - count0 - half, sr, bright=0.65, bright_end=1.0, attack=0.05, release=0.015, amp_end=1.6), G_PAD * 3.3, rev=0.3)
    mx.add(count0, bass_note(hz(43), gap - count0 - 0.02, sr, vel=0.5), G_BASS)
    for tk in ticks:
        mx.add(tk, thump(sr), 0.45)
    mx.add(count0 + 0.3, riser(sr, rng, gap - count0 - 0.3), 0.05)

    # 正解のあと：明るいリズム
    mx.add(reveal, crash(sr, rng, vel=0.9), G_CRASH, rev=0.2)
    groove(reveal, reveal + 3.5, 1.0)
    mx.add(reveal + 3.5, kick(sr, rng, 0.9), G_KICK)
    mx.add(reveal + 3.5, crash(sr, rng, vel=0.6), G_CRASH, rev=0.2)

    # 響き（リバーブ）
    ir = reverb_ir(sr, rng)
    wet = np.stack([conv(mx.send[:, 0], ir[0]), conv(mx.send[:, 1], ir[1])], axis=1)
    out = mx.dry + wet * 0.55

    # 正解の直前の「間」、最初と最後のフェード
    t = _t(mx.n, sr)
    g = np.ones(mx.n)
    m = (t >= gap) & (t < reveal)
    g[m] = 0.0
    g[(t >= gap - 0.02) & (t < gap)] = np.linspace(1.0, 0.0, int(np.sum((t >= gap - 0.02) & (t < gap))))
    g[t < 0.01] = t[t < 0.01] / 0.01
    fade0 = dur - 0.8
    m = t >= fade0
    g[m] *= 0.12 + 0.88 * np.cos((t[m] - fade0) / 0.8 * np.pi / 2) ** 2
    out *= g[:, None]
    return tuple(bell(shelf(fft_filter(out[:, ch], sr, lo=50, order=2), sr, 1600.0, 6.0), sr, 450.0, -3.0) for ch in (0, 1))


# ---------- 音量をそろえる ----------
_K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
_K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def _k_weight(x, sr):
    n = len(x)
    size = 1 << (n - 1).bit_length()
    f = np.fft.rfftfreq(size, 1.0 / sr)
    z = np.exp(-1j * TAU * f / 48000.0)
    h = np.ones_like(z)
    for b, a in (_K1, _K2):
        h *= (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
    return np.fft.irfft(np.fft.rfft(x, size) * h, size)[:n]


def loudness(left, right, sr):
    """だいたいのラウドネス（LUFS、ITU-R BS.1770 の考え方）。"""
    kl, kr = _k_weight(left, sr), _k_weight(right, sr)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    ms = []
    for i in range(0, max(1, len(kl) - blk + 1), hop):
        ms.append(np.mean(kl[i:i + blk] ** 2) + np.mean(kr[i:i + blk] ** 2))
    ms = np.array(ms)
    lk = -0.691 + 10 * np.log10(np.maximum(ms, 1e-12))
    ms = ms[lk > -70]
    if len(ms) == 0:
        return -70.0
    rel = -0.691 + 10 * np.log10(np.mean(ms)) - 10
    ms2 = ms[(-0.691 + 10 * np.log10(ms)) > rel]
    return float(-0.691 + 10 * np.log10(np.mean(ms2 if len(ms2) else ms)))


def limit(left, right, sr, ceiling=0.95, release=0.08):
    """先読みつきの簡単なリミッター（音が割れないように、大きいところだけ下げる）。"""
    st = np.stack([left, right], axis=1)
    hop = int(0.002 * sr)
    nf = (len(st) + hop - 1) // hop
    pk = np.zeros(nf)
    for i in range(nf):
        pk[i] = np.abs(st[i * hop:(i + 1) * hop]).max(initial=0.0)
    need = np.minimum(1.0, ceiling / np.maximum(pk, 1e-9))
    look = 3
    need = np.array([need[max(0, i - look):i + look + 1].min() for i in range(nf)])
    g = np.ones(nf)
    a = np.exp(-hop / sr / release)
    cur = 1.0
    for i in range(nf):
        cur = need[i] if need[i] < cur else a * cur + (1 - a) * need[i]
        g[i] = cur
    gs = np.interp(np.arange(len(st)) / hop, np.arange(nf) + 0.5, g)
    st = st * gs[:, None]
    return np.clip(st[:, 0], -ceiling, ceiling), np.clip(st[:, 1], -ceiling, ceiling)
