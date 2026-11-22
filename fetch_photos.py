#!/usr/bin/env python3
"""Nordic Trip Commons photo LINK finder (hotlink version, no image downloads).

- Only queries the Wikimedia Commons API: no image files are downloaded,
  so there are far fewer requests and far less chance of HTTP 429.
- Writes the photo URL + author + license for each location into
  PHOTO_CREDITS.json (same file as before; new "url" field).
- index.html reads PHOTO_CREDITS.json and shows each photo by its URL.
- Optional exact Commons filenames in PHOTO_OVERRIDES.json always win.
- Keeps previous results that already have a URL, unless an override changes.
Python 3.10+, standard library only (Pillow no longer needed).
"""
from __future__ import annotations
import json
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUERIES = {
    'vienna-stephansdom': 'Stephansdom Vienna cathedral',
    'vienna-am-hof-christmas': 'Am Hof Christmas market Vienna',
    'vienna-freyung-christmas': 'Freyung Christmas market Vienna',
    'vienna-stephansplatz-christmas': 'Stephansplatz Christmas market Vienna',
    'vienna-karlskirche': 'Karlskirche Vienna church',
    'vienna-rathausplatz-christmas': 'Rathausplatz Christmas market Vienna',
    'helsinki-senate-square': 'Senate Square Helsinki',
    'helsinki-uspenski-cathedral': 'Uspenski Cathedral Helsinki',
    'helsinki-cathedral': 'Helsinki Cathedral',
    'helsinki-old-market-hall': 'Old Market Hall Helsinki',
    'rovaniemi-santa-claus-village': 'Santa Claus Village Rovaniemi',
    'levi-christmas-market': 'Levi Christmas market Sirkka Finland',
    'levi-zero-point': 'Levi Zero Point ski resort Finland',
    'levi-panorama': 'Levi Hotel Panorama Sirkka Finland',
    'rovaniemi-arktikum': 'Arktikum Rovaniemi',
    'helsinki-loyly': 'Loyly Helsinki sauna building',
    'stockholm-city-hall': 'Stockholm City Hall',
    'stockholm-gamla-stan': 'Gamla Stan Stockholm',
    'stockholm-stortorget-christmas': 'Stortorget Christmas Market Stockholm',
    'stockholm-vasa-museum': 'Vasa Museum Stockholm ship',
    'stockholm-skansen': 'Skansen Stockholm Christmas market',
    'oslo-opera-house': 'Oslo Opera House',
    'oslo-karl-johans-gate': 'Karl Johans gate Oslo',
    'bergen-bryggen': 'Bryggen Bergen',
    'bergen-fish-market': 'Bergen Fish Market',
    'bergen-floibanen': 'Floibanen Bergen',
    'bergen-christmas-market': 'Bergen Christmas market Festplassen',
    'vienna-schonbrunn-christmas': 'Schonbrunn Palace Christmas market Vienna',
    'taoyuan-airport': 'Taoyuan International Airport terminal',
    'vienna-airport': 'Vienna International Airport terminal',
    'vienna-hotel-korotan': 'Hotel Korotan Vienna',
    'vienna-steffl': 'Steffl Kärntner Straße Vienna',
    'vienna-verde': 'Wallnerstraße Wien',
    'helsinki-airport': 'Helsinki Airport Vantaa terminal',
    'helsinki-central-station': 'Helsinki Central railway station',
    'helsinki-esplanadi': 'Esplanadi park Helsinki',
    'vr-night-train': 'VR Santa Claus Express sleeping car',
    'rovaniemi-railway-station': 'Rovaniemi railway station',
    'rovaniemi-santas-hotel': "Santa's Hotel Santa Claus Rovaniemi",
    'rovaniemi-salmon-place': "Santa's Salmon Place Rovaniemi",
    'rovaniemi-maakuntakatu': 'Maakuntakatu Rovaniemi',
    'rovaniemi-koskikatu': 'Koskikatu Rovaniemi',
    'rovaniemi-bus-station': 'Rovaniemi bus station',
    'levi-village': 'Levi Sirkka village Kittilä',
    'levi-sirkantahti': 'Lapland Hotels Sirkantähti Levi',
    'lapland-reindeer-sledge': 'reindeer sledge Lapland Finland',
    'lapland-husky-safari': 'husky safari sled Lapland',
    'levi-reindeer-manor': 'Reindeer Manor Levi',
    'helsinki-katajanokka-terminal': 'Katajanokka terminal Viking Line Helsinki',
    'viking-line-ferry': 'Viking Line ship Gabriella Mariella Helsinki',
    'stockholm-ferry-terminal': 'Stadsgården Viking Line terminal Stockholm',
    'stockholm-clarion-amaranten': 'Clarion Hotel Amaranten Kungsholmen',
    'stockholm-hotorgshallen': 'Hötorgshallen Stockholm',
    'stockholm-gastabud': 'Stockholms Gästabud Gamla stan',
    'stockholm-djurgarden': 'Djurgården Stockholm',
    'stockholm-strandvagen': 'Strandvägen Stockholm',
    'stockholm-kungstradgarden': 'Kungsträdgården Stockholm',
    'stockholm-vete-katten': 'Vete-Katten Kungsgatan Stockholm',
    'stockholm-central-station': 'Stockholm Central Station',
    'oslo-central-station': 'Oslo Central Station Oslo S',
    'oslo-home-hotel-folketeateret': 'Folketeaterbygningen Oslo',
    'myrdal-station': 'Myrdal station Flåmsbana',
    'flam-station': 'Flåm station Flåmsbana',
    'flam-marina': 'Flåm Marina',
    'flam-village': 'Flåm village Aurlandsfjord',
    'flam-aegir-brewpub': 'Ægir bryggeri Flåm',
    'flam-pier': 'Flåm harbour pier fjord',
    'gudvangen': 'Gudvangen Nærøyfjord',
    'voss': 'Vossevangen Voss Norway',
    'bergen-station': 'Bergen railway station',
    'bergen-magic-kloverhuset': 'Kløverhuset Bergen',
    'bergen-trekroneren': 'Trekroneren Bergen pølse',
    'bergen-bryggeloftet': 'Bryggeloftet Bergen',
    'bergen-city-centre': 'Torgallmenningen Bergen',
    'bergen-line-train': 'Bergensbanen train Vy',
    'oslo-city-centre': 'Oslo city centre Stortorvet',
    'oslo-airport': 'Oslo Airport Gardermoen terminal',
    'vienna-hotel-schonbrunn': 'Hotel Wien Schönbrunn',
}
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    "User-Agent": "NordicTripPhotoBuilder/3.0 (https://github.com/papaya85369-ym/nordic-trip-2026-Visibility)",
    "Accept": "application/json",
}
THUMB_WIDTH = 800          # Commons serves a resized thumbnail at this width
REQUEST_INTERVAL = max(1.5, float(os.getenv("PHOTO_REQUEST_INTERVAL", "2.5")))
RETRIES = 4
_last_request = 0.0


def pace():
    global _last_request
    delay = REQUEST_INTERVAL - (time.monotonic() - _last_request)
    if delay > 0:
        time.sleep(delay)
    _last_request = time.monotonic()


def retry_delay(header, attempt):
    if header:
        if header.isdecimal():
            return max(0, min(300, int(header)))
        try:
            retry_dt = parsedate_to_datetime(header)
            return max(0, min(300, (retry_dt - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            pass
    return min(120, 10 * (2 ** attempt) + random.uniform(0, 3))


def fetch(url):
    for attempt in range(RETRIES + 1):
        pace()
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except urllib.error.HTTPError as err:
            if err.code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                raise
            wait = retry_delay(err.headers.get("Retry-After", ""), attempt)
            print(f"HTTP {err.code}; retry {attempt+1}/{RETRIES} in {wait:.0f}s", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
            if attempt == RETRIES:
                raise
            wait = min(60, 5 * (attempt + 1))
            print(f"Network error {type(err).__name__}; retry in {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError("Exhausted retries")


def api(params):
    params = {**params, "format": "json", "formatversion": 2}
    data = json.loads(fetch(API + "?" + urllib.parse.urlencode(params)))
    if "error" in data:
        raise RuntimeError(f"Commons API: {data['error']}")
    return data.get("query", {}).get("pages", [])


def image_params():
    return {"prop": "imageinfo", "iiprop": "url|extmetadata|size|mime",
            "iiurlwidth": THUMB_WIDTH}


def search_pages(query):
    return api({"action": "query", "generator": "search",
                "gsrsearch": query + " filetype:bitmap", "gsrnamespace": 6,
                "gsrlimit": 12, **image_params()})


def exact_page(filename):
    name = filename.strip().replace("_", " ")
    if not name.lower().startswith("file:"):
        name = "File:" + name
    pages = api({"action": "query", "titles": name, **image_params()})
    pages = [p for p in pages if "missing" not in p and p.get("imageinfo")]
    if not pages:
        raise ValueError(f"Wikimedia Commons 找不到此指定檔案：{name}")
    return pages[0]


def clean_html(value):
    return unescape(re.sub(r"<[^>]*>", "", value or "")).strip()


def photo_metadata(page):
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata") or {}
    license_name = clean_html(meta.get("LicenseShortName", {}).get("value", ""))
    lic = license_name.lower()
    allowed = ("cc by" in lic or "cc0" in lic or "public domain" in lic)
    allowed = allowed and "-nc" not in lic and "-nd" not in lic
    mime = (info.get("mime") or "").lower()
    usable = (allowed and mime in ("image/jpeg", "image/png", "image/webp")
              and info.get("width", 0) >= 400)
    return usable, info, meta, license_name


GENERIC = {"vienna", "wien", "austria", "helsinki", "finland", "rovaniemi", "levi",
           "stockholm", "sweden", "oslo", "norway", "bergen", "hotel", "hotels",
           "church", "christmas", "market", "terminal", "ship", "city", "centre",
           "station", "railway", "central", "building", "park", "village"}


def norm(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = text.replace("ø", "o").replace("æ", "ae").replace("ß", "ss")
    return "".join(c for c in text if not unicodedata.combining(c))


def candidates_for(query, pages):
    words = re.findall(r"[a-z]{4,}", norm(query))
    # A photo title must contain at least one distinctive (non-city/generic) word,
    # so "Hotel Korotan Vienna" never matches a random "Hotel ... Vienna" photo.
    key_words = [w for w in words if w not in GENERIC] or words
    picks = []
    for page in pages:
        if not photo_metadata(page)[0]:
            continue
        title = norm(page.get("title", ""))
        if not any(w in title for w in key_words):
            continue
        rank = sum(w in title for w in words)
        picks.append((rank, page))
    return [p for _, p in sorted(picks, key=lambda x: (-x[0], x[1].get("title", "")))]


def link_record(slug, query, page, override_filename):
    _, info, meta, license_name = photo_metadata(page)
    return {
        "slug": slug, "query": query,
        "status": "已取得連結／待人工審核",
        "url": info.get("thumburl") or info.get("url", ""),
        "photo_title": page.get("title", ""),
        "author": clean_html(meta.get("Artist", {}).get("value", "")),
        "license": license_name,
        "license_url": meta.get("LicenseUrl", {}).get("value", ""),
        "source": info.get("descriptionurl", ""),
        "override": bool(override_filename),
        "requested_file": override_filename or "",
    }


def find_link(slug, query, override_filename=None):
    if override_filename:
        page = exact_page(override_filename)
        if not photo_metadata(page)[0]:
            raise ValueError("指定照片格式、尺寸或授權未通過檢查；請改選 CC BY、CC BY-SA、CC0 或 Public domain 照片")
        print(f"  specified: {page.get('title')}", flush=True)
        return link_record(slug, query, page, override_filename)
    results = search_pages(query)
    pages = candidates_for(query, results)
    print(f"  {len(results)} API results, {len(pages)} licensed candidates", flush=True)
    if not pages:
        return {"slug": slug, "query": query, "status": "未找到／保留原插畫",
                "error": "沒有通過授權及關聯性篩選的照片"}
    return link_record(slug, query, pages[0], None)


def load_overrides():
    path = ROOT / "PHOTO_OVERRIDES.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("photos"), dict):
        data = data["photos"]
    if not isinstance(data, dict):
        raise ValueError("PHOTO_OVERRIDES.json 必須是 {slug: filename} 或 {photos:{slug:filename}}")
    return {k: v.strip() for k, v in data.items()
            if k in QUERIES and isinstance(v, str) and v.strip()}


def same_file(a, b):
    return (a or "").replace("_", " ").lower() == (b or "").replace("_", " ").lower()


def write_reports(results):
    ordered = [results[k] for k in QUERIES]
    (ROOT / "PHOTO_CREDITS.json").write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    found = sum(bool(x.get("url")) for x in ordered)
    rows = ["# 景點照片連結與人工核對清單", "",
            "自動選圖未經人工審核。請點「預覽」確認是否為景點外觀；不合適的請寫進 PHOTO_OVERRIDES.json。", "",
            "| 景點 | 狀態 | 預覽／來源／授權／失敗原因 |", "|---|---|---|"]
    for r in ordered:
        if r.get("url"):
            cell = (f"[預覽]({r['url']})／[來源]({r.get('source','')})／"
                    f"{r.get('license','')}／{r.get('author','')}")
        else:
            cell = r.get("error", "—")
        rows.append(f"| {r['slug']} | {r.get('status','')} | {cell.replace('|', '／').replace(chr(10), ' ')} |")
    rows.append(f"\n已取得連結：{found}/{len(QUERIES)} 個景點。")
    (ROOT / "PHOTO_REVIEW.md").write_text("\n".join(rows), encoding="utf-8")
    items = []
    for r in ordered:
        if r.get("source"):
            items.append(f"<li><b>{escape(r['slug'])}</b> — {escape(r.get('photo_title', ''))}; "
                         f"{escape(r.get('author', ''))}; {escape(r.get('license', ''))}. "
                         f"<a href='{escape(r['source'], quote=True)}'>照片來源</a></li>")
    html = ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>照片來源與授權</title><h1>照片來源與授權</h1>'
            '<p>照片皆連結自 Wikimedia Commons，依各作品授權標示作者與來源。</p><ul>'
            + ''.join(items) + '</ul></html>')
    (ROOT / "photo-credits.html").write_text(html, encoding="utf-8")
    print(f"Photo links found: {found}/{len(QUERIES)}", flush=True)


def main():
    overrides = load_overrides()
    path = ROOT / "PHOTO_CREDITS.json"
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (ValueError, OSError):
        existing = []
    old_by_slug = {r["slug"]: r for r in existing
                   if isinstance(r, dict) and r.get("slug") in QUERIES}
    force = os.getenv("PHOTO_FORCE_ALL") == "1"   # set to 1 to redo every location
    results = {}
    for n, (slug, query) in enumerate(QUERIES.items(), 1):
        old = old_by_slug.get(slug, {})
        override = overrides.get(slug)
        keep = (not force and old.get("url")
                and (not override or same_file(old.get("requested_file"), override)))
        if keep:
            results[slug] = old
            print(f"[{n}/{len(QUERIES)}] {slug}: kept existing link", flush=True)
            continue
        print(f"[{n}/{len(QUERIES)}] {slug}: " + ("exact file" if override else "searching"), flush=True)
        try:
            results[slug] = find_link(slug, query, override)
        except Exception as err:
            msg = f"{type(err).__name__}: {err}"[:300]
            print(f"  failed: {msg}", flush=True)
            results[slug] = ({**old, "override_error": msg} if old.get("url") else
                             {"slug": slug, "query": query,
                              "status": "查詢失敗／保留原插畫", "error": msg})
    write_reports(results)


if __name__ == "__main__":
    main()
