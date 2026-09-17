# 論文導讀與逐段精讀

八篇論文共用同一個首頁，每篇可選擇互動導讀或逐段精讀。精讀提供原始 PDF 聚焦、繁中翻譯、圖表伴讀、參考文獻、筆記及書籤；有完整附錄的論文提供附錄入口。翻譯與解說保留 AI 草稿標示。筆記與閱讀進度只儲存在各自瀏覽器，不會上傳。

線上入口：https://evan645test.github.io/ipbrp-experiment-framework/

第一篇導讀已同步為 2026-09-15「讀者追問試作」版本，第二至第八篇與獨立導讀檔逐字節一致。版本核對記錄在 `論文逐段精讀器/content/guide-version-audit.json`。原集中導讀首頁保留於 `guide-library.html`，舊的 `#paper=01` 至 `#paper=08` 連結會開啟對應導讀。

## 本機開啟

需要 Node.js 22.13 以上版本。首次使用：

```sh
cd 論文逐段精讀器
npm ci
npm run dev
```

開啟 http://localhost:5173/。macOS 已安裝套件後，也可雙擊上一層 `開啟論文閱讀.command`。本機與線上網站各自保留筆記，不會自動互相同步，可由閱讀器匯出或匯入。

## 重建 GitHub Pages

```sh
cd 論文逐段精讀器
npm ci
READER_BASE_PATH=/ipbrp-experiment-framework/ npm run build:static
cp -R dist-static/. ..
```

根目錄為 GitHub Pages 可直接使用的靜態輸出；完整程式與建置設定保存在 `論文逐段精讀器/`。原框架的本機啟動與建置方式保持可用，不需要雲端 API 金鑰或資料庫。根目錄的 `.nojekyll` 確保靜態檔案能直接使用。
