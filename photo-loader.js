/* 景點照片：從 PHOTO_CREDITS.json 讀取 Wikimedia 連結並顯示
   用法：在 HTML 放 <img data-photo="vienna-stephansdom" alt="Stephansdom">
   放在 index.html 的 </body> 前：<script src="photo-loader.js"></script> */
(async function loadPhotoLinks() {
  let links = {};
  try {
    const res = await fetch('PHOTO_CREDITS.json', { cache: 'no-cache' });
    const rows = await res.json();
    rows.forEach(r => { if (r.url) links[r.slug] = r.url; });
  } catch (e) {
    console.warn('[旅帖] 讀不到 PHOTO_CREDITS.json，保留原插畫', e);
    return;
  }
  window.PHOTO_LINKS = links; // 動態產生的卡片也可以用 PHOTO_LINKS[slug]

  document.querySelectorAll('img[data-photo]').forEach(img => {
    const url = links[img.dataset.photo];
    if (!url) return;                         // 沒有連結 → 保留原本的圖
    const original = img.getAttribute('src');
    img.loading = 'lazy';
    img.referrerPolicy = 'no-referrer';
    img.onerror = () => {                     // 連結失效 → 換回原插畫
      img.onerror = null;
      if (original) img.src = original;
    };
    img.src = url;
  });
})();
