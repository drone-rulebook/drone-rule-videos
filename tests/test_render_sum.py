# -*- coding: utf-8 -*-
"""公開前の台本が書きかわったら、その動画だけを作り直すことを確かめる（声なし・小さい画面で2本を書き出す。1〜2分）。

  python tests/test_render_sum.py
"""
import csv, datetime, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import render  # noqa: E402

HEAD = ["台本ID", "公開予定日", "問題ID", "タイトル", "問題1行目", "問題2行目", "選択肢A", "選択肢B", "選択肢C", "正解", "ひっかけ", "状態"]


def rows(day, q1b):
    return [["t901", day, "1", "見本1", "「高度150m以上」の空域", "150mは*どこから*測る？", "海抜高度", "直下の地表・水面", "離陸した地点", "B", "ポイント：直下から測る", "待ち"],
            ["t902", day, "2", "見本2", q1b, "これ違反？", "違反になる", "違反にならない", "", "A", "ポイント：空域で決まる", "待ち"]]


class SumTest(unittest.TestCase):
    def test_印(self):
        a = {"q1": "あ", "q2": "", "a": "1", "b": "2", "c": "3", "answer": "A", "trap": "t"}
        self.assertEqual(render.script_sum(a), render.script_sum(dict(a)))
        self.assertNotEqual(render.script_sum(a), render.script_sum(dict(a, q1="い")))
        self.assertFalse(render.needs_redo("x-5", "", "x-5", a))                       # 印の無い古い動画は作り直さない
        self.assertFalse(render.needs_redo("x-5", render.script_sum(a), "x-5", a))
        self.assertTrue(render.needs_redo("x-5", render.script_sum(a), "x-5", dict(a, trap="u")))
        self.assertTrue(render.needs_redo("x-4", render.script_sum(a), "x-5", a))     # 見た目の版が変わった

    def test_書きかわった台本だけ作り直す(self):
        tmp = tempfile.mkdtemp()
        try:
            theme_dir = os.path.join(tmp, "themes")
            os.makedirs(theme_dir)
            th = json.load(open(os.path.join(ROOT, "themes", "drone.json"), encoding="utf-8"))
            th["画質"] = "720x1280"
            th["声"] = dict(th.get("声", {}), 使う=False)
            th["BGM"] = False
            json.dump(th, open(os.path.join(theme_dir, "drone.json"), "w", encoding="utf-8"), ensure_ascii=False)
            day = (render.jst_today() + datetime.timedelta(days=1)).isoformat()
            csvp = os.path.join(tmp, "s.csv")
            vdir = os.path.join(tmp, "videos")

            def run(q1b):
                with open(csvp, "w", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerows([HEAD] + rows(day, q1b))
                os.environ.update(CSV_FILE=csvp, VIDEOS_DIR=vdir, STATUS_FILE=os.path.join(tmp, "status.json"))
                old = render.load_theme
                render.load_theme = lambda cfg=None: dict(th, _name="drone")
                try:
                    st = {"結果": "", "台本の行数": 0, "作った動画": [], "見送った台本": [], "作れなかった台本": [], "消した動画": 0,
                          "次に作る予定": [], "エラー": "", "見た目の版": "", "型": {}, "締めの声": {}, "長さ（秒）": {},
                          "作り直した動画": [], "作り直せなかった動画": [], "声": ""}
                    render._main(st)
                    return st
                finally:
                    render.load_theme = old

            st1 = run("DIDにある*自宅の庭*で200gの登録機を飛行")
            self.assertEqual(sorted(st1["作った動画"]), ["t901", "t902"], st1)
            self.assertTrue(render.read_meta(os.path.join(vdir, "t902.mp4"))[1])
            st2 = run("DIDにある*自宅の庭*で200gの登録機を飛行")
            self.assertEqual(st2["作った動画"] + st2["作り直した動画"], [], st2)          # 変わっていなければ何もしない
            st3 = run("DIDにある*自宅の庭*で250gの登録機を飛行")
            self.assertEqual(st3["作り直した動画"], ["t902"], st3)                       # 書きかわった t902 だけ
        finally:
            for k in ("CSV_FILE", "VIDEOS_DIR", "STATUS_FILE"):
                os.environ.pop(k, None)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
