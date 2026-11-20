# -*- coding: utf-8 -*-
"""実写の背景の素材を取ってくる（GitHub Actions の「素材をとる」で動く。手元からは Mixkit に届かないため）。
1. sources.json の各ページを読み、使用許諾の表示を確かめる（Restricted・表示が読めないものは使わない）
2. いちばん大きい mp4（1080 → 720 → ページにある mp4 の順）を落とす
3. 縦 720x1280・最長16秒・音なしに切り出して footage/clips/<id>.mp4 に置く。確かめ用の静止画（3こま）も footage/check/<id>.jpg に
4. footage/manifest.json に結果（許諾の表示・元のURL・大きさ・長さ）を書く。Mixkit の許諾ページの文も footage/mixkit_license.txt に残す
"""
import json, os, re, subprocess, sys, urllib.request, html

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def text_of(h):
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def license_label(page_html):
    t = text_of(page_html)
    labels = re.findall(r"(Mixkit [A-Za-z ]{0,30}?License|Restricted License|Free License)", t)
    restricted = bool(re.search(r"restricted license", t, re.I))
    return sorted(set(labels)), restricted, t


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    s = (j.get("streams") or [{}])[0]
    return s.get("width"), s.get("height"), float((j.get("format") or {}).get("duration") or 0)


def main():
    src = json.load(open(os.path.join(HERE, "sources.json"), encoding="utf-8"))
    os.makedirs(os.path.join(HERE, "clips"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "check"), exist_ok=True)
    tmp = os.path.join(HERE, "_tmp")
    os.makedirs(tmp, exist_ok=True)
    try:
        lic = text_of(get("https://mixkit.co/license/"))
        open(os.path.join(HERE, "mixkit_license.txt"), "w", encoding="utf-8").write(lic[:60000])
    except Exception as ex:
        print("許諾ページが読めません:", ex)
    out = []
    for c in src["clips"]:
        cid, page = c["id"], c["page"]
        rec = {"id": cid, "page": page, "使う": False}
        try:
            h = get(page)
            labels, restricted, t = license_label(h)
            m = re.search(r"<title>(.*?)</title>", h, re.S)
            rec["title"] = html.unescape(m.group(1)).strip()[:120] if m else ""
            rec["許諾の表示"] = labels
            i = t.lower().find("license")
            rec["許諾のまわりの文"] = t[max(0, i - 200): i + 300] if i >= 0 else ""
            kw = re.search(r'name="keywords" content="([^"]*)"', h)
            rec["タグ"] = kw.group(1)[:300] if kw else ""
            mp4s = sorted(set(re.findall(r"https://assets\.mixkit\.co/[^\"'\s<>]+?\.mp4", h)))
            rec["ページのmp4"] = mp4s[:10]
            if restricted or not labels:
                rec["理由"] = "Restricted" if restricted else "許諾の表示が読めない"
                out.append(rec); print(cid, rec["理由"]); continue
            cands = [f"https://assets.mixkit.co/videos/{cid}/{cid}-1080.mp4", f"https://assets.mixkit.co/videos/{cid}/{cid}-720.mp4"]
            cands += [u for u in sorted(mp4s, key=lambda u: -int((re.findall(r"-(\d{3,4})\.mp4", u) or ["0"])[0])) if u not in cands]
            raw = os.path.join(tmp, f"{cid}.mp4")
            for u in cands:
                try:
                    data = get(u, binary=True, timeout=120)
                    if len(data) > 200000:
                        open(raw, "wb").write(data); rec["元のURL"] = u; break
                except Exception:
                    continue
            if "元のURL" not in rec:
                rec["理由"] = "mp4 が落とせない"; out.append(rec); print(cid, rec["理由"]); continue
            w, hh, dur = probe(raw)
            rec.update({"元の幅": w, "元の高さ": hh, "元の長さ": round(dur, 1)})
            if not w or dur < 6 or min(w, hh) < 600:
                rec["理由"] = "短すぎるか小さすぎる"; out.append(rec); print(cid, rec["理由"]); continue
            dst = os.path.join(HERE, "clips", f"{cid}.mp4")
            vf = "scale=-2:1280:flags=lanczos,crop=720:1280,fps=30" if w >= hh * 720 / 1280 else "scale=720:-2:flags=lanczos,crop=720:1280,fps=30"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-t", "16", "-an", "-vf", vf,
                            "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], check=True)
            _, _, d2 = probe(dst)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", dst, "-vf",
                            f"fps=3/{max(d2, 3):.2f},scale=240:-2,tile=3x1", "-frames:v", "1", os.path.join(HERE, "check", f"{cid}.jpg")], check=False)
            rec.update({"使う": True, "長さ": round(d2, 1), "大きさ（KB）": os.path.getsize(dst) // 1024})
            print(cid, "OK", labels, w, hh, round(dur, 1))
        except Exception as ex:
            rec["理由"] = "エラー：" + str(ex)[:200]; print(cid, rec["理由"])
        out.append(rec)
    json.dump({"format": "drone-footage/v1", "source": "Mixkit", "clips": out},
              open(os.path.join(HERE, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = sum(r["使う"] for r in out)
    print(f"使える素材：{ok}/{len(out)}")
    if ok == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
