# -*- coding: utf-8 -*-
"""見た目の版5（掴み・ループ）の決まりを確かめる。動画は書き出さない（数秒で終わる）。

  python tests/test_render_v5.py
"""
import os, sys, unittest
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import render  # noqa: E402
from styles import LOOKS, base as B  # noqa: E402

TWO = {"q1": "DID内の*自宅の庭*で200gの機体を昼・目視内で飛行（許可なし）", "q2": "これ違反？", "a": "違反になる",
       "b": "違反にならない", "c": "", "answer": "A", "trap": "ポイント：規制は土地でなく*空域*"}


def small_theme():
    th = render.load_theme()
    th["画質"] = "720x1280"          # 確かめは小さい画面で
    th["声"] = dict(th.get("声", {}), 使う=False)
    return th


class V5Test(unittest.TestCase):
    def test_時刻表(self):
        t = B.Timeline()
        self.assertAlmostEqual(t.dur, B.TR1 + B.HOLD)
        self.assertLess(t.count0, t.reveal)
        self.assertLess(t.trap, t.tr0)
        c = B.Timeline(cta=True)
        self.assertAlmostEqual(c.dur - t.dur, B.CTA_LEN)
        self.assertLess(c.times()["trap"][1], c.cta0)
        e = B.Timeline(extra=1.0)
        self.assertAlmostEqual(e.count0 - t.count0, 1.0)
        self.assertAlmostEqual(e.dur - t.dur, 1.0)

    def test_締めの声は偶数と奇数で分かれる(self):
        th = small_theme()
        th["締めの声を使う"] = "偶数"
        self.assertTrue(B.cta_on("v012", th))
        self.assertFalse(B.cta_on("v013", th))
        th["締めの声を使う"] = "なし"
        self.assertFalse(B.cta_on("v012", th))
        th["締めの声を使う"] = "全部"
        self.assertTrue(B.cta_on("v013", th))

    def test_2択の台本を受け付ける(self):
        r = {"問題1行目": TWO["q1"], "問題2行目": TWO["q2"], "選択肢A": "違反になる", "選択肢B": "違反にならない", "選択肢C": "",
             "正解": "A", "ひっかけ": TWO["trap"]}
        sc, why = render.script_of(r)
        self.assertIsNotNone(sc, why)
        r["正解"] = "C"                       # 2択で C は使えない
        self.assertIsNone(render.script_of(r)[0])
        r["正解"] = "B"; r["選択肢B"] = ""     # B が空はだめ
        self.assertIsNone(render.script_of(r)[0])

    def test_1こま目に問題が出ていて最後は1こま目と同じ(self):
        th = small_theme()
        for style in LOOKS:
            for sc, vid in ((render.SAMPLE, "v013"), (render.SAMPLE, "v012"), (TWO, "w901")):
                look = render.make_look(sc, th, style, vid)
                f0 = np.asarray(look.frame(0.0), dtype=np.float32)
                bg = np.asarray(look.bg.convert("RGB"), dtype=np.float32)
                y0, y1 = int(look.q_y * render.dk.R), int((look.q_y + look.qb.h) * render.dk.R)
                self.assertGreater(np.abs(f0[y0:y1] - bg[y0:y1]).mean(), 3.0, (style, vid, "1こま目に問題文が無い"))
                last = np.asarray(look.frame(look.dur - 1.0 / render.FPS), dtype=np.float32)
                self.assertLess(np.abs(f0 - last).mean(), 2.5, (style, vid, "最後が1こま目と違う"))

    def test_大事な文字は安全な範囲の中(self):
        th = small_theme()
        for style in LOOKS:
            for sc, vid in ((render.SAMPLE, "v013"), (TWO, "w902")):
                look = render.make_look(sc, th, style, vid)
                self.assertLessEqual(look.zone_top + B.ZONE, B.CONTENT_BOTTOM + 1, (style, vid))
                self.assertLessEqual(B.ICON_X + B.ICON_R, render.dk.SAFE["right"])
                self.assertLess(look.prompt_y, B.FOOT_Y - 10)


if __name__ == "__main__":
    unittest.main(verbosity=1)
