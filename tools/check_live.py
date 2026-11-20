"""Check the live site after a deploy: every page in the sitemap loads, has its own link-preview card,
and the card is a 1200x630 PNG. Also checks the favicon, RSS feed and redirects for every CVE/GHSA ID.

  python3 tools/check_live.py                 # checks https://tldrcve.com
  python3 tools/check_live.py http://localhost:8787

Exits non-zero if anything is wrong. Python standard library only.
"""
import json, re, struct, sys, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://tldrcve.com").rstrip("/")
UA = {"User-Agent": "Twitterbot/1.0"}  # the preview crawler's view of the page


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url, follow=True):
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, b""


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def main():
    problems, pages = [], 0
    status, _, sitemap = get(f"{BASE}/sitemap.xml")
    urls = re.findall(r"<loc>https://tldrcve\.com([^<]*)</loc>", sitemap.decode())
    if status != 200 or not urls:
        sys.exit(f"sitemap.xml: HTTP {status}, {len(urls)} URLs")
    for path in urls:
        pages += 1
        status, _, body = get(BASE + path)
        html = body.decode(errors="replace")
        if status != 200:
            problems.append(f"{path}: HTTP {status}")
            continue
        m = re.search(r'property="og:image" content="([^"]+)"', html)
        if not m:
            problems.append(f"{path}: no og:image")
            continue
        img = m.group(1).replace("https://tldrcve.com", BASE)
        expected = "default" if path == "/" else path.strip("/")
        if f"/assets/og/{expected}.png" not in img:
            problems.append(f"{path}: card is {img.rsplit('/', 1)[-1]}, expected its own ({expected}.png); run tools/cards.py")
        istatus, _, data = get(img)
        if istatus != 200 or png_size(data) != (1200, 630):
            problems.append(f"{path}: card {img} HTTP {istatus}, size {png_size(data)}")
        for tag in ('name="twitter:card" content="summary_large_image"', 'rel="icon"', 'rel="canonical"'):
            if tag not in html:
                problems.append(f"{path}: missing {tag}")
    for name in ("/favicon.ico", "/assets/icons/icon-32.png", "/assets/icons/apple-touch-icon.png", "/feed.xml"):
        status, headers, _ = get(BASE + name)
        if status != 200:
            problems.append(f"{name}: HTTP {status}")
    for f in sorted((ROOT / "content").glob("*.json")):
        c = json.loads(f.read_text())
        for cid in c["cves"] + c.get("ghsa", []):
            status, headers, _ = get(f"{BASE}/{cid}", follow=False)
            loc = headers.get("Location", "") if headers else ""
            if status != 301 or not loc.rstrip("/").endswith(c["slug"]):
                problems.append(f"/{cid}: HTTP {status} -> {loc or 'nothing'}, expected /{c['slug']}/")
    for p in problems:
        print("FAIL", p)
    print(f"{pages} pages checked, {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
