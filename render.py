# -*- coding: utf-8 -*-
"""二等学科ひっかけクイズの縦型ショート動画（1080x1920・30fps・14秒）を、台本から作る。

使い方
  python render.py                     … 公開した「動画台本」シート（config.json の csv_url）を読み、近い日の「待ち」の台本を動画にする。
                                         見た目の版（themes/*.json）が変わっていたら、まだ公開していない動画を新しい見た目で作り直す。
  python render.py --sample out.mp4 [--style 黒板]   … 見本の台本で1本だけ作る（確認用）
  python render.py --samples           … 型ごとの見本を samples/ に作る（mp4 と、見せ場を並べた画像）
  python render.py --csv 台本.csv 出力先  … CSV の全行を（日付や状態に関係なく）出力先に作る（確かめ用）

絵・動き・文字・効果音・BGM はすべてプログラムで作る（素材ファイルは使わない。フォントだけ fonts/ に同梱）。
台本の文字は、*で囲んだところを強調する（例：150mは*どこから*測る？）。
見た目の型（styles/）は3つ。台本IDで日替わりに選ぶ（themes/*.json の「型の選び方」）。
"""
import csv, datetime, io, json, os, re, shutil, subprocess, sys, unicodedata, urllib.request, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drawkit as dk
import audio
import voice
from styles import LOOKS
from styles.base import DUR, COUNT0, REVEAL, TR0, TR1

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
N = int(FPS * DUR)
SIZES = {"1080x1920": (1080, 1920), "720x1280": (720, 1280)}
MAX_MB = 2.4          # これより大きくなったら、少し圧縮しなおす
TARGET_MB = 2.0


# ---------- 設定（テーマ） ----------
def load_config():
    return json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))


def load_theme(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    name = cfg.get("theme", "drone")
    theme = json.load(open(os.path.join(HERE, "themes", name + ".json"), encoding="utf-8"))
    theme["_name"] = name
    dk.NO_BREAK_WORDS[:] = theme.get("改行しない言葉", [])
    dk.LANG = theme.get("言語", "ja")
    for k, v in list(theme["文言"].items()):           # 画面に出す文言も、フォントに無い文字を近い字に
        theme["文言"][k], bad = safe_text(v)
        if bad:
            print("注意：文言にフォントに無い文字があります：", k, "".join(bad))
    for k in theme["型の選び方"]["型"]:
        if k not in LOOKS:
            raise ValueError("themes の 型 に知らない名前があります：" + k + "（使えるのは " + "・".join(LOOKS) + "）")
    return theme


def look_tag(theme):
    """動画に書きこむ「見た目の版」の印（テーマ名と版の番号）"""
    return f"{theme['_name']}-{theme['見た目の版']}"


def choose_look(vid, theme, row=None):
    """台本ID（と台本の「型」の列）から、その日の見た目の型を決める"""
    sel = theme["型の選び方"]
    names = sel["型"]
    if row and str(row.get("型", "")).strip() in LOOKS:
        return str(row["型"]).strip()
    if sel.get("方法") == "固定":
        return names[0]
    nums = re.findall(r"\d+", vid)
    n = int(nums[-1]) if nums else zlib.crc32(vid.encode("utf-8"))
    return names[n % len(names)]


# ---------- 書き出し ----------
def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise RuntimeError("ffmpeg が見つかりません（pip install imageio-ffmpeg で入ります）")


def read_tag(path):
    """動画に書きこんだ「見た目の版」を読む（無ければ ""）"""
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace")
    m = re.search(r"comment\s*:\s*look=([^\s;]+)", r.stderr)
    return m.group(1) if m else ""


def make_look(sc, theme, style):
    w, h = SIZES.get(theme.get("画質", "1080x1920"), SIZES["1080x1920"])
    dk.setup(w, h)
    return LOOKS[style](sc, theme, theme["色"][style])


TIMES = {"count0": COUNT0, "reveal": REVEAL, "ticks": [COUNT0 + k for k in range(3)],
         "q": (0.3, COUNT0 - 0.1), "ans": (REVEAL + 0.1, REVEAL + 1.15), "trap": (REVEAL + 1.2, TR1 + 0.6)}


def render(sc, out_path, theme, style, info=None):
    """台本 sc を style の見た目で動画にして out_path に置く。info（dict）に声の結果などを書く。"""
    info = info if info is not None else {}
    look = make_look(sc, theme, style)
    vcfg = theme.get("声", {})
    voices = []
    if vcfg.get("使う"):
        if voice.available(vcfg):
            voices, skipped = voice.lines(sc, theme["文言"], vcfg, TIMES, audio.SR)
            if voices:
                look.voice_credit = safe_text(vcfg.get("クレジット", ""))[0]
            info["声"] = "オン" + ("（時間内に読めず省いた所：" + "・".join(skipped) + "）" if skipped else "")
        else:
            info["声"] = "オン（読み上げの部品が無いので声なし）"
    tmp_wav = out_path + ".wav"
    part = out_path + ".part.mp4"
    try:
        audio.build(look, tmp_wav, DUR, TIMES, bgm=theme.get("BGM", True), voices=voices)
        tag = f"look={look_tag(theme)};style={style}"
        cmd = [ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{dk.W}x{dk.H}", "-r", str(FPS), "-i", "-",
               "-i", tmp_wav, "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-tune", "animation", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-metadata", "comment=" + tag, "-movflags", "+faststart", "-shortest", part]
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for i in range(N):
                p.stdin.write(look.frame(i / FPS).tobytes())
        finally:
            p.stdin.close()
        if p.wait() != 0:
            raise RuntimeError("ffmpeg に失敗しました")
        if os.path.getsize(part) > MAX_MB * 1e6:      # 大きすぎたら、決めた大きさに収まるように圧縮しなおす
            kbps = int((TARGET_MB * 8e6 / DUR - 128e3) / 1000)
            again = part + ".2.mp4"
            subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", part, "-c:v", "libx264", "-preset", "slow", "-b:v", f"{kbps}k",
                            "-maxrate", f"{int(kbps * 1.3)}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p", "-c:a", "copy",
                            "-metadata", "comment=" + tag, "-movflags", "+faststart", again], check=True)
            os.replace(again, part)
        os.replace(part, out_path)
    finally:
        for f in (tmp_wav, part, part + ".2.mp4"):
            if os.path.exists(f):
                os.remove(f)
    return look


# ---------- 台本シート（CSV）→ 作る分を選ぶ ----------
VARIANTS = {"塡": "填", "剝": "剥", "頰": "頬", "𠮟": "叱"}
_CHARS = None

def safe_text(s):
    """動画のフォント（fonts/chars.txt）に無い文字を、近い文字に置き換える。置き換えられなかった文字も返す。"""
    global _CHARS
    if _CHARS is None:
        p = os.path.join(HERE, "fonts", "chars.txt")
        _CHARS = set(open(p, encoding="utf-8").read()) if os.path.exists(p) else set()
    if not _CHARS:
        return s, []
    out, bad = [], []
    for ch in str(s):
        if ch in _CHARS or ch in "*\n ":
            out.append(ch)
            continue
        alt = VARIANTS.get(ch) or unicodedata.normalize("NFKC", ch)
        if alt and all(c in _CHARS for c in alt):
            out.append(alt)
        else:
            out.append(ch); bad.append(ch)
    return "".join(out), bad

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

def jst_today():
    if os.environ.get("TODAY"):                 # 確かめ用：日付を決めて動かす
        return datetime.date.fromisoformat(os.environ["TODAY"])
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()

def parse_date(s):
    s = str(s or "").strip().replace("/", "-")
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None

def status_path():
    return os.environ.get("STATUS_FILE") or os.path.join(HERE, "status.json")

def write_status(st):
    """実行の結果を status.json に残す（Actions の画面を見なくても、置き場で結果がわかるように）。"""
    st = dict({"最終実行（日本時間）": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")}, **st)
    with open(status_path(), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
        f.write("\n")

def script_of(r):
    """CSV の1行 → 台本（足りなければ None と理由）"""
    sc = {"q1": r.get("問題1行目", ""), "q2": r.get("問題2行目", ""), "a": r.get("選択肢A", ""), "b": r.get("選択肢B", ""),
          "c": r.get("選択肢C", ""), "answer": r.get("正解", ""), "trap": r.get("ひっかけ", "")}
    sc = {k: str(v or "").strip() for k, v in sc.items()}
    if not (sc["q1"] and sc["a"] and sc["b"] and sc["c"] and sc["trap"] and sc["answer"].upper() in ("A", "B", "C")):
        return None, "台本が足りない"
    bad = []
    for k in ("q1", "q2", "a", "b", "c", "trap"):
        sc[k], b = safe_text(sc[k]); bad += b
    if bad:
        return None, "使えない文字：" + "".join(sorted(set(bad)))
    return sc, ""

def read_rows(cfg):
    local = os.environ.get("CSV_FILE")          # 確かめ用：手元の CSV を読む
    if local:
        raw = open(local, encoding="utf-8-sig").read()
    else:
        url = os.environ.get("CSV_URL") or cfg.get("csv_url", "")
        if not url.startswith("https://docs.google.com/"):
            return None
        raw = urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    if "台本ID" not in (reader.fieldnames or []):
        raise ValueError("公開したシートが「動画台本」ではないようです（1行目に 台本ID がありません）")
    return list(reader)

def main():
    st = {"結果": "", "台本の行数": 0, "作った動画": [], "見送った台本": [], "作れなかった台本": [], "消した動画": 0,
          "次に作る予定": [], "エラー": "", "見た目の版": "", "型": {}, "作り直した動画": [], "作り直せなかった動画": [], "声": ""}
    try:
        _main(st)
    except Exception as e:
        st["結果"] = "失敗"
        st["エラー"] = (type(e).__name__ + "：" + str(e))[:300]
        write_status(st)
        raise
    st["結果"] = "一部失敗" if st["作れなかった台本"] else (st["結果"] or "成功")
    write_status(st)
    if st["作れなかった台本"]:
        sys.exit(1)

def _main(st):
    cfg = load_config()
    theme = load_theme(cfg)
    tag = look_tag(theme)
    st["見た目の版"] = tag
    st["声"] = "オン" if theme.get("声", {}).get("使う") else "オフ"
    rows = read_rows(cfg)
    if rows is None:
        print("config.json の csv_url が未設定です。何もしません。")
        st["結果"] = "未設定（csv_url）"
        return
    today = jst_today()
    ahead = int(cfg.get("days_ahead", 3))
    keep = int(cfg.get("keep_days", 10))
    vdir = os.environ.get("VIDEOS_DIR") or os.path.join(HERE, "videos")
    os.makedirs(vdir, exist_ok=True)
    dates = {}
    for r in rows:
        vid = str(r.get("台本ID", "")).strip()
        d = parse_date(r.get("公開予定日"))
        if not ID_RE.match(vid) or d is None:
            continue
        st["台本の行数"] += 1
        dates[vid] = d
        if str(r.get("状態", "")).strip() != "待ち":
            continue
        if d > today + datetime.timedelta(days=ahead):
            st["次に作る予定"].append(vid)
            continue
        if d < today - datetime.timedelta(days=1):
            continue
        out = os.path.join(vdir, vid + ".mp4")
        redo = False
        if os.path.exists(out):
            # 見た目の版が変わっていて、まだ公開していない（公開予定日が今日以降）なら作り直す
            if d < today or read_tag(out) == tag:
                continue
            redo = True
        sc, why = script_of(r)
        if sc is None:
            print("見送り：", vid, why)
            st["見送った台本"].append(vid if why == "台本が足りない" else vid + "（" + why + "）")
            continue
        style = choose_look(vid, theme, r)
        info = {}
        try:
            # 作り直しのときは、別の名前で作ってから入れかえる（失敗したら古い動画を残す）
            tmp = out + ".new.mp4" if redo else out
            render(sc, tmp, theme, style, info)
            if redo:
                os.replace(tmp, out)
        except Exception as e:
            print("作れませんでした：", vid, e)
            (st["作り直せなかった動画"] if redo else st["作れなかった台本"]).append(vid)
            for f in os.listdir(vdir):                 # 作りかけのファイルを片づける（元の動画はそのまま）
                if f.startswith(vid + ".mp4.") or f.startswith(vid + ".mp4.new"):
                    os.remove(os.path.join(vdir, f))
            continue
        if info.get("声"):
            st["声"] = info["声"]
        st["型"][vid] = style
        print(("作り直し：" if redo else "作成："), vid, d, style)
        (st["作り直した動画"] if redo else st["作った動画"]).append(vid)
    st["次に作る予定"] = st["次に作る予定"][:3]
    # 古い動画を消す（置き場を軽く保つ）
    for name in os.listdir(vdir):
        if not name.endswith(".mp4"):
            continue
        vid = name[:-4]
        d = dates.get(vid)
        if d is not None and d < today - datetime.timedelta(days=keep):
            os.remove(os.path.join(vdir, name)); st["消した動画"] += 1
    print(f"作成 {len(st['作った動画'])} 本・作り直し {len(st['作り直した動画'])} 本・見送り {len(st['見送った台本'])} 本・"
          f"失敗 {len(st['作れなかった台本']) + len(st['作り直せなかった動画'])} 本・削除 {st['消した動画']} 本")


# ---------- 確かめ用 ----------
SAMPLE = {"q1": "「高度150m以上」の空域", "q2": "150mは*どこから*測る？", "a": "海抜高度（標高）", "b": "直下の地表・水面",
          "c": "飛行場の標点", "answer": "B", "trap": "ひっかけ：*海抜*ではない！"}

SHEET_T = [(0.4, "問題"), (2.6, "3択"), (6.3, "カウントダウン"), (8.45, "正解"), (10.6, "ひっかけ"), ((TR0 + TR1) / 2, "転換"), (13.3, "締め")]


def contact_sheet(sc, theme, style, path, guides=False):
    """見せ場の静止画を横に並べた1枚の画像。guides=True なら、YouTube の文字やボタンが重なる所を赤く示す。"""
    from PIL import Image, ImageDraw
    look = make_look(sc, theme, style)
    tw, th = 360, 640
    lab_h = 44
    sheet = Image.new("RGB", (tw * len(SHEET_T) + 8 * (len(SHEET_T) + 1), th + lab_h + 16), (235, 236, 240))
    d = ImageDraw.Draw(sheet)
    f = dk.font("Bold", 22 / dk.R)
    for k, (t, name) in enumerate(SHEET_T):
        fr = look.frame(t).resize((tw, th), Image.LANCZOS)
        if guides:
            ov = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            s = tw / dk.LW
            od.rectangle([0, dk.SAFE["bottom"] * s, tw, th], fill=(255, 0, 0, 70))
            od.rectangle([dk.SAFE["right"] * s, 0, tw, th], fill=(255, 0, 0, 50))
            od.rectangle([0, 0, tw, dk.SAFE["top"] * s], fill=(255, 0, 0, 50))
            fr = Image.alpha_composite(fr.convert("RGBA"), ov).convert("RGB")
        x = 8 + k * (tw + 8)
        sheet.paste(fr, (x, 8))
        d.text((x + tw / 2, th + 8 + lab_h / 2 + 4), f"{t:.1f}秒 {name}", font=f, fill=(40, 44, 60), anchor="mm")
    sheet.save(path, optimize=True)


def make_samples(outdir, sc=None, guides_dir=None):
    theme = load_theme()
    os.makedirs(outdir, exist_ok=True)
    for style in LOOKS:
        out = os.path.join(outdir, style + ".mp4")
        render(sc or SAMPLE, out, theme, style)
        contact_sheet(sc or SAMPLE, theme, style, os.path.join(outdir, style + ".png"))
        if guides_dir:
            contact_sheet(sc or SAMPLE, theme, style, os.path.join(guides_dir, style + "_目安つき.png"), guides=True)
        print("見本：", out)


def render_csv(path, outdir, sheets=False):
    """CSV の全行を作る（日付・状態は見ない）。作れなかった行の数を返す"""
    theme = load_theme()
    os.makedirs(outdir, exist_ok=True)
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    bad = 0
    for r in rows:
        vid = str(r.get("台本ID", "")).strip()
        sc, why = script_of(r)
        if sc is None:
            print("見送り：", vid, why); continue
        style = choose_look(vid, theme, r)
        try:
            render(sc, os.path.join(outdir, vid + ".mp4"), theme, style)
            if sheets:
                contact_sheet(sc, theme, style, os.path.join(outdir, vid + ".png"), guides=True)
            print("作成：", vid, style)
        except Exception as e:
            bad += 1
            print("作れませんでした：", vid, type(e).__name__, e)
    return bad


if __name__ == "__main__":
    args = sys.argv[1:]
    style = None
    if "--style" in args:
        i = args.index("--style"); style = args[i + 1]; del args[i:i + 2]
    if len(args) >= 2 and args[0] == "--sample":
        th = load_theme()
        render(SAMPLE, args[1], th, style or th["型の選び方"]["型"][0]); print("作成：", args[1])
    elif args and args[0] == "--samples":
        make_samples(os.path.join(HERE, "samples"), guides_dir=args[1] if len(args) > 1 else None)
    elif len(args) >= 3 and args[0] == "--csv":
        sys.exit(1 if render_csv(args[1], args[2], sheets="--sheets" in args) else 0)
    else:
        main()
