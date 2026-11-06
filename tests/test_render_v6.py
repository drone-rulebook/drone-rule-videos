# -*- coding: utf-8 -*-
"""見た目の版6（1こま目＝掴みの画面）の決まりを確かめる。動画は書き出さない（声は作り物の長さで試す。数十秒で終わる）。

  python tests/test_render_v6.py
"""
import os, sys, unittest
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import render  # noqa: E402
import voice  # noqa: E402
import audio  # noqa: E402
import drawkit as dk  # noqa: E402
from styles import LOOKS, base as B  # noqa: E402

TITLE = "知人のドローンを借りて飛ばす、これ違反？｜ドローン国家資格・二等学科"
TWO = {"q1": "知人の登録機（記号表示・リモートID付）を借りて飛行。DID外・空港等遠方、昼・目視内20m、30m内人物件・催し等なし",
       "q2": "これ違反？", "a": "違反になる", "b": "違反にならない", "c": "", "answer": "B",
       "trap": "ポイント：登録は人でなく機体ごと", "title": TITLE}
THREE = {"q1": "河原でドローンを飛ばす", "q2": "*30m*離す「物件」でないのは？", "a": "電線や鉄塔", "b": "樹木や雑草",
         "c": "走行中の自動車", "answer": "B", "trap": "ポイント：*自然物*は物件ではない",
         "title": "河原で飛ばすとき、30m離す「物件」でないのは？｜ドローン国家資格・二等学科"}
CASES = ((TWO, "h927"), (TWO, "h928"), (THREE, "v927"), (THREE, "v928"))     # 偶数の ID は締めの声つき


def small_theme(version=6):
    th = render.load_theme()
    th["画質"] = "720x1280"          # 確かめは小さい画面で
    th["声"] = dict(th.get("声", {}), 使う=False)
    th["見た目の版"] = version
    return th


def arr(img):
    return np.asarray(img, dtype=np.float32)


class V6Test(unittest.TestCase):
    # ---------- 時刻表 ----------
    def test_時刻表は掴みの分だけずれる(self):
        self.assertAlmostEqual(B.HOOK_SHIFT, B.HOOK + B.HOOK_TR)
        self.assertLessEqual(B.HOOK_SHIFT, 1.5 + 1e-9)                    # 長さの増えは1.5秒まで
        for extra in (0.0, 1.0, 2.6):
            for cta in (False, True):
                t5, t6 = B.Timeline(extra, cta), B.Timeline(extra, cta, hook=True)
                s = B.HOOK_SHIFT
                self.assertEqual((t5.start, t5.hook0), (0.0, 0.0))
                self.assertAlmostEqual(t6.hook0, B.HOOK)
                self.assertAlmostEqual(t6.start, s)
                for k in ("count0", "count1", "reveal", "trap", "tr0", "tr1", "sw"):
                    self.assertAlmostEqual(getattr(t6, k) - getattr(t5, k), s, msg=k)
                for a, b in zip(t6.ticks, t5.ticks):
                    self.assertAlmostEqual(a - b, s)
                self.assertAlmostEqual(t6.ticks[0], t6.count0)
                self.assertLessEqual(t6.dur - t5.dur, 1.5 + 1e-9)
                self.assertLess(t6.hook0, t6.start)
                self.assertLess(t6.start, t6.count0)
                q6, q5 = t6.times(), t5.times()
                self.assertAlmostEqual(q6["q"][0], 0.15)                    # 問題の声は掴みのあいだに読み始める
                self.assertAlmostEqual(q6["q"][1], t6.count0 - 0.1)
                for k in ("ans", "trap"):
                    self.assertAlmostEqual(q6[k][0] - q5[k][0], s)
                    self.assertAlmostEqual(q6[k][1] - q5[k][1], s)
                if cta:
                    self.assertAlmostEqual(q6["cta"][0] - q5["cta"][0], s)
                    self.assertLess(q6["trap"][1], t6.cta0)
        t = B.Timeline(0.0, False, hook=True)
        t.set(1.0, True)                                                    # ずらし直しても掴みはそのまま
        self.assertAlmostEqual(t.start, B.HOOK_SHIFT)
        self.assertAlmostEqual(t.count0, B.COUNT0 + B.HOOK_SHIFT + 1.0)

    def test_版6は版5より長くても1秒半まで(self):
        for style in LOOKS:
            for sc, vid in CASES:
                l5 = render.make_look(sc, small_theme(5), style, vid)
                l6 = render.make_look(sc, small_theme(6), style, vid)
                self.assertFalse(l5.v6)
                self.assertTrue(l6.v6)
                self.assertGreater(l6.dur, l5.dur)
                self.assertLessEqual(l6.dur - l5.dur, 1.5 + 1e-9, (style, vid))
                self.assertEqual(l6.card_t, [x + B.HOOK_SHIFT for x in l5.card_t])

    # ---------- 掴みの文字 ----------
    def test_掴みの文字_2択はタイトルから(self):
        w = render.load_theme()["文言"]
        self.assertEqual(B.hook_texts(TWO, w), ("知人のドローンを借りて飛ばす", "これ違反？", "AかBで答えてね"))
        self.assertEqual(B.title_scene("自宅の庭で飛ばす、これ違反？｜ドローン国家資格・二等学科"), "自宅の庭で飛ばす")
        self.assertEqual(B.title_scene("自宅の庭で飛ばす これ違反?|説明"), "自宅の庭で飛ばす")
        self.assertEqual(B.title_scene("庭で飛ばす｜ドローン国家資格・二等学科"), "庭で飛ばす")     # 「これ違反？」が無いタイトル
        self.assertEqual(B.title_scene("これ違反？庭で飛ばす"), "庭で飛ばす")
        self.assertEqual(B.title_scene(""), "")
        # タイトルが空なら、問題1行目の最初の文
        self.assertEqual(B.hook_texts(dict(TWO, title=""), w)[0], "知人の登録機（記号表示・リモートID付）を借りて飛行")
        self.assertEqual(B.hook_texts(dict(TWO, title="、これ違反？｜ドローン国家資格・二等学科"), w)[0],
                         "知人の登録機（記号表示・リモートID付）を借りて飛行")
        self.assertEqual(B.hook_texts({k: v for k, v in TWO.items() if k != "title"}, w)[1], "これ違反？")

    def test_掴みの文字_3択は問題1行目と2行目(self):
        w = render.load_theme()["文言"]
        self.assertEqual(B.hook_texts(THREE, w), ("河原でドローンを飛ばす", "*30m*離す「物件」でないのは？", "A・B・Cどれ？コメントで"))
        long_q = {"q1": "「夜間飛行」は*日没から日の出まで*の飛行。この日没・日の出の時刻は、何を基準にする？", "q2": "", "c": "x"}
        self.assertEqual(B.hook_texts(long_q, w)[:2], ("「夜間飛行」は*日没から日の出まで*の飛行", "この日没・日の出の時刻は、何を基準にする？"))
        one = {"q1": "目視外飛行の「目視」に*含まれる*のはどれ？", "q2": "", "c": "x"}
        self.assertEqual(B.hook_texts(one, w)[:2], ("目視外飛行の「目視」に*含まれる*のはどれ？", ""))

    def test_掴みの文言はテーマにあってフォントで出せる(self):
        th = render.load_theme()
        for k in ("掴みの問い（2択）", "掴みの呼びかけ（2択）", "掴みの呼びかけ（3択）"):
            self.assertIn(k, th["文言"])
            self.assertEqual(render.safe_text(th["文言"][k])[1], [], k)
        self.assertEqual(th["文言"]["掴みの呼びかけ（2択）"], "AかBで答えてね")
        self.assertEqual(th["文言"]["掴みの呼びかけ（3択）"], "A・B・Cどれ？コメントで")
        self.assertGreaterEqual(B.version_of(th), B.HOOK_VERSION)

    def test_台本にタイトルが入る(self):
        r = {"問題1行目": TWO["q1"], "問題2行目": "これ違反？", "選択肢A": "違反になる", "選択肢B": "違反にならない", "選択肢C": "",
             "正解": "B", "ひっかけ": TWO["trap"], "タイトル": TITLE}
        sc, why = render.script_of(r)
        self.assertIsNotNone(sc, why)
        self.assertEqual(sc["title"], TITLE)
        sc, _ = render.script_of(dict(r, タイトル="𪚲で飛ばす、これ違反？｜ドローン国家資格・二等学科"))   # フォントに無い字 → タイトルは使わない
        self.assertEqual(sc["title"], "")
        sc, _ = render.script_of({k: v for k, v in r.items() if k != "タイトル"})
        self.assertEqual(sc["title"], "")

    def test_台本の印に2択のタイトルの場面が入る(self):
        s = render.script_sum
        self.assertNotEqual(s(TWO), s(dict(TWO, title="友人のドローンを借りて飛ばす、これ違反？｜ドローン国家資格・二等学科")))
        self.assertEqual(s(TWO), s(dict(TWO, title="知人のドローンを借りて飛ばす、これ違反？｜別の説明")))   # 「｜」の後ろだけなら同じ
        self.assertEqual(s(THREE), s(dict(THREE, title="別のタイトル")))                              # 3択のタイトルは画面に出ない

    def test_場面は言葉の切れ目で大きく分ける(self):
        render.load_theme()                                                  # 改行しない言葉を読む
        dk.setup(720, 1280)

        def lines(text, n=3):
            tb = dk.TextBlock([dk.segments(text, (0, 0, 0, 255), (255, 0, 0, 255))], "Black", B.HOOK_W, n, B.SCENE_PX, 46,
                              align="center", keep_emphasis=True, balanced=True)
            return ["".join(c[0] for c in l) for l in tb.lines], tb.px
        self.assertEqual(lines("知人のドローンを借りて飛ばす")[0], ["知人の", "ドローンを", "借りて飛ばす"])
        self.assertEqual(lines("河原でドローンを飛ばす")[0], ["河原で", "ドローンを", "飛ばす"])
        self.assertEqual(lines("引っ越し後、登録を変えずに飛ばす")[0][0], "引っ越し後、")
        ls, _ = lines("「夜間飛行」は*日没から日の出まで*の飛行")
        self.assertTrue(ls[0].endswith("は"), ls)                            # 行の頭に助詞を置かない
        self.assertTrue(any("日の出" in l for l in ls), ls)                  # 改行しない言葉
        self.assertGreaterEqual(lines("知人のドローンを借りて飛ばす")[1], 1.5 * 58)   # 問題文（58）の1.5倍以上

    # ---------- 絵 ----------
    def test_1こま目は掴みで最後は1こま目と同じ(self):
        th = small_theme()
        for style in LOOKS:
            for sc, vid in CASES:
                look = render.make_look(sc, th, style, vid)
                T, R = look.T, dk.R
                bg = arr(look.bg.convert("RGB"))
                f0 = arr(look.frame(0.0))
                y0, y1 = int(look.hk_scene_y * R), int((look.hk_scene_y + look.hk_sb.h) * R)
                self.assertGreater(np.abs(f0[y0:y1] - bg[y0:y1]).mean(), 3.0, (style, vid, "1こま目に場面の1行が無い"))
                # 掴みのあいだは止まっている（ドローンのローターだけ回る）
                self.assertLess(np.abs(arr(look.frame(T.hook0 - 1.0 / render.FPS)) - f0).mean(), 0.5, (style, vid))
                # 掴みのあとは問題の画面（問題文がある・掴みとは違う絵）
                fq = arr(look.frame(T.start + 0.05))
                qy0, qy1 = int(look.q_y * R), int((look.q_y + look.qb.h) * R)
                self.assertGreater(np.abs(fq[qy0:qy1] - bg[qy0:qy1]).mean(), 3.0, (style, vid, "問題の画面に問題文が無い"))
                self.assertGreater(np.abs(fq - f0).mean(), 3.0, (style, vid, "掴みから問題の画面に変わっていない"))
                # 最後のこまは1こま目と同じ（くり返し再生がつながる）
                n = int(round(render.FPS * look.dur))
                last = arr(look.frame((n - 1) / render.FPS))
                self.assertLess(np.abs(f0 - last).mean(), 0.5, (style, vid, "最後が1こま目と違う"))
                # 最後の場面転換は掴みの画面へ戻る（転換が終わったあとは1こま目と同じ）
                self.assertLess(np.abs(arr(look.frame(T.tr1 + 1.0 / render.FPS)) - f0).mean(), 0.5, (style, vid))

    def test_掴みは安全な範囲の中(self):
        th = small_theme()
        S = dk.SAFE
        for style in LOOKS:
            for sc, vid in CASES:
                look = render.make_look(sc, th, style, vid)
                self.assertGreaterEqual(look.hk_scene_y, B.HOOK_TOP, (style, vid))
                self.assertLessEqual(look.hk_bottom, B.CONTENT_BOTTOM, (style, vid))
                self.assertLessEqual(len(look.hk_sb.lines), 3, (style, vid))
                self.assertTrue(look.hk_sb.fits, (style, vid))
                self.assertLessEqual(look.hk_sb.w, B.HOOK_W + 0.5)
                w, _ = look.tag_box()
                self.assertLessEqual(B.CX + w / 2, S["right"] - 4, (style, vid))
                self.assertGreaterEqual(B.CX - w / 2, S["left"] + 4, (style, vid))
                self.assertGreater(look.hk_sb.px, look.hk_pb.px)                 # 場面 ＞ 呼びかけ
                # 掴みと、問題の画面へ移るあいだは、YouTube の文字やボタンが重なる所（SAFE の右と下）に背景のほか何も描かない
                # （そのあとの選択肢が右から入る動きは版5のまま）
                R = dk.R
                bg = arr(look.bg.convert("RGB"))
                for t in (0.0, look.T.hook0 - 0.1, look.T.hook0 + 0.15, look.T.start):
                    if style in ("黒板", "ノート") and look.T.hook0 < t < look.T.start:
                        continue                                                  # 黒板消し・めくれてくるページは画面の端も通る（文字ではない）
                    f = arr(look.frame(t))
                    right = np.abs(f[:, int((S["right"] + 2) * R):] - bg[:, int((S["right"] + 2) * R):]).max()
                    bottom = np.abs(f[int(S["bottom"] * R):] - bg[int(S["bottom"] * R):]).max()
                    self.assertLess(right, 8, (style, vid, t, "右端"))
                    self.assertLess(bottom, 8, (style, vid, t, "下"))

    # ---------- 音 ----------
    def test_効果音とBGMは時刻表にそろう(self):
        th = small_theme()
        for style in LOOKS:
            for sc, vid in CASES:
                look = render.make_look(sc, th, style, vid)
                T = look.T
                ev = look.sounds()
                ticks = sorted(t for name, t, _, _ in ev if name == "tick")
                self.assertEqual(len(ticks), 3, (style, vid))
                for a, b in zip(ticks, T.ticks):
                    self.assertAlmostEqual(a, b)
                self.assertIn(T.reveal, [t for name, t, _, _ in ev if name == "chime"])
                self.assertTrue(all(0 <= t < look.dur for _, t, _, _ in ev), (style, vid))
                # 掴み → 問題の画面の場面転換の音
                self.assertTrue(any(abs(t - T.hook0) < 0.1 and name in ("swoosh", "eraser", "flip") for name, t, _, _ in ev), (style, vid))
                # 選択肢の音は、選択肢が出る時刻（問題の画面のあと）
                first_card = min(look.card_t)
                self.assertGreaterEqual(first_card, T.start)
                tm = T.times()
                self.assertEqual(tm["ticks"], T.ticks)
                self.assertAlmostEqual(tm["count0"], T.ticks[0])
                self.assertAlmostEqual(tm["reveal"], T.count1)

    def test_声は掴みのあいだに読み始め増えは1秒半まで(self):
        """声の長さを作り物にして、plan_voice が版6の時刻表に合わせてずらすことと、版5より1.5秒を超えて伸びないことを確かめる"""
        old = voice.say, voice.lines
        seen = {}
        try:
            for sc, vid in ((TWO, "h927"), (THREE, "v927"), (TWO, "h928")):
                for full in (2.0, 3.5, 4.4, 5.0, 5.7, 6.5, 8.0):
                    durs = {}
                    th6, th5 = render.load_theme(), render.load_theme()
                    th5["見た目の版"] = 5
                    vcfg = th6["声"]

                    def fake_say(texts, window, speed, sr):
                        for k, text in enumerate(texts):
                            L = full if k == 0 else 0.9
                            if L <= window:
                                return np.zeros(int(L * sr)), text
                        return None, None

                    def fake_lines(sc_, words, cfg, times, sr, cta=False, question=True):
                        seen["times"] = times
                        return [(times["ans"][0], np.zeros(int(0.5 * sr)))], []
                    voice.say, voice.lines = fake_say, fake_lines
                    for ver, th in ((5, th5), (6, th6)):
                        th["画質"] = "720x1280"
                        look = render.make_look(sc, th, "モーション", vid)
                        voices, _ = render.plan_voice(look, sc, th, vcfg)
                        durs[ver] = look.dur
                        T = look.T
                        q0, qx = voices[0]
                        self.assertAlmostEqual(q0, 0.15)                              # 問題の声は 0.15秒から
                        self.assertLessEqual(q0 + len(qx) / audio.SR, T.count0 - 0.1 + 1e-6, (ver, vid, full))   # カウントダウンの前に読み終わる
                        self.assertAlmostEqual(seen["times"]["ans"][0], T.reveal + 0.1)
                        self.assertAlmostEqual(seen["times"]["count0"], T.count0)
                        if ver == 6:
                            self.assertGreaterEqual(T.count0, B.COUNT0 + B.HOOK_SHIFT)
                    self.assertLessEqual(durs[6] - durs[5], 1.5 + 1e-6, (vid, full, durs))
                    self.assertGreaterEqual(durs[6] - durs[5], 0.0, (vid, full, durs))
        finally:
            voice.say, voice.lines = old


if __name__ == "__main__":
    unittest.main(verbosity=1)
