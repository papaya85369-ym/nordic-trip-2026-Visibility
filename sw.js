/* 北歐旅帖 離線功能
   - 行程頁（index.html）與照片清單：有網路時抓最新版，沒網路時用手機裡存的版本
   - 照片、圖示、字型：看過一次就存起來，之後離線也能顯示
   改了 index.html 不用動這個檔案；只有大改離線邏輯時才需要把 VERSION 加 1 */
const VERSION = 'v1';
const PAGE_CACHE = 'nordic-page-' + VERSION;
const MEDIA_CACHE = 'nordic-media-' + VERSION;
const CORE = ['./', './index.html', './PHOTO_CREDITS.json', './apple-touch-icon.png', './manifest.json'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(PAGE_CACHE)
      .then(cache => Promise.all(CORE.map(url => cache.add(url).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys
        .filter(k => k.startsWith('nordic-') && k !== PAGE_CACHE && k !== MEDIA_CACHE)
        .map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function networkFirst(request) {
  return fetch(request).then(response => {
    if (response && response.ok) {
      const copy = response.clone();
      caches.open(PAGE_CACHE).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(() => caches.match(request, { ignoreSearch: true })
    .then(hit => hit || (request.mode === 'navigate' ? caches.match('./index.html') : undefined))
    .then(hit => hit || new Response('', { status: 504, statusText: 'offline' })));
}

function cacheFirst(request) {
  return caches.match(request).then(hit => hit || fetch(request).then(response => {
    // opaque（跨網站圖片）status 為 0，也一併存起來
    if (response && (response.ok || response.type === 'opaque')) {
      const copy = response.clone();
      caches.open(MEDIA_CACHE).then(cache => cache.put(request, copy));
    }
    return response;
  }).catch(() => new Response('', { status: 504, statusText: 'offline' })));
}

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const sameSite = url.origin === self.location.origin;
  const isMedia = req.destination === 'image' || req.destination === 'font' ||
    url.hostname.endsWith('wikimedia.org') || url.hostname.endsWith('gstatic.com') ||
    url.hostname.endsWith('googleapis.com');

  if (sameSite && (req.mode === 'navigate' || url.pathname.endsWith('.html') ||
      url.pathname.endsWith('.json') || url.pathname.endsWith('/'))) {
    event.respondWith(networkFirst(req));
  } else if (isMedia || sameSite) {
    event.respondWith(cacheFirst(req));
  }
});
