# -*- coding: utf-8 -*-
"""読み上げの声（入れるかどうかは themes/*.json の「声」→「使う」。はじめはオフ）。

使うのは Open JTalk（名古屋工業大学ほか・修正BSDライセンス）と、
声のデータ HTS Voice "NITECH-JP-ATR503-M001"（名古屋工業大学・CC BY 3.0：クレジットを出せば、商用を含めて使える）。
Ubuntu の公式の部品（apt の open-jtalk・open-jtalk-mecab-naist-jdic・hts-voice-nitech-jp-atr503-m001）で入る。
入っていなければ、声なしで動画を作る（止まらない）。
"""
import os, re, shutil, subprocess, tempfile, wave
import numpy as np

DIC_DIRS = ["/var/lib/mecab/dic/open-jtalk/naist-jdic", "/usr/share/open_jtalk/dic"]
VOICES = ["/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"]


def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def available():
    return bool(shutil.which("open_jtalk") and _find(DIC_DIRS) and _find(VOICES))


def reading(text, table):
    """画面の文字を、読み上げ用に直す（*を消す、単位などを読み替える）"""
    s = str(text).replace("*", "")
    for k in sorted(table, key=len, reverse=True):
        v = table[k]
        if re.fullmatch(r"[a-z]+", k):          # 小文字の単位（m・kg など）は、数字のすぐ後ろだけ
            s = re.sub(r"(?<=[0-9０-９])" + re.escape(k) + r"(?![A-Za-z])", v, s)
        else:
            s = s.replace(k, v)
    return s


def synth(text, speed, sr):
    """text を読み上げた音（モノラル、sr Hz、-1〜1）を返す"""
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "v.wav")
        cmd = ["open_jtalk", "-x", _find(DIC_DIRS), "-m", _find(VOICES), "-r", f"{speed:.2f}", "-ow", out]
        subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True, timeout=60)
        with wave.open(out, "rb") as w:
            rate, n = w.getframerate(), w.getnframes()
            x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if rate != sr:
        x = np.interp(np.arange(int(len(x) * sr / rate)) * rate / sr, np.arange(len(x)), x)
    # 前後の無音を詰める
    idx = np.where(np.abs(x) > 0.01)[0]
    if len(idx):
        x = x[max(0, idx[0] - int(0.02 * sr)): idx[-1] + int(0.05 * sr)]
    return x


def fit(text, window, speed, sr, max_speed=1.7):
    """window 秒に収まる速さで読み上げる（少しずつ速くして試す）。収まらなければ None"""
    sp = speed
    while sp <= max_speed + 1e-6:
        x = synth(text, sp, sr)
        if len(x) / sr <= window:
            return x
        sp = round(sp * 1.12, 2)
    return None


def lines(sc, words, cfg, times, sr):
    """動画の中で読む声のリスト [(開始の秒, 音)] と、読めなかった所の名前"""
    tbl = cfg.get("読み替え", {})
    speed = float(cfg.get("速さ", 1.15))
    q = reading(sc["q1"], tbl) + ("。" + reading(sc["q2"], tbl) if sc.get("q2") else "")
    letter = sc["answer"].strip().upper()
    trap = sc["trap"].split("：", 1)[1] if "：" in sc["trap"] else sc["trap"]
    q2 = reading(sc["q2"], tbl) if sc.get("q2") else ""
    plan = [("問題", [q] + ([q2] if q2 else []), times["q"]),     # 長すぎたら、2行目（問いの部分）だけを読む
            ("正解", [reading(words.get("正解", "正解は"), tbl) + "、" + letter + "。", letter + "。"], times["ans"]),
            ("ひっかけ", [reading(trap, tbl)], times["trap"])]
    out, skipped = [], []
    for name, texts, (t0, t1) in plan:
        for text in texts:
            x = fit(text, t1 - t0, speed, sr)
            if x is not None:
                out.append((t0, x))
                break
        else:
            skipped.append(name)
    return out, skipped
