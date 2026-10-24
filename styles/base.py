# -*- coding: utf-8 -*-
"""3つの型に共通する「流れ」と「置き場所」。

流れ（秒・見た目の版5）：1こま目から問題の全文（掴み）→ 3択 → カウントダウン（3.4〜6.4）→ 正解（6.4）→ ひっかけ（7.1〜）
  →（締めの声を使う動画だけ：毎日1問の帯と声 2.0秒。声は戻る場面転換の途中まで）→ 問題だけの画面へ戻る（1こま目と同じ絵なので、くり返し再生がつながる）
  問題の読み上げが長いときは、カウントダウンから後ろを、読み終わるまで後ろへずらす（Timeline の extra）。
置き場所：大事な文字は drawkit.SAFE の中（下の約4分の1と右端は YouTube の題名やボタンが重なるので避ける）。
  SAFE の下のほうの細い帯（FOOT_Y あたり）は、「毎日18時に1問」と声のクレジットの小さな文字に使う。
"""
import re, zlib
from drawkit import SAFE, PAD, TextBlock, segments, rgba, paste, crop_reveal
import drawkit as dk

# ---------- 流れ（どの型も同じ。動画ごとのずれは Timeline で） ----------
DUR = 11.0                       # 締めの声なし・ずれなしのときの長さ
COUNT0, COUNT1 = 3.4, 6.4        # カウントダウン 3→2→1
REVEAL = 6.4                     # 正解を見せる
TRAP = 7.1                       # ひっかけの説明
TR0, TR1 = 10.2, 10.7            # 問題だけの画面へ戻る場面転換
HOLD = 0.3                       # 戻ったあと、最後に止めておく長さ
CTA_LEN = 2.0                    # 締めの声（毎日1問の帯）の長さ
Q_EXTRA_MAX = 1.2                # 読み上げが長いとき、後ろへずらしてよい上限（3択）
Q_EXTRA_MAX2 = 2.6               # 同じ（2択。場面の文が長いので）
READ_EXTRA2 = 1.0                # 声なしの2択で、場面を読む時間として足す秒数

# ---------- 置き場所（論理座標 720×1280） ----------
Q_X, Q_Y, Q_W = 52, 168, 540     # 問題文
CARD_X, CARD_W = SAFE["left"], 564
CONTENT_BOTTOM = 898             # 問題・選択肢・カウントダウン・ひっかけを置く下の端（その下は小さな文字の帯）
ZONE = 184                       # 選択肢の下に残す高さ（カウントダウンの輪・コメントの呼びかけ・ひっかけ）
FOOT_Y = 918                     # 「毎日18時に1問」の行
CREDIT_Y = 941                   # 声のクレジット
LABEL_Y = 126                    # 見出しの行（縦の真ん中）
ICON_X, ICON_R = 566, 30         # ドローンの絵（真ん中の x と半径）。SAFE の右端 600 の内側


class Timeline:
    """1本の動画の時刻表。extra＝カウントダウンから後ろを後ろへずらす秒数。cta＝締めの声を入れるか。"""

    def __init__(self, extra=0.0, cta=False):
        self.set(extra, cta)

    def set(self, extra, cta):
        e = max(0.0, float(extra))
        self.extra, self.cta = e, bool(cta)
        self.count0, self.count1 = COUNT0 + e, COUNT1 + e
        self.reveal = REVEAL + e
        self.trap = TRAP + e
        t = TR0 + e
        if self.cta:
            self.cta0, self.cta1 = t, t + CTA_LEN
            t += CTA_LEN
        else:
            self.cta0 = self.cta1 = None
        self.tr0, self.tr1 = t, t + (TR1 - TR0)
        self.sw = (self.tr0 + self.tr1) / 2       # 場面転換の途中で、中身が入れかわる時刻
        self.dur = round(self.tr1 + HOLD, 3)
        self.ticks = [self.count0 + k for k in range(3)]

    def times(self):
        """声と BGM に使う時刻（render.py・voice.py・audio.py が読む）"""
        trap_end = (self.cta0 - 0.05) if self.cta else (self.tr1 - 0.1)
        return {"count0": self.count0, "reveal": self.reveal, "ticks": list(self.ticks),
                "q": (0.15, self.count0 - 0.1), "ans": (self.reveal + 0.1, self.reveal + 1.0),
                "trap": (self.reveal + 1.05, trap_end),
                "cta": (self.cta0 + 0.05, self.tr1 - 0.05) if self.cta else None}


def id_number(vid):
    """台本ID の数字（v012 → 12）。無ければ 0"""
    nums = re.findall(r"\d+", str(vid or ""))
    return int(nums[-1]) if nums else 0


def cta_on(vid, theme):
    """この動画に締めの声を入れるか（themes の「締めの声を使う」：偶数・奇数・全部・なし）"""
    mode = str(theme.get("締めの声を使う", "なし")).strip()
    if mode == "全部":
        return True
    if mode in ("偶数", "奇数"):
        n = id_number(vid)
        return (n % 2 == 0) == (mode == "偶数")
    return False


class Look:
    name = "base"
    card_t = [0.3, 0.5, 0.7]      # 選択肢が出る時刻

    def __init__(self, sc, theme, colors, vid=None):
        self.theme, self.words = theme, theme["文言"]
        self.c = {k: rgba(v) for k, v in colors.items()}
        self.n = 3 if str(sc.get("c", "")).strip() else 2      # 選択肢の数（C が空なら2択）
        self.correct = "ABC".index(sc["answer"].strip().upper())
        self.letter = "ABC"[self.correct]
        self.sc = sc
        self.vid = vid
        self.no = id_number(vid)
        self.voice_credit = ""
        self.seed = zlib.crc32((sc["q1"] + sc.get("q2", "")).encode("utf-8"))
        self.T = Timeline(READ_EXTRA2 if self.n == 2 else 0.0, cta_on(vid, theme))
        self.card_t = list(type(self).card_t)[:self.n]

    # ---------- 時刻表 ----------
    @property
    def dur(self):
        return self.T.dur

    def retime(self, extra):
        """カウントダウンから後ろを extra 秒だけ後ろへずらす（読み上げの長さに合わせる）"""
        self.T.set(extra, self.T.cta)

    def q_extra_max(self):
        return Q_EXTRA_MAX2 if self.n == 2 else Q_EXTRA_MAX

    # ---------- 置き場所 ----------
    def place(self, qb, card_h=108, gap=14, zone=ZONE):
        """問題文の下に選択肢を並べ、その下の残り（CONTENT_BOTTOM まで）をカウントダウンとひっかけに使う。
        問題文が長いときは、選択肢の間を詰めて、下に zone（論理座標）だけは残す。"""
        n = self.n
        self.card_h0 = card_h
        avail = CONTENT_BOTTOM - Q_Y - qb.h - 24 - 18 - zone
        fit_h = (avail - (n - 1) * gap) / n
        if fit_h < card_h:
            gap = min(gap, 10)
            card_h = max(84 if n == 3 else 100, (avail - (n - 1) * gap) / n)
        else:
            # 余裕があるときは、選択肢を少し大きく・間を少し広くする（残りは全体を真ん中寄りに下げるのに使う）
            spare = avail - (n * card_h + (n - 1) * gap)
            grow = min(18.0, spare * 0.45 / n)
            card_h += grow
            spare -= grow * n
            gap += min(8.0, spare * 0.3 / max(1, n - 1))
        self.card_h = card_h
        need = qb.h + 24 + n * card_h + (n - 1) * gap + 18 + zone
        self.q_y = Q_Y + max(0, min(90, (CONTENT_BOTTOM - Q_Y - need) / 2))   # 余裕があれば全体を下げて、画面の真ん中寄りに
        top = self.q_y + qb.h + 24
        self.card_y = [top + i * (card_h + gap) for i in range(n)]
        self.zone_top = self.card_y[-1] + card_h + 18
        self.cd_r = 58
        self.cd_y = self.zone_top + 10 + self.cd_r
        self.prompt_y = min(CONTENT_BOTTOM - 14, self.cd_y + self.cd_r + 30)
        self.trap_y = self.zone_top + 14

    def trap_room(self, pad):
        """ひっかけの本文に使える高さ（論理座標）"""
        return CONTENT_BOTTOM - self.trap_y - pad

    # 文字の色の決め方は型ごと（base=ふつうの色、accent=強調の色）
    def q_block(self, base, accent, weight="Bold", px=58, min_px=34, max_w=Q_W):
        paras = [segments(self.sc["q1"], base, accent)]
        if self.sc.get("q2"):
            paras.append(segments(self.sc["q2"], base, accent))
        return TextBlock(paras, weight, max_w, 3 if self.n == 3 else 5, px, min_px, line_h=1.3, cap=0.74, keep_emphasis=True)

    def fit_q(self, make, px, min_px, card_h, gap):
        """問題文を px から作り、選択肢とカウントダウンの場所（ZONE）が CONTENT_BOTTOM に収まるまで小さくする。
        make(px) は TextBlock を返す関数。place() もここで済ませる。"""
        while True:
            qb = make(px)
            self.place(qb, card_h, gap)
            if self.zone_top + ZONE <= CONTENT_BOTTOM + 1 or qb.px <= min_px:
                return qb
            px = qb.px - 2

    def choice_block(self, i, base, accent, max_w, weight="Bold", px=46, min_px=28, max_h=None):
        """選択肢の文字（2行まで）。max_h があれば、その高さに収まるまで小さくする"""
        segs = [segments(self.sc["abc"[i]], base, accent)]
        tb = TextBlock(segs, weight, max_w, 2, px, min_px, line_h=1.2)
        while max_h and tb.h > max_h and tb.px > 24:
            tb = TextBlock(segs, weight, max_w, 2, tb.px - 2, tb.px - 2, line_h=1.2)
        return tb

    def choice_blocks(self, base, accent, max_w, px, max_h):
        """選択肢の文字（長い選択肢だけ小さくなる。短いものは読みやすい大きさのまま）。
        place() で選択肢の高さに余裕ができたときは、文字も少し（最大+6）大きくする"""
        px = px + int(max(0.0, min(6.0, (getattr(self, "card_h", 0) - getattr(self, "card_h0", 1e9)) / 3)))
        return [self.choice_block(i, base, accent, max_w, px=px, max_h=max_h) for i in range(self.n)]

    def trap_parts(self):
        """「ひっかけ：〜」を 見出し と 本文 に分ける"""
        trap = self.sc["trap"]
        if "：" in trap:
            head, body = trap.split("：", 1)
            if 0 < len(head.replace("*", "")) <= 8:
                return head.replace("*", ""), body
        return self.words.get("ひっかけ見出し", "ひっかけ"), trap

    def trap_block(self, base, accent, max_w=520, px=34, min_px=24, weight="Bold", room=150):
        _, body = self.trap_parts()
        lines = 3 if room >= 3 * 30 * 1.28 else 2
        tb = TextBlock([segments(body, base, accent)], weight, max_w, lines, px, min_px, line_h=1.28)
        while tb.h > room and tb.px > min_px - 4:   # 高さに収まらなければ、さらに小さく
            tb = TextBlock([segments(body, base, accent)], weight, max_w, lines, tb.px - 2, tb.px - 2, line_h=1.28)
        return tb

    def label_text(self):
        return self.words.get("ラベル", "")

    def no_text(self):
        return f"No.{self.no}"

    def cta_lines(self):
        """締めの帯の2行（「毎日」の文言を｜で分ける）"""
        s = self.words.get("毎日", "")
        if "｜" in s:
            a, b = s.split("｜", 1)
            return a.strip(), b.strip()
        return s, ""

    # ---------- ドローンの絵（オリジナルの上から見た4枚ローター機） ----------
    def drone_icon(self, color, t, alpha=1.0):
        """上から見たドローン（胴・X字の腕・4つのローター）。ローターの中の弧は t で回る。"""
        r = ICON_R
        key = ("drone", r, tuple(color))
        def make_body():
            def fn(d, k, pad):
                cx = cy = pad + r
                arm = r * 0.62
                w = max(1, int(3.4 * k))
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    d.line([(cx * k, cy * k), ((cx + sx * arm) * k, (cy + sy * arm) * k)], fill=color, width=w)
                rr = r * 0.36
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    x, y = cx + sx * arm, cy + sy * arm
                    d.ellipse([(x - rr) * k, (y - rr) * k, (x + rr) * k, (y + rr) * k], outline=color, width=max(1, int(2.4 * k)))
                    d.ellipse([(x - 2.2) * k, (y - 2.2) * k, (x + 2.2) * k, (y + 2.2) * k], fill=color)
                b = r * 0.26
                d.rounded_rectangle([(cx - b) * k, (cy - b * 0.8) * k, (cx + b) * k, (cy + b * 0.8) * k], radius=b * 0.45 * k, fill=color)
            return dk.aa_shape(2 * r, 2 * r, fn)
        body = dk.cached(key, make_body)
        step = int((t * 30) % 6)                       # ローターの弧は6段階で回す（1こまごとに60度）
        def make_arcs():
            def fn(d, k, pad):
                cx = cy = pad + r
                arm, rr = r * 0.62, r * 0.36 - 3
                a0 = step * 60
                faint = color[:3] + (int(color[3] * 0.55),)
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    x, y = cx + sx * arm, cy + sy * arm
                    box = [(x - rr) * k, (y - rr) * k, (x + rr) * k, (y + rr) * k]
                    d.arc(box, start=a0, end=a0 + 70, fill=faint, width=max(1, int(2.0 * k)))
                    d.arc(box, start=a0 + 180, end=a0 + 250, fill=faint, width=max(1, int(2.0 * k)))
            return dk.aa_shape(2 * r, 2 * r, fn)
        arcs = dk.cached(key + ("arcs", step), make_arcs)
        return body, arcs

    # ---------- 書いている途中のように見せる ----------
    @staticmethod
    def write_block(cv, tb, imgs, x, y, frac, soft=14, center=False, alpha=1.0):
        """TextBlock を左上 (x, y)（center=True なら x は真ん中）に、frac（0〜1）まで書いた状態で貼る"""
        if frac <= 0:
            return
        total = sum(tb.widths) or 1
        done = frac * total
        for i, img in enumerate(imgs):
            lx = (x - tb.widths[i] / 2) if center else x
            ly = y + i * tb.line_h
            w = tb.widths[i]
            if done <= 0:
                break
            f = 1.0 if (frac >= 1 or not w) else min(1.0, done / w)
            done -= w
            spr = img if f >= 0.999 else crop_reveal(img, (PAD + (w + PAD + 1) * f) / (w + 2 * PAD + 1), soft)
            paste(cv, spr, lx - PAD, ly - PAD, alpha=alpha)

    def sounds(self):
        """効果音の予定 [(名前, 時刻, 大きさ, 長さ)]。型ごとに上書きする。"""
        return []
