# -*- coding: utf-8 -*-
"""「動画台本」シート（公開したCSV）から、受験生向けの無料サイト（GitHub Pages 用）を作る。

使い方
  python site/build.py                          … config.json の csv_url を読んで _site/ に作る
  python site/build.py --csv tests/sample.csv   … 手元のCSVで作る（確認用）
  python site/build.py --out 出力先 --today 2026-10-16

文言・色・リンクは site/site.json にまとめてある。説明は docs/サイト.md。
問題・答え・ひっかけの文は CSV の文だけを使う（このプログラムは問題の中身を書かない）。
"""
import argparse, csv, datetime, html, io, json, os, re, shutil, sys, unicodedata, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

USE_STATES = ("待ち", "投稿済み")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
VIDEO_RE = re.compile(r"^https://(www\.|m\.)?(youtube\.com|youtu\.be)/[^\s\"'<>]+$")
NEEDED = ["問題ID", "タイトル", "問題1行目", "選択肢A", "選択肢B", "選択肢C", "正解", "ひっかけ", "状態"]


# ---------- 読み込み ----------
def jst_now():
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)

def parse_date(s):
    s = str(s or "").strip().replace("/", "-")
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if not m:
        return None
    try:
        return datetime.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None

def read_csv_text(args):
    if args.csv:
        with open(args.csv, encoding="utf-8-sig") as f:
            return f.read()
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    url = os.environ.get("CSV_URL") or cfg.get("csv_url", "")
    if not url.startswith("https://docs.google.com/"):
        raise SystemExit("config.json の csv_url が未設定です。")
    return urllib.request.urlopen(url, timeout=60).read().decode("utf-8-sig")

def load_questions(raw):
    """使う行だけを選び、問題IDが重なったら1つにする。"""
    reader = csv.DictReader(io.StringIO(raw))
    missing = [c for c in NEEDED if c not in (reader.fieldnames or [])]
    if missing:
        raise SystemExit("CSVに必要な列がありません：" + "・".join(missing))
    log = {"行数": 0, "使わない行": 0, "足りない行": [], "重なり": []}
    best = {}
    for r in reader:
        r = {k: str(v or "").strip() for k, v in r.items() if k}
        log["行数"] += 1
        if r.get("状態") not in USE_STATES or "限定公開" in r.get("メモ", ""):
            log["使わない行"] += 1
            continue
        qid = unicodedata.normalize("NFKC", r.get("問題ID", ""))
        ans = unicodedata.normalize("NFKC", r.get("正解", "")).upper()
        if not ID_RE.match(qid) or ans not in ("A", "B", "C") or not all(
                r.get(k) for k in ("タイトル", "問題1行目", "選択肢A", "選択肢B", "選択肢C", "ひっかけ")):
            log["足りない行"].append(r.get("台本ID") or qid or "?")
            continue
        video = r.get("動画URL", "")
        q = {
            "id": qid,
            "title": r["タイトル"],
            "q1": r["問題1行目"],
            "q2": r.get("問題2行目", ""),
            "choices": [r["選択肢A"], r["選択肢B"], r["選択肢C"]],
            "answer": "ABC".index(ans),
            "trap": r["ひっかけ"],
            "date": parse_date(r.get("公開予定日")),
            "video": video if VIDEO_RE.match(video) else "",
            "posted": r.get("状態") == "投稿済み",
            "kaisetsu": clean_kaisetsu(r.get("解説", "")),
            "basis": r.get("根拠", "").strip(),
        }
        if qid in best:
            log["重なり"].append(qid)
            if rank(q) >= rank(best[qid]):
                continue
        best[qid] = q
    return list(best.values()), log

EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")

def clean_kaisetsu(s):
    """Xの答え合わせの文（クイズDB の X_Post2）を、サイト用の解説の行にする。
    1行目の「正解X：…」（記号の並びがサイトと違うことがある）と、note・プロフィールへの誘導の行は外す。"""
    out = []
    for line in str(s or "").replace("\r", "").split("\n"):
        line = EMOJI_RE.sub("", line).strip()
        if not line or re.match(r"^正解\s*[A-CＡ-Ｃ](?![A-Za-z])", line) or re.search(r"note|ノート|プロフ", line, re.I):
            continue
        out.append(line)
    return out

def rank(q):
    """問題IDが重なったときの優先順（小さいほど優先）：動画がある → 投稿済み → 公開予定日が早い"""
    return (not q["video"], not q["posted"], q["date"] or datetime.date.max)


# ---------- 文字の加工 ----------
def esc(s):
    return html.escape(str(s), quote=True)

def rich(s):
    """*で囲んだ所を強調にしたHTML（ほかの記号はすべてエスケープ）"""
    out, on = [], False
    for part in str(s).split("*"):
        if part:
            out.append(f'<strong class="em">{esc(part)}</strong>' if on else esc(part))
        on = not on
    return "".join(out)

def plain(s):
    return str(s).replace("*", "")

def fill(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl

def jdate(d):
    return f"{d.year}年{d.month}月{d.day}日"


# ---------- 見た目 ----------
def css(c):
    return f"""
:root{{color-scheme:light}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:{c['bg']};color:{c['text']};font-family:system-ui,-apple-system,"Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic UI",Meiryo,sans-serif;font-size:17px;line-height:1.7;overflow-wrap:anywhere}}
a{{color:{c['primary']}}}
.wrap{{max-width:640px;margin:0 auto;padding:0 16px}}
header.top{{background:{c['primary']};color:{c['primary_text']}}}
header.top .wrap{{display:flex;align-items:center;min-height:52px}}
header.top a{{color:{c['primary_text']};text-decoration:none;font-weight:700;font-size:18px}}
header.top a::before{{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;background:{c['accent']};margin-right:8px;vertical-align:1px}}
main{{padding:20px 0 32px}}
h1{{font-size:24px;line-height:1.4;margin:0 0 12px}}
h2{{font-size:19px;line-height:1.4;margin:28px 0 10px}}
p{{margin:0 0 12px}}
.lead{{color:{c['muted']}}}
.card{{background:{c['card']};border:1px solid {c['border']};border-radius:12px;padding:16px;margin:0 0 16px}}
.btn{{display:block;width:100%;text-align:center;padding:14px 16px;border-radius:12px;font-weight:700;font-size:17px;text-decoration:none;border:0;cursor:pointer;font-family:inherit;line-height:1.4}}
.btn-main{{background:{c['accent']};color:{c['accent_text']}}}
.btn-sub{{background:{c['primary']};color:{c['primary_text']}}}
.btn-line{{background:{c['card']};color:{c['primary']};border:2px solid {c['primary']}}}
.btn+.btn{{margin-top:10px}}
.em{{background:linear-gradient(transparent 55%,{c['em_bg']} 55%);font-weight:700}}
.label{{display:inline-block;font-size:13px;font-weight:700;color:{c['muted']};letter-spacing:.05em;margin-bottom:4px}}
.q{{font-size:19px;font-weight:700;line-height:1.6}}
.q span{{display:block}}
ol.choices{{list-style:none;padding:0;margin:14px 0 0}}
ol.choices li{{margin:0 0 10px}}
.choice{{display:flex;align-items:flex-start;gap:12px;width:100%;text-align:left;padding:12px 14px;border:2px solid {c['border']};border-radius:12px;background:{c['card']};color:{c['text']};font:inherit;line-height:1.5}}
button.choice{{cursor:pointer}}
.choice .k{{flex:none;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:{c['primary']};color:{c['primary_text']};font-weight:700;font-size:15px}}
.choice.ok{{border-color:{c['ok']};background:{c['ok_bg']}}}
.choice.ok .k{{background:{c['ok']}}}
.choice.ng{{border-color:{c['ng']};background:{c['ng_bg']}}}
.choice.ng .k{{background:{c['ng']}}}
button.choice:disabled{{cursor:default;opacity:1}}
details.reveal{{margin-top:6px}}
details.reveal summary{{list-style:none;cursor:pointer}}
details.reveal summary::-webkit-details-marker{{display:none}}
details.reveal[open] summary{{display:none}}
.answer{{border-radius:12px;padding:14px;margin-top:10px;background:{c['bg']};border:1px solid {c['border']}}}
.answer .res{{font-weight:700;font-size:19px;margin:0 0 6px}}
.answer .res.ok{{color:{c['ok']}}}
.answer .res.ng{{color:{c['ng']}}}
.trap{{margin:8px 0 0}}
.basis{{margin:10px 0 0;font-size:13px;color:{c['muted']}}}
table.plan{{width:100%;border-collapse:collapse;font-size:15px;line-height:1.55}}
table.plan th,table.plan td{{text-align:left;vertical-align:top;padding:8px 6px;border-bottom:1px solid {c['border']}}}
table.plan th{{white-space:nowrap;color:{c['muted']};font-weight:700;width:6.5em}}
ul.ex{{margin:6px 0 0;padding-left:1.2em}}
ul.ex li{{margin:0 0 6px}}
ul.list{{list-style:none;padding:0;margin:0;background:{c['card']};border:1px solid {c['border']};border-radius:12px;overflow:hidden}}
ul.list li+li{{border-top:1px solid {c['border']}}}
ul.list a{{display:block;padding:12px 14px;text-decoration:none;color:{c['text']}}}
ul.list a small{{display:block;color:{c['muted']};font-size:13px}}
ul.list a b{{font-weight:700}}
.more{{display:block;text-align:right;margin-top:8px;font-size:15px}}
.note{{border-left:6px solid {c['accent']}}}
.progress{{font-weight:700;color:{c['muted']};font-size:15px;margin-bottom:6px}}
.bar{{height:6px;border-radius:3px;background:{c['border']};margin-bottom:14px;overflow:hidden}}
.bar i{{display:block;height:100%;background:{c['accent']}}}
.score{{font-size:32px;font-weight:800;text-align:center;margin:6px 0 4px}}
.center{{text-align:center}}
.short{{margin-top:6px}}
footer{{border-top:1px solid {c['border']};color:{c['muted']};font-size:13px;line-height:1.6;padding:18px 0 32px}}
footer p{{margin:0 0 8px}}
footer nav a{{margin-right:14px}}
.hide{{display:none}}
:focus-visible{{outline:3px solid {c['accent']};outline-offset:2px}}
"""

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='6' fill='%2313213c'/%3E%3Crect x='9' y='9' width='14' height='14' rx='2' fill='%23ffc400'/%3E%3C/svg%3E")
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; "
       "base-uri 'none'; form-action 'none'")


class Site:
    def __init__(self, cfg, questions, today, out):
        self.cfg, self.t, self.links = cfg, cfg["texts"], cfg["links"]
        self.url = cfg["site_url"].rstrip("/") + "/"
        self.today, self.out = today, out
        self.css = css(cfg["colors"])
        # 公開予定日が今日までのものを新しい順に、そのあとにこれからのものを近い順に
        past = [q for q in questions if not q["date"] or q["date"] <= today]
        future = [q for q in questions if q["date"] and q["date"] > today]
        past.sort(key=lambda q: (q["date"] or datetime.date.min, q["id"]), reverse=True)
        future.sort(key=lambda q: (q["date"], q["id"]))
        self.qs, self.past = past + future, past
        self.og_ok = set()
        kp = os.path.join(HERE, "kijou.json")
        self.kijou_data = json.load(open(kp, encoding="utf-8")) if os.path.exists(kp) else None
        self.has_kijou = False

    # --- 共通の枠 ---
    def page(self, path, title, desc, body, og, script=""):
        depth = path.count("/")
        root = "../" * depth
        name = self.cfg["site_name"]
        head_title = name if not title else f"{title}｜{name}"
        canon = self.url + path
        og_url = self.url + og
        footer = (
            f'<footer><div class="wrap"><p>{esc(self.t["footer_source"])}</p>'
            f'<p>{esc(fill(self.t["footer_updated"], date=jdate(self.today)))}</p>'
            f'<nav><a href="{root or "./"}">{esc(self.t["back_home"])}</a>'
            f'<a href="{root}q/">{esc(self.t["all_heading"])}</a>'
            f'<a href="{esc(self.links["x"])}" rel="noopener">X</a>'
            f'<a href="{esc(self.links["note"])}" rel="noopener">note</a></nav></div></footer>')
        doc = f"""<!doctype html>
<html lang="{esc(self.cfg.get('lang', 'ja'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{esc(head_title)}</title>
<meta name="description" content="{esc(desc)}">
{'<meta name="robots" content="noindex">' if path == "404.html" else f'<link rel="canonical" href="{esc(canon)}">'}
<link rel="icon" href="{FAVICON}">
<meta name="theme-color" content="{esc(self.cfg['colors']['primary'])}">
<meta property="og:type" content="{'website' if path == '' else 'article'}">
<meta property="og:site_name" content="{esc(name)}">
<meta property="og:locale" content="ja_JP">
<meta property="og:title" content="{esc(head_title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:image" content="{esc(og_url)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<style>{self.css}</style>
</head>
<body>
<header class="top"><div class="wrap"><a href="{root or './'}">{esc(name)}</a></div></header>
<main><div class="wrap">
{body}
</div></main>
{footer}
{script}
</body>
</html>
"""
        p = os.path.join(self.out, path, "index.html") if not path.endswith(".html") else os.path.join(self.out, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(doc)

    def note_box(self):
        t = self.t
        return (f'<section class="card note"><h2 style="margin-top:0">{esc(t["note_heading"])}</h2>'
                f'<p>{esc(t["note_text"])}</p>'
                f'<a class="btn btn-sub" href="{esc(self.links["note"])}" rel="noopener">{esc(t["note_label"])}</a></section>')

    def qtext(self, q):
        s = f'<span>{rich(q["q1"])}</span>'
        if q["q2"]:
            s += f'<span>{rich(q["q2"])}</span>'
        return s

    def item(self, q, root):
        d = ""
        if q["date"]:
            d = jdate(q["date"]) + ("" if q["date"] <= self.today else " " + self.t["planned_badge"])
            d = f"<small>{esc(d)}</small>"
        return f'<li><a href="{root}q/{esc(q["id"])}/">{d}<b>{esc(plain(q["title"]))}</b></a></li>'

    def og_path(self, q):
        return f"og/q/{q['id']}.png" if q["id"] in self.og_ok else "og/site.png"

    # --- 各ページ ---
    def home(self):
        t = self.t
        latest = (self.past or self.qs)[: int(self.cfg.get("latest_count", 10))]
        body = f"""<h1>{esc(t['tagline'])}</h1>
<p class="lead">{esc(t['intro'])}</p>
<a class="btn btn-main" href="quiz/">{esc(t['start_quiz'])}</a>
{f'<a class="btn btn-line" href="kijou/">{esc(t["kijou_link"])}</a>' if self.kijou_data else ''}
<h2>{esc(t['latest_heading'])}</h2>
<ul class="list">{''.join(self.item(q, '') for q in latest)}</ul>
<a class="more" href="q/">{esc(t['all_heading'])}（{len(self.qs)}問）</a>
<h2>{esc(t['follow_heading'])}</h2>
<p>{esc(t['follow_text'])}</p>
<a class="btn btn-line" href="{esc(self.links['x'])}" rel="noopener">{esc(t['x_label'])}</a>
<div style="height:16px"></div>
{self.note_box()}"""
        self.page("", "", t["home_description"], body, "og/site.png")

    def all_list(self):
        t = self.t
        body = (f'<h1>{esc(t["all_heading"])}</h1><p class="lead">{len(self.qs)}問</p>'
                f'<a class="btn btn-main" href="../quiz/">{esc(t["start_quiz"])}</a><div style="height:16px"></div>'
                f'<ul class="list">{"".join(self.item(q, "../") for q in self.qs)}</ul>')
        self.page("q/", t["all_heading"], t["home_description"], body, "og/site.png")

    def question(self, i, q):
        t = self.t
        L = "ABC"
        choices = "".join(
            f'<li><button type="button" class="choice" data-i="{k}"><span class="k">{L[k]}</span><span>{rich(c)}</span></button></li>'
            for k, c in enumerate(q["choices"]))
        if q["video"]:
            short = f'<a class="btn btn-sub" href="{esc(q["video"])}" rel="noopener">{esc(t["short_link"])}</a>'
        elif q["date"] and q["date"] > self.today:
            short = f'<p>{esc(fill(t["short_planned"], date=jdate(q["date"])))}</p>'
        else:
            short = f'<p>{esc(t["short_unknown"])}</p>'
        n = int(self.cfg.get("others_count", 5))
        others = [self.qs[(i + k) % len(self.qs)] for k in range(1, min(n, len(self.qs) - 1) + 1)]
        body = f"""<h1>{esc(plain(q['title']))}</h1>
<section class="card">
<div class="label">{esc(t['question_label'])}</div>
<div class="q">{self.qtext(q)}</div>
<ol class="choices" id="choices">{choices}</ol>
<details class="reveal" id="reveal"><summary class="btn btn-main">{esc(t['show_answer'])}</summary>
<div class="answer" id="answer" tabindex="-1"><p class="res" id="res"></p>
<p><b>{esc(t['answer_label'])}：{L[q['answer']]}</b>　{rich(q['choices'][q['answer']])}</p>
<p class="trap"><span class="label">{esc(t['trap_label'])}</span><br>{rich(q['trap'])}</p>{self.extra(q)}</div></details>
</section>
<h2>{esc(t['short_heading'])}</h2>
<div class="short">{short}</div>
<a class="btn btn-main" style="margin-top:20px" href="../../quiz/">{esc(t['start_quiz'])}</a>
<h2>{esc(t['others_heading'])}</h2>
<ul class="list">{''.join(self.item(o, '../../') for o in others)}</ul>
<a class="more" href="../">{esc(t['all_heading'])}</a>
<div style="height:16px"></div>
{self.note_box()}"""
        script = f"""<script>
(function(){{var A={q['answer']},L="ABC",bs=document.querySelectorAll("#choices .choice"),d=document.getElementById("reveal"),r=document.getElementById("res");
for(var i=0;i<bs.length;i++)bs[i].addEventListener("click",function(){{var k=+this.getAttribute("data-i");
for(var j=0;j<bs.length;j++){{bs[j].disabled=true;if(j===A)bs[j].classList.add("ok");else if(j===k)bs[j].classList.add("ng");}}
r.className="res "+(k===A?"ok":"ng");r.textContent=k===A?{json.dumps(t['quiz_correct'], ensure_ascii=False)}:{json.dumps(t['quiz_wrong'], ensure_ascii=False)};d.open=true;document.getElementById("answer").focus({{preventScroll:true}});}});
d.addEventListener("toggle",function(){{if(d.open)for(var j=0;j<bs.length;j++){{bs[j].disabled=true;if(j===A)bs[j].classList.add("ok");}}}});}})();
</script>"""
        desc = fill(t["question_description"], title=plain(q["title"]))
        self.page(f"q/{q['id']}/", plain(q["title"]), desc, body, self.og_path(q), script)

    def extra(self, q):
        """解説と根拠（シートに列があるときだけ）"""
        t, out = self.t, ""
        if q.get("kaisetsu"):
            out += f'<p class="trap"><span class="label">{esc(t["kaisetsu_label"])}</span><br>{"<br>".join(esc(l) for l in q["kaisetsu"])}</p>'
        if q.get("basis"):
            out += f'<p class="basis">{esc(t["basis_label"])}：{esc(t["basis_prefix"])} {esc(q["basis"])}</p>'
        return out

    def quiz(self):
        t = self.t
        size = int(self.cfg.get("quiz_size", 10))
        total = min(size, len(self.qs))
        data = [{"id": q["id"], "title": plain(q["title"]), "q": self.qtext(q), "c": [rich(c) for c in q["choices"]],
                 "a": q["answer"], "trap": rich(q["trap"]), "x": self.extra(q)} for q in self.qs]
        js_data = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        texts = {k: t[k] for k in ("quiz_next", "quiz_finish", "quiz_correct", "quiz_wrong", "quiz_answer_is", "quiz_score",
                                   "quiz_all_correct", "trap_label", "share_text")}
        js_texts = json.dumps(texts, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        share = json.dumps({"base": self.links["share_base"], "url": self.url})
        body = f"""<h1>{esc(t['quiz_title'])}</h1>
<p class="lead" id="lead">{esc(fill(t['quiz_lead'], total=total))}</p>
<noscript><p class="card">{esc(t['quiz_noscript'])}</p><a class="btn btn-sub" href="../q/">{esc(t['all_heading'])}</a></noscript>
<section id="play" class="hide">
<div class="progress" id="prog"></div>
<div class="bar"><i id="barfill" style="width:0"></i></div>
<div class="card">
<div class="label" id="qtitle"></div>
<div class="q" id="qtext"></div>
<ol class="choices" id="qchoices"></ol>
<div class="answer hide" id="fb" tabindex="-1"><p class="res" id="fbres"></p><p id="fbans"></p>
<p class="trap"><span class="label">{esc(t['trap_label'])}</span><br><span id="fbtrap"></span></p><div id="fbx"></div></div>
</div>
<button type="button" class="btn btn-main hide" id="next"></button>
</section>
<section id="result" class="hide" tabindex="-1">
<h2 style="margin-top:0">{esc(t['quiz_result_heading'])}</h2>
<div class="card center"><div class="score" id="score"></div><p id="scoremsg" class="lead" style="margin:0"></p></div>
<a class="btn btn-main" id="share" href="#" rel="noopener">{esc(t['share_label'])}</a>
<button type="button" class="btn btn-line" id="retry">{esc(t['quiz_retry'])}</button>
<div id="missedbox"><h2>{esc(t['quiz_missed_heading'])}</h2><ul class="list" id="missed"></ul></div>
<div style="height:16px"></div>
{self.note_box()}
</section>"""
        script = f"""<script>
(function(){{
var Q={js_data},T={js_texts},S={share},N={size},L="ABC";
var $=function(id){{return document.getElementById(id)}};
function f(s,o){{for(var k in o)s=s.split("{{"+k+"}}").join(o[k]);return s}}
var set,i,score,missed;
function start(){{
  set=Q.slice();for(var k=set.length-1;k>0;k--){{var j=Math.floor(Math.random()*(k+1)),x=set[k];set[k]=set[j];set[j]=x}}
  set=set.slice(0,Math.min(N,set.length));i=0;score=0;missed=[];
  $("result").classList.add("hide");$("play").classList.remove("hide");show();
}}
function show(){{
  var q=set[i];
  $("prog").textContent="第"+(i+1)+"問 / "+set.length+"問";
  $("barfill").style.width=(i/set.length*100)+"%";
  $("qtitle").textContent=q.title;$("qtext").innerHTML=q.q;
  var ol=$("qchoices");ol.innerHTML="";
  q.c.forEach(function(c,k){{var li=document.createElement("li"),b=document.createElement("button");
    b.type="button";b.className="choice";b.innerHTML='<span class="k">'+L[k]+'</span><span>'+c+'</span>';
    b.addEventListener("click",function(){{answer(k)}});li.appendChild(b);ol.appendChild(li)}});
  $("fb").classList.add("hide");$("next").classList.add("hide");
  window.scrollTo(0,0);
}}
function answer(k){{
  var q=set[i],bs=$("qchoices").querySelectorAll(".choice"),ok=k===q.a;
  for(var j=0;j<bs.length;j++){{bs[j].disabled=true;if(j===q.a)bs[j].classList.add("ok");else if(j===k)bs[j].classList.add("ng")}}
  if(ok)score++;else missed.push(q);
  $("fbres").className="res "+(ok?"ok":"ng");$("fbres").textContent=ok?T.quiz_correct:T.quiz_wrong;
  $("fbans").innerHTML="<b>"+f(T.quiz_answer_is,{{letter:L[q.a]}})+"</b>　"+q.c[q.a];
  $("fbtrap").innerHTML=q.trap;$("fbx").innerHTML=q.x||"";
  $("fb").classList.remove("hide");
  $("barfill").style.width=((i+1)/set.length*100)+"%";
  var nx=$("next");nx.textContent=i+1<set.length?T.quiz_next:T.quiz_finish;nx.classList.remove("hide");
  $("fb").focus({{preventScroll:true}});$("fb").scrollIntoView({{behavior:"smooth",block:"nearest"}});
}}
function finish(){{
  $("play").classList.add("hide");$("result").classList.remove("hide");
  $("score").textContent=f(T.quiz_score,{{total:set.length,n:score}});
  $("scoremsg").textContent=score===set.length?T.quiz_all_correct:"";
  var text=f(T.share_text,{{total:set.length,n:score}});
  $("share").href=S.base+"?text="+encodeURIComponent(text)+"&url="+encodeURIComponent(S.url);
  var ul=$("missed");ul.innerHTML="";
  missed.forEach(function(q){{var li=document.createElement("li"),a=document.createElement("a");
    a.href="../q/"+q.id+"/";var b=document.createElement("b");b.textContent=q.title;a.appendChild(b);li.appendChild(a);ul.appendChild(li)}});
  $("missedbox").classList.toggle("hide",missed.length===0);
  window.scrollTo(0,0);$("result").focus({{preventScroll:true}});
}}
$("next").addEventListener("click",function(){{i++;if(i<set.length)show();else finish()}});
$("retry").addEventListener("click",start);
start();
}})();
</script>"""
        self.page("quiz/", t["quiz_title"], t["quiz_description"], body, "og/quiz.png", script)

    def kijou(self, k):
        """机上試験の練習問題（site/kijou.json があるときだけ）。表を読んで4択に答え、その場で正解と解説を出す"""
        t = self.t
        M = "①②③④"
        rows = "".join(f"<tr><th>{esc(a)}</th><td>{esc(b)}</td></tr>" for a, b in k["plan"])
        qs = ""
        for n, q in enumerate(k["questions"], 1):
            ch = "".join(f'<li><button type="button" class="choice" data-i="{j}"><span class="k">{M[j]}</span><span>{esc(c)}</span></button></li>'
                         for j, c in enumerate(q["c"]))
            ex = "".join(f"<li>{esc(e)}</li>" for e in q["ex"])
            qs += f"""<section class="card kq" data-a="{int(q['a'])}">
<div class="label">{esc(fill(t['kijou_q_label'], n=n))}</div>
<div class="q" style="font-size:17px">{esc(q['q'])}</div>
<ol class="choices">{ch}</ol>
<details class="reveal"><summary class="btn btn-main">{esc(t['show_answer'])}</summary>
<div class="answer" tabindex="-1"><p class="res"></p><p><b>{esc(t['answer_label'])}：{M[int(q['a'])]}</b></p><ul class="ex">{ex}</ul></div></details>
</section>"""
        body = f"""<h1>{esc(k['title'])}</h1>
<p class="lead">{esc(k['lead'])}</p>
<section class="card"><div class="label">{esc(t['kijou_plan_label'])}</div><table class="plan">{rows}</table></section>
{qs}
<section class="card note"><h2 style="margin-top:0">{esc(k['paid_heading'])}</h2><p>{esc(k['paid_text'])}</p>
<a class="btn btn-line" href="{esc(self.links['x'])}" rel="noopener">{esc(t['x_label'])}</a></section>
<a class="btn btn-main" href="../quiz/">{esc(t['start_quiz'])}</a>"""
        script = f"""<script>
(function(){{var ok={json.dumps(t['quiz_correct'], ensure_ascii=False)},ng={json.dumps(t['quiz_wrong'], ensure_ascii=False)};
document.querySelectorAll(".kq").forEach(function(sec){{var A=+sec.getAttribute("data-a"),bs=sec.querySelectorAll(".choice"),d=sec.querySelector("details"),r=sec.querySelector(".res");
function lock(){{for(var j=0;j<bs.length;j++){{bs[j].disabled=true;if(j===A)bs[j].classList.add("ok");}}}}
bs.forEach(function(b){{b.addEventListener("click",function(){{var k=+b.getAttribute("data-i");lock();if(k!==A)b.classList.add("ng");
r.className="res "+(k===A?"ok":"ng");r.textContent=k===A?ok:ng;d.open=true;sec.querySelector(".answer").focus({{preventScroll:true}});}});}});
d.addEventListener("toggle",function(){{if(d.open)lock();}});}});}})();
</script>"""
        self.page("kijou/", k["title"], k["lead"], body, "og/site.png", script)
        self.has_kijou = True

    def not_found(self):
        t = self.t
        body = (f'<h1>{esc(t["not_found_title"])}</h1><p>{esc(t["not_found_text"])}</p>'
                f'<a class="btn btn-main" href="{esc(self.url)}">{esc(t["back_home"])}</a>')
        # 404 はどの深さでも出るので、リンクはすべて絶対URLにする
        self.page("404.html", t["not_found_title"], t["not_found_text"], body, "og/site.png")
        p = os.path.join(self.out, "404.html")
        s = open(p, encoding="utf-8").read().replace('href="./"', f'href="{esc(self.url)}"').replace('href="q/"', f'href="{esc(self.url)}q/"')
        open(p, "w", encoding="utf-8").write(s)

    def seo_files(self):
        d = self.today.isoformat()
        urls = [(self.url, d), (self.url + "quiz/", d), (self.url + "q/", d)] + ([(self.url + "kijou/", d)] if self.has_kijou else []) + [(self.url + f"q/{q['id']}/", None) for q in self.qs]
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for u, lm in urls:
            xml.append(f"<url><loc>{esc(u)}</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") + "</url>")
        xml.append("</urlset>")
        open(os.path.join(self.out, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(xml) + "\n")
        open(os.path.join(self.out, "robots.txt"), "w", encoding="utf-8").write(
            f"User-agent: *\nAllow: /\n\nSitemap: {self.url}sitemap.xml\n")
        open(os.path.join(self.out, ".nojekyll"), "w").close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="手元のCSVファイル（指定しないと config.json の csv_url を読む）")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--today", help="日付を決めて作る（確認用）YYYY-MM-DD")
    ap.add_argument("--no-images", action="store_true", help="共有画像を作らない（確認用）")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, "site.json"), encoding="utf-8"))
    if os.environ.get("SITE_URL"):
        cfg["site_url"] = os.environ["SITE_URL"]
    today = datetime.date.fromisoformat(args.today) if args.today else jst_now().date()

    questions, log = load_questions(read_csv_text(args))
    print(f"CSV {log['行数']}行 → 使う問題 {len(questions)}問（使わない行 {log['使わない行']}・"
          f"足りない行 {len(log['足りない行'])}・重なり {len(log['重なり'])}）")
    if log["足りない行"]:
        print("  足りない行：", "、".join(log["足りない行"]))
    if log["重なり"]:
        print("  重なった問題ID：", "、".join(sorted(set(log["重なり"]))))
    if os.environ.get("GITHUB_ACTIONS"):
        # Actions の実行結果の画面に1行で出す（あとから「どの問題に動画が付いたか」を確かめるため）
        with_video = sorted((q["id"] for q in questions if q["video"]), key=lambda s: (len(s), s))
        print(f"::notice title=サイトの中身::使う問題 {len(questions)}問・動画リンクあり "
              f"{len(with_video)}問（問題ID {'、'.join(with_video) or 'なし'}）")
    if not questions:
        raise SystemExit("使える問題が1問もありません。公開中のサイトはそのままにします。")

    out = os.path.abspath(args.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    site = Site(cfg, questions, today, out)
    if not args.no_images:
        import og
        site.og_ok = og.make_all(cfg, site.qs, out)
    site.home()
    site.all_list()
    site.quiz()
    if site.kijou_data:
        site.kijou(site.kijou_data)
    for i, q in enumerate(site.qs):
        site.question(i, q)
    site.not_found()
    site.seo_files()
    print("作成：", out, f"（問題ページ {len(site.qs)}・共有画像 {len(site.og_ok)}）")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()
