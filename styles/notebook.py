# -*- coding: utf-8 -*-
"""型3「ノート」：罫線ノートに青いボールペンで書く。強調は黄色のマーカー、正解は赤ペンの丸、ひっかけはふせん。
最後はページをめくって、1こま目と同じページに戻る。
版6：1こま目は掴みのページ（青いペンの場面の1行・マーカーを引いた赤い札・呼びかけ）。1.2秒でページをめくって問題のページへ。"""
import numpy as np
from PIL import Image, ImageDraw
import drawkit as dk
from drawkit import CX, paste, prog, ease_out, ease_in_out, with_alpha, cached, shadow
from .hand import Hand
from .base import Q_X, CARD_X, CARD_W, HOOK_TR


class Notebook(Hand):
    name = "ノート"
    write_kind = "pen"
    bgm_mix = {"KICK": 0.7, "CLAP": 0.6, "ARP": 1.25, "EP": 0.9}
    rough = 0.0
    line_w = 3.6

    def colors(self):
        c = self.c
        self.ink, self.em, self.ok, self.ng, self.sub = c["インク"], c["赤ペン"], c["赤ペン"], c["インク"], c["赤ペン"]

    def make_bg(self):
        c = self.c
        R = dk.R
        img = Image.new("RGB", (dk.W, dk.H), c["紙"][:3])
        arr = np.asarray(img, dtype=np.float32)
        arr += dk.grain(dk.W, dk.H, 31, 50 * R)[:, :, None] * 3
        arr += dk.grain(dk.W, dk.H, 32, 1.0)[:, :, None] * 3
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        for y in range(70, 1280, 54):
            d.line([(0, y * R), (dk.W, y * R)], fill=c["罫線"][:3], width=max(1, int(1.4 * R)))
        d.line([(22 * R, 0), (22 * R, dk.H)], fill=c["余白線"][:3], width=max(1, int(1.6 * R)))
        # とじ側の影
        sh = np.zeros((dk.H, dk.W), np.float32)
        xs = np.arange(dk.W, dtype=np.float32) / R
        sh[:] = np.clip(1 - xs / 26, 0, 1)[None, :] * 26
        arr = np.asarray(img, dtype=np.float32) - sh[:, :, None]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        return dk.vignette(img, 0.12)

    def emphasis(self, cv, t):
        pass

    def emphasis_under(self, cv, t):
        """強調の文字の下に、黄色のマーカーを引く（問題のページになったすぐあと）"""
        mk = self.c["マーカー"]
        lh = self.qb.line_h
        s = self.T.start
        for k, (i, x0, x1) in enumerate(self.qb.spans):
            f = ease_out(prog(t, s + 0.15 + 0.1 * k, s + 0.4 + 0.1 * k))
            if f <= 0:
                continue
            w = (x1 - x0 + 8) * f
            y = self.q_y + i * lh + lh * 0.45
            paste(cv, dk.rrect(max(2, w), lh * 0.42, 4, with_alpha(mk, 170)), Q_X + x0 - 4 - 4, y - 4)

    def letter_path(self, i, seed):
        x, y, r = CARD_X + 30, self.row_cy[i], 24
        return dk.wobble_path([(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r), (x - r, y - r + 3)], seed, 0.7, 8)

    # ---------- ひっかけ・締めの帯＝ふせん ----------
    def make_note(self, w, h):
        c = self.c
        pad = 26
        img = Image.new("RGBA", (int((w + pad * 2) * dk.R), int((h + pad * 2) * dk.R)), (0, 0, 0, 0))
        img.alpha_composite(shadow(w, h, 4, 10, 70), dest=(int((pad - 20) * dk.R), int((pad - 16) * dk.R)))
        note = Image.new("RGBA", (int(w * dk.R), int(h * dk.R)), c["ふせん"])
        dn = ImageDraw.Draw(note)
        dn.rectangle([0, 0, note.width, int(10 * dk.R)], fill=tuple(int(v * 0.93) for v in c["ふせん"][:3]) + (255,))
        img.alpha_composite(note, dest=(int(pad * dk.R), int(pad * dk.R)))
        return img.rotate(-1.2, resample=Image.BICUBIC, expand=False)

    def make_trap(self):
        super().make_trap()
        self.note = self.make_note(CARD_W - 8, self.trap_h)

    def make_cta(self):
        super().make_cta()
        self.cta_note = self.make_note(CARD_W - 8, self.cta_h + 16) if self.T.cta else None

    def trap(self, cv, t):
        T = self.T
        if t < T.trap:
            return
        p = ease_out(prog(t, T.trap - 0.1, T.trap + 0.2))
        x, y = CARD_X + 4, self.trap_y + 2
        paste(cv, self.note, x + (CARD_W - 8) / 2, y + self.trap_h / 2, alpha=min(1, p * 2), scale=1.1 - 0.1 * p, anchor="cc")
        if p >= 1:
            super().trap(cv, t)

    def cta(self, cv, t):
        """締めの帯は、新しいふせんに書く"""
        T = self.T
        p = ease_out(prog(t, T.cta0 - 0.05, T.cta0 + 0.2))
        x, y = CARD_X + 4, self.trap_y + 2
        h = self.cta_h + 16
        paste(cv, self.cta_note, x + (CARD_W - 8) / 2, y + h / 2, alpha=min(1, p * 2), scale=1.1 - 0.1 * p, anchor="cc")
        if p >= 1:
            super().cta(cv, t)

    # ---------- 版6の掴み：札の下に黄色のマーカー ----------
    def hook_colors(self):
        # 札の文字＝赤ペン・札の強調＝インク・（囲みの線は使わずマーカー）・呼びかけ＝インク・A/B/C＝赤ペン
        return self.em, self.ink, self.em, self.ink, self.em

    def tag_mark(self, cv):
        if self.hk_tb is None:
            return
        _, h = self.tag_box()
        mk = self.c["マーカー"]
        tb = self.hk_tb
        y0 = self.hk_tag_y + (h - tb.h) / 2
        for i, lw in enumerate(tb.widths):         # 札の行ごとに、文字の下半分へ太いマーカー
            y = y0 + i * tb.line_h + tb.line_h * 0.42
            paste(cv, dk.rrect(lw + 24, tb.line_h * 0.5, 6, with_alpha(mk, 200)), CX - lw / 2 - 12 - 4, y - 4)

    # ---------- ページめくり（最後と、版6の掴み → 問題のページ） ----------
    def swap(self, t, t0, t1, old, new):
        """新しいページ（new）が右からめくれて入ってきて、old のページにかぶさる"""
        p = ease_in_out(prog(t, t0, t1))
        cv = old
        X = int(dk.W * (1 - p))
        if X < dk.W:
            if X > int(40 * dk.R):
                cv.alpha_composite(self.page_shadow(), dest=(X - int(40 * dk.R), 0))
            cv.alpha_composite(new.crop((0, 0, dk.W - X, dk.H)), dest=(X, 0))
        return cv

    def page_shadow(self):
        def make():
            w = int(40 * dk.R)
            a = (np.linspace(0, 1, w) ** 2 * 90).astype(np.uint8)
            arr = np.zeros((dk.H, w, 4), np.uint8)
            arr[:, :, 3] = a[None, :]
            return Image.fromarray(arr, "RGBA")
        return cached(("pgsh",), make)

    def sounds(self):
        T = self.T
        ev = [e for e in super().sounds()]
        ev.append(("flip", T.tr0 + 0.05, 0.45, T.tr1 - T.tr0))
        if T.hook:
            ev.append(("flip", T.hook0, 0.4, HOOK_TR + 0.05))      # 掴み → 問題のページ
        ev.append(("stick", T.trap - 0.05, 0.4, 0))
        if T.cta:
            ev.append(("stick", T.cta0 - 0.05, 0.4, 0))
        return ev
