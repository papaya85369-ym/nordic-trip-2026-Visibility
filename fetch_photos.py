"""Find open-licensed Wikimedia Commons photo candidates for the trip.

Run with network access (e.g. GitHub Actions). All matches need human visual review.
"""
from __future__ import annotations
import io, json, re, time, urllib.parse, urllib.request
from pathlib import Path
from html import escape
from PIL import Image, ImageOps
ROOT=Path(__file__).parent
QUERIES={
'vienna-stephansdom':'Stephansdom Vienna cathedral',
'vienna-am-hof-christmas':'Am Hof Christmas market Vienna',
'vienna-freyung-christmas':'Freyung Christmas market Vienna',
'vienna-stephansplatz-christmas':'Stephansplatz Christmas market Vienna',
'vienna-karlskirche':'Karlskirche Vienna church',
'vienna-rathausplatz-christmas':'Rathausplatz Christmas market Vienna',
'helsinki-senate-square':'Senate Square Helsinki',
'helsinki-uspenski-cathedral':'Uspenski Cathedral Helsinki',
'helsinki-cathedral':'Helsinki Cathedral',
'helsinki-old-market-hall':'Old Market Hall Helsinki',
'rovaniemi-santa-claus-village':'Santa Claus Village Rovaniemi',
'levi-christmas-market':'Levi Christmas market Sirkka Finland',
'levi-zero-point':'Levi Zero Point ski resort Finland',
'levi-panorama':'Levi Hotel Panorama Sirkka Finland',
'rovaniemi-arktikum':'Arktikum Rovaniemi',
'helsinki-loyly':'Loyly Helsinki sauna building',
'stockholm-city-hall':'Stockholm City Hall',
'stockholm-gamla-stan':'Gamla Stan Stockholm',
'stockholm-stortorget-christmas':'Stortorget Christmas Market Stockholm',
'stockholm-vasa-museum':'Vasa Museum Stockholm ship',
'stockholm-skansen':'Skansen Stockholm Christmas market',
'oslo-opera-house':'Oslo Opera House',
'oslo-karl-johans-gate':'Karl Johans gate Oslo',
'bergen-bryggen':'Bryggen Bergen',
'bergen-fish-market':'Bergen Fish Market',
'bergen-floibanen':'Floibanen Bergen',
'bergen-christmas-market':'Bergen Christmas market Festplassen',
'vienna-schonbrunn-christmas':'Schonbrunn Palace Christmas market Vienna',
}
API='https://commons.wikimedia.org/w/api.php'
HEADERS={'User-Agent':'NordicTripPhotoBuilder/1.0 (private trip website; images with attribution)','Accept':'application/json'}
def get(url):
  request=urllib.request.Request(url,headers=HEADERS)
  with urllib.request.urlopen(request,timeout=25) as f:return f.read()
def api(q):
  qs=urllib.parse.urlencode({'action':'query','generator':'search','gsrsearch':q+' filetype:bitmap','gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo','iiprop':'url|extmetadata|size|mime','iiurlwidth':'720','format':'json'})
  return json.loads(get(API+'?'+qs)).get('query',{}).get('pages',{})
def strip(x): return re.sub(r'<[^>]*>','',x or '').strip()
def fetch_one(slug,query):
  pages=api(query)
  print(f'{slug}: {len(pages)} API results', flush=True)
  candidates=[]
  for row in pages.values():
    ii=(row.get('imageinfo') or [{}])[0]; meta=ii.get('extmetadata') or {}
    license_short=meta.get('LicenseShortName',{}).get('value','')
    lic=license_short.lower()
    if not ('cc by' in lic or 'cc0' in lic or 'public domain' in lic):continue
    if (ii.get('mime') or '').lower() not in ('image/jpeg','image/png','image/webp'): continue
    if ii.get('width',0)<400:continue
    title=row.get('title','')
    # Reject unrelated broad search results; final visual verification is still necessary.
    words=re.findall(r'[a-z]{4,}', query.lower())
    in_title=sum(w in title.lower() for w in words)
    if in_title<1: continue
    candidates.append((in_title, row,ii,meta,license_short))
  print(f'{slug}: {len(candidates)} licensed candidate(s) after filtering', flush=True)
  candidates.sort(key=lambda x:(-x[0], x[1].get('title','')))
  for score,row,ii,meta,license_short in candidates[:4]:
    try:
      raw=get(ii.get('thumburl') or ii['url'])
      with Image.open(io.BytesIO(raw)) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        im=ImageOps.fit(im,(520,360),method=Image.Resampling.LANCZOS)
        out=ROOT/'images'/f'{slug}.webp';out.parent.mkdir(exist_ok=True)
        im.save(out,'WEBP',quality=80,method=5)
      return {'slug':slug,'query':query,'status':'下載成功／仍需人工確認是否對應景點', 'file':str(out.relative_to(ROOT)), 'photo_title':row.get('title',''), 'author':strip(meta.get('Artist',{}).get('value','')), 'license':license_short, 'license_url':meta.get('LicenseUrl',{}).get('value',''), 'source':ii.get('descriptionurl','')}
    except Exception as e: print(slug,type(e).__name__,str(e)[:120]);continue
  return {'slug':slug,'query':query,'status':'找不到可用照片，保留原插畫'}
def main():
  results=[]
  for slug,query in QUERIES.items():
    print('Finding',slug,flush=True)
    try:results.append(fetch_one(slug,query))
    except Exception as e:
      print(f'{slug}: API ERROR {type(e).__name__}: {e}', flush=True)
      results.append({'slug':slug,'query':query,'status':'查詢失敗，保留原插畫','error':str(e)[:160]})
    time.sleep(.2)
  (ROOT/'PHOTO_CREDITS.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
  rows=['# 景點縮圖來源與人工核對清單','','注意：自動搜尋可能找到不相符的照片。**發布前請逐張開啟 images/，核對拍攝地點與內容**。','','| 檔名 | 狀態 | 原始來源／授權 |','|---|---|---|']
  for r in results:
    src=f"[來源]({r.get('source')})／{r.get('license','')}／{r.get('author','')}" if r.get('source') else '—'
    rows.append(f"| {r['slug']} | {r['status']} | {src} |")
  (ROOT/'PHOTO_REVIEW.md').write_text('\n'.join(rows),encoding='utf-8')
  credit_rows=[]
  for r in results:
    if r.get('source'):
      credit_rows.append(f"<li><b>{escape(r['slug'])}</b> — {escape(r.get('photo_title',''))}; {escape(r.get('author',''))}; {escape(r.get('license',''))}. <a href=\"{escape(r.get('source',''),quote=True)}\">原始照片與授權</a></li>")
  page='<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>照片來源與授權</title><style>body{font:16px/1.7 -apple-system,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;color:#365b4b}li{margin:12px 0}a{color:#527e70}</style><h1>旅行縮圖來源與授權</h1><p>自動挑選的照片仍需人工確認其景點是否相符；照片來源、作者與授權如下。</p><ul>'+''.join(credit_rows)+'</ul><p><a href="./">返回行程</a></p></html>'
  (ROOT/'photo-credits.html').write_text(page,encoding='utf-8')
  print('Downloaded',sum('下載成功' in x['status'] for x in results),'of',len(results))
if __name__=='__main__':main()
