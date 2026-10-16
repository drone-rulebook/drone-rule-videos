# -*- coding: utf-8 -*-
"""型1「モーション」：平らな図形がすっと動く、モーショングラフィックス風。"""
import math
import numpy as np
from PIL import Image, ImageDraw
import drawkit as dk
from drawkit import (CX, SAFE, PAD, paste, prog, ease_out, ease_back, ease_in_out, with_alpha, rrect, circle, shadow,
                     text_sprite, cached, aa_shape)
from .base import Look, COUNT0, COUNT1, REVEAL, TRAP, TR0, TR1, SWITCH, Q_X, CARD_X, CARD_W


class Motion(Look):
    name = "モーション"
    card_t = [0.45, 0.65, 0.85]

    def __init__(self, sc, theme, colors):
        super().__init__(sc, theme, colors)
        c = self.c
        self.bg = self.make_bg()
        self.qb = self.q_block(c["文字"], c["強調"], "Black", 52, 34)
        self.q_imgs = self.qb.line_images()
        self.place(self.qb, 112, 16)
        self.cb = self.choice_blocks(c["カードの文字"], c.get("カードの強調", c["カードの文字"]), CARD_W - 100 - 70, 42, self.card_h - 14)
        self.cards = [self.make_card(i, False) for i in range(3)]
        self.cards_done = [self.make_card(i, True) for i in range(3)]
        self.tb = self.trap_block(c["文字"], c["強調"], 516, min_px=24, room=self.trap_room(50), px=38)
        self.trap_img = self.make_trap()

    # ---------- 動かない部品 ----------
    def make_bg(self):
        c = self.c
        img = dk.vgradient(c["背景上"], c["背景下"]).convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        R = dk.R
        # うすい大きな円と点の格子（模様。動かさない）
        for (x, y, r, a) in ((640, 140, 260, 14), (40, 1180, 320, 10), (700, 980, 150, 8)):
            d.ellipse([(x - r) * R, (y - r) * R, (x + r) * R, (y + r) * R], fill=with_alpha(c["強調"], a))
        for gy in range(40, 1280, 40):
            for gx in range(20, 720, 40):
                d.ellipse([(gx - 1.3) * R, (gy - 1.3) * R, (gx + 1.3) * R, (gy + 1.3) * R], fill=(255, 255, 255, 9))
        img = dk.vignette(img, 0.35)
        return dk.add_grain(img, 5.0, 3)

    def make_card(self, i, done):
        c = self.c
        correct = i == self.correct
        fill = c["強調"] if (done and correct) else c["カード"]
        w, h = CARD_W, self.card_h
        pad = 24
        img = Image.new("RGBA", (int((w + pad * 2) * dk.R), int((h + pad * 2) * dk.R)), (0, 0, 0, 0))
        img.alpha_composite(shadow(w, h, 22, 12, 110), dest=(int((pad - 24 + 0) * dk.R), int((pad - 24 + 6) * dk.R)))
        img.alpha_composite(rrect(w, h, 22, fill), dest=(int((pad - 4) * dk.R), int((pad - 4) * dk.R)))
        # A・B・C の丸
        cy = pad + h / 2
        img.alpha_composite(circle(30, c["背景上"]), dest=(int((pad + 20 - 4) * dk.R), int((cy - 30 - 4) * dk.R)))
        lt = text_sprite("ABC"[i], c["文字"], "Black", 34)
        img.alpha_composite(lt, dest=(int((pad + 50) * dk.R - lt.width / 2), int(cy * dk.R - lt.height / 2)))
        tb = self.cb[i]
        for k, li in enumerate(tb.line_images()):
            y = cy - tb.h / 2 + k * tb.line_h
            img.alpha_composite(li, dest=(int((pad + 100 - PAD) * dk.R), int((y - PAD) * dk.R)))
        return img

    def make_mark(self, ok):
        c = self.c
        def fn(d, k, pad):
            if ok:
                d.ellipse([pad * k, pad * k, (pad + 56) * k, (pad + 56) * k], fill=c["背景上"])
                d.line([((pad + 15) * k, (pad + 29) * k), ((pad + 25) * k, (pad + 39) * k), ((pad + 42) * k, (pad + 18) * k)],
                       fill=c["強調"], width=int(7 * k), joint="curve")
            else:
                for a, b in (((pad + 14, pad + 14), (pad + 42, pad + 42)), ((pad + 14, pad + 42), (pad + 42, pad + 14))):
                    d.line([(a[0] * k, a[1] * k), (b[0] * k, b[1] * k)], fill=c["まちがい"], width=int(8 * k))
        return cached(("mk", ok, tuple(c["強調"])), lambda: aa_shape(56, 56, fn))

    def make_trap(self):
        c = self.c
        head, _ = self.trap_parts()
        tb = self.tb
        w, h = CARD_W, tb.h + 46
        pad = 30
        img = Image.new("RGBA", (int((w + pad * 2) * dk.R), int((h + pad * 2) * dk.R)), (0, 0, 0, 0))
        img.alpha_composite(rrect(w, h, 18, c["面"]), dest=(int((pad - 4) * dk.R), int((pad - 4) * dk.R)))
        x = pad + 18
        for txt, bg, fg in ((self.words["正解"] + " " + self.letter, c["強調"], c["カードの文字"]), (head, c["まちがい"], c["文字"])):
            tag = text_sprite(txt, fg, "Black", 26)
            tw = tag.width / dk.R
            img.alpha_composite(rrect(tw + 12, 40, 20, bg), dest=(int((x - 4) * dk.R), int((pad - 18 - 4) * dk.R)))
            img.alpha_composite(tag, dest=(int((x + 6) * dk.R), int(pad * dk.R - tag.height / 2)))
            x += tw + 22
        for k, li in enumerate(tb.line_images()):
            img.alpha_composite(li, dest=(int((pad + 22 - PAD) * dk.R), int((pad + 30 + k * tb.line_h - PAD) * dk.R)))
        self.trap_pad = pad
        return img

    # ---------- 1こま ----------
    def frame(self, t):
        cv = self.bg.copy()
        if t < SWITCH:
            self.header(cv, t)
            self.question(cv, t)
            self.draw_cards(cv, t)
            self.countdown(cv, t)
            self.answer(cv, t)
        else:
            self.ending(cv, t)
        self.wipe(cv, t)
        return cv.convert("RGB")

    def header(self, cv, t):
        c = self.c
        p = ease_out(prog(t, -0.3, 0.3))
        spr = text_sprite(self.words["ラベル"], c["強調"], "Bold", 26)
        tw = spr.width / dk.R
        paste(cv, rrect(tw + 22, 44, 22, with_alpha(c["強調"], 34), c["強調"], 2), SAFE["left"] - 4 - 20 * (1 - p), 104 - 4, alpha=p)
        paste(cv, spr, SAFE["left"] + 11 - 20 * (1 - p), 126, alpha=p, anchor="lc")

    def question(self, cv, t):
        c, qb = self.c, self.qb
        pb = ease_out(prog(t, -0.3, 0.25))
        hh = qb.h * pb
        if hh > 1:
            paste(cv, rrect(6, max(1, hh - 8), 3, c["強調"]), SAFE["left"] - 4, self.q_y)
        for i, img in enumerate(self.q_imgs):
            p = ease_out(prog(t, -0.25 + 0.08 * i, 0.25 + 0.08 * i))
            paste(cv, img, Q_X - PAD - 40 * (1 - p), self.q_y + i * qb.line_h - PAD, alpha=p)

    def card_pos(self, i):
        return CARD_X - 24, self.card_y[i] - 24

    def draw_cards(self, cv, t):
        rv = ease_out(prog(t, REVEAL, REVEAL + 0.25))
        for i in range(3):
            p = ease_out(prog(t, self.card_t[i], self.card_t[i] + 0.4))
            if p <= 0:
                continue
            x, y = self.card_pos(i)
            x += 300 * (1 - p)
            correct = i == self.correct
            if t < REVEAL:
                paste(cv, self.cards[i], x, y, alpha=p)
                continue
            if correct:
                sc = 1 + 0.06 * math.sin(math.pi * prog(t, REVEAL, REVEAL + 0.35))
                cxm, cym = x + 24 + CARD_W / 2, y + 24 + self.card_h / 2
                paste(cv, self.cards[i], cxm, cym, alpha=1 - rv, scale=sc, anchor="cc")
                paste(cv, self.cards_done[i], cxm, cym, alpha=rv, scale=sc, anchor="cc")
            else:
                paste(cv, self.cards[i], x, y, alpha=1 - 0.55 * rv)
            m = prog(t, REVEAL + 0.1, REVEAL + 0.4)
            if m > 0:
                paste(cv, self.make_mark(correct), x + 24 + CARD_W - 34, y + 24 + self.card_h / 2,
                      alpha=min(1, m * 3), scale=0.86 * ease_back(m), anchor="cc")
        self.burst(cv, t)

    def burst(self, cv, t):
        """正解の瞬間の小さな紙吹雪（毎回同じ動き）"""
        p = prog(t, REVEAL + 0.05, REVEAL + 0.75)
        if p <= 0 or p >= 1:
            return
        c = self.c
        rng = np.random.default_rng(5)
        ox, oy = CARD_X + CARD_W - 34, self.card_y[self.correct] + self.card_h / 2
        d = ImageDraw.Draw(cv)
        R = dk.R
        for k in range(16):
            ang = rng.uniform(0, 2 * math.pi)
            sp = rng.uniform(70, 150)
            col = (c["強調"], c["文字"], c["まちがい"])[k % 3]
            e = ease_out(p)
            x = ox + math.cos(ang) * sp * e
            y = oy + math.sin(ang) * sp * e + 40 * p * p
            if x > SAFE["right"] + 40:
                x = SAFE["right"] + 40 - (x - SAFE["right"] - 40) * 0.3
            r = 5 * (1 - p) + 1
            d.ellipse([(x - r) * R, (y - r) * R, (x + r) * R, (y + r) * R], fill=with_alpha(col, 255 * (1 - p)))

    def countdown(self, cv, t):
        if not (COUNT0 - 0.2 <= t < COUNT1 + 0.25):
            return
        c = self.c
        a = ease_out(prog(t, COUNT0 - 0.2, COUNT0 + 0.05)) * (1 - prog(t, COUNT1, COUNT1 + 0.2))
        frac = prog(t, COUNT0, COUNT1)
        r = 62
        def fn(d, k, pad):
            box = [pad * k, pad * k, (pad + 2 * r) * k, (pad + 2 * r) * k]
            d.ellipse(box, outline=c["面"], width=int(11 * k))
            if frac > 0:
                d.arc(box, start=-90, end=-90 + 360 * frac, fill=c["強調"], width=int(11 * k))
        ring = aa_shape(2 * r, 2 * r, fn)
        paste(cv, ring, CX, self.cd_y, alpha=a, anchor="cc")
        k = min(2, int(max(0.0, t - COUNT0)))
        t_k = COUNT0 + k
        sc = 1 + 0.35 * (1 - ease_out(prog(t, t_k, t_k + 0.25)))
        paste(cv, text_sprite(str(3 - k), c["文字"], "Black", 76), CX, self.cd_y - 4, alpha=a, scale=sc, anchor="cc")

    def answer(self, cv, t):
        if t < REVEAL:
            return
        c = self.c
        p = prog(t, REVEAL + 0.05, REVEAL + 0.4)
        lab = text_sprite(self.words["正解"], c["文字"], "Black", 40)
        let = text_sprite(self.letter, c["強調"], "Black", 84)
        lw, ew = lab.width / dk.R, let.width / dk.R
        x0 = CX - (lw + ew - 4) / 2
        sc = 0.6 + 0.4 * ease_back(p)
        q = ease_out(prog(t, TRAP, TRAP + 0.4))
        a = min(1, p * 4) * (1 - q)
        paste(cv, lab, x0 + lw / 2, self.cd_y + 8, alpha=a, anchor="cc")
        paste(cv, let, x0 + lw - 4 + ew / 2, self.cd_y, alpha=a, scale=sc, anchor="cc")
        pad = self.trap_pad
        paste(cv, self.trap_img, CARD_X - pad + 4, self.trap_y - pad + 4 + 30 * (1 - q), alpha=q)

    def ending(self, cv, t):
        c, w = self.c, self.words
        e = ease_out(prog(t, SWITCH + 0.1, SWITCH + 0.45))
        paste(cv, text_sprite(self.theme.get("チャンネル名", ""), c["うすい文字"], "Bold", 28), CX, 420, alpha=e, anchor="cc")
        paste(cv, text_sprite(w["締め1"], c["強調"], "Black", 110), CX, 530, alpha=e,
              scale=0.7 + 0.3 * ease_back(prog(t, SWITCH + 0.1, SWITCH + 0.5)), anchor="cc")
        paste(cv, text_sprite(w["締め2"], c["文字"], "Black", 64), CX, 644 + 16 * (1 - e), alpha=e, anchor="cc")
        bw = 300 * ease_out(prog(t, SWITCH + 0.35, SWITCH + 0.7))
        if bw > 2:
            paste(cv, rrect(bw, 10, 5, c["強調"]), CX - bw / 2 - 4, 700 - 4)
        q = ease_out(prog(t, SWITCH + 0.5, SWITCH + 0.85))
        paste(cv, text_sprite(w["締め3"], c["文字"], "Bold", 32), CX, 760 + 12 * (1 - q), alpha=q, anchor="cc")
        if w.get("締め4"):
            q4 = ease_out(prog(t, SWITCH + 0.7, SWITCH + 1.05))
            paste(cv, text_sprite(w["締め4"], c["強調"], "Bold", 30), CX, 822 + 12 * (1 - q4), alpha=q4, anchor="cc")
        if self.voice_credit:
            paste(cv, text_sprite(self.voice_credit, c["うすい文字"], "Medium", 15), CX, 900, alpha=q, anchor="cc")

    def wipe(self, cv, t):
        if not (TR0 <= t <= TR1):
            return
        p = ease_in_out(prog(t, TR0, TR1))
        cx = -560 + 1840 * p
        k = 260
        pts = [(cx - 540, 0), (cx + 540 + k, 0), (cx + 540, 1280), (cx - 540 - k, 1280)]
        R = dk.R
        ImageDraw.Draw(cv).polygon([(px * R, py * R) for px, py in pts], fill=self.c["強調"])

    def sounds(self):
        ev = [("swoosh", 0.0, 0.16, 0.35)]
        for i, ct in enumerate(self.card_t):
            ev.append(("pop" + str(i), ct + 0.05, 0.36, 0))
        for k in range(3):
            ev.append(("tick", COUNT0 + k, 0.5, 0))
        ev += [("chime", REVEAL, 0.3, 0), ("sparkle", REVEAL + 0.08, 0.16, 0), ("pop1", TRAP + 0.05, 0.22, 0),
               ("swoosh", TR0, 0.24, 0.45), ("endchord", SWITCH + 0.1, 0.12, 0)]
        return ev
