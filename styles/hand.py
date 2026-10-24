# -*- coding: utf-8 -*-
"""手で書いていく型（黒板・ノート）の共通部分。文字は書き順のように左から現れ、丸や線は引いていくように伸びる。
見た目の版5：1こま目から見出しと問題文は書き終わった状態（掴み）。選択肢から先を書いていく。最後は問題だけの画面へ戻る。"""
import math
import drawkit as dk
from drawkit import (CX, SAFE, PAD, paste, prog, ease_out, text_sprite, wobble_path, ellipse_path, partial, stroke_sprite,
                     chalkify)
from .base import Look, Q_X, CARD_X, CARD_W, FOOT_Y, CREDIT_Y, LABEL_Y, ICON_X

WRITE = 0.28   # 選択肢1つを書く時間


class Hand(Look):
    rough = 0.0                  # >0 でチョークのかすれ
    card_t = [0.45, 0.75, 1.05]
    line_w = 4.0                 # 丸や線の太さ

    # 型ごとに決める：self.ink（ふつうの文字）・self.em（強調）・self.ok（正解の丸）・self.ng（まちがいの線）・self.sub（小さな文字）
    def __init__(self, sc, theme, colors, vid=None):
        super().__init__(sc, theme, colors, vid)
        self.colors()
        self.bg = self.make_bg()
        self._strokes = {}
        two = self.n == 2
        self.qb = self.fit_q(lambda px: self.q_block(self.ink, self.em, "Bold", px, 32), 58 if not two else 54, 32,
                             128 if two else 112, 18 if two else 14)
        self.q_imgs = self.tex(self.qb.line_images(), 1)
        tx = CARD_X + 78
        self.c_x = tx
        self.cb = self.choice_blocks(self.ink, self.em, CARD_W - 78 - 30, 52 if two else 46, self.card_h - 6)
        self.c_imgs = [self.tex(b.line_images(), 10 + i) for i, b in enumerate(self.cb)]
        self.letters = [self.tex([text_sprite(L, self.ink, "Black", 36)], 20 + i)[0] for i, L in enumerate("ABC"[:self.n])]
        self.row_cy = [y + self.card_h / 2 for y in self.card_y]
        s = self.seed
        self.p_letter = [self.letter_path(i, s + i) for i in range(self.n)]
        cy = self.row_cy[self.correct]
        ry = max(self.card_h / 2 + 2, self.cb[self.correct].h / 2 + 16)   # 2行の選択肢でも文字にかからない高さ
        self.p_ok = ellipse_path(CX + 4, cy, 290, ry, s + 7, amp=1.4, power=3.2)
        self.p_ng = {}
        for i in range(self.n):
            if i != self.correct:          # まちがいの選択肢は、1行ずつ線で消す
                tb = self.cb[i]
                y0 = self.row_cy[i] - tb.h / 2
                self.p_ng[i] = [wobble_path([(tx - 8, y0 + (k + 0.55) * tb.line_h + 2), (tx + w + 10, y0 + (k + 0.55) * tb.line_h - 3)],
                                            s + 30 + i * 5 + k, 1.0, 10) for k, w in enumerate(tb.widths)]
        r = self.cd_r
        self.p_count = ellipse_path(CX, self.cd_y - 2, r + 2, r, s + 9, turns=1.0, start=-math.pi / 2, amp=1.2)
        self.p_under = [wobble_path([(Q_X + x0 - 2, self.q_y + (i + 0.93) * self.qb.line_h), (Q_X + x1 + 2, self.q_y + (i + 0.93) * self.qb.line_h)],
                                    s + 40 + k, 1.0, 10) for k, (i, x0, x1) in enumerate(self.qb.spans)]
        self.make_label()
        self.make_trap()
        self.make_cta()
        self.make_small()

    # ---------- 型ごとに上書き ----------
    def colors(self):
        raise NotImplementedError

    def make_bg(self):
        raise NotImplementedError

    def letter_path(self, i, seed):
        return ellipse_path(CARD_X + 30, self.row_cy[i], 26, 25, seed, turns=1.08, amp=0.8)

    def emphasis(self, cv, t):
        """問題文の強調のしるし（黒板＝下線、ノート＝マーカー）。1こま目のあとすぐに引く"""
        for k, path in enumerate(self.p_under):
            self.stroke(cv, ("u", k), path, prog(t, 0.15 + 0.1 * k, 0.45 + 0.1 * k), self.em, 3.2)

    def transition(self, t):
        raise NotImplementedError

    # ---------- 見出し（1こま目から書いてある） ----------
    def make_label(self):
        spr = self.tex([text_sprite(self.label_text(), self.sub, "Bold", 26)], 3)[0]
        self.label_spr = spr
        self.label_w = spr.width / dk.R - 2 * PAD
        self.no_spr = self.tex([text_sprite(self.no_text(), self.sub, "Bold", 24)], 4)[0]
        self.p_label = wobble_path([(SAFE["left"], LABEL_Y + 20), (SAFE["left"] + self.label_w, LABEL_Y + 18)], self.seed + 2, 0.8, 10)

    def header(self, cv, t):
        paste(cv, self.label_spr, SAFE["left"] - PAD, LABEL_Y - 18 - PAD)
        self.stroke(cv, "h", self.p_label, 1.0, self.sub, 2.4)
        paste(cv, self.no_spr, SAFE["left"] + self.label_w + 16 - PAD, LABEL_Y - 16 - PAD)
        body, arcs = self.drone_icon(self.icon_color(), t)
        paste(cv, body, ICON_X, LABEL_Y, anchor="cc")
        paste(cv, arcs, ICON_X, LABEL_Y, anchor="cc")

    def icon_color(self):
        return self.ink

    def hook(self, cv, t):
        """1こま目の絵（見出し・番号・ドローン・問題文）。最後に戻る絵も同じ"""
        self.header(cv, t)
        self.write_block(cv, self.qb, self.q_imgs, Q_X, self.q_y, 1.0)

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
        T = self.T
        if t < T.tr0:
            cv = self.bg.copy()
            self.scene(cv, t)
        elif t < T.tr1:
            cv = self.transition(t)
        else:
            cv = self.hook_state(t - T.dur)
        return cv.convert("RGB")

    def hook_state(self, t):
        cv = self.bg.copy()
        self.hook(cv, t)
        return cv

    def scene(self, cv, t):
        self.emphasis_under(cv, t)
        self.hook(cv, t)
        self.emphasis(cv, t)
        self.choices(cv, t)
        self.countdown(cv, t)
        self.answer(cv, t)
        self.footer(cv, t)

    def emphasis_under(self, cv, t):
        """文字の下に描くもの（ノートのマーカー）"""

    def choices(self, cv, t):
        T = self.T
        rv = prog(t, T.reveal, T.reveal + 0.3)
        for i in range(self.n):
            t0 = self.card_t[i]
            if t < t0:
                continue
            a = 1.0 if i == self.correct else 1 - 0.5 * rv
            y = self.row_cy[i]
            self.stroke(cv, ("L", i), self.p_letter[i], prog(t, t0, t0 + 0.15), self.sub, 3.0, alpha=a)
            paste(cv, self.letters[i], CARD_X + 30, y + 1, alpha=a * prog(t, t0 + 0.04, t0 + 0.12), anchor="cc")
            tb = self.cb[i]
            self.write_block(cv, tb, self.c_imgs[i], self.c_x, y - tb.h / 2, prog(t, t0 + 0.08, t0 + 0.08 + WRITE), alpha=a)
        if t >= T.reveal:
            self.stroke(cv, "ok", self.p_ok, ease_out(prog(t, T.reveal, T.reveal + 0.4)), self.ok, self.line_w + 1)
            for k, (i, paths) in enumerate(self.p_ng.items()):
                for j, path in enumerate(paths):
                    t1 = T.reveal + 0.25 + 0.12 * k + 0.08 * j
                    self.stroke(cv, ("ng", i, j), path, prog(t, t1, t1 + 0.18), self.ng, self.line_w)

    def countdown(self, cv, t):
        T = self.T
        if not (T.count0 - 0.1 <= t < T.count1 + 0.1):
            return
        a = 1 - prog(t, T.count1 - 0.05, T.count1 + 0.08)
        self.stroke(cv, "cd", self.p_count, prog(t, T.count0, T.count1), self.em, self.line_w, alpha=a)
        k = min(2, int(max(0.0, t - T.count0)))
        spr = self.tex([text_sprite(str(3 - k), self.ink, "Black", 80)], 30 + k)[0]
        f = prog(t, T.count0 + k - 0.02, T.count0 + k + 0.16)
        x = CX - spr.width / dk.R / 2
        paste(cv, dk.crop_reveal(spr, f, 10) if f < 1 else spr, x, self.cd_y - spr.height / dk.R / 2 - 4, alpha=a)
        if self.prompt_spr is not None:
            self.write_spr(cv, self.prompt_spr, CX, self.prompt_y - 16, prog(t, T.count0 - 0.1, T.count0 + 0.3),
                           alpha=a, anchor_center=True)

    def answer(self, cv, t):
        T = self.T
        if t < T.reveal:
            return
        q = prog(t, T.trap - 0.05, T.trap + 0.2)
        if q < 1:
            lab = self.tex([text_sprite(self.words["正解"], self.ink, "Black", 40)], 40)[0]
            let = self.tex([text_sprite(self.letter, self.ok, "Black", 84)], 41)[0]
            lw, ew = lab.width / dk.R - 2 * PAD, let.width / dk.R - 2 * PAD
            x0 = CX - (lw + ew + 8) / 2
            f = prog(t, T.reveal + 0.1, T.reveal + 0.4)
            self.write_spr(cv, lab, x0, self.cd_y - 20, f * 1.6, alpha=1 - q)
            self.write_spr(cv, let, x0 + lw + 8, self.cd_y - 58, f * 1.6 - 0.6, alpha=1 - q)
        if T.cta and t >= T.cta0:
            self.cta(cv, t)
        else:
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
        T = self.T
        if t < T.trap:
            return
        x, y = CARD_X + 14, self.trap_y + 10
        aw = self.t_ans.width / dk.R - 2 * PAD
        self.write_spr(cv, self.t_ans, x, y, prog(t, T.trap, T.trap + 0.2))
        self.write_spr(cv, self.t_head, x + aw + 22, y, prog(t, T.trap + 0.15, T.trap + 0.35))
        self.write_block(cv, self.tb, self.t_imgs, x + 6, y + 52, prog(t, T.trap + 0.35, T.trap + 1.0))

    # ---------- 締めの帯（締めの声を使う動画だけ） ----------
    def make_cta(self):
        a, b = self.cta_lines()
        self.cta_s1 = self.tex([text_sprite(a, self.em, "Black", 46)], 70)[0] if a else None
        self.cta_s2 = self.tex([text_sprite(b, self.ink, "Bold", 28)], 71)[0] if b else None
        self.cta_h = 128 if self.cta_s2 is not None else 90
        bw = 320
        y = self.trap_y + 70
        self.p_cta = wobble_path([(CX - bw / 2, y), (CX + bw / 2, y - 3)], self.seed + 72, 1.0, 10)

    def cta(self, cv, t):
        T = self.T
        y = self.trap_y + 12
        if self.cta_s1 is not None:
            self.write_spr(cv, self.cta_s1, CX, y, prog(t, T.cta0 + 0.05, T.cta0 + 0.45), anchor_center=True)
        self.stroke(cv, "cta", self.p_cta, prog(t, T.cta0 + 0.4, T.cta0 + 0.65), self.em, self.line_w)
        if self.cta_s2 is not None:
            self.write_spr(cv, self.cta_s2, CX, y + 76, prog(t, T.cta0 + 0.5, T.cta0 + 0.9), anchor_center=True)

    # ---------- 小さな文字（コメントの呼びかけ・毎日1問・声のクレジット） ----------
    def make_small(self):
        pr = self.words.get("コメント", "")
        self.prompt_spr = self.tex([text_sprite(pr, self.sub, "Bold", 28)], 80)[0] if pr else None
        line = self.words.get("毎日", "")
        self.foot_spr = text_sprite(line, self.sub, "Bold", 22) if line else None

    def footer(self, cv, t):
        T = self.T
        end = T.cta0 if T.cta else T.tr0
        a = ease_out(prog(t, T.count0 - 0.2, T.count0 + 0.1)) * (1 - prog(t, end, end + 0.25))
        if self.foot_spr is not None and a > 0:
            paste(cv, self.foot_spr, CX, FOOT_Y, alpha=a * 0.9, anchor="cc")
        if self.voice_credit:
            ac = ease_out(prog(t, T.trap, T.trap + 0.3)) * (1 - prog(t, T.tr0, T.tr0 + 0.25))
            if ac > 0:
                paste(cv, text_sprite(self.voice_credit, self.sub, "Medium", 15), CX, CREDIT_Y, alpha=ac * 0.85, anchor="cc")

    def sounds(self):
        T = self.T
        ev = []
        for ct in self.card_t:
            ev.append(("write", ct, 0.26, WRITE + 0.1))
        ev.append(("write", 0.15, 0.12, 0.3))                 # 強調の線
        for tk in T.ticks:
            ev.append(("tap", tk, 0.55, 0))
            ev.append(("tick", tk, 0.25, 0))
        ev += [("chime", T.reveal, 0.26, 0), ("circle", T.reveal, 0.32, 0.4), ("write", T.reveal + 0.25, 0.2, 0.35),
               ("write", T.trap, 0.26, 1.0)]
        if T.cta:
            ev.append(("write", T.cta0 + 0.05, 0.24, 0.85))
        return ev
