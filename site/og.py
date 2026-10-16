# -*- coding: utf-8 -*-
"""共有したときの画像（1200×630）を Pillow と fonts/ で作る。build.py から呼ぶ。

答えは画像に入れない（問題と3択だけ）。フォントに無い文字がある問題は、サイト共通の画像を使う。
"""
import os, unicodedata
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
W, H = 1200, 630
FONTS = {w: os.path.join(ROOT, "fonts", f"NotoSansJP-{w}-subset.otf") for w in ("Black", "Bold", "Medium")}
VARIANTS = {"塡": "填", "剝": "剥", "頰": "頬", "𠮟": "叱"}

_chars = None
_fonts = {}


def font(w, px):
    if (w, px) not in _fonts:
        _fonts[(w, px)] = ImageFont.truetype(FONTS[w], px)
    return _fonts[(w, px)]


def safe(s):
    """フォントにある文字だけにする。置きかえられない文字があれば None。"""
    global _chars
    if _chars is None:
        _chars = set(open(os.path.join(ROOT, "fonts", "chars.txt"), encoding="utf-8").read())
    out = []
    for ch in str(s):
        if ch in _chars or ch in "* ":
            out.append(ch)
            continue
        alt = VARIANTS.get(ch) or unicodedata.normalize("NFKC", ch)
        if alt and all(c in _chars for c in alt):
            out.append(alt)
        else:
            return None
    return "".join(out)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def segments(text, base, accent):
    out, on = [], False
    for part in str(text).split("*"):
        if part:
            out.append((part, accent if on else base))
        on = not on
    return out


def wrap(segs, f, max_w):
    """色つきの文字列を、横幅に収まるように行に分ける（1文字ずつ）。"""
    lines, cur, cur_w = [], [], 0.0
    for s, col in segs:
        for ch in s:
            w = f.getlength(ch)
            if cur and cur_w + w > max_w:
                lines.append(cur); cur, cur_w = [], 0.0
            if cur or ch != " ":
                cur.append((ch, col)); cur_w += w
    if cur:
        lines.append(cur)
    return lines


def draw_lines(d, lines, f, x, y, gap, center_w=None):
    """行を描いて、次の y を返す（行の高さ＝文字の大きさ×gap）"""
    px = f.size
    lh = int(px * gap)
    for line in lines:
        lw = sum(f.getlength(ch) for ch, _ in line)
        cx = x + (center_w - lw) / 2 if center_w else x
        for ch, col in line:
            d.text((cx, y + px * 0.88 + (lh - px) / 2), ch, font=f, fill=col, anchor="ls")
            cx += f.getlength(ch)
        y += lh
    return y


def fit_box(blocks, max_w, max_h):
    """いくつかの文のかたまり [(segs, 太さ, 大きさの候補, 最大行数, 行間)] を、高さ max_h に収まる大きさで並べる"""
    n = max(len(b[2]) for b in blocks)
    for step in range(n):
        res, h = [], 0
        for segs, weight, sizes, max_lines, gap in blocks:
            px = sizes[min(step, len(sizes) - 1)]
            f = font(weight, px)
            lines = wrap(segs, f, max_w)
            res.append((f, lines[:max_lines], gap))
            h += int(px * gap) * min(len(lines), max_lines)
            if len(lines) > max_lines:
                h = 10 ** 6
        if h <= max_h:
            return res
    return res


def base(c, name, label):
    img = Image.new("RGB", (W, H), rgb(c["bg"]))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 96], fill=rgb(c["bg2"]))
    d.rectangle([0, H - 12, W, H], fill=rgb(c["accent"]))
    d.rounded_rectangle([60, 30, 96, 66], radius=6, fill=rgb(c["accent"]))
    f = font("Bold", 34)
    d.text((114, 48), name, font=f, fill=rgb(c["text"]), anchor="lm")
    if label:
        f2 = font("Medium", 26)
        d.text((W - 60, 48), label, font=f2, fill=rgb(c["muted"]), anchor="rm")
    return img, d


def site_image(cfg, path, big, sub):
    c, t = cfg["og"], cfg["texts"]
    img, d = base(c, cfg["site_name"], "")
    blocks = fit_box([([(big, rgb(c["text"]))], "Black", [96, 84, 72, 60], 2, 1.3),
                      ([(sub, rgb(c["muted"]))], "Bold", [38, 34, 30, 28], 3, 1.5)], W - 120, 300)
    y = 140
    for f, lines, gap in blocks:
        y = draw_lines(d, lines, f, 60, y, gap) + 12
    badge = t["start_quiz"]
    f = font("Black", 40)
    bw = f.getlength(badge) + 64
    d.rounded_rectangle([60, H - 136, 60 + bw, H - 56], radius=40, fill=rgb(c["accent"]))
    d.text((60 + bw / 2, H - 96), badge, font=f, fill=rgb(c["bg"]), anchor="mm")
    img.save(path, optimize=True)


def question_image(cfg, q, path):
    c, t = cfg["og"], cfg["texts"]
    texts = [safe(x) for x in [q["q1"], q["q2"]] + q["choices"]]
    if any(x is None for x in texts):
        return False
    q1, q2, *choices = texts
    white, yellow, muted = rgb(c["text"]), rgb(c["accent"]), rgb(c["muted"])
    img, d = base(c, cfg["site_name"], t.get("og_label", ""))
    # 3択（答えは出さない）は下に固定し、問題文はその上の高さに収める
    gap, bh = 20, 168
    top = H - 44 - bh
    if q2:
        blocks = [(segments(q1, muted, yellow), "Bold", [40, 36, 32, 28, 26], 2, 1.4),
                  (segments(q2, white, yellow), "Black", [68, 60, 52, 46, 40], 2, 1.3)]
    else:
        blocks = [(segments(q1, white, yellow), "Black", [64, 56, 48, 42, 36, 32], 3, 1.3)]
    y0, room = 116, top - 20 - 116
    laid = fit_box(blocks, W - 120, room)
    y = y0 + max(0, (room - sum(int(f.size * g) * len(lines) for f, lines, g in laid)) / 2)
    for f, lines, g in laid:
        y = draw_lines(d, lines, f, 60, y, g)
    bw = (W - 120 - gap * 2) / 3
    for k, ch in enumerate(choices):
        x0 = 60 + k * (bw + gap)
        d.rounded_rectangle([x0, top, x0 + bw, top + bh], radius=18, fill=rgb(c["bg2"]))
        d.ellipse([x0 + 16, top + 14, x0 + 56, top + 54], fill=yellow)
        d.text((x0 + 36, top + 34), "ABC"[k], font=font("Black", 26), fill=rgb(c["bg"]), anchor="mm")
        (fc, lc, g), = fit_box([(segments(ch, white, yellow), "Bold", [30, 27, 24, 22, 20], 3, 1.3)], bw - 32, bh - 70)
        h = int(fc.size * g) * len(lc)
        draw_lines(d, lc, fc, x0 + 16, top + 62 + (bh - 70 - h) / 2, g, center_w=bw - 32)
    img.save(path, optimize=True)
    return True


def make_all(cfg, questions, out):
    t = cfg["texts"]
    os.makedirs(os.path.join(out, "og", "q"), exist_ok=True)
    site_image(cfg, os.path.join(out, "og", "site.png"), cfg["site_name"], t["tagline"])
    site_image(cfg, os.path.join(out, "og", "quiz.png"), t["quiz_title"], t["tagline"])
    ok, skipped = set(), []
    for q in questions:
        if question_image(cfg, q, os.path.join(out, "og", "q", q["id"] + ".png")):
            ok.add(q["id"])
        else:
            skipped.append(q["id"])
    if skipped:
        print("  フォントに無い文字があるので共通の画像を使う問題：", "、".join(skipped))
    return ok
