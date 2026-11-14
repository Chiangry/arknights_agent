import sys, json
from pathlib import Path
import requests
from http.cookiejar import MozillaCookieJar

ROOT = Path(__file__).resolve().parent.parent
cj = MozillaCookieJar(ROOT / "cookies.txt")
cj.load(ignore_discard=True, ignore_expires=True)
s = requests.Session()
s.cookies = cj
s.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"})

bvid = "BV1n9uq6NEWu"

# 1. 拿 cid
r = s.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid}, timeout=20)
d = r.json()
print("view code:", d.get("code"), d.get("message"))
cid = d["data"]["cid"]
print("title:", d["data"]["title"], "cid:", cid, "duration:", d["data"]["duration"])

# 2. 官方 player 接口拿字幕列表
for ep in ["https://api.bilibili.com/x/player/wbi/v2", "https://api.bilibili.com/x/player/v2"]:
    try:
        pr = s.get(ep, params={"bvid": bvid, "cid": cid}, timeout=20)
        pd = pr.json()
        print("\n==", ep, "code:", pd.get("code"), pd.get("message"))
        subs = (pd.get("data") or {}).get("subtitle") or {}
        lst = subs.get("subtitles") or []
        print("字幕轨道数:", len(lst))
        for it in lst:
            print("  lan:", it.get("lan"), "| type:", it.get("type"),
                  "| ai_type:", it.get("ai_type"), "| url:", (it.get("subtitle_url") or "")[:80])
    except Exception as e:
        print(ep, "ERR", e)
