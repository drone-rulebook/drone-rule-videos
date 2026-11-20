# -*- coding: utf-8 -*-
"""見た目の版7（実写の背景）の確かめ：枠で型が決まる・背景が動く・最後は1こま目に戻る・使わない素材は選ばない。"""
import os, sys, unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import render  # noqa: E402
import drawkit as dk  # noqa: E402
from styles import jissha  # noqa: E402

TWO = {"q1": "河原で登録機を飛行。昼・目視内20m、DID外・空港遠方、30m内人物件なし", "q2": "これ違反？", "a": "違反になる",
       "b": "違反にならない", "c": "", "answer": "B", "trap": "ポイント：条件がそろえば手続き不要",
       "title": "河原で飛ばす、これ違反？｜ドローン国家資格・二等学科"}


def small_theme():
    th = render.load_theme()
    th["画質"] = "720x1280"
    th["声"] = dict(th.get("声", {}), 使う=False)
    return th


def arr(img):
    return np.asarray(img.convert("RGB"), dtype=np.float32)


class V7Test(unittest.TestCase):
    def setUp(self):
        self.old_still = jissha.Jissha.still
        jissha.Jissha.still = False

    def tearDown(self):
        jissha.Jissha.still = self.old_still

    def test_枠で型が決まる(self):
        th = small_theme()
        self.assertEqual(render.choose_look("h030", th, {"枠": "朝"}), "実写")
        self.assertNotEqual(render.choose_look("h030", th, {"枠": "昼"}), "実写")
        self.assertNotEqual(render.choose_look("v030", th, {"枠": ""}), "実写")
        self.assertEqual(render.choose_look("h030", th, {"枠": "朝", "型": "黒板"}), "黒板")     # 台本の「型」が優先
        th["実写の背景"] = dict(th["実写の背景"], 使う=False)
        self.assertNotEqual(render.choose_look("h030", th, {"枠": "朝"}), "実写")

    def test_使わない素材は選ばない(self):
        th = small_theme()
        cs = jissha.clips(th)
        self.assertGreaterEqual(len(cs), 5)
        skip = {int(x) for x in th["実写の背景"]["使わない素材"]}
        self.assertFalse(skip & {c[0] for c in cs})
        for c in cs:
            self.assertTrue(os.path.exists(c[1]))
        ids = {jissha.pick_clip(f"h{n:03d}", th)[0] for n in range(len(cs))}
        self.assertEqual(len(ids), len(cs))                       # 台本IDの順で全部の素材を回す

    def test_背景が動き最後は1こま目に戻る(self):
        th = small_theme()
        look = render.make_look(TWO, th, "実写", "h031")
        T = look.T
        f0 = arr(look.frame(0.0))
        f1 = arr(look.frame(T.hook0 - 1.0 / render.FPS))
        self.assertGreater(np.abs(f1 - f0).mean(), 0.3, "掴みのあいだも背景の実写が動く")
        n = int(round(render.FPS * look.dur))
        last = arr(look.frame((n - 1) / render.FPS))
        self.assertLess(np.abs(last - f0).mean(), 2.5, "最後が1こま目と違う")
        mid = arr(look.frame(T.start + 0.5))                       # 前に戻って読んでも動く（読み直し）
        self.assertGreater(np.abs(mid - f0).mean(), 3.0)

    def test_文字の所は暗い膜で読みやすい(self):
        th = small_theme()
        look = render.make_look(TWO, th, "実写", "h032")
        a = np.asarray(look.overlay)[:, :, 3].astype(np.float32) / 255
        H = a.shape[0]
        self.assertGreater(a[int(H * 0.05)].mean(), 0.5)           # 見出しの所
        self.assertGreater(a[int(H * 0.25)].mean(), 0.35)          # 問題文の所
        self.assertGreater(a[int(H * 0.95)].mean(), 0.5)           # 下（題名と重なる所）
        self.assertEqual(dk.W, 720)


if __name__ == "__main__":
    unittest.main(verbosity=1)
