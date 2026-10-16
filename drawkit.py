# -*- coding: utf-8 -*-
"""動画の絵を描くための共通の道具（文字・図形・手書き風の線・質感）。

座標はすべて「720×1280 の画面」を基準に書く（論理座標）。
実際の画質（1080×1920 など）には setup() で合わせ、内部で R 倍して描く。
"""
import math, os, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LW, LH = 720, 1280          # 論理座標の画面
R = 1.0                     # 論理座標 → 実際の画素 の倍率
W, H = LW, LH               # 実際の画素数

# YouTube ショートで題名やボタンが重なる所を避けた「大事な文字を置いてよい範囲」（論理座標・目安）
SAFE = {"left": 36, "right": 600, "top": 92, "bottom": 950}
CX = (SAFE["left"] + SAFE["right"]) / 2      # 安全な範囲の真ん中


def setup(out_w, out_h):
    global R, W, H
    R, W, H = out_w / LW, out_w, out_h
    _fonts.clear(); _sprites.clear()


# ---------- 便利関数 ----------
def clamp(v, a=0.0, b=1.0): return max(a, min(b, v))
def prog(t, t0, t1): return clamp((t - t0) / (t1 - t0)) if t1 > t0 else (1.0 if t >= t1 else 0.0)
def ease_out(p): return 1 - (1 - p) ** 3
def ease_in(p): return p ** 3
def ease_in_out(p): return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
def ease_back(p, s=1.70158): return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2
def mix(c1, c2, p): return tuple(int(c1[i] + (c2[i] - c1[i]) * p) for i in range(4))


def rgba(c, a=255):
    """'#RRGGBB' や [r,g,b] を (r,g,b,a) にする"""
    if isinstance(c, str):
        c = c.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)
    c = tuple(int(v) for v in c)
    return c if len(c) == 4 else c + (a,)


def with_alpha(c, a):
    return (c[0], c[1], c[2], int(a))


# ---------- フォント・文字 ----------
FONT_FILES = {
    "Black": ["fonts/NotoSansJP-Black-subset.otf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
    "Bold": ["fonts/NotoSansJP-Bold-subset.otf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"],
    "Medium": ["fonts/NotoSansJP-Medium-subset.otf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"],
}
_fonts = {}


def font(weight, px):
    key = (weight, px)
    if key not in _fonts:
        for p in FONT_FILES[weight]:
            path = p if os.path.isabs(p) else os.path.join(HERE, p)
            if os.path.exists(path):
                _fonts[key] = ImageFont.truetype(path, max(1, int(round(px * R))), index=0)
                break
        else:
            raise SystemExit("フォントが見つかりません：" + weight)
    return _fonts[key]


def segments(text, base, accent):
    """「*強調*」を accent 色にした [(文字, 色, 強調か)] にする"""
    out, on = [], False
    for part in str(text).split("*"):
        if part:
            out.append((part, accent if on else base, on))
        on = not on
    return out


NO_HEAD = set("、。，．・：；？！ー～」』）】〕｝〉》’”…‥ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ%％")  # 行の頭に来ないほうがよい文字
NO_TAIL = set("「『（【〔｛〈《‘“")


def _kind(ch):
    if "\u3041" <= ch <= "\u309f":
        return "ひ"
    if "\u30a0" <= ch <= "\u30ff" or ch == "ー":
        return "カ"
    if ch.isascii() and ch.isalnum() or ch in "０１２３４５６７８９．.%％":
        return "英"
    if "\u4e00" <= ch <= "\u9fff" or ch in "々〆":
        return "漢"
    return "他"


PARTICLES = set("はがをにでともやのへ")
NO_BREAK_WORDS = []      # 途中で改行しない言葉（themes の「改行しない言葉」から入る）


def _break_score(prev, nxt):
    """prev と nxt の間で改行してよいかの点数（大きいほど自然。0＝言葉の途中なので避けたい）"""
    a, b = prev[0], nxt[0]
    if b in NO_HEAD or a in NO_TAIL:
        return -1
    if a in "、。，．！？」』）】・：；":
        s = 3
    elif b in "「『（【":
        s = 3
    elif _kind(a) == "ひ" and _kind(b) in "漢カ英他":
        s = 3          # 「から｜午前」「の｜時刻」
    elif a in PARTICLES and _kind(b) == "ひ":
        s = 1          # 「表示は｜いらない」
    else:
        s = 0
    if s > 0 and prev[2] and nxt[2]:
        s -= 1         # 強調のまとまりは、なるべく分けない
    return s


def _wrap_line(chars, f, max_px, nice=True):
    """chars: [(文字, 色, 強調)] を1行 max_px に収まるように折り返す。
    言葉の途中で切らないよう、少し前の「切ってよい所」（ひらがな→漢字の変わり目・句読点など）で改行する。"""
    lines, cur, w = [], [], 0.0
    text = "".join(c[0] for c in chars)
    glue_all = set()                       # 「改行しない言葉」の中の切れ目（文字の位置）
    for word in NO_BREAK_WORDS:
        for m in re.finditer(re.escape(word), text):
            glue_all.update(range(m.start() + 1, m.end()))
    start = 0                              # cur[0] が chars の何文字目か
    for c in chars:
        cw = f.getlength(c[0])
        if cur and w + cw > max_px:
            seq = cur + [c]
            glue = {g - start for g in glue_all}
            look = max(1, min(10, int(len(cur) * 0.6)))
            best, best_s = None, 0
            for k in (range(len(cur), max(0, len(cur) - look), -1) if nice else ()):   # 改行は seq[k-1] と seq[k] の間
                if k < 1:
                    break
                sc = -1 if k in glue else _break_score(seq[k - 1], seq[k])
                if sc > best_s:
                    best, best_s = k, sc
                    if sc >= 3:
                        break
            if best is None:          # よい所が無い：禁則だけ守って、ここで切る
                best = len(cur)
                while best > 1 and (seq[best][0] in NO_HEAD or seq[best - 1][0] in NO_TAIL):
                    best -= 1
            lines.append(cur[:best])
            cur = cur[best:]
            start += best
            w = sum(f.getlength(x[0]) for x in cur)
        cur.append(c); w += cw
    if cur:
        lines.append(cur)
    return lines


def _merge(chars):
    out = []
    for ch, col, emp in chars:
        if out and out[-1][1] == col and out[-1][2] == emp:
            out[-1] = (out[-1][0] + ch, col, emp)
        else:
            out.append((ch, col, emp))
    return out


def layout(text_lines, weight, max_w, max_lines, px, min_px, step=2):
    """文字の大きさを px から min_px まで下げながら、横幅 max_w・max_lines 行に収まる大きさを探す。
    言葉の切れ目で改行でき、最後の行がぽつんと短くならない大きさを優先する。ただしそのために小さくしすぎない（元の84%まで）。
    text_lines: 段落ごとの [(文字, 色, 強調)]。返り値：(行のリスト, 文字の大きさ, 収まったか)"""
    p, fallback, lines = px, None, []
    while True:
        f = font(weight, p)
        for nice in (True, False):
            lines, orphan = [], False
            for segs in text_lines:
                chars = [(ch, col, emp) for s, col, emp in segs for ch in s]
                ls = _wrap_line(chars, f, max_w * R, nice) if chars else [[]]
                orphan |= len(ls) > 1 and len(ls[-1]) <= 3       # 折り返した最後の行が3文字以下
                lines += ls
            fits = len(lines) <= max_lines
            if fits and nice and not orphan:
                return [_merge(l) for l in lines], p, True
            if fits and fallback is None:
                fallback = ([_merge(l) for l in lines], p, True)
        if fallback and p - step < max(min_px, fallback[1] * 0.84):
            return fallback
        if p <= min_px:
            return fallback or ([_merge(l) for l in lines], p, False)
        p -= step


class TextBlock:
    """折り返し済みの文字のかたまり。行ごとの画像と、強調部分の位置を持つ。"""

    def __init__(self, text_lines, weight, max_w, max_lines, px, min_px, line_h=1.32, align="left"):
        self.lines, self.px, self.fits = layout(text_lines, weight, max_w, max_lines, px, min_px)
        self.weight, self.align = weight, align
        self.line_h = self.px * line_h
        f = font(weight, self.px)
        self.widths = [sum(f.getlength(s) for s, _, _ in l) / R for l in self.lines]
        self.w = max(self.widths) if self.widths else 0
        self.h = self.line_h * len(self.lines)
        self.max_w = max_w
        self.spans = []   # 強調部分 (行番号, x0, x1)：行の左端からの論理座標
        for i, l in enumerate(self.lines):
            x = 0.0
            for s, col, emp in l:
                w = f.getlength(s) / R
                if emp:
                    self.spans.append((i, x, x + w))
                x += w
        self._imgs = None

    def line_x(self, i, x0):
        """行 i の左端（align に合わせる）"""
        if self.align == "center":
            return x0 - self.widths[i] / 2
        return x0

    def line_images(self, recolor=None):
        """行ごとの文字の画像（RGBA）。recolor={元の色: 新しい色} で色を差し替えられる。"""
        key = ("tb", self.weight, self.px, tuple(tuple(l) for l in self.lines), tuple(sorted((recolor or {}).items())))
        if key in _sprites:
            return _sprites[key]
        f = font(self.weight, self.px)
        asc, desc = f.getmetrics()
        pad = int(4 * R)
        hh = int(self.line_h * R)
        imgs = []
        for i, l in enumerate(self.lines):
            img = Image.new("RGBA", (int(self.widths[i] * R) + pad * 2 + 2, hh + pad * 2), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            x = pad
            base = pad + (hh - (asc + desc)) / 2 + asc
            for s, col, emp in l:
                c = (recolor or {}).get(col, col)
                d.text((x, base), s, font=f, fill=c, anchor="ls")
                x += f.getlength(s)
            imgs.append(img)
        _sprites[key] = imgs
        return imgs


_sprites = {}


def cached(key, make):
    if key not in _sprites:
        _sprites[key] = make()
    return _sprites[key]


def text_sprite(text, color, weight, px):
    """1行だけの文字の画像（強調なし）"""
    key = ("ts", text, color, weight, px)
    if key in _sprites:
        return _sprites[key]
    f = font(weight, px)
    asc, desc = f.getmetrics()
    pad = int(4 * R)
    img = Image.new("RGBA", (int(f.getlength(text)) + pad * 2 + 2, asc + desc + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad, pad + asc), text, font=f, fill=color, anchor="ls")
    _sprites[key] = img
    return img


PAD = 4  # 文字の画像のまわりの余白（論理座標）


# ---------- 貼りつけ ----------
def fade(spr, alpha):
    if alpha >= 0.999:
        return spr
    a = np.asarray(spr.getchannel("A"), dtype=np.float32) * alpha
    spr = spr.copy()
    spr.putalpha(Image.fromarray(a.astype(np.uint8)))
    return spr


def paste(canvas, spr, x, y, alpha=1.0, scale=1.0, anchor="lt", angle=0.0):
    """論理座標 (x, y) に画像を貼る。anchor：lt=左上、ct=上の真ん中、cc=真ん中、lc=左の真ん中"""
    if spr is None or alpha <= 0.003 or scale <= 0.01:
        return
    if angle:
        spr = spr.rotate(angle, resample=Image.BICUBIC, expand=True)
    if abs(scale - 1.0) > 1e-3:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
    spr = fade(spr, alpha)
    X, Y = int(round(x * R)), int(round(y * R))
    if anchor[0] == "c": X -= spr.width // 2
    elif anchor[0] == "r": X -= spr.width
    if anchor[1] == "c": Y -= spr.height // 2
    elif anchor[1] == "b": Y -= spr.height
    blit(canvas, spr, X, Y)


def blit(canvas, spr, X, Y):
    l, t = max(0, X), max(0, Y)
    r, b = min(canvas.width, X + spr.width), min(canvas.height, Y + spr.height)
    if r <= l or b <= t:
        return
    if (l, t, r, b) != (X, Y, X + spr.width, Y + spr.height):
        spr = spr.crop((l - X, t - Y, r - X, b - Y))
    canvas.alpha_composite(spr, dest=(l, t))


def crop_reveal(spr, frac, soft=0.0):
    """左から frac（0〜1）の幅だけ見せる（書いている途中のように）"""
    if frac >= 1.0:
        return spr
    if frac <= 0.0:
        return None
    w = max(1, int(spr.width * frac))
    out = spr.crop((0, 0, w, spr.height))
    if soft > 0:
        k = min(w, int(soft * R))
        if k > 1:
            a = np.asarray(out.getchannel("A"), dtype=np.float32)
            a[:, w - k:] *= np.linspace(1.0, 0.0, k)[None, :]
            out = out.copy(); out.putalpha(Image.fromarray(a.astype(np.uint8)))
    return out


# ---------- なめらかな図形（2倍で描いて縮める） ----------
SS = 2


def aa_shape(w, h, draw_fn, pad=4):
    """w×h（論理座標）の画像を作る。draw_fn(draw, k) の k は「論理座標 → 下書きの画素」の倍率。左上が (pad, pad)。"""
    k = R * SS
    img = Image.new("RGBA", (int((w + pad * 2) * k), int((h + pad * 2) * k)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_fn(d, k, pad)
    return img.resize((max(1, int((w + pad * 2) * R)), max(1, int((h + pad * 2) * R))), Image.LANCZOS)


def rrect(w, h, r, fill, outline=None, width=0):
    key = ("rr", w, h, r, fill, outline, width)
    def make():
        def fn(d, k, pad):
            d.rounded_rectangle([pad * k, pad * k, (pad + w) * k - 1, (pad + h) * k - 1], radius=r * k, fill=fill,
                                outline=outline, width=int(width * k))
        return aa_shape(w, h, fn)
    return cached(key, make)


def circle(r, fill, outline=None, width=0):
    key = ("ci", r, fill, outline, width)
    def make():
        def fn(d, k, pad):
            d.ellipse([pad * k, pad * k, (pad + 2 * r) * k - 1, (pad + 2 * r) * k - 1], fill=fill, outline=outline, width=int(width * k))
        return aa_shape(2 * r, 2 * r, fn)
    return cached(key, make)


def shadow(w, h, r, blur=14, alpha=90, color=(0, 0, 0)):
    key = ("sh", w, h, r, blur, alpha, color)
    def make():
        pad = blur * 2
        img = Image.new("RGBA", (int((w + pad * 2) * R), int((h + pad * 2) * R)), (0, 0, 0, 0))
        ImageDraw.Draw(img).rounded_rectangle([pad * R, pad * R, (pad + w) * R, (pad + h) * R], radius=r * R, fill=color + (alpha,))
        return img.filter(ImageFilter.GaussianBlur(blur * R / 2))
    return cached(key, make)


# ---------- 手書き風の線 ----------
def wobble_path(pts, seed, amp=1.5, step=6):
    """折れ線を細かく分け、少し揺らす（手で引いた線のように）"""
    rng = np.random.default_rng(seed)
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / step))
        for i in range(n):
            u = i / n
            out.append([x0 + (x1 - x0) * u, y0 + (y1 - y0) * u])
    out.append(list(pts[-1]))
    out = np.array(out, dtype=float)
    noise = rng.standard_normal((len(out), 2))
    k = np.ones(5) / 5
    noise = np.stack([np.convolve(noise[:, 0], k, "same"), np.convolve(noise[:, 1], k, "same")], 1)
    return out + noise * amp * 2.0


def ellipse_path(cx, cy, rx, ry, seed, turns=1.12, start=-2.4, amp=2.0, power=2.0):
    """手で丸を描いたような、少しはみ出して閉じる楕円。power を大きくすると角の丸い四角に近づく（横長の文字を囲みやすい）"""
    rng = np.random.default_rng(seed)
    n = int(90 * turns)
    th = start + np.linspace(0, 2 * math.pi * turns, n)
    grow = 1 + 0.06 * np.linspace(-1, 1, n)
    wob = np.convolve(rng.standard_normal(n), np.ones(9) / 9, "same") * amp * 2.5
    c, s_ = np.cos(th), np.sin(th)
    e = 2.0 / power
    c, s_ = np.sign(c) * np.abs(c) ** e, np.sign(s_) * np.abs(s_) ** e
    x = cx + (rx * grow + wob) * c
    y = cy + (ry * grow + wob) * s_
    return np.stack([x, y], 1)


def partial(path, frac):
    """線を始まりから frac（0〜1）の長さまで"""
    if frac >= 1.0:
        return path
    seg = np.hypot(*np.diff(path, axis=0).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    L = cum[-1] * frac
    i = int(np.searchsorted(cum, L))
    if i <= 0:
        return path[:1]
    u = (L - cum[i - 1]) / max(1e-9, seg[i - 1])
    p = path[i - 1] + (path[i] - path[i - 1]) * u
    return np.vstack([path[:i], p[None, :]])


def stroke_sprite(path, color, width, rough=0.0, seed=0, alpha_jitter=0.0):
    """線の画像を作る。返り値：(画像, 左上の論理座標)。rough>0 でチョークのかすれ。"""
    if len(path) < 2:
        return None, (0, 0)
    pad = width * 2 + 4
    x0, y0 = path[:, 0].min() - pad, path[:, 1].min() - pad
    x1, y1 = path[:, 0].max() + pad, path[:, 1].max() + pad
    k = R * SS
    img = Image.new("RGBA", (max(1, int((x1 - x0) * k)), max(1, int((y1 - y0) * k))), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pts = [((x - x0) * k, (y - y0) * k) for x, y in path]
    d.line(pts, fill=color, width=max(1, int(width * k)), joint="curve")
    r = width * k / 2
    for px, py in (pts[0], pts[-1]):
        d.ellipse([px - r, py - r, px + r, py + r], fill=color)
    img = img.resize((max(1, int((x1 - x0) * R)), max(1, int((y1 - y0) * R))), Image.LANCZOS)
    if rough > 0:
        img = chalkify(img, seed, rough, origin=(x0, y0))
    return img, (x0, y0)


def draw_stroke(canvas, path, frac, color, width, rough=0.0, seed=0):
    if frac <= 0:
        return
    spr, (x, y) = stroke_sprite(partial(path, frac), color, width, rough, seed)
    if spr is not None:
        paste(canvas, spr, x, y)


# ---------- 質感 ----------
_grain = {}


def grain(w, h, seed, scale=1.0):
    """動かない細かいノイズ（-1〜1）"""
    key = (w, h, seed, scale)
    if key not in _grain:
        rng = np.random.default_rng(seed)
        if scale > 1:
            small = rng.standard_normal((max(2, int(h / scale)), max(2, int(w / scale)))).astype(np.float32)
            img = Image.fromarray(((np.clip(small, -3, 3) + 3) / 6 * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
            g = np.asarray(img, dtype=np.float32) / 127.5 - 1
        else:
            g = np.clip(rng.standard_normal((h, w)).astype(np.float32) / 2.5, -1, 1)
        _grain[key] = g
    return _grain[key]


def chalkify(spr, seed, rough=0.5, origin=None):
    """文字や線をチョークのようにかすれさせる。ざらざらは画面に固定（origin＝貼る位置の論理座標）なので、動かない。"""
    a = np.asarray(spr.getchannel("A"), dtype=np.float32)
    h, w = a.shape
    g1, g2 = grain(W, H, 11, 1.0), grain(W, H, 12, 3.0 * R)
    if origin is not None:
        ox, oy = int(round(origin[0] * R)), int(round(origin[1] * R))
    else:
        ox, oy = seed % W, (seed // 7) % H
    rows, cols = (oy + np.arange(h)) % H, (ox + np.arange(w)) % W
    m1, m2 = g1[np.ix_(rows, cols)], g2[np.ix_(rows, cols)]
    m = 1.0 - rough * (0.55 * np.clip(m1 * 0.5 + 0.5, 0, 1) + 0.45 * np.clip(-m2 * 0.6 + 0.2, 0, 1))
    out = spr.copy()
    out.putalpha(Image.fromarray(np.clip(a * m, 0, 255).astype(np.uint8)))
    return out


def add_grain(img, amount, seed, scale=1.0):
    """背景に動かない粒状の質感をのせる（RGB 画像を返す）"""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    g = grain(arr.shape[1], arr.shape[0], seed, scale)
    arr += g[:, :, None] * amount
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def vgradient(c_top, c_bot):
    """縦のグラデーション（RGBA の画面いっぱい）"""
    t = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    a, b = np.array(c_top[:3], np.float32), np.array(c_bot[:3], np.float32)
    col = a[None, :] * (1 - t) + b[None, :] * t
    arr = np.repeat(col[:, None, :], W, axis=1)
    return Image.fromarray(arr.astype(np.uint8)).convert("RGBA")


def vignette(img, strength=0.35):
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]].astype(np.float32)
    d = np.sqrt(((xx / arr.shape[1]) - 0.5) ** 2 * 1.6 + ((yy / arr.shape[0]) - 0.45) ** 2)
    m = 1 - strength * np.clip((d - 0.25) / 0.5, 0, 1) ** 1.5
    return Image.fromarray(np.clip(arr * m[:, :, None], 0, 255).astype(np.uint8)).convert("RGBA")
