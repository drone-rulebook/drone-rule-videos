# -*- coding: utf-8 -*-
"""長尺の解説動画（横長 1920x1080・約7〜10分・声は VOICEVOX のずんだもん）を、台本 JSON から作る。

  python long.py long/L001.json out/L001.mp4      … 動画と、サムネイル（out/L001_thumb.png）・説明文（out/L001_desc.txt）を作る
  python long.py long/L001.json out/L001.mp4 --no-voice   … 声なし（文字数から長さを見積もった無音）で流れだけ確かめる

台本の形（long/*.json）：
  {"id":"L001","theme":"…","title":"…","intro":["文",…],"outro":["文",…],
   "questions":[{"q":"問題文","choices":["A","B","C"],"answer":"B","explain":["文",…],"points":["要点",…],"basis":"第3章 …"}]}
  選択肢が2つなら2択（これ違反？）。*で囲んだ語は黄色。

作り方：場面ごとに静止画（動くのはカウントダウンだけ）を作り、ffmpeg の concat で時間どおりにつなぐ。
同じ画像が続くところは1枚で済むので、8分でも数分で書き出せる。音は声・効果音・BGM を numpy で混ぜる。
文字は Noto Sans CJK（フルセット。Actions では fonts-noto-cjk を入れる）。無ければ置き場の Noto Sans JP（字が欠けることがある）。
"""
import json, math, os, re, subprocess, sys, tempfile, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import music  # noqa: E402

W, H = 1920, 1080
FPS = 30
SR = 44100
VOICE_SPEED = 1.1
GAP = 0.28                     # 文と文のあいだ（秒）
THINK = 3                      # カウントダウン（秒）

C = {"bg1": (22, 40, 74), "bg2": (13, 24, 48), "panel": (34, 55, 94), "text": (245, 247, 250), "sub": (154, 167, 189),
     "accent": (255, 196, 0), "card": (247, 248, 251), "cardtext": (14, 22, 40), "good": (38, 166, 91), "bad": (236, 76, 62),
     "zunda": (122, 196, 82)}

CJK = ["/usr/share/fonts/opentype/noto/NotoSansCJK-{w}.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-{w}.ttc"]
SUBSET = {"Bold": "NotoSansJP-Bold-subset.otf", "Black": "NotoSansJP-Black-subset.otf", "Medium": "NotoSansJP-Medium-subset.otf"}
_fonts = {}


def font(weight, px):
    key = (weight, px)
    if key not in _fonts:
        f = None
        for pat in CJK:
            p = pat.format(w=weight)
            if os.path.exists(p):
                f = ImageFont.truetype(p, px, index=0)        # ttc の0番が日本語（JP）
                break
        if f is None:
            f = ImageFont.truetype(os.path.join(HERE, "fonts", SUBSET.get(weight, SUBSET["Bold"])), px)
        _fonts[key] = f
    return _fonts[key]


def full_font_available():
    return any(os.path.exists(p.format(w="Bold")) for p in CJK)


# ───────── 文字の折り返し（強調 *…* と行頭禁則） ─────────
NO_HEAD = set("、。，．・：；？！ー～」』）】〕｝〉》’”…‥ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ%％")
NO_TAIL = set("「『（【〔｛〈《‘“")


def runs(text):
    """「*強調*」→ [(文字, 強調か)]（1文字ずつ）"""
    out, on = [], False
    for part in str(text).split("*"):
        out += [(ch, on) for ch in part]
        on = not on
    return out


def wrap(text, f, max_w):
    """1文字ずつのリストを、max_w に収まる行に分ける（英数字の続きは途中で切らない。\n は改行）"""
    if "\n" in str(text):
        out = []
        for part in str(text).split("\n"):
            out += wrap(part, f, max_w)
        return out
    chars = runs(text)
    lines, cur = [], []
    def width(cs): return f.getlength("".join(c for c, _ in cs))
    i = 0
    while i < len(chars):
        # 英数字のかたまりは1つとして扱う
        j = i + 1
        if re.match(r"[A-Za-z0-9.,]", chars[i][0]):
            while j < len(chars) and re.match(r"[A-Za-z0-9.,%]", chars[j][0]):
                j += 1
        word = chars[i:j]
        if cur and width(cur + word) > max_w:
            # 行頭に来てはいけない文字は前の行へぶら下げる
            while word and word[0][0] in NO_HEAD:
                cur.append(word.pop(0))
            if cur and cur[-1][0] in NO_TAIL:
                carry = [cur.pop()]
            else:
                carry = []
            lines.append(cur)
            cur = carry + word
        else:
            cur += word
        i = j
    if cur:
        lines.append(cur)
    return lines


def fit_text(text, weight, max_w, max_lines, px, min_px=24):
    """max_lines 行に収まる大きさを探す → (font, 行のリスト)"""
    while True:
        f = font(weight, px)
        ls = wrap(text, f, max_w)
        if len(ls) <= max_lines or px <= min_px:
            return f, ls
        px -= 2


def draw_lines(d, lines, f, x, y, color, accent, lh=1.35, align="left", box_w=None):
    """行を描く。強調は accent 色。描いた高さを返す"""
    step = int(f.size * lh)
    for k, ln in enumerate(lines):
        w = f.getlength("".join(c for c, _ in ln))
        xx = x + (box_w - w) / 2 if (align == "center" and box_w) else x
        for ch, on in ln:
            d.text((xx, y + k * step), ch, font=f, fill=accent if on else color)
            xx += f.getlength(ch)
    return step * len(lines)


# ───────── 画面の部品 ─────────
_bg = None


def background():
    global _bg
    if _bg is None:
        top, bot = np.array(C["bg1"], float), np.array(C["bg2"], float)
        t = np.linspace(0, 1, H)[:, None, None]
        arr = top * (1 - t) + bot * t
        img = Image.fromarray(np.repeat(arr, W, axis=1).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(img, "RGBA")
        for x in range(0, W, 60):
            d.line([(x, 0), (x, H)], fill=(255, 255, 255, 10))
        for y in range(0, H, 60):
            d.line([(0, y), (W, y)], fill=(255, 255, 255, 10))
        _bg = img
    return _bg.copy()


def drone_icon(d, cx, cy, s, color):
    """オリジナルのドローンの絵（4つのプロペラと本体）"""
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        px, py = cx + dx * s, cy + dy * s
        d.line([(cx, cy), (px, py)], fill=color, width=max(2, s // 6))
        d.ellipse([px - s * 0.55, py - s * 0.18, px + s * 0.55, py + s * 0.18], outline=color, width=max(2, s // 8))
    d.rounded_rectangle([cx - s * 0.35, cy - s * 0.35, cx + s * 0.35, cy + s * 0.35], radius=s // 5, fill=color)


class Frame:
    def __init__(self, ep, qno=None):
        self.img = background()
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self.ep = ep
        n = len(ep["questions"])
        # 上の帯
        self.d.rectangle([0, 0, W, 96], fill=(10, 18, 36, 235))
        drone_icon(self.d, 64, 48, 18, C["accent"])
        self.d.text((104, 22), "ドローン国家資格 二等学科", font=font("Bold", 30), fill=C["accent"])
        self.d.text((520, 24), "｜ " + ep.get("theme", ""), font=font("Medium", 28), fill=C["text"])
        if qno:
            label = f"Q{qno} / {n}"
            f = font("Black", 34)
            self.d.text((W - 60 - f.getlength(label), 26), label, font=f, fill=C["text"])
            # 進み具合
            self.d.rectangle([0, 96, int(W * qno / n), 102], fill=C["accent"])
        # 下の帯（クレジット）
        cf = font("Medium", 22)
        cr = "音声：VOICEVOX:ずんだもん　｜　教則第5版対応"
        self.d.text((W - 40 - cf.getlength(cr), H - 40), cr, font=cf, fill=C["sub"])

    def save(self, path):
        self.img.save(path)
        return path


def card(d, x, y, w, h, fill, radius=22, outline=None, width=0):
    d.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=outline, width=width)


def speaker_tag(fr, x, y):
    """話している人の札（キャラクターの絵は使わない）"""
    f = font("Black", 30)
    t = "ずんだもん"
    w = int(f.getlength(t)) + 80
    card(fr.d, x, y, w, 56, C["zunda"], radius=28)
    fr.d.ellipse([x + 14, y + 14, x + 42, y + 42], fill=(255, 255, 255))
    fr.d.text((x + 54, y + 9), t, font=f, fill=(20, 40, 10))


def subtitle(fr, text):
    """画面下の字幕（いま読んでいる文）"""
    if not text:
        return
    f, ls = fit_text(text, "Bold", W - 360, 2, 46, 30)
    hgt = int(f.size * 1.35) * len(ls) + 40
    y = H - 70 - hgt
    card(fr.d, 120, y, W - 240, hgt, (5, 10, 24, 225), radius=20)
    speaker_tag(fr, 140, y - 40)
    draw_lines(fr.d, ls, f, 160, y + 20, C["text"], C["accent"], align="center", box_w=W - 320)


# ───────── 場面 ─────────
def scene_title(ep):
    fr = Frame(ep)
    drone_icon(fr.d, W // 2, 300, 70, C["accent"])
    f, ls = fit_text(ep.get("theme", ""), "Black", W - 300, 1, 110, 60)
    y = 420
    y += draw_lines(fr.d, ls, f, 150, y, C["text"], C["accent"], align="center", box_w=W - 300)
    tf = font("Black", 84)
    t2 = f"ひっかけ{len(ep['questions'])}問"
    fr.d.text(((W - tf.getlength(t2)) / 2, y + 10), t2, font=tf, fill=C["accent"])
    y += 120
    sub = "二等学科　｜　教則第5版対応"
    sf = font("Bold", 46)
    fr.d.text(((W - sf.getlength(sub)) / 2, y + 40), sub, font=sf, fill=C["accent"])
    return fr


def scene_question(ep, i, phase, text=None, count=None):
    """phase: ask（問題）/ think（カウントダウン）/ answer（正解）"""
    q = ep["questions"][i]
    fr = Frame(ep, i + 1)
    two = len(q["choices"]) == 2
    head = "これ違反？" if two else f"第{i + 1}問"
    fr.d.text((120, 140), head, font=font("Black", 44), fill=C["accent"])
    f, ls = fit_text(q["q"], "Bold", W - 240, 3, 60, 36)
    y = 210 + draw_lines(fr.d, ls, f, 120, 210, C["text"], C["accent"])
    y = max(y + 30, 430)
    ans = "ABC".index(q["answer"].upper())
    cw, ch = (820, 120) if two else (W - 240, 100)
    for k, c in enumerate(q["choices"]):
        if two:
            x, yy = 120 + k * (cw + 40), y
        else:
            x, yy = 120, y + k * (ch + 22)
        fill, tcol, out = C["card"], C["cardtext"], None
        if phase == "answer":
            if k == ans:
                fill, out = (255, 236, 179), C["accent"]
            else:
                fill, tcol = (120, 130, 150), (60, 66, 80)
        card(fr.d, x, yy, cw, ch, fill, outline=out, width=8 if out else 0)
        lf = font("Black", 52)
        fr.d.text((x + 32, yy + (ch - 64) / 2), "ABC"[k], font=lf, fill=C["bad"] if phase == "answer" and k != ans else (37, 99, 235))
        cf, cls = fit_text(c, "Bold", cw - 140, 1, 54, 30)
        fr.d.text((x + 110, yy + (ch - cf.size * 1.3) / 2), "".join(ch_ for ch_, _ in cls[0]), font=cf, fill=tcol)
        if phase == "answer" and k == ans:
            fr.d.text((x + cw - 110, yy + (ch - 70) / 2), "正解", font=font("Black", 54), fill=C["good"])
    if phase == "think" and count is not None:
        cx, cy, r = W - 220, 170, 70
        fr.d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=C["accent"], width=10)
        nf = font("Black", 90)
        s = str(count)
        fr.d.text((cx - nf.getlength(s) / 2, cy - 64), s, font=nf, fill=C["text"])
    subtitle(fr, text)
    return fr


def scene_explain(ep, i, shown_points, text):
    q = ep["questions"][i]
    fr = Frame(ep, i + 1)
    ans = "ABC".index(q["answer"].upper())
    fr.d.text((120, 140), f"解説　正解は {q['answer'].upper()}「{q['choices'][ans]}」", font=font("Black", 50), fill=C["accent"])
    y = 240
    for p in q["points"][:shown_points]:
        f, ls = fit_text(p, "Bold", W - 400, 2, 58, 36)
        hgt = int(f.size * 1.35) * len(ls) + 36
        card(fr.d, 120, y, W - 240, hgt, C["panel"], radius=18)
        fr.d.rectangle([120, y, 132, y + hgt], fill=C["accent"])
        draw_lines(fr.d, ls, f, 170, y + 18, C["text"], C["accent"])
        y += hgt + 24
    bf = font("Medium", 28)
    fr.d.text((120, min(y + 6, H - 330)), "根拠：教則（第5版）" + q.get("basis", ""), font=bf, fill=C["sub"])
    subtitle(fr, text)
    return fr


def clip_line(text, f, max_w):
    """1行に入らなければ末尾を「…」にして切る"""
    if f.getlength(text) <= max_w:
        return text
    while text and f.getlength(text + "…") > max_w:
        text = text[:-1]
    return text + "…"


def scene_talk(ep, heading, text, extra=None):
    fr = Frame(ep)
    fr.d.text((120, 150), heading, font=font("Black", 64), fill=C["accent"])
    items = extra or []
    cols = 1 if len(items) <= 6 else 2            # 字幕の上（y=820まで）に必ず収める
    rows = -(-len(items) // cols) if items else 0
    col_w = (W - 300) // cols - (40 if cols == 2 else 0)
    f = font("Bold", 42 if cols == 1 else 38)
    lh = int(f.size * 1.55)
    for k, line in enumerate(items):
        x = 150 + (k // rows) * ((W - 300) // cols)
        y = 270 + (k % rows) * lh
        fr.d.text((x, y), clip_line("・" + line, f, col_w), font=f, fill=C["text"])
    subtitle(fr, text)
    return fr


def thumbnail(ep, path):
    img = Image.new("RGB", (1280, 720), C["bg2"])
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 0, 1280, 720], fill=C["bg1"])
    d.polygon([(0, 520), (1280, 380), (1280, 720), (0, 720)], fill=(255, 196, 0, 255))
    drone_icon(d, 1100, 160, 60, C["accent"])
    d.text((60, 50), "ドローン国家資格 二等学科", font=font("Black", 54), fill=C["accent"])
    f, ls = fit_text(ep.get("thumb", ep.get("theme", "")), "Black", 900, 2, 120, 70)   # 右上のドローンに重ねない
    draw_lines(d, ls, f, 60, 150, (255, 255, 255), C["accent"], lh=1.15)
    tf = font("Black", 92)
    d.text((60, 560), f"ひっかけ{len(ep['questions'])}問", font=tf, fill=(14, 22, 40))
    sf = font("Black", 46)
    d.text((760, 610), "教則第5版対応", font=sf, fill=(14, 22, 40))
    img.save(path)


# ───────── 声 ─────────
def load_voice_cfg():
    th = json.load(open(os.path.join(HERE, "themes", "drone.json"), encoding="utf-8"))
    return th.get("声", {})


class Voice:
    def __init__(self, use):
        self.cfg = load_voice_cfg()
        self.on = False
        if use:
            import voice
            self.v = voice
            self.on = voice.available(dict(self.cfg, エンジン="VOICEVOX"))
        self.table = self.cfg.get("読み替え", {})

    def say(self, text):
        """文を読んだ音（numpy, SR）。声が無ければ文字数から長さを見積もった無音"""
        t = self.read_text(text)
        if self.on:
            return self.v.synth(t, VOICE_SPEED, SR)
        return np.zeros(int(SR * (0.4 + len(t) / 8.0)))

    def read_text(self, text):
        s = str(text).replace("*", "")
        for k in sorted(self.table, key=len, reverse=True):
            v = self.table[k]
            if re.fullmatch(r"[a-z]+", k):
                s = re.sub(r"(?<=[0-9０-９])" + re.escape(k) + r"(?![A-Za-z])", v, s)
            else:
                s = s.replace(k, v)
        return s


# ───────── 組み立て ─────────
class Builder:
    def __init__(self, ep, tmp, voice):
        self.ep, self.tmp, self.v = ep, tmp, voice
        self.t = 0.0
        self.items = []          # (画像のパス, 長さ)
        self.voices = []         # (開始, 音)
        self.sfx = []            # (開始, 名前)
        self.chapters = []       # (開始, 名前)
        self.n = 0

    def img(self, fr):
        self.n += 1
        return fr.save(os.path.join(self.tmp, f"f{self.n:05d}.png"))

    def hold(self, fr, dur):
        self.items.append((self.img(fr), dur))
        self.t += dur

    def speak(self, make_frame, text, tail=GAP):
        """make_frame(text) の画面で text を読む"""
        x = self.v.say(text)
        self.voices.append((self.t + 0.1, x))
        self.hold(make_frame(text), 0.1 + len(x) / SR + tail)

    def build(self):
        ep = self.ep
        self.chapters.append((0.0, "はじめに"))
        self.sfx.append((0.0, "chime"))
        self.hold(scene_title(ep), 2.5)
        for s in ep["intro"]:
            self.speak(lambda tx: scene_talk(ep, ep.get("theme", ""), tx,
                                             [f"Q{k + 1}  {q['q'].replace('*', '')}" for k, q in enumerate(ep["questions"])]), s)
        for i, q in enumerate(ep["questions"]):
            self.chapters.append((self.t, f"Q{i + 1} " + (q.get("chapter") or q["q"].replace("*", "")[:22])))
            self.sfx.append((self.t, "swoosh"))
            two = len(q["choices"]) == 2
            lead = "これ違反？" if two else f"第{i + 1}問"
            ask = scene_question(ep, i, "ask", None)        # 問題と選択肢は画面に出ているので、字幕は出さない
            self.speak(lambda tx: ask, lead + ("" if lead.endswith("？") else "。") + q["q"])
            if not two:
                for k, c in enumerate(q["choices"]):
                    self.speak(lambda tx: ask, f"{'ABC'[k]}、{c}。", tail=0.15)
            for c in range(THINK, 0, -1):
                self.sfx.append((self.t, "tick"))
                self.hold(scene_question(ep, i, "think", None, c), 1.0)
            self.sfx.append((self.t, "chime"))
            ans = "ABC".index(q["answer"].upper())
            self.speak(lambda tx: scene_question(ep, i, "answer", tx), f"正解は、{q['answer'].upper()}、{q['choices'][ans]}、なのだ。", tail=0.5)
            ex = q["explain"]
            np_ = len(q["points"])
            for k, s in enumerate(ex):
                shown = min(np_, 1 + (k * np_) // max(1, len(ex)))
                self.speak(lambda tx, sh=shown: scene_explain(ep, i, sh, tx), s)
            self.hold(scene_explain(ep, i, np_, None), 0.8)
        self.chapters.append((self.t, "まとめ"))
        recap = [q["points"][0].replace("*", "") for q in ep["questions"]]
        for s in ep["outro"]:
            self.speak(lambda tx: scene_talk(ep, "今日のまとめ", tx, recap), s)
        self.sfx.append((self.t, "endchord"))
        self.hold(scene_talk(ep, "今日のまとめ", None, recap), 2.0)
        return self.t


def bgm_bed(dur, seed=5):
    """BGM（Fmaj7→G→Em7→Am7 をくり返す。パッド・ピアノ・ベースに、マリンバの分散和音と軽いリズム）"""
    bpm = 84
    beat = 60 / bpm
    bar = 4 * beat
    n = int(dur * SR) + 2 * SR
    L, R = np.zeros(n), np.zeros(n)
    rng = np.random.default_rng(seed)
    chords = [music.CHORDS[c] for c in music.PROG_A]
    kick, hat_c, hat_o = music.kick(SR, rng, 0.55), music.hat(SR, rng, 0.16), music.hat(SR, rng, 0.10, open_=True)
    arp_order = [0, 1, 2, 3, 2, 1, 0, 2]

    def put(sig, t0, gl=1.0, gr=1.0):
        i = int(t0 * SR)
        sl, sr_ = (sig[:, 0], sig[:, 1]) if sig.ndim == 2 else (sig, sig)
        m = min(len(sl), n - i)
        if m > 0:
            L[i:i + m] += sl[:m] * gl
            R[i:i + m] += sr_[:m] * gr

    t, k = 0.0, 0
    while t < dur + bar:
        ch = chords[k % len(chords)]
        put(music.pad_chord(ch["ep"], bar * 1.05, SR, bright=0.3) * 0.45, t)
        put(music.ep_chord(ch["ep"], bar * 0.9, SR, vel=0.45) * 0.30, t)
        put(music.bass_note(music.hz(ch["bass"]), beat * 1.8, SR, vel=0.6) * 0.40, t)
        put(music.bass_note(music.hz(ch["bass"]), beat * 1.8, SR, vel=0.5) * 0.32, t + 2 * beat)
        for j, idx in enumerate(arp_order):                 # 8分音符のマリンバ（左右に少し振る）
            f = music.hz(ch["arp"][idx])
            pan = 0.35 if j % 2 else -0.35
            put(music.marimba(f, SR, vel=0.5 if j % 4 == 0 else 0.36) * 0.22, t + j * beat / 2, 1 - pan * 0.5, 1 + pan * 0.5)
        if k % 8 != 7:                                      # 8小節目はリズムを抜いて息つぎ
            for q in range(4):
                if q in (0, 2):
                    put(kick * 0.55, t + q * beat)
                put(hat_c * (0.9 if q % 2 else 0.6), t + q * beat + beat / 2)
            put(hat_o * 0.7, t + 3.5 * beat)
        t += bar
        k += 1
    return L[:int(dur * SR)], R[:int(dur * SR)]


def mix_audio(b, dur, path):
    import audio
    n = int(dur * SR)
    vo = np.zeros(n)
    for t0, x in b.voices:
        i = int(t0 * SR)
        m = min(len(x), n - i)
        if m > 0:
            vo[i:i + m] += x[:m]
    if np.abs(vo).max() > 0:
        vo = vo / np.abs(vo).max() * 0.9
    sx = audio.Sfx(7)
    fx = np.zeros(n)
    for t0, name in b.sfx:
        sig = {"chime": sx.chime, "tick": sx.tick, "swoosh": sx.swoosh, "endchord": sx.endchord}[name]()
        i = int(t0 * SR)
        m = min(len(sig), n - i)
        if m > 0:
            fx[i:i + m] += sig[:m] * (0.35 if name == "tick" else 0.5)
    try:
        ml, mr = bgm_bed(dur)
    except Exception as e:                       # BGM が作れなくても、声と効果音だけで仕上げる
        print("BGM なし：", e)
        ml = mr = np.zeros(n)
    if np.abs(ml).max() > 0:
        duck = audio.duck_env(vo, 0.5, rel=0.4, thresh=0.25) if np.abs(vo).max() > 0 else 1.0
        g = 10 ** ((-23.0 - music.loudness(ml, mr, SR)) / 20)   # 声の下でも聞こえるくらい
        ml, mr = ml * g * duck, mr * g * duck
    left, right = vo + fx * 0.5 + ml, vo + fx * 0.5 + mr
    g = 10 ** ((-15.0 - music.loudness(left, right, SR)) / 20)
    left, right = music.limit(left * g, right * g, SR)
    pcm = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def ffmpeg_bin():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def encode(b, wav, out):
    lst = os.path.join(b.tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p, d in b.items:
            f.write(f"file '{p}'\nduration {d:.3f}\n")
        f.write(f"file '{b.items[-1][0]}'\n")
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", wav,
           "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-tune", "stillimage",
           "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)


def stamp(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def description(ep, b, note_url="", site_url=""):
    lines = [ep["title"], "", ep.get("lead", "ドローン国家資格（二等無人航空機操縦士）学科のひっかけ問題を、1問ずつ解説します。内容は国土交通省『無人航空機の飛行の安全に関する教則』（第5版）に対応しています。最新の規則は国土交通省の発表で確かめてください。"), ""]
    lines += ["▼目次"] + [f"{stamp(t)} {name}" for t, name in b.chapters] + [""]
    if note_url:
        lines += ["▼くわしい解説つきの問題集（note）", note_url, ""]
    if site_url:
        lines += ["▼無料の10問ミニ模試", site_url, ""]
    lines += ["音声：VOICEVOX:ずんだもん", "", "#ドローン #ドローン国家資格 #二等無人航空機操縦士 #学科試験 #ずんだもん"]
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    src, out = argv[0], argv[1]
    use_voice = "--no-voice" not in argv
    ep = json.load(open(src, encoding="utf-8"))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if not full_font_available():
        print("注意：Noto Sans CJK が見つかりません。置き場の字の少ないフォントで作るので、字が欠けることがあります。")
    v = Voice(use_voice)
    print("声：", "オン" if v.on else "なし（長さだけ見積もり）")
    with tempfile.TemporaryDirectory() as tmp:
        b = Builder(ep, tmp, v)
        dur = b.build()
        wav = os.path.join(tmp, "a.wav")
        mix_audio(b, dur, wav)
        encode(b, wav, out)
    base = os.path.splitext(out)[0]
    thumbnail(ep, base + "_thumb.png")
    th = json.load(open(os.path.join(HERE, "themes", "drone.json"), encoding="utf-8"))
    note = ""   # ずんだもんの声の規約（情報商材の宣伝に使わない）のため、長尺では note を案内しない。無料のサイトだけ
    site = ep.get("site_url", "https://drone-rulebook.github.io/drone-rule-videos/")
    with open(base + "_desc.txt", "w", encoding="utf-8") as f:
        f.write(description(ep, b, note, site))
    info = {"長さ（秒）": round(dur, 1), "声": "オン" if v.on else "なし", "場面の画像": len(b.items),
            "目次": [[stamp(t), n] for t, n in b.chapters], "フォント": "Noto Sans CJK" if full_font_available() else "置き場の字の少ないフォント"}
    with open(base + "_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
