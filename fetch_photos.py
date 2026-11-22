#!/usr/bin/env python3
"""Nordic Trip Commons photo downloader, one run for all 28 locations.

- Optional exact Wikimedia Commons filename overrides in PHOTO_OVERRIDES.json.
- Preserves existing WebP files and credits unless override changes.
- Handles 429 Retry-After and paced API/media requests.
- Records attribution and failures, never assumes pictures are correct without review.
Requires: Pillow. Python 3.10+.
"""
from __future__ import annotations
import io
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
QUERIES = {'vienna-stephansdom': 'Stephansdom Vienna cathedral', 'vienna-am-hof-christmas': 'Am Hof Christmas market Vienna', 'vienna-freyung-christmas': 'Freyung Christmas market Vienna', 'vienna-stephansplatz-christmas': 'Stephansplatz Christmas market Vienna', 'vienna-karlskirche': 'Karlskirche Vienna church', 'vienna-rathausplatz-christmas': 'Rathausplatz Christmas market Vienna', 'helsinki-senate-square': 'Senate Square Helsinki', 'helsinki-uspenski-cathedral': 'Uspenski Cathedral Helsinki', 'helsinki-cathedral': 'Helsinki Cathedral', 'helsinki-old-market-hall': 'Old Market Hall Helsinki', 'rovaniemi-santa-claus-village': 'Santa Claus Village Rovaniemi', 'levi-christmas-market': 'Levi Christmas market Sirkka Finland', 'levi-zero-point': 'Levi Zero Point ski resort Finland', 'levi-panorama': 'Levi Hotel Panorama Sirkka Finland', 'rovaniemi-arktikum': 'Arktikum Rovaniemi', 'helsinki-loyly': 'Loyly Helsinki sauna building', 'stockholm-city-hall': 'Stockholm City Hall', 'stockholm-gamla-stan': 'Gamla Stan Stockholm', 'stockholm-stortorget-christmas': 'Stortorget Christmas Market Stockholm', 'stockholm-vasa-museum': 'Vasa Museum Stockholm ship', 'stockholm-skansen': 'Skansen Stockholm Christmas market', 'oslo-opera-house': 'Oslo Opera House', 'oslo-karl-johans-gate': 'Karl Johans gate Oslo', 'bergen-bryggen': 'Bryggen Bergen', 'bergen-fish-market': 'Bergen Fish Market', 'bergen-floibanen': 'Floibanen Bergen', 'bergen-christmas-market': 'Bergen Christmas market Festplassen', 'vienna-schonbrunn-christmas': 'Schonbrunn Palace Christmas market Vienna'}
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {
    # Wikimedia expects a descriptive user agent with contact information.
    "User-Agent": "NordicTripPhotoBuilder/2.0 (https://github.com/papaya85369-ym/nordic-trip-2026-Visibility)",
    "Accept": "application/json, image/webp, image/jpeg, image/png, */*",
}
REQUEST_INTERVAL = max(2.0, float(os.getenv("PHOTO_REQUEST_INTERVAL", "3.5")))
RETRIES = 4
_last_request = 0.0


def images_directory():
    folder = ROOT / "images"
    if folder.exists() and not folder.is_dir():
        i = 0
        backup = ROOT / "images_original_file_backup"
        while backup.exists():
            i += 1
            backup = ROOT / f"images_original_file_backup_{i}"
        folder.rename(backup)
        print(f"Renamed conflicting file images to {backup.name}", flush=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


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
            now = datetime.now(timezone.utc)
            return max(0, min(300, (retry_dt - now).total_seconds()))
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
            # A 403 can be a persistent policy restriction; don't retry indefinitely.
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
    return {"prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 720}


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
    # Exclude NC/ND licenses; attribution is retained for BY/BY-SA.
    allowed = ("cc by" in lic or "cc0" in lic or "public domain" in lic)
    mime = (info.get("mime") or "").lower()
    usable = (allowed and mime in ("image/jpeg", "image/png", "image/webp")
              and info.get("width", 0) >= 400)
    return usable, info, meta, license_name


def candidates_for(query, pages):
    words = re.findall(r"[a-z]{4,}", query.lower())
    picks = []
    for page in pages:
        usable, info, meta, lic = photo_metadata(page)
        if not usable:
            continue
        title = page.get("title", "").lower()
        rank = sum(w in title for w in words)
        if rank >= 1:
            picks.append((rank, page))
    return [p for _, p in sorted(picks, key=lambda x: (-x[0], x[1].get("title", "")))]


def download(slug, query, folder, override_filename=None):
    if override_filename:
        pages = [exact_page(override_filename)]
        print(f"{slug}: specified File: {pages[0].get('title')}", flush=True)
        usable, *_ = photo_metadata(pages[0])
        if not usable:
            raise ValueError("指定照片格式、尺寸或授權未通過檢查；請改選 CC BY、CC BY-SA、CC0 或 Public domain 照片")
    else:
        results = search_pages(query)
        pages = candidates_for(query, results)
        print(f"{slug}: {len(results)} API results, {len(pages)} licensed candidates", flush=True)
    errors = []
    for page in pages[:1 if override_filename else 4]:
        usable, info, meta, license_name = photo_metadata(page)
        if not usable:
            continue
        try:
            raw = fetch(info.get("thumburl") or info["url"])
            with Image.open(io.BytesIO(raw)) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im = ImageOps.fit(im, (520, 360), method=Image.Resampling.LANCZOS)
                temp = folder / f".{slug}.temporary.webp"
                im.save(temp, "WEBP", quality=80, method=5)
                temp.replace(folder / f"{slug}.webp")
            return {
                "slug": slug, "query": query,
                "status": "下載成功／待人工審核",
                "file": f"images/{slug}.webp",
                "photo_title": page.get("title", ""),
                "author": clean_html(meta.get("Artist", {}).get("value", "")),
                "license": license_name,
                "license_url": meta.get("LicenseUrl", {}).get("value", ""),
                "source": info.get("descriptionurl", ""),
                "override": bool(override_filename),
                "requested_file": override_filename or "",
                "note": "縮圖已裁切及縮小；CC BY / BY-SA 請依原授權標示修改及署名",
            }
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            errors.append(message)
            print(f"{slug}: candidate download failed: {message[:200]}", flush=True)
            if isinstance(err, urllib.error.HTTPError) and err.code in (403, 429):
                raise
    return {"slug": slug, "query": query, "status": "未下載成功／保留原插畫",
            "error": "; ".join(errors[:2]) or "沒有通過授權及關聯性篩選的照片"}


def load_overrides():
    path = ROOT / "PHOTO_OVERRIDES.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("photos"), dict):
        data = data["photos"]
    if not isinstance(data, dict):
        raise ValueError("PHOTO_OVERRIDES.json 必須是 {slug: filename} 或 {photos:{slug:filename}}")
    return {key: val.strip() for key, val in data.items()
            if key in QUERIES and isinstance(val, str) and val.strip()}


def write_reports(results):
    ordered = [results[k] for k in QUERIES]
    (ROOT / "PHOTO_CREDITS.json").write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    downloaded = sum("下載成功" in x.get("status", "") for x in ordered)
    rows = ["# 景點縮圖來源與人工核對清單", "",
            "自動選圖未經人工審核。請檢查景點是否正確、照片來源與授權。", "",
            "| 景點 | 狀態 | 原始來源／授權／失敗原因 |", "|---|---|---|"]
    for r in ordered:
        source = r.get("source", "")
        src = (f"[來源]({source})／{r.get('license','')}／{r.get('author','')}" if source
               else r.get("error", "—"))
        rows.append(f"| {r['slug']} | {r.get('status','')} | {src.replace('|', '／').replace(chr(10),' ')} |")
    rows.append(f"\n此次下載成功累計：{downloaded}/{len(QUERIES)} 張。")
    (ROOT / "PHOTO_REVIEW.md").write_text("\n".join(rows), encoding="utf-8")
    credits = []
    for r in ordered:
        if r.get("source"):
            credits.append(f"<li><b>{escape(r['slug'])}</b> — {escape(r.get('photo_title', ''))}; "
                           f"{escape(r.get('author', ''))}; {escape(r.get('license', ''))}. "
                           f"<a href='{escape(r['source'], quote=True)}'>照片來源</a>. "
                           "縮圖經過裁切及壓縮。</li>")
    html = ('<!doctype html><html lang="zh-Hant"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>照片來源與授權</title><h1>照片來源與授權</h1>'
            '<p>自動選圖仍需人工確認；請遵守每張作品授權及署名要求。</p><ul>'
            + ''.join(credits) + '</ul></html>')
    (ROOT / "photo-credits.html").write_text(html, encoding="utf-8")
    print(f"Photos downloaded: {downloaded}/{len(QUERIES)}", flush=True)


def main():
    folder = images_directory()
    overrides = load_overrides()
    credits_path = ROOT / "PHOTO_CREDITS.json"
    try:
        existing = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else []
    except (ValueError, OSError):
        existing = []
    existing_by_slug = {row["slug"]: row for row in existing
                        if isinstance(row, dict) and row.get("slug") in QUERIES}
    results = {}
    for n, (slug, query) in enumerate(QUERIES.items(), 1):
        old = existing_by_slug.get(slug, {})
        path = folder / f"{slug}.webp"
        override = overrides.get(slug)
        # Override forces replacement if filename differs from previously recorded exact choice.
        replace_override = bool(override and old.get("requested_file", "").replace("_", " ").lower()
                                != override.replace("_", " ").lower())
        if path.is_file() and path.stat().st_size > 500 and not replace_override:
            results[slug] = {**old, "slug": slug, "query": query,
                             "status": "下載成功／待人工審核", "file": f"images/{slug}.webp"}
            print(f"[{n}/{len(QUERIES)}] {slug}: preserved existing photo", flush=True)
            continue
        print(f"[{n}/{len(QUERIES)}] {slug}: " + ("exact Commons file" if override else "searching"), flush=True)
        try:
            result = download(slug, query, folder, override)
            # On failed override, don't lose the previous working file/credit.
            if path.is_file() and path.stat().st_size > 500 and "下載成功" not in result.get("status", ""):
                result = {**old, "slug": slug, "query": query,
                          "status": "下載成功／待人工審核",
                          "file": f"images/{slug}.webp",
                          "override_error": result.get("error", "overridden file unavailable")}
            results[slug] = result
        except Exception as err:
            message = f"{type(err).__name__}: {err}"
            print(f"{slug}: {message}", flush=True)
            if path.is_file() and path.stat().st_size > 500:
                results[slug] = {**old, "slug": slug, "query": query,
                                 "status": "下載成功／待人工審核", "file": f"images/{slug}.webp",
                                 "override_error": message[:300]}
            else:
                results[slug] = {"slug": slug, "query": query,
                                 "status": "查詢或下載失敗／保留原插畫", "error": message[:300]}
    write_reports(results)


if __name__ == "__main__":
    main()
