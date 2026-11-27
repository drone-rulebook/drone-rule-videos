# -*- coding: utf-8 -*-
"""解説（「なぜ？」の画面）のテスト：解説の無い台本は今までと同じ、解説のある18時の台本だけ長くなり、どの型でも1こまが作れる。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import render
from styles import base as B

ROW = {"台本ID": "v046", "公開予定日": "2026-11-28", "タイトル": "紐は何mまで？｜ドローン国家資格・二等学科", "問題1行目": "住宅街の庭で、紐につないで飛ばしたい",
       "問題2行目": "例外になる*紐*は何mまで？", "選択肢A": "30m以下", "選択肢B": "50m以下", "選択肢C": "10m以下", "正解": "A",
       "ひっかけ": "ポイント：立入管理などの措置も必要", "状態": "待ち", "枠": ""}
EX = "十分な強度がある*30m以下*の紐で係留し、飛ぶ範囲に第三者が入らないよう管理すれば、手続きが要らなくなります。"


def theme():
    th = render.load_theme()
    th["声"] = dict(th.get("声", {}), 使う=False)
    return th


def test_no_explain_same_sum_and_length():
    th = theme()
    sc, _ = render.script_of(ROW)
    assert sc["explain"] == ""
    sc2, _ = render.script_of(dict(ROW, 動画の解説=""))
    assert render.script_sum(sc) == render.script_sum(sc2)
    look = render.make_look(sc, th, "モーション", "v046")
    assert look.T.explain_len == 0 and look.T.ex0 is None
    assert look.T.times()["explain"] is None


def test_explain_only_in_slot():
    th = theme()
    sc, _ = render.script_of(dict(ROW, 動画の解説=EX, 動画の根拠="教則（第5版）3.1.2"))
    assert sc["explain"] and sc["basis"]
    sc_h, _ = render.script_of(dict(ROW, 動画の解説=EX, 枠="昼"))      # 昼の行には入れない（themes の「枠」が18時だけ）
    assert sc_h["explain"] == ""
    s0, _ = render.script_of(ROW)
    assert render.script_sum(sc) != render.script_sum(s0)          # 解説が付いたら作り直す


def test_explain_timeline_and_frames():
    th = theme()
    sc, _ = render.script_of(dict(ROW, 動画の解説=EX, 動画の根拠="教則（第5版）3.1.2"))
    for style in ("モーション", "黒板", "ノート"):
        look = render.make_look(sc, th, style, "v046")
        T = look.T
        assert T.explain_len >= B.EX_MIN and T.ex0 is not None and T.ex1 > T.ex0
        assert T.tr0 >= T.ex1 and (not T.cta or T.cta0 >= T.ex1)
        tm = T.times()
        assert tm["trap"][1] < T.ex0 and tm["explain"][0] > T.ex0
        for t in (T.ex0 - 0.1, T.ex0 + 0.2, (T.ex0 + T.ex1) / 2, T.ex1 - 0.05, T.ex1 + 0.1):
            fr = look.render_frame(t)
            assert fr.size == (1080, 1920) and fr.mode == "RGB"
        look.set_explain(9.0)
        assert abs(look.T.explain_len - (B.EX_VOICE0 + 9.0 + B.EX_TAIL + 0.15)) < 1e-6
