# -*- coding: utf-8 -*-
"""英語版の見本をつくる（一時的。en-sample ブランチだけ）。声の結果も表示する。"""
import csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render

out = sys.argv[1] if len(sys.argv) > 1 else "en_samples"
os.makedirs(out, exist_ok=True)
th = render.load_theme()
for r in csv.DictReader(open("en_sample.csv", encoding="utf-8")):
    vid = r["台本ID"]
    sc, why = render.script_of(r)
    if sc is None:
        print("skip", vid, why)
        continue
    style = render.choose_look(vid, th, r)
    info = {}
    render.render(sc, os.path.join(out, f"{vid}_{style}.mp4"), th, style, info)
    render.contact_sheet(sc, th, style, os.path.join(out, f"{vid}_{style}.png"))
    print(vid, style, info)
