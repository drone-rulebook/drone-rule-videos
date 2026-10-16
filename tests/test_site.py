# -*- coding: utf-8 -*-
"""見本CSV（tests/sample.csv）でサイトを作り、決まりどおりにできているかを確かめる。

  python tests/test_site.py
"""
import json, os, re, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = tempfile.mkdtemp(prefix="site-test-")
ALLOWED_HOSTS = ("x.com", "note.com", "youtube.com", "www.youtube.com", "youtu.be", "drone-rulebook.github.io",
                 "www.sitemaps.org", "www.w3.org")


def read(*p):
    with open(os.path.join(OUT, *p), encoding="utf-8") as f:
        return f.read()


def readp(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class SiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([sys.executable, os.path.join(ROOT, "site", "build.py"), "--csv", os.path.join(ROOT, "tests", "sample.csv"),
                        "--out", OUT, "--today", "2026-10-16"], check=True)
        cls.pages = []
        for d, _, files in os.walk(OUT):
            cls.pages += [os.path.join(d, f) for f in files if f.endswith(".html")]

    def test_使う行だけ(self):
        ids = sorted(os.listdir(os.path.join(OUT, "q")))
        self.assertEqual(ids, ["Q001", "Q002", "Q006", "Q007", "Q008", "Q009", "Q010", "Q011", "Q012", "Q013", "Q016", "index.html"])
        for bad in ("Q099", "Q098", "出てはいけない"):  # 限定公開・停止
            for p in self.pages:
                self.assertNotIn(bad, readp(p), p)

    def test_重なりは動画のある行(self):
        s = read("q", "Q002", "index.html")
        self.assertIn("https://youtu.be/sample0002", s)
        self.assertNotIn("重なった行", s)

    def test_記号はそのまま文字として出る(self):
        s = read("q", "Q006", "index.html")
        self.assertNotIn("<script>alert", s)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", s)
        self.assertNotIn("javascript:", s)
        self.assertIn("ショート動画は準備中です", s)  # 変なURLは使わない

    def test_強調(self):
        self.assertIn('150mは<strong class="em">どこから</strong>測る？', read("q", "Q001", "index.html"))

    def test_ショートの予定日(self):
        self.assertIn("2026年10月17日 に公開予定", read("q", "Q008", "index.html"))

    def test_ミニ模試のデータと正解(self):
        s = read("quiz", "index.html")
        data = json.loads(re.search(r"var Q=(\[.*?\]),T=", s).group(1))
        ans = {d["id"]: d["a"] for d in data}
        self.assertEqual(ans["Q001"], 1)
        self.assertEqual(ans["Q013"], 2)  # 小文字の c も C として読む
        self.assertEqual(len(data), 11)
        self.assertIn("N=10", s)

    def test_外のものを読み込まない(self):
        for p in self.pages:
            s = readp(p)
            self.assertNotRegex(s, r"<script[^>]+src=", p)
            self.assertNotRegex(s, r"<link[^>]+stylesheet", p)
            self.assertNotRegex(s, r"<(input|form|iframe|img)\b", p)
            self.assertNotIn("cookie", s.lower(), p)
            for host in re.findall(r"https?://([^/\"'\s?]+)", s):
                self.assertIn(host, ALLOWED_HOSTS, p)

    def test_足もとと説明文(self):
        for p in self.pages:
            s = readp(p)
            self.assertIn("国土交通省『無人航空機の飛行の安全に関する教則』（第5版）にもとづいて作成", s, p)
            self.assertIn("最終更新日：2026年10月16日", s, p)
            self.assertRegex(s, r'<meta name="description" content="[^"]{20,}">', p)
            self.assertRegex(s, r'<meta property="og:image" content="https://[^"]+\.png">', p)

    def test_画像と地図(self):
        from PIL import Image
        for name in ("site.png", "quiz.png", os.path.join("q", "Q001.png")):
            self.assertEqual(Image.open(os.path.join(OUT, "og", name)).size, (1200, 630))
        self.assertFalse(os.path.exists(os.path.join(OUT, "og", "q", "Q016.png")))  # フォントに無い文字 → 共通の画像
        self.assertIn('content="https://drone-rulebook.github.io/drone-rule-videos/og/site.png"', read("q", "Q016", "index.html"))
        sm = read("sitemap.xml")
        self.assertEqual(sm.count("<loc>"), 3 + 11)
        self.assertIn("Sitemap: https://drone-rulebook.github.io/drone-rule-videos/sitemap.xml", read("robots.txt"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
