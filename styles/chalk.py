# -*- coding: utf-8 -*-
"""型2「黒板」：深緑の黒板に、チョークで書いていく。締めの前に黒板消しが横切る。"""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import drawkit as dk
from drawkit import paste, prog, ease_in_out, aa_shape, cached
from .hand import Hand
from .base import TR0, TR1


class Chalk(Hand):
    name = "黒板"
    write_kind = "chalk"
    bgm_mix = {"KICK": 0.6, "CLAP": 0.5, "HAT": 0.7, "EP": 1.15}
    rough = 0.5
    line_w = 4.5

    def colors(self):
        c = self.c
        self.ink, self.em, self.ok, self.ng, self.sub = c["チョーク"], c["黄色"], c["黄色"], c["ピンク"], c["水色"]

    def make_bg(self):
        c = self.c
        R = dk.R
        img = Image.new("RGB", (dk.W, dk.H), c["黒板"][:3])
        arr = np.asarray(img, dtype=np.float32)
        arr += dk.grain(dk.W, dk.H, 21, 60 * R)[:, :, None] * 7      # ぼんやりしたむら
        arr += dk.grain(dk.W, dk.H, 22, 1.0)[:, :, None] * 5          # 細かいざらざら
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        # 前に消したチョークのあと（うすい横すじ）
        smear = Image.new("L", (dk.W, dk.H), 0)
        d = ImageDraw.Draw(smear)
        rng = np.random.default_rng(23)
        for _ in range(9):
            y = rng.uniform(120, 1150); x = rng.uniform(-100, 500); w = rng.uniform(200, 520); h = rng.uniform(30, 80)
            d.rounded_rectangle([x * R, y * R, (x + w) * R, (y + h) * R], radius=h * R / 2, fill=int(rng.uniform(10, 22)))
        smear = smear.filter(ImageFilter.GaussianBlur(18 * R))
        img = Image.composite(Image.new("RGB", img.size, (200, 215, 205)), img, smear)
        # 木の枠
        d = ImageDraw.Draw(img)
        fw = c["枠"][:3]
        dark = tuple(int(v * 0.6) for v in fw)
        for box in ([0, 0, dk.W, 14 * R], [0, dk.H - 14 * R, dk.W, dk.H], [0, 0, 14 * R, dk.H], [dk.W - 14 * R, 0, dk.W, dk.H]):
            d.rectangle(box, fill=fw)
        d.rectangle([14 * R, 14 * R, dk.W - 14 * R, 18 * R], fill=dark)
        d.rectangle([14 * R, 14 * R, 18 * R, dk.H - 14 * R], fill=dark)
        img = dk.vignette(img, 0.3)
        return img

    def make_bg_end(self):
        """黒板消しで消したあと（消しあとが少し残る）"""
        R = dk.R
        img = self.bg.convert("RGB")
        smear = Image.new("L", (dk.W, dk.H), 0)
        d = ImageDraw.Draw(smear)
        for k in range(7):
            y0 = 100 + k * 160
            pts = [(x * R, (y0 + 40 * math.sin(x / 90 + k)) * R) for x in range(-20, 760, 20)]
            d.line(pts, fill=16, width=int(120 * R))
        smear = smear.filter(ImageFilter.GaussianBlur(20 * R))
        img = Image.composite(Image.new("RGB", img.size, (205, 220, 210)), img, smear)
        return img.convert("RGBA")

    def eraser(self):
        def make():
            def fn(d, k, pad):
                d.rounded_rectangle([pad * k, pad * k, (pad + 96) * k, (pad + 230) * k], radius=10 * k, fill=(150, 104, 62, 255))
                d.rounded_rectangle([(pad + 60) * k, (pad + 4) * k, (pad + 92) * k, (pad + 226) * k], radius=8 * k, fill=(64, 66, 72, 255))
                for j in range(6):
                    y = (pad + 20 + j * 36) * k
                    d.line([((pad + 64) * k, y), ((pad + 88) * k, y)], fill=(84, 86, 92, 255), width=int(2 * k))
            return aa_shape(96, 230, fn)
        return cached(("eraser",), make)

    def transition(self, t):
        """黒板消しが左から右へ横切って、消していく"""
        p = ease_in_out(prog(t, TR0, TR1))
        ex = -120 + 960 * p
        cv = self.bg.copy()
        self.scene(cv, t)
        X = int(ex * dk.R)
        if X > 0:
            clean = self.bg_end.crop((0, 0, min(dk.W, X), dk.H))
            cv.alpha_composite(clean, dest=(0, 0))
        bob = 380 * math.sin((t - TR0) * 2 * math.pi * 2.2)
        paste(cv, self.eraser(), ex - 70, 640 + bob, anchor="cc", angle=8)
        return cv

    def sounds(self):
        ev = super().sounds()
        ev.append(("eraser", TR0, 0.4, TR1 - TR0))
        return ev
