# Nordic Trip 2026 — GitHub Pages

這份網站以 V6.4.1（連結整合版）為底稿。
`index.html` 已包含原本的行程、CSS、互動功能與離線 SVG 插畫，無須安裝套件。

## 第一次發布
1. GitHub 建立 repository，例如 `nordic-trip-2026`，選 **Public**。
2. 在 repository 選 **Add file → Upload files**，上傳 `index.html`、`.nojekyll`、`photo-list.json` 和 `images` 資料夾（上傳時至少保留 `images/.gitkeep`）；按 **Commit changes**。
3. 到 **Settings → Pages → Build and deployment**，Source 選 **Deploy from a branch**；Branch 選 `main`，資料夾選 `/(root)`，按 Save。
4. 網址通常是 `https://你的帳號.github.io/nordic-trip-2026/`，待 GitHub Pages 顯示已部署後開啟。

## 加入實景縮圖
圖片尚未附在這份套件內；目前網站仍顯示原本的精簡插畫，避免破圖。
1. 參照 `photo-list.json` 的檔名，準備有權使用的照片。
2. 將照片裁成正方形或 4:3，壓縮至每張約 80–200 KB，轉成 WebP。
3. 把照片上傳至 GitHub repository 的 `images/` 資料夾，檔名必須和清單相同。
4. 網路可連線且照片成功載入時，該景點的插畫會自動變成照片；離線／照片缺失時維持原本內嵌 SVG 插畫。

## 提醒
- GitHub Pages 網站通常是公開可瀏覽的。你的行程有確切日期、飯店和交通資訊，發布前請考慮隱私；`noindex` 只要求搜尋引擎不要收錄，不構成存取保護。
- HTML 本身可離線開啟；GitHub Pages 網址本身並**未**設計成可靠的離線網站。旅途中請另外下載 `index.html` 到 iPhone「檔案」App 留作備援。
- 不要上傳真正的電子車票、QR Code、訂單代碼、姓名或付款資料。
- GitHub Pages 設定有時顯示在不同位置，請以目前 GitHub 頁面的 Settings → Pages 為準。

## 自動準備景點照片候選（GitHub Actions）
現在含 `fetch_photos.py` 及 `.github/workflows/get-photos.yml`。網站上傳完畢後，開啟 GitHub Repository 的 **Actions → Find Creative Commons travel photos → Run workflow**。工作流程會搜尋 Wikimedia Commons 上具有開放授權的照片、轉成壓縮 WebP，並將候選照片及 `PHOTO_CREDITS.json`、`PHOTO_REVIEW.md` 放回 Repo。請逐張目視檢查，因為自動搜尋不保證照片對應景點，也不保證冬季場景；錯誤照片請移除，原本 SVG 插畫會自動恢復。授權要求標示作者及來源者，網站公開前應讓訪客能看到授權資訊（可把 `PHOTO_REVIEW.md` 做成公開頁）。若 GitHub 帳號沒有開啟 Actions 寫入權限，可於 Settings → Actions → General → Workflow permissions 設成 Read and write permissions。
