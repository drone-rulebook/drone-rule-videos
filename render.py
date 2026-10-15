# -*- coding: utf-8 -*-
"""二等学科ひっかけクイズの縦型ショート動画（720x1280・30fps・13秒）を、台本から作る。

使い方
  python render.py                   … 公開した「動画台本」シート（config.json の csv_url）を読み、近い日の「待ち」の台本を動画にする
  python render.py --sample out.mp4  … 見本の台本で1本だけ作る（確認用）

絵・動き・文字・効果音はすべてプログラムで作る（素材ファイルは使わない。フォントだけ fonts/ に同梱）。
台本の文字は、*で囲んだところを黄色にする（例：150mは*どこから*測る？）。
"""
import csv, datetime, io, json, math, os, re, subprocess, sys, urllib.request, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, S = 720, 1280, 2
W2, H2 = W * S, H * S
FPS, DUR = 30, 13.0
N = int(FPS * DUR)

NAVY = (19, 33, 60, 255)
NAVY2 = (36, 58, 98, 255)
YELLOW = (255, 196, 0, 255)
WHITE = (245, 247, 250, 255)
GREY = (150, 162, 182, 255)
DARK = (14, 22, 40, 255)
RED = (236, 76, 62, 255)

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
                _fonts[key] = ImageFont.truetype(path, int(px * S), index=0)
                break
        else:
            raise SystemExit("フォントが見つかりません：" + weight)
    return _fonts[key]

# ---------- 便利関数 ----------
def clamp(v, a=0.0, b=1.0): return max(a, min(b, v))
def prog(t, t0, t1): return clamp((t - t0) / (t1 - t0)) if t1 > t0 else (1.0 if t >= t1 else 0.0)
def ease_out(p): return 1 - (1 - p) ** 3
def ease_in_out(p): return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
def ease_back(p, s=1.70158): return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2
def mix(c1, c2, p): return tuple(int(c1[i] + (c2[i] - c1[i]) * p) for i in range(4))

def segments(text, base, accent=YELLOW):
    """「*強調*」を黄色にした [(文字, 色)] にする"""
    out, on = [], False
    for part in str(text).split("*"):
        if part:
            out.append((part, accent if on else base))
        on = not on
    return out or [("", base)]

_sprites = {}
def text_sprite(segs, weight, px):
    key = (tuple(segs), weight, px)
    if key in _sprites:
        return _sprites[key]
    f = font(weight, px)
    asc, desc = f.getmetrics()
    total = sum(f.getlength(s) for s, _ in segs)
    pad = 6 * S
    img = Image.new("RGBA", (int(total) + pad * 2, asc + desc + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for s, col in segs:
        d.text((x, pad + asc), s, font=f, fill=col, anchor="ls")
        x += f.getlength(s)
    _sprites[key] = img
    return img

def fit_sprite(segs, weight, px, max_w, min_px):
    """横幅 max_w（最終の px）に収まるまで文字を小さくする"""
    p = px
    while p > min_px:
        spr = text_sprite(segs, weight, p)
        if spr.width / S - 12 <= max_w:
            return spr
        p -= 2
    return text_sprite(segs, weight, min_px)

def paste(canvas, spr, x, y, alpha=1.0, scale=1.0, anchor="lt"):
    if alpha <= 0.003 or scale <= 0.01:
        return
    if scale != 1.0:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.LANCZOS)
    if alpha < 0.999:
        spr = spr.copy()
        spr.putalpha(spr.getchannel("A").point(lambda v: int(v * alpha)))
    X, Y = int(x * S), int(y * S)
    if anchor == "ct": X -= spr.width // 2
    elif anchor == "cc": X -= spr.width // 2; Y -= spr.height // 2
    elif anchor == "lc": Y -= spr.height // 2
    l, t = max(0, X), max(0, Y)
    r, b = min(W2, X + spr.width), min(H2, Y + spr.height)
    if r <= l or b <= t:
        return
    canvas.alpha_composite(spr.crop((l - X, t - Y, r - X, b - Y)), dest=(l, t))

def rrect_layer(w, h, r, fill):
    img = Image.new("RGBA", (int(w * S), int(h * S)), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, int(w * S) - 1, int(h * S) - 1], radius=int(r * S), fill=fill)
    return img

# ---------- 台本 → 動画 ----------
T_TITLE_END = 1.0
CARD_T = [1.70, 1.95, 2.20]
T_COUNT0, T_COUNT1 = 5.5, 8.0
T_REVEAL = 8.0
T_WIPE0, T_WIPE1, T_SWITCH = 11.4, 11.8, 11.6
CARD_X, CARD_W, CARD_H = 40, 560, 104
CARD_Y = [440, 562, 684]

class Video:
    def __init__(self, sc):
        self.q1, self.q2 = sc["q1"], sc.get("q2", "")
        self.choices = [("A", sc["a"]), ("B", sc["b"]), ("C", sc["c"])]
        self.correct = "ABC".index(sc["answer"].strip().upper())
        trap = sc["trap"]
        if "：" in trap:
            head, tail = trap.split("：", 1)
            self.trap = [(head + "：", GREY)] + segments(tail, WHITE)
        else:
            self.trap = segments(trap, WHITE)

    def label(self, cv, t):
        p = ease_out(prog(t, 1.0, 1.35))
        if p <= 0:
            return
        y = 64 - 20 * (1 - p)
        ImageDraw.Draw(cv).rectangle([40 * S, int((y + 14) * S), 48 * S, int((y + 50) * S)], fill=mix(NAVY, YELLOW, p))
        paste(cv, text_sprite([("二等学科 ひっかけ問題", YELLOW)], "Bold", 30), 56, y + 4, alpha=p)

    def title(self, cv, t):
        out = prog(t, 0.82, 1.0)
        paste(cv, text_sprite([("二等学科", WHITE)], "Medium", 44), 360, 470, alpha=prog(t, 0.0, 0.3) * (1 - out), anchor="ct")
        sc = ease_back(prog(t, 0.15, 0.5)) * (1 + 0.15 * out)
        paste(cv, text_sprite([("ひっかけ問題", YELLOW)], "Black", 96), 360, 600, alpha=prog(t, 0.15, 0.25) * (1 - out), scale=sc, anchor="cc")
        bw = 380 * ease_out(prog(t, 0.35, 0.6))
        if bw > 2 and out < 1:
            ImageDraw.Draw(cv).rectangle([int((360 - bw / 2) * S), 706 * S, int((360 + bw / 2) * S), 718 * S], fill=mix(NAVY, YELLOW, 1 - out))

    def question(self, cv, t):
        p1 = ease_out(prog(t, 1.05, 1.4)); p2 = ease_out(prog(t, 1.2, 1.55))
        paste(cv, fit_sprite(segments(self.q1, WHITE), "Bold", 50, 640, 34), 40 - 60 * (1 - p1), 196, alpha=p1)
        if self.q2:
            paste(cv, fit_sprite(segments(self.q2, WHITE), "Bold", 50, 640, 34), 40 - 60 * (1 - p2), 276, alpha=p2)

    def cards(self, cv, t):
        rv = prog(t, T_REVEAL, T_REVEAL + 0.22)
        for i, (letter, label) in enumerate(self.choices):
            p = ease_out(prog(t, CARD_T[i], CARD_T[i] + 0.4))
            if p <= 0:
                continue
            correct = i == self.correct
            fill = mix(WHITE, YELLOW, rv) if correct else WHITE
            alpha = 1.0 if correct else 1 - 0.62 * rv
            sc = 1 + 0.05 * math.sin(math.pi * prog(t, T_REVEAL, T_REVEAL + 0.3)) if (correct and t >= T_REVEAL) else 1.0
            card = rrect_layer(CARD_W, CARD_H, 22, fill)
            d = ImageDraw.Draw(card)
            cx, cy = 58 * S, CARD_H / 2 * S
            d.ellipse([cx - 34 * S, cy - 34 * S, cx + 34 * S, cy + 34 * S], fill=NAVY)
            lt = text_sprite([(letter, WHITE)], "Black", 40)
            card.alpha_composite(lt, dest=(int(cx - lt.width / 2), int(cy - lt.height / 2)))
            tx = fit_sprite([(label, DARK)], "Bold", 42, CARD_W - 118 - 74, 26)
            card.alpha_composite(tx, dest=(118 * S, int(cy - tx.height / 2)))
            if t >= T_REVEAL + 0.12:
                m = ease_out(prog(t, T_REVEAL + 0.12, T_REVEAL + 0.35))
                mx, my = (CARD_W - 52) * S, cy
                if correct:
                    rr = 30 * S * m
                    d.ellipse([mx - rr, my - rr, mx + rr, my + rr], fill=NAVY)
                    if m > 0.5:
                        d.line([mx - 13 * S, my + 1 * S, mx - 3 * S, my + 11 * S, mx + 15 * S, my - 11 * S], fill=WHITE, width=6 * S, joint="curve")
                else:
                    k = 14 * S * m
                    d.line([mx - k, my - k, mx + k, my + k], fill=RED, width=7 * S)
                    d.line([mx - k, my + k, mx + k, my - k], fill=RED, width=7 * S)
            paste(cv, card, CARD_X + 700 * (1 - p) + CARD_W / 2, CARD_Y[i] + CARD_H / 2, alpha=alpha, scale=sc, anchor="cc")

    def countdown(self, cv, t):
        if not (T_COUNT0 - 0.05 <= t < T_COUNT0 + 2.65):
            return
        a = prog(t, T_COUNT0 - 0.05, T_COUNT0 + 0.15) * (1 - prog(t, T_COUNT1, T_COUNT1 + 0.15))
        if a <= 0:
            return
        layer = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx, cy, r = 360, 905, 74
        box = [int((cx - r) * S), int((cy - r) * S), int((cx + r) * S), int((cy + r) * S)]
        d.ellipse(box, outline=NAVY2, width=12 * S)
        frac = prog(t, T_COUNT0, T_COUNT1)
        if frac > 0:
            d.arc(box, start=-90, end=-90 + 360 * frac, fill=YELLOW, width=12 * S)
        seg = (T_COUNT1 - T_COUNT0) / 3
        k = min(2, int((t - T_COUNT0) / seg)) if t >= T_COUNT0 else 0
        t_k = T_COUNT0 + k * seg
        sc = 1 + 0.35 * (1 - ease_out(prog(t, t_k, t_k + 0.25)))
        if a < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v: int(v * a)))
        cv.alpha_composite(layer)
        paste(cv, text_sprite([(str(3 - k), WHITE)], "Black", 92), cx, cy - 4, alpha=a, scale=sc, anchor="cc")

    def answer(self, cv, t):
        if t < T_REVEAL:
            return
        p = prog(t, T_REVEAL + 0.05, T_REVEAL + 0.35)
        letter = "ABC"[self.correct]
        paste(cv, text_sprite([("正解 " + letter, YELLOW)], "Black", 80), 360, 900, alpha=prog(t, T_REVEAL + 0.05, T_REVEAL + 0.12), scale=0.5 + 0.5 * ease_back(p), anchor="cc")
        q = ease_out(prog(t, T_REVEAL + 0.45, T_REVEAL + 0.75))
        paste(cv, fit_sprite(self.trap, "Bold", 38, 640, 26), 360, 968 + 16 * (1 - q), alpha=q, anchor="ct")

    def ending(self, cv, t):
        e = ease_out(prog(t, T_SWITCH + 0.05, T_SWITCH + 0.4))
        paste(cv, text_sprite([("毎日1問", YELLOW)], "Black", 100), 360, 560, alpha=e, scale=0.7 + 0.3 * ease_back(prog(t, T_SWITCH + 0.05, T_SWITCH + 0.45)), anchor="cc")
        paste(cv, text_sprite([("ひっかけ対策", WHITE)], "Black", 60), 360, 676 + 16 * (1 - e), alpha=e, anchor="cc")
        bw = 300 * ease_out(prog(t, T_SWITCH + 0.3, T_SWITCH + 0.6))
        if bw > 2:
            ImageDraw.Draw(cv).rectangle([int((360 - bw / 2) * S), 730 * S, int((360 + bw / 2) * S), 740 * S], fill=YELLOW)
        q = ease_out(prog(t, T_SWITCH + 0.45, T_SWITCH + 0.75))
        paste(cv, text_sprite([("チャンネル登録で毎日届きます", WHITE)], "Bold", 34), 360, 790 + 12 * (1 - q), alpha=q, anchor="ct")

    def wipe(self, cv, t):
        if not (T_WIPE0 <= t <= T_WIPE1):
            return
        p = ease_in_out(prog(t, T_WIPE0, T_WIPE1))
        cx = -500 + 1720 * p
        k = 260
        pts = [(cx - 520, 0), (cx + 520 + k, 0), (cx + 520, 1280), (cx - 520 - k, 1280)]
        ImageDraw.Draw(cv).polygon([(px * S, py * S) for px, py in pts], fill=YELLOW)

    def frame(self, t):
        cv = Image.new("RGBA", (W2, H2), NAVY)
        if t < T_TITLE_END:
            self.title(cv, t)
        elif t < T_SWITCH:
            self.label(cv, t); self.question(cv, t); self.cards(cv, t); self.countdown(cv, t); self.answer(cv, t)
        else:
            self.label(cv, t); self.ending(cv, t)
        self.wipe(cv, t)
        return cv.convert("RGB").resize((W, H), Image.LANCZOS)

# ---------- 効果音 ----------
SR = 44100
def env(n, att, dec):
    e = np.ones(n); a = max(1, int(att * SR)); e[:a] = np.linspace(0, 1, a)
    return e * np.exp(-np.arange(n) / (dec * SR))

def build_audio(path):
    rng = np.random.default_rng(7)
    buf = np.zeros(int(SR * DUR) + SR)
    def add(t0, sig, gain):
        i = int(t0 * SR); buf[i:i + len(sig)] += sig[: len(buf) - i] * gain
    def swoosh(dur=0.35):
        n = int(dur * SR); x = rng.standard_normal(n)
        x = np.convolve(x, np.ones(24) / 24, mode="same")
        x = x - np.convolve(x, np.ones(300) / 300, mode="same")
        return x * np.sin(np.linspace(0, math.pi, n)) ** 2 * 3.0
    def pop(f=880, dur=0.09):
        n = int(dur * SR); tt = np.arange(n) / SR
        return np.sin(2 * math.pi * f * tt) * env(n, 0.002, 0.025)
    def tick():
        n = int(0.05 * SR); tt = np.arange(n) / SR
        return (np.sin(2 * math.pi * 2100 * tt) * 0.7 + rng.standard_normal(n) * 0.3) * env(n, 0.0005, 0.008)
    def tone(f, dur, dec, harm=0.25):
        n = int(dur * SR); tt = np.arange(n) / SR
        return (np.sin(2 * math.pi * f * tt) + harm * np.sin(4 * math.pi * f * tt)) * env(n, 0.004, dec)
    add(0.0, swoosh(), 0.22); add(0.2, pop(660), 0.45)
    add(1.0, swoosh(), 0.18)
    for i, ct in enumerate(CARD_T):
        add(ct + 0.05, pop(740 + 120 * i), 0.38)
    seg = (T_COUNT1 - T_COUNT0) / 3
    for k in range(3):
        add(T_COUNT0 + k * seg, tick(), 0.5)
    add(T_REVEAL, tone(1046.5, 0.5, 0.18), 0.28); add(T_REVEAL + 0.12, tone(1568.0, 0.7, 0.25), 0.28)
    add(T_WIPE0, swoosh(0.4), 0.25)
    for f in (523.25, 659.25, 783.99):
        add(T_SWITCH + 0.1, tone(f, 1.0, 0.35, 0.1), 0.12)
    buf = buf[: int(SR * DUR)]
    buf = buf / max(1e-9, np.abs(buf).max()) * 0.85
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(np.stack([pcm, pcm], axis=1).tobytes())

def render(sc, out_path):
    v = Video(sc)
    tmp_wav = out_path + ".wav"
    build_audio(tmp_wav)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", tmp_wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", "-shortest", out_path + ".part.mp4"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(N):
        p.stdin.write(v.frame(i / FPS).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg に失敗しました")
    os.replace(out_path + ".part.mp4", out_path)
    os.remove(tmp_wav)

# ---------- 台本シート（CSV）→ 作る分を選ぶ ----------
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

def jst_today():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()

def parse_date(s):
    s = str(s or "").strip().replace("/", "-")
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None

def write_status(st):
    """実行の結果を status.json に残す（Actions の画面を見なくても、置き場で結果がわかるように）。"""
    st = dict({"最終実行（日本時間）": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")}, **st)
    with open(os.path.join(HERE, "status.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
        f.write("\n")

def main():
    st = {"結果": "", "台本の行数": 0, "作った動画": [], "見送った台本": [], "作れなかった台本": [], "消した動画": 0,
          "次に作る予定": [], "エラー": ""}
    try:
        _main(st)
    except Exception as e:
        st["結果"] = "失敗"
        st["エラー"] = (type(e).__name__ + "：" + str(e))[:300]
        write_status(st)
        raise
    st["結果"] = "一部失敗" if st["作れなかった台本"] else (st["結果"] or "成功")
    write_status(st)
    if st["作れなかった台本"]:
        sys.exit(1)

def _main(st):
    cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    url = os.environ.get("CSV_URL") or cfg.get("csv_url", "")
    if not url.startswith("https://docs.google.com/"):
        print("config.json の csv_url が未設定です。何もしません。")
        st["結果"] = "未設定（csv_url）"
        return
    raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if "台本ID" not in (reader.fieldnames or []):
        raise ValueError("公開したシートが「動画台本」ではないようです（1行目に 台本ID がありません）")
    rows = list(reader)
    today = jst_today()
    ahead = int(cfg.get("days_ahead", 3))
    keep = int(cfg.get("keep_days", 10))
    vdir = os.path.join(HERE, "videos")
    os.makedirs(vdir, exist_ok=True)
    dates = {}
    for r in rows:
        vid = str(r.get("台本ID", "")).strip()
        d = parse_date(r.get("公開予定日"))
        if not ID_RE.match(vid) or d is None:
            continue
        st["台本の行数"] += 1
        dates[vid] = d
        if str(r.get("状態", "")).strip() != "待ち":
            continue
        if d > today + datetime.timedelta(days=ahead):
            st["次に作る予定"].append(vid)
            continue
        if d < today - datetime.timedelta(days=1):
            continue
        out = os.path.join(vdir, vid + ".mp4")
        if os.path.exists(out):
            continue
        sc = {"q1": r.get("問題1行目", ""), "q2": r.get("問題2行目", ""), "a": r.get("選択肢A", ""), "b": r.get("選択肢B", ""),
              "c": r.get("選択肢C", ""), "answer": r.get("正解", ""), "trap": r.get("ひっかけ", "")}
        if not (sc["q1"] and sc["a"] and sc["b"] and sc["c"] and sc["trap"] and sc["answer"].strip().upper() in ("A", "B", "C")):
            print("台本が足りないので見送り：", vid); st["見送った台本"].append(vid)
            continue
        try:
            render(sc, out)
        except Exception as e:
            print("作れませんでした：", vid, e); st["作れなかった台本"].append(vid)
            for p in (out + ".part.mp4", out + ".wav"):
                if os.path.exists(p):
                    os.remove(p)
            continue
        print("作成：", vid, d)
        st["作った動画"].append(vid)
    st["次に作る予定"] = st["次に作る予定"][:3]
    # 古い動画を消す（置き場を軽く保つ）
    for name in os.listdir(vdir):
        if not name.endswith(".mp4"):
            continue
        vid = name[:-4]
        d = dates.get(vid)
        if d is not None and d < today - datetime.timedelta(days=keep):
            os.remove(os.path.join(vdir, name)); st["消した動画"] += 1
    print(f"作成 {len(st['作った動画'])} 本・見送り {len(st['見送った台本'])} 本・失敗 {len(st['作れなかった台本'])} 本・削除 {st['消した動画']} 本")

SAMPLE = {"q1": "「高度150m以上」の空域", "q2": "150mは*どこから*測る？", "a": "海抜高度（標高）", "b": "直下の地表・水面",
          "c": "飛行場の標点", "answer": "B", "trap": "ひっかけ：*海抜*ではない！"}

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--sample":
        render(SAMPLE, sys.argv[2]); print("作成：", sys.argv[2])
    else:
        main()
