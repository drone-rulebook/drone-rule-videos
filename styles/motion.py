# -*- coding: utf-8 -*-
"""型1「モーション」：平らな図形がすっと動く、モーショングラフィックス風。"""
import math
import numpy as np
from PIL import Image, ImageDraw
import drawkit as dk
from drawkit import (CX, SAFE, PAD, paste, prog, ease_out, ease_back, ease_in_out, with_alpha, rrect, circle, shadow,
                     text_sprite, cached, aa_shape)
from .base import Look, Q_X, CARD_X, CARD_W, FOOT_Y, CREDIT_Y, LABEL_Y, ICON_X


class Motion(Look):
    name = "モーション"
    card_t = [0.3, 0.5, 0.7]

    def __init__(self, sc, theme, colors, vid=None):
        super().__init__(sc, theme, colors, vid)
        c = self.c
        self.bg = self.make_bg()
        two = self.n == 2
        self.qb = self.fit_q(lambda px: self.q_block(c["文字"], c["強調"], "Black", px, 32), 58 if not two else 54, 32,
                             128 if two else 108, 18 if two else 14)
        self.q_imgs = self.qb.line_images()
        self.cb = self.choice_blocks(c["カードの文字"], c.get("カードの強調", c["カードの文字"]), CARD_W - 100 - 70,
                                     52 if two else 46, self.card_h - 14)
        self.cards = [self.make_card(i, False) for i in range(self.n)]
        self.cards_done = [self.make_card(i, True) for i in range(self.n)]
        self.tb = self.trap_block(c["文字"], c["強調"], 516, min_px=24, room=self.trap_room(50), px=38)
        self.trap_img = self.make_trap()
        self.cta_img = self.make_cta() if self.T.cta else None
        self.hook_img = self.make_hook()

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

    def make_hook(self):
        """1こま目の絵（見出し・番号・問題文）。最後に戻る絵も同じものを使う（くり返し再生がつながるように）"""
        c = self.c
        img = Image.new("RGBA", (dk.W, dk.H), (0, 0, 0, 0))
        spr = text_sprite(self.label_text(), c["強調"], "Bold", 26)
        tw = spr.width / dk.R
        paste(img, rrect(tw + 22, 44, 22, with_alpha(c["強調"], 34), c["強調"], 2), SAFE["left"] - 4, LABEL_Y - 22 - 4)
        paste(img, spr, SAFE["left"] + 11, LABEL_Y, anchor="lc")
        no = text_sprite(self.no_text(), c["うすい文字"], "Bold", 24)
        paste(img, no, SAFE["left"] + tw + 22 + 14, LABEL_Y, anchor="lc")
        qb = self.qb
        paste(img, rrect(6, max(1, qb.h - 8), 3, c["強調"]), SAFE["left"] - 4, self.q_y)
        for i, li in enumerate(self.q_imgs):
            paste(img, li, Q_X - PAD, self.q_y + i * qb.line_h - PAD)
        return img

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

    def make_cta(self):
        """締めの帯（毎日18時に1問／チャンネル登録で届きます）"""
        c = self.c
        a, b = self.cta_lines()
        s1 = text_sprite(a, c["強調"], "Black", 46)
        s2 = text_sprite(b, c["文字"], "Bold", 28) if b else None
        w = CARD_W
        h = 128 if s2 else 90
        pad = 30
        img = Image.new("RGBA", (int((w + pad * 2) * dk.R), int((h + pad * 2) * dk.R)), (0, 0, 0, 0))
        img.alpha_composite(shadow(w, h, 20, 12, 90), dest=(int((pad - 24) * dk.R), int((pad - 24 + 6) * dk.R)))
        img.alpha_composite(rrect(w, h, 20, c["面"], c["強調"], 3), dest=(int((pad - 4) * dk.R), int((pad - 4) * dk.R)))
        cx = pad + w / 2
        img.alpha_composite(s1, dest=(int(cx * dk.R - s1.width / 2), int((pad + (40 if s2 else h / 2)) * dk.R - s1.height / 2)))
        if s2:
            img.alpha_composite(s2, dest=(int(cx * dk.R - s2.width / 2), int((pad + 94) * dk.R - s2.height / 2)))
        self.cta_pad, self.cta_h = pad, h
        return img

    # ---------- 1こま ----------
    def frame(self, t):
        T = self.T
        cv = self.bg.copy()
        if t < T.sw:
            self.hook(cv, t)
            self.draw_cards(cv, t)
            self.countdown(cv, t)
            self.answer(cv, t)
            self.cta(cv, t)
            self.footer(cv, t)
        else:
            self.hook(cv, t - T.dur)       # 1こま目と同じ絵へ戻る（ローターの回り方も、次の1こま目につながる）
        self.wipe(cv, t)
        return cv.convert("RGB")

    def hook(self, cv, t):
        cv.alpha_composite(self.hook_img)
        body, arcs = self.drone_icon(self.c["強調"], t)
        paste(cv, body, ICON_X, LABEL_Y, anchor="cc")
        paste(cv, arcs, ICON_X, LABEL_Y, anchor="cc")

    def card_pos(self, i):
        return CARD_X - 24, self.card_y[i] - 24

    def draw_cards(self, cv, t):
        T = self.T
        rv = ease_out(prog(t, T.reveal, T.reveal + 0.25))
        for i in range(self.n):
            p = ease_out(prog(t, self.card_t[i], self.card_t[i] + 0.35))
            if p <= 0:
                continue
            x, y = self.card_pos(i)
            x += 300 * (1 - p)
            correct = i == self.correct
            if t < T.reveal:
                paste(cv, self.cards[i], x, y, alpha=p)
                continue
            if correct:
                sc = 1 + 0.06 * math.sin(math.pi * prog(t, T.reveal, T.reveal + 0.35))
                cxm, cym = x + 24 + CARD_W / 2, y + 24 + self.card_h / 2
                paste(cv, self.cards[i], cxm, cym, alpha=1 - rv, scale=sc, anchor="cc")
                paste(cv, self.cards_done[i], cxm, cym, alpha=rv, scale=sc, anchor="cc")
            else:
                paste(cv, self.cards[i], x, y, alpha=1 - 0.55 * rv)
            m = prog(t, T.reveal + 0.1, T.reveal + 0.4)
            if m > 0:
                paste(cv, self.make_mark(correct), x + 24 + CARD_W - 34, y + 24 + self.card_h / 2,
                      alpha=min(1, m * 3), scale=0.86 * ease_back(m), anchor="cc")
        self.burst(cv, t)

    def burst(self, cv, t):
        """正解の瞬間の小さな紙吹雪（毎回同じ動き）"""
        p = prog(t, self.T.reveal + 0.05, self.T.reveal + 0.75)
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
        T = self.T
        if not (T.count0 - 0.2 <= t < T.count1 + 0.1):
            return
        c = self.c
        a = ease_out(prog(t, T.count0 - 0.2, T.count0 + 0.05)) * (1 - prog(t, T.count1 - 0.05, T.count1 + 0.08))
        frac = prog(t, T.count0, T.count1)
        r = self.cd_r
        def fn(d, k, pad):
            box = [pad * k, pad * k, (pad + 2 * r) * k, (pad + 2 * r) * k]
            d.ellipse(box, outline=c["面"], width=int(11 * k))
            if frac > 0:
                d.arc(box, start=-90, end=-90 + 360 * frac, fill=c["強調"], width=int(11 * k))
        ring = aa_shape(2 * r, 2 * r, fn)
        paste(cv, ring, CX, self.cd_y, alpha=a, anchor="cc")
        k = min(2, int(max(0.0, t - T.count0)))
        t_k = T.count0 + k
        sc = 1 + 0.35 * (1 - ease_out(prog(t, t_k, t_k + 0.25)))
        paste(cv, text_sprite(str(3 - k), c["文字"], "Black", 72), CX, self.cd_y - 4, alpha=a, scale=sc, anchor="cc")
        pr = self.words.get("コメント", "")
        if pr:
            q = ease_out(prog(t, T.count0 - 0.1, T.count0 + 0.25))
            paste(cv, text_sprite(pr, c["文字"], "Bold", 28), CX, self.prompt_y + 8 * (1 - q), alpha=a * q, anchor="cc")

    def answer(self, cv, t):
        T = self.T
        if t < T.reveal:
            return
        c = self.c
        p = prog(t, T.reveal + 0.1, T.reveal + 0.45)
        lab = text_sprite(self.words["正解"], c["文字"], "Black", 40)
        let = text_sprite(self.letter, c["強調"], "Black", 84)
        lw, ew = lab.width / dk.R, let.width / dk.R
        x0 = CX - (lw + ew - 4) / 2
        sc = 0.6 + 0.4 * ease_back(p)
        q = ease_out(prog(t, T.trap, T.trap + 0.4))
        a = min(1, p * 4) * (1 - q)
        paste(cv, lab, x0 + lw / 2, self.cd_y + 8, alpha=a, anchor="cc")
        paste(cv, let, x0 + lw - 4 + ew / 2, self.cd_y, alpha=a, scale=sc, anchor="cc")
        out = ease_out(prog(t, T.cta0, T.cta0 + 0.3)) if T.cta else 0.0     # 締めの帯が出たら、ひっかけは下げる
        pad = self.trap_pad
        paste(cv, self.trap_img, CARD_X - pad + 4, self.trap_y - pad + 4 + 30 * (1 - q) - 20 * out, alpha=q * (1 - out))

    def cta(self, cv, t):
        T = self.T
        if not T.cta or t < T.cta0:
            return
        p = ease_out(prog(t, T.cta0 + 0.05, T.cta0 + 0.4))
        sc = 0.9 + 0.1 * ease_back(prog(t, T.cta0 + 0.05, T.cta0 + 0.45))
        pad = self.cta_pad
        paste(cv, self.cta_img, CX, self.trap_y - pad + 4 + pad + self.cta_h / 2, alpha=p, scale=sc, anchor="cc")

    def footer(self, cv, t):
        """カウントダウンからひっかけまでの小さな文字（毎日18時に1問・声のクレジット）"""
        T = self.T
        c = self.c
        end = T.cta0 if T.cta else T.tr0
        a = ease_out(prog(t, T.count0 - 0.2, T.count0 + 0.1)) * (1 - prog(t, end, end + 0.25))
        line = self.words.get("毎日", "")
        if line and a > 0:
            paste(cv, text_sprite(line, c["うすい文字"], "Bold", 22), CX, FOOT_Y, alpha=a, anchor="cc")
        if self.voice_credit:
            ac = ease_out(prog(t, T.trap, T.trap + 0.3)) * (1 - prog(t, T.tr0, T.tr0 + 0.25))
            if ac > 0:
                paste(cv, text_sprite(self.voice_credit, c["うすい文字"], "Medium", 15), CX, CREDIT_Y, alpha=ac * 0.9, anchor="cc")

    def wipe(self, cv, t):
        T = self.T
        if not (T.tr0 <= t <= T.tr1):
            return
        p = ease_in_out(prog(t, T.tr0, T.tr1))
        cx = -560 + 1840 * p
        k = 260
        pts = [(cx - 540, 0), (cx + 540 + k, 0), (cx + 540, 1280), (cx - 540 - k, 1280)]
        R = dk.R
        ImageDraw.Draw(cv).polygon([(px * R, py * R) for px, py in pts], fill=self.c["強調"])

    def sounds(self):
        T = self.T
        ev = [("swoosh", 0.0, 0.12, 0.3)]
        for i, ct in enumerate(self.card_t):
            ev.append(("pop" + str(i), ct + 0.05, 0.36, 0))
        for tk in T.ticks:
            ev.append(("tick", tk, 0.5, 0))
        ev += [("chime", T.reveal, 0.3, 0), ("sparkle", T.reveal + 0.08, 0.16, 0), ("pop1", T.trap + 0.05, 0.22, 0),
               ("swoosh", T.tr0, 0.22, 0.45)]
        if T.cta:
            ev.append(("pop2", T.cta0 + 0.08, 0.3, 0))
        return ev
