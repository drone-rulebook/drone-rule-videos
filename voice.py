# -*- coding: utf-8 -*-
"""読み上げの声（入れるかどうかは themes/*.json の「声」→「使う」。はじめはオフ）。

声の作り方は「声」→「エンジン」で選ぶ。
- "VOICEVOX"：VOICEVOX ENGINE（Actions では docker の voicevox/voicevox_engine を立てる）。話者は「話者」「スタイル」で選ぶ
  （例：ずんだもん／ノーマル）。キャラクターごとの規約に従い、クレジット「VOICEVOX:キャラ名」を動画内に出す。
- "OpenJTalk"：Open JTalk（修正BSD）と HTS Voice "NITECH-JP-ATR503-M001"（名古屋工業大学・CC BY 3.0）。apt で入る。
どちらも使えなければ、声なしで動画を作る（止まらない）。
"""
import io, json, os, re, shutil, subprocess, tempfile, urllib.parse, urllib.request, wave
import numpy as np

VOICEVOX_URL = os.environ.get("VOICEVOX_URL", "http://127.0.0.1:50021")
KOKORO_DIR = os.environ.get("KOKORO_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"))
_engine = {"name": "OpenJTalk", "speaker": None}

DIC_DIRS = ["/var/lib/mecab/dic/open-jtalk/naist-jdic", "/usr/share/open_jtalk/dic"]
VOICES = ["/usr/share/hts-voice/nitech-jp-atr503-m001/nitech_jp_atr503_m001.htsvoice"]


def _find(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _vv(path, params=None, body=None, timeout=60):
    url = VOICEVOX_URL + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode("utf-8") if body is not None else (b"" if path != "/speakers" and path != "/version" else None)
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _vv_speaker(name, style):
    for sp in json.loads(_vv("/speakers")):
        if sp.get("name") == name:
            for st in sp.get("styles", []):
                if st.get("name") == style:
                    return st["id"]
    return None


def available(cfg=None):
    """声を作れるか。cfg（themes の「声」）の「エンジン」で使う方を選ぶ"""
    cfg = cfg or {}
    if str(cfg.get("エンジン", "OpenJTalk")).upper() == "KOKORO":
        # Kokoro（英語。モデルは Apache-2.0）。kokoro-onnx と、models/ の kokoro-v1.0.onnx・voices-v1.0.bin を使う
        try:
            from kokoro_onnx import Kokoro
            model = os.path.join(KOKORO_DIR, cfg.get("モデル", "kokoro-v1.0.onnx"))
            voices = os.path.join(KOKORO_DIR, "voices-v1.0.bin")
            if not (os.path.exists(model) and os.path.exists(voices)):
                return False
            if _engine.get("name") != "Kokoro":
                _engine.update(name="Kokoro", kokoro=Kokoro(model, voices))
            _engine.update(speaker=cfg.get("話者", "af_heart"), lang=cfg.get("言語コード", "en-us"))
            return True
        except Exception:
            return False
    if str(cfg.get("エンジン", "OpenJTalk")).upper() == "VOICEVOX":
        try:
            sid = _vv_speaker(cfg.get("話者", "ずんだもん"), cfg.get("スタイル", "ノーマル"))
        except Exception:
            return False
        if sid is None:
            return False
        _engine.update(name="VOICEVOX", speaker=sid)
        return True
    _engine.update(name="OpenJTalk", speaker=None)
    return bool(shutil.which("open_jtalk") and _find(DIC_DIRS) and _find(VOICES))


def reading(text, table):
    """画面の文字を、読み上げ用に直す（*を消す、単位などを読み替える）。
    「re:」で始まる見出しは正規表現として先に使う（例："re:(\\d)\\s?ft\\b" → "\\1 feet"）"""
    s = str(text).replace("*", "")
    for k, v in table.items():
        if k.startswith("re:"):
            s = re.sub(k[3:], v, s)
    for k in sorted((k for k in table if not k.startswith("re:")), key=len, reverse=True):
        v = table[k]
        if re.fullmatch(r"[a-z]+", k):          # 小文字の単位（m・kg など）は、数字のすぐ後ろだけ
            s = re.sub(r"(?<=[0-9０-９])" + re.escape(k) + r"(?![A-Za-z])", v, s)
        else:
            s = s.replace(k, v)
    return s


def synth(text, speed, sr):
    """text を読み上げた音（モノラル、sr Hz、-1〜1）を返す"""
    if _engine["name"] == "Kokoro":
        x, rate = _engine["kokoro"].create(text, voice=_engine["speaker"], speed=float(speed), lang=_engine.get("lang", "en-us"))
        return _finish(np.asarray(x, dtype=np.float64), rate, sr)
    if _engine["name"] == "VOICEVOX":
        sid = _engine["speaker"]
        q = json.loads(_vv("/audio_query", {"text": text, "speaker": sid}))
        q.update(speedScale=speed, prePhonemeLength=0.05, postPhonemeLength=0.08,
                 outputSamplingRate=sr, outputStereo=False)
        wav = _vv("/synthesis", {"speaker": sid}, body=q, timeout=120)
        with wave.open(io.BytesIO(wav), "rb") as w:
            rate, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
            x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        return _finish(x, rate, sr)
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "v.wav")
        cmd = ["open_jtalk", "-x", _find(DIC_DIRS), "-m", _find(VOICES), "-r", f"{speed:.2f}", "-ow", out]
        subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True, timeout=60)
        with wave.open(out, "rb") as w:
            rate, n = w.getframerate(), w.getnframes()
            x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    return _finish(x, rate, sr)


def _finish(x, rate, sr):
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
    en = _engine.get("name") == "Kokoro"
    sep = " " if en else "。"
    q = reading(sc["q1"], tbl) + (sep + reading(sc["q2"], tbl) if sc.get("q2") else "")
    letter = sc["answer"].strip().upper()
    trap = sc["trap"]
    for mark in ("：", ":"):
        if mark in trap and 0 < len(trap.split(mark, 1)[0].replace("*", "")) <= 8:
            trap = trap.split(mark, 1)[1].strip()
            break
    q2 = reading(sc["q2"], tbl) if sc.get("q2") else ""
    if words.get("正解の読み"):                        # 例："The answer is {}."
        ans = [words["正解の読み"].format(letter), letter + "."]
    else:
        ans = [reading(words.get("正解", "正解は"), tbl) + "、" + letter + "。", letter + "。"]
    plan = [("問題", [q] + ([q2] if q2 else []), times["q"]),     # 長すぎたら、2行目（問いの部分）だけを読む
            ("正解", ans, times["ans"]),
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
