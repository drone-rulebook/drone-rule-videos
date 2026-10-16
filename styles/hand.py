# -*- coding: utf-8 -*-
"""手で書いていく型（黒板・ノート）の共通部分。文字は書き順のように左から現れ、丸や線は引いていくように伸びる。"""
import math
import drawkit as dk
from drawkit import (CX, SAFE, PAD, paste, prog, ease_out, text_sprite, wobble_path, ellipse_path, partial, stroke_sprite,
                     chalkify)
from .base import Look, COUNT0, COUNT1, REVEAL, TRAP, TR0, TR1, Q_X, CARD_X, CARD_W

WRITE = 0.38   # 選択肢1つを書く時間


class Hand(Look):
    rough = 0.0                  # >0 でチョークのかすれ
    card_t = [0.85, 1.25, 1.65]
    line_w = 4.0                 # 丸や線の太さ

    # 型ごとに決める：self.ink（ふつうの文字）・self.em（強調）・self.ok（正解の丸）・self.ng（まちがいの線）・self.sub（小さな文字）
    def __init__(self, sc, theme, colors):
        super().__init__(sc, theme, colors)
        self.colors()
        self.bg = self.make_bg()
        self.bg_end = self.make_bg_end()
        self._strokes = {}
        self.qb = self.q_block(self.ink, self.em, "Bold", 52, 34)
        self.q_imgs = self.tex(self.qb.line_images(), 1)
        self.place(self.qb, 116, 16)
        tx = CARD_X + 78
        self.c_x = tx
        self.cb = self.choice_blocks(self.ink, self.em, CARD_W - 78 - 30, 42, self.card_h - 6)
        self.c_imgs = [self.tex(b.line_images(), 10 + i) for i, b in enumerate(self.cb)]
        self.letters = [self.tex([text_sprite(L, self.ink, "Black", 36)], 20 + i)[0] for i, L in enumerate("ABC")]
        self.row_cy = [y + self.card_h / 2 for y in self.card_y]
        s = self.seed
        self.p_letter = [self.letter_path(i, s + i) for i in range(3)]
        cy = self.row_cy[self.correct]
        ry = max(self.card_h / 2 + 2, self.cb[self.correct].h / 2 + 16)   # 2行の選択肢でも文字にかからない高さ
        self.p_ok = ellipse_path(CX + 4, cy, 290, ry, s + 7, amp=1.4, power=3.2)
        self.p_ng = {}
        for i in range(3):
            if i != self.correct:          # まちがいの選択肢は、1行ずつ線で消す
                tb = self.cb[i]
                y0 = self.row_cy[i] - tb.h / 2
                self.p_ng[i] = [wobble_path([(tx - 8, y0 + (k + 0.55) * tb.line_h + 2), (tx + w + 10, y0 + (k + 0.55) * tb.line_h - 3)],
                                            s + 30 + i * 5 + k, 1.0, 10) for k, w in enumerate(tb.widths)]
        self.p_count = ellipse_path(CX, self.cd_y - 2, 64, 62, s + 9, turns=1.0, start=-math.pi / 2, amp=1.2)
        self.p_under = [wobble_path([(Q_X + x0 - 2, self.q_y + (i + 0.93) * self.qb.line_h), (Q_X + x1 + 2, self.q_y + (i + 0.93) * self.qb.line_h)],
                                    s + 40 + k, 1.0, 10) for k, (i, x0, x1) in enumerate(self.qb.spans)]
        self.make_trap()
        self.make_end()

    # ---------- 型ごとに上書き ----------
    def colors(self):
        raise NotImplementedError

    def make_bg(self):
        raise NotImplementedError

    def make_bg_end(self):
        return self.bg

    def letter_path(self, i, seed):
        return ellipse_path(CARD_X + 30, self.row_cy[i], 26, 25, seed, turns=1.08, amp=0.8)

    def emphasis(self, cv, t):
        """問題文の強調のしるし（黒板＝下線、ノート＝マーカー）"""
        for k, path in enumerate(self.p_under):
            self.stroke(cv, ("u", k), path, prog(t, 0.95 + 0.12 * k, 1.25 + 0.12 * k), self.em, 3.2)

    def header(self, cv, t):
        spr = self.tex([text_sprite(self.words["ラベル"], self.sub, "Bold", 26)], 3)[0]
        w = spr.width / dk.R - 2 * PAD
        self.write_spr(cv, spr, SAFE["left"], 108, prog(t, -0.4, 0.0))
        path = self._strokes.get("hpath")
        if path is None:
            path = self._strokes["hpath"] = wobble_path([(SAFE["left"], 146), (SAFE["left"] + w, 144)], self.seed + 2, 0.8, 10)
        self.stroke(cv, "h", path, prog(t, -0.1, 0.25), self.sub, 2.4)

    def transition(self, t):
        raise NotImplementedError

    # ---------- 道具 ----------
    def tex(self, imgs, seed):
        if not self.rough:
            return imgs
        key = ("tex", id(imgs[0]) if imgs else 0, seed)
        if key not in self._strokes:
            self._strokes[key] = [chalkify(im, self.seed + seed * 131 + k * 17, self.rough) for k, im in enumerate(imgs)]
        return self._strokes[key]

    def stroke(self, cv, key, path, frac, color, width, alpha=1.0):
        if frac <= 0:
            return
        if frac >= 1:
            k = ("st", key, color, width)
            if k not in self._strokes:
                self._strokes[k] = stroke_sprite(path, color, width, self.rough * 0.9, self.seed)
            spr, (x, y) = self._strokes[k]
        else:
            spr, (x, y) = stroke_sprite(partial(path, frac), color, width, self.rough * 0.9, self.seed)
        if spr is not None:
            paste(cv, spr, x, y, alpha=alpha)

    def write_spr(self, cv, spr, x, y, frac, alpha=1.0, anchor_center=False):
        """1枚の文字画像を、左から frac まで書いた状態で貼る（x, y は文字の左上。anchor_center なら x は真ん中）"""
        if frac <= 0:
            return
        if anchor_center:
            x -= (spr.width / dk.R) / 2 - PAD
        s = spr if frac >= 1 else dk.crop_reveal(spr, frac, 12)
        paste(cv, s, x - PAD, y - PAD, alpha=alpha)

    # ---------- 1こま ----------
    def frame(self, t):
        if t < TR0:
            cv = self.bg.copy()
            self.scene(cv, t)
        elif t < TR1:
            cv = self.transition(t)
        else:
            cv = self.bg_end.copy()
            self.ending(cv, t)
        return cv.convert("RGB")

    def scene(self, cv, t):
        self.header(cv, t)
        self.emphasis_under(cv, t)
        self.write_block(cv, self.qb, self.q_imgs, Q_X, self.q_y, prog(t, -0.25, 0.85))
        self.emphasis(cv, t)
        self.choices(cv, t)
        self.countdown(cv, t)
        self.answer(cv, t)

    def emphasis_under(self, cv, t):
        """文字の下に描くもの（ノートのマーカー）"""

    def choices(self, cv, t):
        rv = prog(t, REVEAL, REVEAL + 0.3)
        for i in range(3):
            t0 = self.card_t[i]
            if t < t0:
                continue
            a = 1.0 if i == self.correct else 1 - 0.5 * rv
            y = self.row_cy[i]
            self.stroke(cv, ("L", i), self.p_letter[i], prog(t, t0, t0 + 0.18), self.sub, 3.0, alpha=a)
            paste(cv, self.letters[i], CARD_X + 30, y + 1, alpha=a * prog(t, t0 + 0.05, t0 + 0.15), anchor="cc")
            tb = self.cb[i]
            self.write_block(cv, tb, self.c_imgs[i], self.c_x, y - tb.h / 2, prog(t, t0 + 0.1, t0 + 0.1 + WRITE), alpha=a)
        if t >= REVEAL:
            self.stroke(cv, "ok", self.p_ok, ease_out(prog(t, REVEAL, REVEAL + 0.4)), self.ok, self.line_w + 1)
            for k, (i, paths) in enumerate(self.p_ng.items()):
                for j, path in enumerate(paths):
                    t1 = REVEAL + 0.25 + 0.12 * k + 0.08 * j
                    self.stroke(cv, ("ng", i, j), path, prog(t, t1, t1 + 0.18), self.ng, self.line_w)

    def countdown(self, cv, t):
        if not (COUNT0 - 0.1 <= t < COUNT1 + 0.15):
            return
        a = 1 - prog(t, COUNT1, COUNT1 + 0.15)
        self.stroke(cv, "cd", self.p_count, prog(t, COUNT0, COUNT1), self.em, self.line_w, alpha=a)
        k = min(2, int(max(0.0, t - COUNT0)))
        spr = self.tex([text_sprite(str(3 - k), self.ink, "Black", 84)], 30 + k)[0]
        f = prog(t, COUNT0 + k - 0.02, COUNT0 + k + 0.16)
        x = CX - spr.width / dk.R / 2
        paste(cv, dk.crop_reveal(spr, f, 10) if f < 1 else spr, x, self.cd_y - spr.height / dk.R / 2 - 4, alpha=a)

    def answer(self, cv, t):
        if t < REVEAL:
            return
        q = prog(t, TRAP - 0.05, TRAP + 0.2)
        if q < 1:
            lab = self.tex([text_sprite(self.words["正解"], self.ink, "Black", 40)], 40)[0]
            let = self.tex([text_sprite(self.letter, self.ok, "Black", 84)], 41)[0]
            lw, ew = lab.width / dk.R - 2 * PAD, let.width / dk.R - 2 * PAD
            x0 = CX - (lw + ew + 8) / 2
            f = prog(t, REVEAL + 0.1, REVEAL + 0.4)
            self.write_spr(cv, lab, x0, self.cd_y - 20, f * 1.6, alpha=1 - q)
            self.write_spr(cv, let, x0 + lw + 8, self.cd_y - 58, f * 1.6 - 0.6, alpha=1 - q)
        self.trap(cv, t)

    # ---------- ひっかけ ----------
    def make_trap(self):
        head, _ = self.trap_parts()
        self.tb = self.trap_block(self.ink, self.em, 520, 40, 24, room=self.trap_room(66))
        self.t_imgs = self.tex(self.tb.line_images(), 50)
        self.t_head = self.tex([text_sprite(head, self.ng, "Black", 30)], 51)[0]
        self.t_ans = self.tex([text_sprite(self.words["正解"] + " " + self.letter, self.ok, "Black", 30)], 52)[0]
        self.trap_h = self.tb.h + 62

    def trap(self, cv, t):
        if t < TRAP:
            return
        x, y = CARD_X + 14, self.trap_y + 10
        aw = self.t_ans.width / dk.R - 2 * PAD
        self.write_spr(cv, self.t_ans, x, y, prog(t, TRAP, TRAP + 0.2))
        self.write_spr(cv, self.t_head, x + aw + 22, y, prog(t, TRAP + 0.15, TRAP + 0.35))
        self.write_block(cv, self.tb, self.t_imgs, x + 6, y + 52, prog(t, TRAP + 0.35, TRAP + 1.1))

    # ---------- 締め ----------
    def make_end(self):
        w = self.words
        self.e_lines = []
        items = [(self.theme.get("チャンネル名", ""), self.sub, "Bold", 28, 420), (w["締め1"], self.em, "Black", 104, 530),
                 (w["締め2"], self.ink, "Black", 60, 642), (w["締め3"], self.ink, "Bold", 32, 760),
                 (w.get("締め4", ""), self.em, "Bold", 30, 822)]
        for k, (txt, col, wt, px, y) in enumerate(items):
            if txt:
                self.e_lines.append((self.tex([text_sprite(txt, col, wt, px)], 60 + k)[0], y))
        bw = 300
        self.p_end = wobble_path([(CX - bw / 2, 702), (CX + bw / 2, 699)], self.seed + 70, 1.0, 10)

    def ending(self, cv, t):
        t0 = TR1 - 0.05
        for k, (spr, y) in enumerate(self.e_lines):
            f = prog(t, t0 + 0.16 * k, t0 + 0.16 * k + 0.3)
            self.write_spr(cv, spr, CX, y - spr.height / dk.R / 2 + PAD, f, anchor_center=True)
        self.stroke(cv, "end", self.p_end, prog(t, t0 + 0.55, t0 + 0.85), self.em, self.line_w + 1)
        if self.voice_credit:
            spr = text_sprite(self.voice_credit, self.sub, "Medium", 15)
            paste(cv, spr, CX, 900, alpha=prog(t, t0 + 0.8, t0 + 1.1), anchor="cc")

    def sounds(self):
        ev = [("write", -0.1, 0.30, 0.95)]
        for ct in self.card_t:
            ev.append(("write", ct, 0.26, WRITE + 0.1))
        ev.append(("write", 0.95, 0.15, 0.4))
        for k in range(3):
            ev.append(("tap", COUNT0 + k, 0.55, 0))
            ev.append(("tick", COUNT0 + k, 0.25, 0))
        ev += [("chime", REVEAL, 0.26, 0), ("circle", REVEAL, 0.32, 0.4), ("write", REVEAL + 0.25, 0.2, 0.35),
               ("write", TRAP, 0.26, 1.1), ("endchord", TR1 + 0.05, 0.12, 0), ("write", TR1 - 0.05, 0.24, 1.0)]
        return ev
