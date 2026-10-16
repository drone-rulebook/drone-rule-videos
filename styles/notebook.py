# -*- coding: utf-8 -*-
"""型3「ノート」：罫線ノートに青いボールペンで書く。強調は黄色のマーカー、正解は赤ペンの丸、ひっかけはふせん。締めの前にページをめくる。"""
import numpy as np
from PIL import Image, ImageDraw
import drawkit as dk
from drawkit import paste, prog, ease_out, ease_in_out, with_alpha, cached, shadow
from .hand import Hand
from .base import TRAP, TR0, TR1, Q_X, CARD_X, CARD_W


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
        """強調の文字の下に、黄色のマーカーを引く（文字を書き終えてから）"""
        mk = self.c["マーカー"]
        lh = self.qb.line_h
        for k, (i, x0, x1) in enumerate(self.qb.spans):
            f = ease_out(prog(t, 0.9 + 0.1 * k, 1.15 + 0.1 * k))
            if f <= 0:
                continue
            w = (x1 - x0 + 8) * f
            y = self.q_y + i * lh + lh * 0.45
            paste(cv, dk.rrect(max(2, w), lh * 0.42, 4, with_alpha(mk, 170)), Q_X + x0 - 4 - 4, y - 4)

    def letter_path(self, i, seed):
        x, y, r = CARD_X + 30, self.row_cy[i], 24
        return dk.wobble_path([(x - r, y - r), (x + r, y - r), (x + r, y + r), (x - r, y + r), (x - r, y - r + 3)], seed, 0.7, 8)

    # ---------- ひっかけ＝ふせん ----------
    def make_trap(self):
        super().make_trap()
        c = self.c
        w, h = CARD_W - 8, self.trap_h
        pad = 26
        img = Image.new("RGBA", (int((w + pad * 2) * dk.R), int((h + pad * 2) * dk.R)), (0, 0, 0, 0))
        img.alpha_composite(shadow(w, h, 4, 10, 70), dest=(int((pad - 20) * dk.R), int((pad - 16) * dk.R)))
        note = Image.new("RGBA", (int(w * dk.R), int(h * dk.R)), c["ふせん"])
        dn = ImageDraw.Draw(note)
        dn.rectangle([0, 0, note.width, int(10 * dk.R)], fill=tuple(int(v * 0.93) for v in c["ふせん"][:3]) + (255,))
        img.alpha_composite(note, dest=(int(pad * dk.R), int(pad * dk.R)))
        self.note = img.rotate(-1.2, resample=Image.BICUBIC, expand=False)
        self.note_pad = pad

    def trap(self, cv, t):
        if t < TRAP:
            return
        p = ease_out(prog(t, TRAP - 0.1, TRAP + 0.2))
        x, y = CARD_X + 4, self.trap_y + 2
        paste(cv, self.note, x + (CARD_W - 8) / 2, y + self.trap_h / 2, alpha=min(1, p * 2), scale=1.1 - 0.1 * p, anchor="cc")
        if p >= 1:
            super().trap(cv, t)

    def transition(self, t):
        """新しいページが右からめくれて入ってくる"""
        p = ease_in_out(prog(t, TR0, TR1))
        cv = self.bg.copy()
        self.scene(cv, t)
        X = int(dk.W * (1 - p))
        if X < dk.W:
            if X > int(40 * dk.R):
                cv.alpha_composite(self.page_shadow(), dest=(X - int(40 * dk.R), 0))
            cv.alpha_composite(self.bg_end.crop((0, 0, dk.W - X, dk.H)), dest=(X, 0))
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
        ev = [e for e in super().sounds()]
        ev.append(("flip", TR0 + 0.05, 0.45, TR1 - TR0))
        ev.append(("stick", TRAP - 0.05, 0.4, 0))
        return ev
