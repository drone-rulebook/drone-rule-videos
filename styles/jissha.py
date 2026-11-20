# -*- coding: utf-8 -*-
"""型4「実写」（見た目の版7。2026-11-20）：モーションの文字・カード・動きのまま、背景に空撮の実写が流れる。
素材は footage/clips/<id>.mp4（Mixkit の無料素材。footage/manifest.json で許諾の表示を確かめたものだけ）。
文字が読めるよう、実写は全体を暗くし、上（見出し）と下（説明・題名の重なる所）をさらに暗くする。
素材が短いときは、ゆっくり再生して動画の長さに合わせる。最後の0.5秒で1こま目の背景へ溶かし、くり返し再生をつなげる。
どの枠で使うかは themes の「実写の背景」（使う・枠・使わない素材）で決める（render.py の choose_look）。"""
import json, os, subprocess
import numpy as np
from PIL import Image
import drawkit as dk
from .motion import Motion

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOT = os.path.join(HERE, "footage")
FPS = 30
XFADE = 0.5          # 最後に1こま目の背景へ溶かす秒数


def clips(theme=None):
    """使える素材の一覧（id の順）：manifest で「使う」・ファイルがある・themes の「使わない素材」に無い"""
    try:
        man = json.load(open(os.path.join(FOOT, "manifest.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return []
    skip = {str(x) for x in ((theme or {}).get("実写の背景", {}).get("使わない素材") or [])}
    out = []
    for c in man.get("clips", []):
        p = os.path.join(FOOT, "clips", f"{c['id']}.mp4")
        if c.get("使う") and str(c["id"]) not in skip and os.path.exists(p):
            out.append((int(c["id"]), p, float(c.get("長さ") or 0)))
    return sorted(out)


def pick_clip(vid, theme):
    cs = clips(theme)
    if not cs:
        return None
    from .base import id_number
    n = id_number(vid) if vid else 0
    return cs[(n or 0) % len(cs)]


def _ffmpeg():
    import shutil
    p = shutil.which("ffmpeg")
    if p:
        return p
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Jissha(Motion):
    name = "実写"
    still = False        # 確かめ用：True なら背景を1こま目の実写で止める（版5・版6の絵のテストを同じ形で通すため）

    def __init__(self, sc, theme, colors, vid=None):
        self.clip = pick_clip(vid, theme)
        if self.clip is None:
            raise RuntimeError("実写の素材がありません（footage/clips と footage/manifest.json）")
        self._proc, self._pos, self._cur = None, -1, None
        self._first = None
        super().__init__(sc, theme, colors, vid)
        self.overlay = self.bg          # Motion が作った self.bg（make_bg）を、実写の上にかぶせる暗い膜として使う
        self.bg = self._first_bg()      # こまを描く前の背景＝1こま目の背景

    # 実写の上にかぶせる膜（文字を読みやすくする）
    def make_bg(self):
        H, W = dk.H, dk.W
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        a = 0.26 + 0.34 * np.clip((0.40 - y) / 0.40, 0, 1) + 0.36 * np.clip((y - 0.72) / 0.28, 0, 1)
        a = np.clip(a, 0, 0.85)
        alpha = np.repeat((a * 255).astype(np.uint8), W, axis=1)
        rgb = np.zeros((H, W, 3), np.uint8)
        rgb[:] = (6, 12, 24)
        return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")

    # ---------- 実写の読み出し（前から順に読む。戻るときは読み直す） ----------
    def _open(self):
        if self._proc:
            self._proc.kill()
        _, path, length = self.clip
        need = self.dur + 0.2
        slow = max(1.0, need / length) if length > 0 else 1.0
        vf = f"setpts={slow:.4f}*PTS,fps={FPS},scale={dk.W}:{dk.H}:flags=bicubic"
        cmd = [_ffmpeg(), "-v", "error", "-i", path, "-vf", vf, "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._pos, self._cur = -1, None

    def _read_one(self):
        n = dk.W * dk.H * 3
        buf = self._proc.stdout.read(n) if self._proc else b""
        if len(buf) < n:
            return False
        self._cur = np.frombuffer(buf, np.uint8).reshape(dk.H, dk.W, 3)
        self._pos += 1
        return True

    def _video(self, i):
        if self._proc is None or i < self._pos:
            self._open()
        while self._pos < i:
            if not self._read_one():
                break                       # 素材が足りなければ最後のこまを使い続ける
        if self._cur is None:
            return np.zeros((dk.H, dk.W, 3), np.uint8)
        return self._cur

    def _first_bg(self):
        """1こま目の背景（実写の最初のこま＋膜）。最後に溶かしてもどる先"""
        if self._first is None:
            _, path, _ = self.clip
            cmd = [_ffmpeg(), "-v", "error", "-i", path, "-vf", f"scale={dk.W}:{dk.H}:flags=bicubic", "-frames:v", "1",
                   "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            buf = subprocess.run(cmd, capture_output=True).stdout
            n = dk.W * dk.H * 3
            arr = np.frombuffer(buf[:n], np.uint8).reshape(dk.H, dk.W, 3) if len(buf) >= n else np.zeros((dk.H, dk.W, 3), np.uint8)
            self._first = Image.fromarray(arr).convert("RGBA")
            self._first.alpha_composite(self.overlay)
        return self._first

    def _bg_at(self, t):
        img = Image.fromarray(self._video(int(round(t * FPS)))).convert("RGBA")
        img.alpha_composite(self.overlay)
        p = dk.prog(t, self.dur - XFADE, self.dur - 1.0 / FPS)
        if p > 0:
            img = Image.blend(img, self._first_bg(), p)
        return img

    def frame(self, t):
        if not self.still:
            self.bg = self._bg_at(t)
        return super().frame(t)

    def __del__(self):
        try:
            if self._proc:
                self._proc.kill()
        except Exception:
            pass
