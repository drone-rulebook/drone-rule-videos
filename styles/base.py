# -*- coding: utf-8 -*-
"""3つの型に共通する「流れ」と「置き場所」。

流れ（秒）：問題（0秒から）→ 3択 → カウントダウン（5〜8）→ 正解（8）→ ひっかけ（8.75〜）→ 締め（12前後〜14）
置き場所：大事な文字は drawkit.SAFE の中（下の約4分の1と右端は YouTube の題名やボタンが重なるので避ける）
"""
import zlib
from drawkit import SAFE, PAD, TextBlock, segments, rgba, paste, crop_reveal

# ---------- 流れ（どの型も同じ） ----------
DUR = 14.0
COUNT0, COUNT1 = 5.0, 8.0       # カウントダウン 3→2→1
REVEAL = 8.0                     # 正解を見せる
TRAP = 8.75                      # ひっかけの説明
TR0, TR1 = 11.6, 12.2            # 締めへの場面転換
SWITCH = 11.9                    # 転換の途中で中身が入れかわる

# ---------- 置き場所（論理座標 720×1280） ----------
Q_X, Q_Y, Q_W = 52, 166, 540     # 問題文
CARD_X, CARD_W = SAFE["left"], 564
# 選択肢・カウントダウン・ひっかけの縦の位置は、問題文の行数に合わせて Look.place() で決める


class Look:
    name = "base"
    card_t = [0.45, 0.65, 0.85]   # 選択肢が出る時刻

    def __init__(self, sc, theme, colors):
        self.theme, self.words = theme, theme["文言"]
        self.c = {k: rgba(v) for k, v in colors.items()}
        self.correct = "ABC".index(sc["answer"].strip().upper())
        self.letter = "ABC"[self.correct]
        self.sc = sc
        self.voice_credit = ""
        self.seed = zlib.crc32((sc["q1"] + sc.get("q2", "")).encode("utf-8"))

    def place(self, qb, card_h=108, gap=14, zone=250):
        """問題文の下に選択肢を並べ、その下の残り（SAFE の下端まで）をカウントダウンとひっかけに使う。
        問題文が長いときは、選択肢の間を詰めて、下に zone（論理座標）だけは残す。"""
        avail = SAFE["bottom"] - Q_Y - qb.h - 24 - 18 - zone
        fit_h = (avail - 2 * gap) / 3
        if fit_h < card_h:
            gap = min(gap, 10)
            card_h = max(92, (avail - 2 * gap) / 3)
        self.card_h = card_h
        need = qb.h + 24 + 3 * card_h + 2 * gap + 18 + zone
        self.q_y = Q_Y + max(0, min(60, (SAFE["bottom"] - Q_Y - need) / 2))   # 余裕があれば全体を少し下げて、画面の真ん中寄りに
        top = self.q_y + qb.h + 24
        self.card_y = [top + i * (card_h + gap) for i in range(3)]
        self.zone_top = self.card_y[2] + card_h + 18
        self.cd_y = min(880, (self.zone_top + SAFE["bottom"]) / 2)
        self.trap_y = self.zone_top + 14

    def trap_room(self, pad):
        """ひっかけの本文に使える高さ（論理座標）"""
        return SAFE["bottom"] - self.trap_y - pad

    # 文字の色の決め方は型ごと（base=ふつうの色、accent=強調の色）
    def q_block(self, base, accent, weight="Bold", px=48, min_px=32, max_w=Q_W):
        paras = [segments(self.sc["q1"], base, accent)]
        if self.sc.get("q2"):
            paras.append(segments(self.sc["q2"], base, accent))
        return TextBlock(paras, weight, max_w, 3, px, min_px, line_h=1.3)

    def choice_block(self, i, base, accent, max_w, weight="Bold", px=40, min_px=26, max_h=None):
        """選択肢の文字（2行まで）。max_h があれば、その高さに収まるまで小さくする"""
        segs = [segments(self.sc["abc"[i]], base, accent)]
        tb = TextBlock(segs, weight, max_w, 2, px, min_px, line_h=1.2)
        while max_h and tb.h > max_h and tb.px > 24:
            tb = TextBlock(segs, weight, max_w, 2, tb.px - 2, tb.px - 2, line_h=1.2)
        return tb

    def choice_blocks(self, base, accent, max_w, px, max_h):
        """3つの選択肢の文字（長い選択肢だけ小さくなる。短いものは読みやすい大きさのまま）"""
        return [self.choice_block(i, base, accent, max_w, px=px, max_h=max_h) for i in range(3)]

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
