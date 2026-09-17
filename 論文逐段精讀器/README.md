# 頁間：論文逐段精讀器

這是整合既有八篇互動導讀與逐段精讀的本機網站。左側保留原始 PDF 版面並聚焦目前段落，右側提供繁體中文忠實翻譯、白話說明、圖表共讀、參考文獻、書籤與筆記。目前為三階段功能的本機驗證版，內容仍需人工校訂，不可發布為已完成內容。

## 目前狀態

- 已納入 8 篇已授權英文 PDF。
- 自動擷取 1,217 個閱讀段。章節標題只用於顯示所屬章節，不會被列為閱讀段落。
- 1,217 段均已有繁體中文忠實翻譯與白話說明，每段保留頁碼、PDF 座標與來源檔案 SHA-256。
- 所有翻譯均為 `ai-draft`，未翻譯數為 0；目前沒有任何段落通過人工校訂。
- 已建立 123 個圖表項目；閱讀圖說或正文解釋時，左側會同步聚焦完整原始圖表，行動版則直接顯示裁切圖。介面會明確區分「正文有說明」與「未找到明確正文說明」。詳見 `content/figure-extraction-assessment.md`。
- 已建立 500 筆帶 PDF 頁碼與座標的書目、884 處正文引用；點開可查看完整來源摘要的繁中翻譯、本文引用脈絡、引用原句及書目來源。書目擷取已修正期刊名稱誤刪、斷行 DOI、文章編號誤併及主副標題漏配。
- 從「本文中引用這篇文獻的段落」跳轉後，底部提供「返回上一個位置」，可回到原段落並重新開啟原文獻視窗、恢復視窗捲動位置；連續跳轉可逐次返回。這是位置返回，不會撤銷筆記或已理解標記，重新整理後不保留返回歷史。
- 所有八篇書目均納入摘要補查，不限定 DOI 出版社頁；可取得且身分相符的摘要才完整翻譯並內嵌，皆為 AI 草稿。22 處同作者同年份引用先顯示候選清單，不猜測身分。逐筆完成數、來源類型及未完成原因以 `public/data/reference-abstract-audit.json` 為準；詳見 `content/reference-assessment.md`。
- 本次驗證已有 427 筆完整摘要翻譯（本輪新增 30 筆）；72 筆未取得可核對來源、1 筆身分衝突，已取得來源的待翻譯數為 0。這不是全部 500 筆內容已完成或已通過人工校訂。

### 閱讀步驟第一輪清理

本輪保留全部 1,217 筆原始段落紀錄與 ID，將 253 筆明確標題、表格名稱、表頭、表內數值碎片及統計註腳排除於獨立閱讀順序；目前 964 個閱讀單位。原始 PDF、翻譯、圖表、參考文獻與引用資料不刪除，也不標成已人工校訂。

10 個英文／數字詞項以下只用於篩查，必須再有 PDF 粗體、標題角色、表格區域或完整統計註腳等證據；表格名稱有獨立的明確編號規則。短完整句、研究問題、一般正文公式與圖說入口仍保留。以 Table 開頭的正文解釋不當作表格名稱。碎段與錯誤合併尚未在此輪重建。

執行 `npm run data:cleanup-reading-units` 套用可重複的清理；重建原始資料後需再次套用。`python3 scripts/cleanup_reading_units.py` 只產出候選盤點，不套用；`python3 scripts/cleanup_reading_units.py --restore` 依來源雜湊與原始旗標還原本輪排除。`npm run test:reading-cleanup` 執行防誤刪測試。

判斷證據保存在 `content/reading-unit-cleanup-audit.json`，可還原檢查點在 `content/reading-unit-cleanup.json`。已有筆記與書籤保留；原閱讀位置被排除時恢復到鄰近的有效單位。舊校編稿繼承未改動內容的新排除旗標，但保留使用者明確的納入／排除決定。

### 段落完整性與語意可解釋性

內容必須恢復成完整原始段落或作者條列項目，才能提供獨立段落解釋。斷字、被切開的研究問題或不完整句子不能因為已有機器翻譯而視為完整段落；但上下文依賴、短句或文風不順本身不證明作者段落無效。

目前以原 PDF 的 soft hyphen、字詞座標與問題延續行核對，確認 9 個來源片段，另有 20 個僅待核對的單位。這是可追溯的切分完整性檢查，不是已完成全篇 AI 語意審查。確認片段標示「不是完整段落」，保留為核對入口但不提供獨立白話解釋、不計為已確認的完整段落；原文、舊翻譯、筆記與相接片段連結保留，尚未重建或重新翻譯。總閱讀單位數仍包含這些核對入口，不代表完整原始段落數。

清理命令會接著執行完整性檢查；亦可用 `npm run data:assess-paragraphs` 重新檢查，或 `python3 scripts/assess_paragraph_completeness.py` 只產出盤點。原始證據在 `content/paragraph-completeness-audit.json`，判斷與原文 SHA-256 綁定，修改原文後不可沿用；`npm run test:paragraph-completeness` 驗證不誤判正常跨行、另一欄文字、完整短句與上下文依賴。

## 執行環境

- Node.js `>=22.13.0`
- npm
- Python 3.11 以上
- PyMuPDF（只用於目前本機原型的 PDF 後處理）
- Chrome 在本機翻譯與瀏覽器煙霧測試時需要，且需開啟本機 DevTools Protocol；摘要翻譯使用獨立工具分頁，不讀寫閱讀器筆記或進度

PyMuPDF 有 AGPL／商業授權要求。未來將專案封裝成可散佈 skill 前，必須先確認授權相容性，或替換 PDF 後處理相依。PDF 前端顯示使用 Apache-2.0 的 PDF.js。

## 本機啟動

直接雙擊上一層的 `開啟論文閱讀.command`，即可啟動網站並開啟統一閱讀入口。已啟動時會直接開啟，不重複啟動。首頁每篇都有「互動導讀」與「逐段精讀」；兩種模式可切換同一篇論文，精讀進度、筆記與書籤沿用原儲存位置。`#guide:paper-03` 可直接開啟第三篇導讀，原本 `#paper-03` 仍直接開啟精讀。

互動導讀已逐篇比對本機獨立版本：第二到第八篇與原首頁一致；第一篇更新為 2026-09-15 的「讀者追問試作」版本（仍為試作內容），原首頁同步更新。八篇首頁內嵌內容、獨立檔與 `public/guides/` 均以 SHA-256 核對一致，記錄在 `content/guide-version-audit.json`；第一篇舊版保存在 `content/paper-01-guide-before-version-sync.html`。研究聲明不另設欄位；有完整附錄的論文提供「完整附錄」入口。研究聲明原文仍在 PDF 與來源資料中，既有筆記與書籤保留。

```bash
npm install
npm run dev
```

預設網址為 `http://localhost:5173/`。本機閱讀進度、書籤、筆記與校編草稿都存在瀏覽器 `localStorage`，不會上傳。

## 資料重建與翻譯覆寫

來源 PDF 預設放在專案的上一層，檔名必須以 `1.` 到 `8.` 的連續數字開頭。

```bash
npm run data:extract
npm run data:apply-overrides
npm run data:link-exhibits
npm run data:references
npm run data:validate
```

`data:extract` 會重建 `public/data` 並複製 PDF 至 `public/papers`。`data:apply-overrides` 會依 `content/full-translation-overrides.json` 的來源雜湊與段落 ID 回套完整翻譯；任一對應不一致都會失敗，不會靜默套錯譯文。`data:link-exhibits` 會驗證已裁切的圖表檔、套用人工確認座標，並建立圖說、圖表與正文解釋段落的雙向關聯；仍有失敗或可疑裁切時會直接中止。

若要從現有檢查點續跑本機翻譯，需先在已開啟 Translator API 與 Prompt API 的 Chrome 分頁打開本站，再執行 `npm run data:translate`。輸出會逐段原子寫入 `content/full-translation-overrides.json`，且只會標示為 AI 草稿。

`data:references` 只讀本機 PDF，回套已快取的引用資料，不需要網路。要補查摘要，可執行：

```bash
npm run data:fetch-reference-abstracts
CHROME_DEBUG_URL=http://localhost:9222 npm run data:summarize-reference-abstracts
npm run data:references
npm run data:validate
```

摘要查核只將 DOI 傳至 Crossref，不上傳原始論文。以上 `data:summarize-reference-abstracts` 是保留的舊版重點整理流程，不是閱讀器目前主要顯示的忠實翻譯。新版可由 DOI 解析出版社頁面，確認 DOI 與標題後擷取 Abstract，使用 Chrome 本機 Translator API 翻譯完整內容，不抽句、不生成額外總結。無付費 API 或雲端模型備援。成功結果逐筆原子寫入，可中斷後續跑。

例如補查你指定的 Ching 與 Hsu 文獻：

```bash
npm run data:fetch-publisher-abstracts -- --doi 10.1007/s11528-023-00841-1
CHROME_DEBUG_URL=http://localhost:9222 npm run data:translate-reference-abstracts -- --doi 10.1007/s11528-023-00841-1
npm run data:references
npm run data:validate
```

不帶 `--doi` 時，出版社擷取程式會查詢本機書目中的非身分衝突 DOI；翻譯程式則處理所有已取得的完整摘要。出版社原文優先於 Crossref。來源文字 SHA-256 必須與翻譯檢查點一致，才會嵌入；來源更新後需要重新翻譯。出版社阻擋自動存取、未提供摘要或身分不符時，不猜測或改用重點整理冒充翻譯。自動存取僅循已支援出版社的公開頁面與正常訪客轉址，不登入或繞過付費牆。需要機器翻譯的文獻仍需確認個人處理與未來散佈的授權範圍。

出版社快取為 `content/reference-publisher-cache.json`，完整摘要翻譯檢查點為 `content/reference-abstract-translations.json`。出版社補查資料位於 `content/reference-publisher-enrichment.json`；圖 2 的特定引用角色整理位於 `content/reference-relationship-overrides.json`，僅在引用原句相符時套用。

來源摘要完整快取留在本機；閱讀器主要顯示繁中忠實翻譯，核對區提供至多 25 個英文詞的原文節錄。摘要區沒有外連按鈕或超連結；來源網址保留為折疊區的純文字查核記錄，不以連結代替摘要內容。舊版中文重點整理保留為次要折疊區，不取代忠實翻譯。摘要翻譯與本文段落脈絡並非同一種證據；未提供特定角色整理的引用，會使用整段白話說明，且清楚提示不能把整段主張歸給單一文獻。編輯原文後，不再相符的舊引用會隱藏；匯入校編後可重跑 `data:references` 重新索引。

出版社一般抓取無法取得公開內容時，可使用隔離的正常 Chrome 分頁查閱支援的官方來源，例如作者機構頁：

```bash
npm run data:fetch-browser-abstract -- --doi 10.1016/j.compedu.2018.07.004 --url https://scholar.lib.ntnu.edu.tw/en/publications/how-to-learn-and-how-to-teach-computational-thinking-suggestions--2/
npm run data:translate-reference-abstracts -- --doi 10.1016/j.compedu.2018.07.004
npm run data:references
npm run data:validate
```

這個流程核對頁面標題與 DOI，使用一般訪客存取，不登入、解驗證或繞過限制；來源不可讀時會失敗，不會製造摘要，也不會將未取得摘要改成外連按鈕。取得資料後會標示實際來源類型（出版社或作者機構），並經來源雜湊核對後嵌入翻譯。

### 全部八篇的資料庫補查與完整翻譯

出版社／作者機構公開頁優先，其次是 Crossref 已提交摘要；仍缺少時可採用 OpenAlex、Semantic Scholar、Europe PMC、ERIC 收錄的摘要。ScienceDirect 也屬於支援的出版社摘要來源，包含 Elsevier Linking Hub 的正常公開轉址；核對文獻身分後，完整 Abstract 會翻成繁中並直接嵌入。若遇存取限制，改查其他已支援來源，不繞過限制，也不把資料庫內容誤標成直接取自 ScienceDirect。資料庫來源如實顯示，不冒充直接讀取出版社原文，也不使用 Semantic Scholar 的 TLDR 或任何 AI 研究總結。OpenAlex 依原始索引詞序完整重建摘要，詞序有缺漏或重複時拒絕套用。ERIC 保留摘要編撰者欄位；資料庫編撰或未標明編撰者的摘要，不宣稱是作者原始 Abstract。

本輪另加入 OpenAIRE、DOAJ、EBSCO。OpenAIRE 只讀非推論產生的來源摘要／描述欄位，若多個來源的內容實質不同，不自行拼接；介面標示資料庫摘要翻譯。DOAJ 只使用期刊提交的完整 `bibjson.abstract`。EBSCO 只讀無須登入的公開頁面 `itemInfo.ab` 摘要欄位，編撰者未標明時明確標示資料庫摘要，不使用 TLDR。以上仍須符合 DOI 與標題，或無 DOI 時符合標題、第一作者與年份，且候選唯一。

人工找到的官方來源網址存於 `content/reference-abstract-source-overrides.json`；程式再次核對文獻身分，只讀明確 Abstract 區或 ePrints／Dublin Core Abstract 欄位。雙語期刊必須有唯一完整英文摘要區才套用，不把其他語言誤送入英文翻譯器。書籍介紹與一般網頁描述不冒充正式 Abstract。

Google 學術搜尋可用來發現來源網址；摘要不要求附有全文或 PDF。搜尋結果指向的出版社、作者機構或資料庫只有書目與完整摘要時，核對文獻身分後即可完整翻譯並嵌入。搜尋結果的截斷文字、其他文章引用這筆文獻的說明及 AI 總結不當作正式摘要；實際取得內容的來源才列為翻譯依據，不把搜尋引擎誤標成摘要原始來源。Google 搜尋若要求驗證或限制存取，就停止該路徑，不繞過限制。

在本機 Chrome 已開啟閱讀器與 Translator API、且 DevTools Protocol 位於 `localhost:9222` 時，依序續跑：

```bash
CHROME_DEBUG_URL=http://localhost:9222 npm run data:complete-reference-abstracts
```

流程會重建全部書目、依標題／作者／年份補查缺少的 DOI、查詢公開來源與資料庫、完整翻譯、嵌入、驗證並產出逐筆盤點。補齊的 DOI 保留原書目 DOI 與查核證據；原始 PDF 不變。只傳送 DOI、書目標題與必要作者資訊，不上傳 PDF、閱讀筆記或進度。各來源成功快取保存在本機，可中斷後續跑；請勿同時啟動多個會寫入同一來源快取的補查流程。所有資料庫使用公開唯讀介面，遇到權限或流量限制就保留失敗原因，不繞過限制。

結束碼 `0` 代表全部書目已嵌入翻譯；`2` 表示流程完成但仍有來源缺漏、身分衝突或尚待翻譯，不代表全部內容已完成；`1` 表示本機驗證或必要流程失敗。來源未提供摘要不代表原文一定沒有 Abstract，書籍／網頁也可能沒有正式摘要。沒有來源時不根據標題、引用句或全文自行生成 Abstract。

只核對本機快取與目前完成範圍、不連網、不啟動翻譯，可執行：

```bash
npm run data:complete-reference-abstracts -- --offline
```

個別步驟亦可執行 `data:resolve-reference-dois`、`data:fetch-database-abstracts`、`data:fetch-semantic-scholar-abstracts`、`data:fetch-europe-pmc-abstracts`、`data:fetch-eric-abstracts`、`data:fetch-openaire-abstracts`、`data:fetch-doaj-abstracts`、`data:fetch-ebsco-abstracts`、`data:fetch-curated-abstracts`、`data:translate-reference-abstracts`、`data:references`、`data:audit-reference-abstracts`。OpenAIRE／DOAJ／EBSCO 可加 `-- --retry-errors` 重試未查核來源；ERIC 可加 `-- --refresh --reference 本機書目ID` 重查指定書目。寫入同一資料庫快取的步驟必須依序執行，不能同時執行；整合流程已依序調度。資料庫完整來源快取為 `content/reference-database-cache.json`；逐筆盤點為 `public/data/reference-abstract-audit.json`，會驗證每筆內嵌翻譯與目前完整來源的 SHA-256 及翻譯檢查點完全一致。

目前為私人本機驗證用途；未來公開網站或封裝 skill 時，仍須逐來源確認摘要與翻譯的散佈授權，不應直接打包私人完整摘要快取。

## 校編工作流程

### 八篇文圖伴讀（目前啟用）

第一篇的閱讀品質修正已延伸至第二至第八篇。正文依原始版面順序閱讀，圖表另開可停靠、浮動、縮放的伴讀視窗；研究聲明保留在來源資料與 PDF，介面僅為有附錄的論文提供「完整附錄」入口。每張圖表都有中文讀法、解讀限制與有來源的作者說明。明確提及圖號的關聯與待核對的語意候選分開標示；候選不會自動成為已確認的關聯。

| 論文 | 正文步驟 | 完整圖表 | 保留的來源聲明紀錄 | 完整附錄 |
| --- | ---: | ---: | ---: | ---: |
| 01 | 66 | 25 | 6 | 2 |
| 02 | 83 | 22 | 4 | 0 |
| 03 | 50 | 13 | 9 | 0 |
| 04 | 58 | 5 | 13 | 0 |
| 05 | 79 | 13 | 6 | 1 |
| 06 | 68 | 17 | 4 | 0 |
| 07 | 72 | 18 | 6 | 0 |
| 08 | 108 | 19 | 6 | 0 |

第二、七、八篇依雙欄版面排序。被圖表打斷的正文與研究問題恢復為完整閱讀單位；表格資料列不再混入正文。第三篇補回原來漏掉的引言；第八篇補回文字層缺漏的正文與九張未收入清單的圖，局部 OCR 證據記錄在 `content/paper-08-recovered-text.json`，原始 PDF 不變。第五篇提供原始 PDF 第 17 頁的完整編碼附錄；第四篇正文提到的另外提供的補充資料不冒充為本地 PDF 中的附錄。

原圖表以 300 dpi 重裁，保留圖名、欄名、資料列與註腳，舊圖檔仍保留。第六篇正文的圖號錯置、第八篇訪談圖與表的次數差異，以及第三篇投入效果量的數字疑點，皆保留原文並附核對提示，不改寫作者數值。翻譯、白話解釋及讀圖說明均為 AI 草稿，沒有標記為人工校訂。

每篇原始資料備份為 `content/paper-0N-before-remaining-companion.json`。原 ID、吸收關係與原引用保留，修正前段落及譯文另有紀錄；新增正文補上可點選的引用索引。舊校編稿自動接續，保留手動移動、刪除、譯文與納入／排除決定。若人工修改與段落合併衝突，保留修改並提示待核對；筆記和書籤仍使用原 ID，可以從合併段落及完整圖表的封存筆記查看。本次沒有發布、部署或上傳 PDF。

完整重建與檢查流程（本機 Python 3、PyMuPDF、Tesseract 英文套件；Node.js 22.13 以上；本機 Chrome 翻譯功能與 `localhost:9222` 偵錯端點）：

```sh
python3 scripts/recover_paper08_text.py
python3 scripts/annotate_remaining_papers.py
python3 scripts/build_remaining_companions.py --prepare
python3 scripts/refine_remaining_companions.py
node scripts/translate_remaining_companions.mjs
python3 scripts/build_remaining_companions.py --apply
python3 scripts/validate_phase_a.py
python3 scripts/test_remaining_companions.py
node scripts/test_remaining_companions.mjs
node scripts/browser_remaining_companions.mjs
```

來源計畫已附於 `content/remaining-papers-source-plan.json`。已完成的資料可直接重跑 `--apply`；不要在已更新的讀者資料上重新執行來源註記。調整來源計畫時，先在保留的原資料上重新準備，並以 `--prepare --refresh` 明確重建暫存稿；翻譯檢查點依原文 SHA-256 重用，原文改變時必須重譯。本機模型呼叫使用獨立工作頁並於完成後關閉，使用者的閱讀頁及筆記不受影響。隔離瀏覽器測試不會清空使用者的本機資料。

### 第一篇文圖伴讀與歷史流程

第一篇目前以 66 個正文單位依原順序切換；25 張完整圖表不再獨立占閱讀步驟。未來研究的引導句及五項建議已合併，兩份完整附錄另設「完整附錄」入口；六項研究聲明保留在 PDF 與來源資料，不另設欄位。所有 156 筆原始紀錄、吸收關係、筆記與書籤 ID 保留，舊翻譯有修正前備份；合併前的段落筆記仍可查看及編輯。此模式取代下方歷史試修中的 76 正文步驟與「101 步及 modal 彈窗」。以下保留當時僅處理第一篇的流程；其他七篇的現行狀態以上節為準。

### 第一篇閱讀品質修正與其他論文的預防流程

以下記錄最初第一篇的修正流程；目前 `readingQuality` 已延伸八篇，介面不另設研究聲明欄位。研究聲明不刪除：貢獻、倫理、兩處資料取用、利益衝突與致謝保留原文、中文草稿及各自筆記／書籤。附錄 I 與 II 透過 figure-extractor 從原 PDF 第 18、19 頁裁出完整內容，300 dpi，不把題型圖片、EF 表格或其截圖拆成孤立正文；支援圖片縮放、捲動及拖移。附錄旁附上中文草稿、解讀限制與相關正文量測說明。原表 Card Sorting 條件敘述較簡略，不自行補出所有兒童必經的試次程序。查閱附錄不改正文進度，不標記正文已讀。

修正八處白話說明與一處資料取用翻譯；各自記錄原文、前後翻譯及原 ID。舊校編稿只有在原文、位置與翻譯未被使用者修改時才升級；人工修改或已校訂稿保留。核對過的原文／白話稿若再變更，未校訂的版本會隱藏白話解釋並提示重核，不冒充已核對內容；CT／EF 已知術語錯配也會提示。這些是具體錯誤防線，不等同通用語意正確性保證。

```bash
npm run data:audit-reading-quality
npm run data:audit-reading-quality -- --paper-id paper-01 --fail-on-known-errors
npm run test:reading-quality
npm run data:repair-paper01-reading-quality
```

稽核完全唯讀，以 JSON 列出頁碼、ID、原文與原因。少於十字、清單引導、數字比例高、位於表格內的正文框、聲明／附錄混入正文均是**人工核對候選**，不是刪除條件；來源與核對版本不符或本篇已知 CT 錯譯才列為確定需重核的錯誤。十字以上仍可能是表格資料列。修正命令只接受已核對 SHA-256 的第一篇，可重複執行，保留 `content/paper-01-before-reading-quality.json` 中的原資料、清單與翻譯快取備份。沒有新增模型 API、金鑰或資料上傳。

套用新論文時依序驗收：

1. 先辨識版面與內容角色：正文、標題、圖名、表格、公式、研究聲明、參考書目、附錄分開；完整表格包含表名、欄名、資料列及註記。
2. 按 PDF 的欄位與頁序重建正文，先合回被圖表／換頁切開的續文；保留各頁原始位置、來源 ID 與吸收關係，不把圖表資料夾進正文。清單引導與條目一起核對，不能只按十字門檻刪除。
3. 檢查語意是否能獨立說明；必要的短句或完整條列可保留，不完整的續句要合回，疑似數字／公式片段送人工核對而非逕自刪除。
4. 先建立本篇術語表，再對重建後的全文產生翻譯及解釋；每份解釋綁定當前原文，不能從其他段落沿用。統計結果需核對組別、時間點、顯著性與限制，避免把趨勢當成正式檢定。
5. 圖表關聯由明確編號或核對過的語意建立，不依空間接近直接配對；逐段模式只解釋當前段落，其他引用段落留在圖表總覽。
6. 產生每頁原始 PDF 加框審核圖，確認正文沒有遺漏、重複、錯序，整張圖表與附錄沒有切開。先驗收一篇，再擴展；人工筆記、書籤與校編修改都須回歸測試。

### 第一篇文圖伴讀細節

正文有明確圖表編號或經本次原文核對建立的高信心語意關聯時，自動顯示完整圖表；同段多張圖表以頁籤切換。共有 26 筆編號關聯、20 筆高信心語意關聯。主題詞相似的 10 筆候選不能自動升級，須由使用者確認；不將詞彙相似度冒充模型信心機率，也不以 PDF 位置接近作為關聯證據。每筆關聯保留原段全文、SHA-256、來源段落 ID 與中文關係說明；本機校編原文變動後，不沿用不相符的關聯。

伴讀視窗為非阻擋 region，沒有遮罩、背景鎖定或焦點限制。預設靠翻譯區，可用按鈕改為原文旁或浮動；拖曳標題列至文字區頂端的提示區亦可停靠。支援滑鼠、觸控與方向鍵，視窗尺寸和圖片 50%–400% 縮放獨立控制，提供適合視窗／重設。放大圖片後可滑鼠拖移或原生捲動。寬桌面採三區並排，窄桌面改圖表與對應文字區上下排，手機採上圖下文，仍可切換原文／翻譯。切換正文自動跟隨圖表，無關聯就收起；手動收起只影響當前段落。停靠、尺寸及每張圖縮放保留。

讀圖指南、欄位／座標軸、組別、單位、符號、主要觀察與限制都在圖表伴讀視窗內，隨圖表拖曳、停靠及調整尺寸；翻譯區不再重複顯示。逐段模式只呈現目前段落的作者翻譯，英文原文可展開，不列出其他段落索引；本段與圖表的關係明確標為 AI 解釋，語意關聯不冒充作者明確引用。25 份解讀皆為 AI 草稿。表 7 的正文 p 值與原表不一致，以及圖 15 說明段落的 LT／LI 代碼不一致，並列提示而不更改作者文字。Fig. 12／13 修正裁切以去除鄰近表格；其他頁首裁切去除期刊頁眉，原圖不刪除，新圖使用 `_companion.png`。

「全部圖表」始終保留所有圖表，包括未配對的資料，亦可查閱／編輯完整圖表筆記、書籤及查看被吸收片段的舊筆記。舊圖表位置恢復到相關正文；沒有關聯時恢復到鄰近正文，但不捏造圖表關聯。

在全部圖表按「查看完整圖表」會開啟獨立、非遮罩的圖表總覽：寬視窗左側完整原圖，右側先列圖表解讀，再依論文順序列出預設收合的各段說明。展開可核對中文翻譯、英文原文及各段關係，標示「明確引用／語意關聯／使用者加入」。關聯與逐段模式共用來源有效性及本機修正判定，未確認候選不列入。窄視窗（含手機）採上圖下說明，可觸控拖曳分隔列或用上下方向鍵調整高度，兩區分別捲動。總覽可拖曳、調整尺寸、圖片縮放；其尺寸、位置與每圖縮放在此次閱讀畫面內獨立保留，不寫入正文伴讀備份。開啟時原伴讀保持掛載但隱藏，關閉後恢復原圖表、縮放、展開狀態與捲動位置；查看及展開總覽不標記正文已讀，也不改進度、筆記或書籤。

關聯修正、停靠及縮放以 `paper-focus-companion:v1:paper-01` 獨立存於 localStorage，不混入既有閱讀進度及研究筆記。閱讀設定可匯出／匯入伴讀 JSON，匯入驗證論文身分、PDF SHA-256、段落／圖表 ID、修正動作、尺寸及縮放範圍；異常備份拒絕且不改原設定。備份最大 1 MB。沒有新增 API、模型服務、金鑰或網路上傳需求；修正只屬本機，正式整合或封裝 skill 前仍須人工驗收。

```bash
npm run data:build-paper01-companion
npm run test:paper01-companion
npm run data:validate
npm run data:render-paper01-review
CHROME_DEBUG_URL=http://localhost:9222 npm run test:browser
```

產生資料前備份為 `content/paper-01-before-companion.json`。重建來源連結及前三階段單篇修正後，最後執行 `data:build-paper01-companion` 再產生核對圖。修正圖表需 PyMuPDF 及 figure-extractor CLI／來源模組；來源位置可用 `FIGURE_EXTRACTOR_SRC=/absolute/path/to/figure-extractor/src` 指定，預設查找使用者的已安裝 skill。已有完整裁切時不重新產生；程式缺少 extractor 時明確停止，不產生假的原圖。UI 執行僅使用專案既有依賴。

本機原文校編變更後，舊語意關聯失效，不把舊解釋套到新文字；匯入校編檔會保留現有來源圖表與伴讀模式，移除失效關聯並更新正文計數，不阻止合法校編，也不讓舊匯出稿還原過時裁切。重建時不自動恢復已變動原文的人工核對語意關聯，仍需重新核對。

若需暫停此模式，可在保留原始資料與修正備份後移除第一篇的可選 `exhibitCompanion` 設定及 manifest 的 `bodySegmentCount`，即回到原閱讀流程；不清除 localStorage，也不刪除任何筆記。完整回復來源圖表設定需對照上述備份，避免覆蓋之後的人工校編。

### 第一篇閱讀順序試修（待使用者確認）

本次只校正 `paper-01`：依已逐頁核對的單欄版面，以頁碼及原文首片段的垂直位置排序，補回 Introduction 前三段及其中文草稿、引用關聯。誤混入正文的一筆書目只標為排除，原始紀錄保留。其他七篇資料不變；不將本篇的單欄排序直接套用到雙欄論文。

第一篇初次排序修正後有 156 筆保留紀錄、118 個納入閱讀單位；第 10–11 頁跨頁合併後為 117 個，再核對並合併其他六處圖表插斷的正文後為 111 個。確認順序為「摘要 → 運算思維介紹 → 程式設計與執行功能 → 教育機器人 → 機器人程式設計的教學方法」。筆記與進度仍使用原有 ID。初次修正前完整備份在 `content/paper-01-before-order-repair.json`；跨頁與表格修正前備份在 `content/paper-01-before-page10-11-repair.json`；其他六處合併前備份在 `content/paper-01-before-interruption-repair.json`。

舊本機校編稿若仍為原自動產生順序，載入時套用修正順序並補回漏段，保留本機翻譯。如果使用者已手動排序、合併或刪除，保留其校編決定，只插入此次新補回的三段。此修正不代表跨頁段落、表格儲存格或全文語意已完成人工驗收。

```bash
npm run data:repair-paper01-order
npm run test:paper01-order
npm run data:validate
```

重複執行修正具冪等性。這是限第一篇、綁定 PDF SHA-256 的修正，不能用來直接處理其餘論文。

第 10–11 頁核對：原 R053 與原 R055 是被 Table 1 隔開的同一段正文，已合回原 R053 ID 並重譯；原 R055 紀錄標為吸收、排除，不刪除原文及筆記。Table 1 獨立作為完整圖表閱讀單位，含表名、欄名及 12 列資料。Table 1、Table 2 均依原 PDF 以 300 dpi 裁出完整區域，不含頁碼。正文開頭的「Table N shows/displays/presents」及「Fig. N presents」已改回正文分類，不再冒充圖說。

第一篇原始 PDF 的 Table/Fig. 編號與中文翻譯中的表／圖編號可點選，直接彈出原圖，不跳換段落。視窗支援放大及捲動；關閉後位置、筆記與書籤不變。其他七篇未啟用此試驗流程。舊校編稿若有相關原文、位置或翻譯的手動修改，不強制覆蓋，會提示待核對。吸收片段的舊筆記仍保留於原 ID，完整筆記匯出可讀取。修正腳本同時更新這兩個閱讀單位的翻譯快取，避免重新套用翻譯時還原成舊版本；其他篇的快取不變。

```bash
npm run data:repair-paper01-spots
npm run test:paper01-spots
npm run data:render-paper01-review
```

核對圖位於本機 `/review/paper-01/index.html`，反映目前納入閱讀的原文框；重建圖表連結後需再次執行單篇 spot 修正及驗證，不將此規則批次套用其他論文。

圖表插斷正文的核對與合併只套用第一篇，已確認的頁面接續為 4→5、5→6、7→8、8→9、11→12、14→15。需同時核對原文句子接續、跨頁位置、中間確實有圖表、沒有其他正文插入，以及續文未縮排為新段落。沒有句點或少於十個單字只作為檢查線索，不足以決定合併。數字開頭的年齡資料也可為續文；跨頁「C-」接「PBRP」保留為完整組名「C-PBRP」。六段重譯為 AI 草稿，原 ID、吸收片段、既有筆記、引用及圖表解釋關聯都保留或轉接；不將表格資料列混入正文。已校訂內容或與核對邊界不同的來源會拒絕自動覆蓋。

圖表彈窗可用滑鼠或觸控拖曳標題列，亦可聚焦移動按鈕後用方向鍵移動（Shift 加快），或按「置中」還原。移動、圖片載入造成尺寸改變、放大及螢幕縮小時，視窗均限制在畫面內。拖曳、放大及關閉不改變段落、筆記或書籤。這個視窗仍為既有的 modal，未改成可操作背景內容的非 modal。

```bash
npm run data:repair-paper01-interruptions
npm run test:paper01-interruptions
npm run data:validate
npm run data:render-paper01-review
```

第一篇的 Table 1–10 各為一個完整閱讀單位；表名、欄名、全部資料列及表下注記不得拆成正文段落。已核對 Table 3、5、7、9 的固定效應、隨機效應、模型配適與公式需一起閱讀，Table 10 的 12 種行為列也保持整張表。完整表格修正後第一篇為 156 筆保留紀錄、101 個閱讀單位。裁切納入表名與表下注記，不包含相鄰折線圖、下一張表或頁碼。表格譯文保留所有原始數值；公式按原文保留，不自行更正作者的符號。圖表點選與拖曳仍可使用。

```bash
npm run data:repair-paper01-tables
npm run test:paper01-tables
npm run data:validate
npm run data:render-paper01-review
```

完整表格合併前備份為 `content/paper-01-before-complete-table-repair.json`，包含原資料、單篇 manifest 紀錄及圖表 manifest。原裁切圖片不刪除，新完整裁切使用 `_complete.png`。舊校編稿若有人工修改，不覆蓋該表翻譯或自動吸收其片段，會提示待核對；舊片段 ID 的閱讀位置轉接完整表，筆記與書籤仍保留。只修正第一篇。重建圖表連結後依序重跑 spots、interruptions、tables，再產生核對圖。

1. 在書庫選擇一篇論文的「校編」。
2. 修正章節、擷取原文、忠實翻譯與白話說明。可調整順序、在光標處切段、與下一段合併，或將雜訊段落排除。
3. 內容改寫後會自動降級為草稿。只有忠實翻譯與白話說明都非空白時，才能標為「人工校訂」。
4. 點「試讀」會使用目前本機草稿，不改寫專案資料檔。
5. 點「匯出」取得完整校編 JSON，再從終端寫回專案：

```bash
python3 scripts/import_curated_paper.py /absolute/path/paper-01-curated.json
npm run data:validate
```

全篇納入閱讀的段落都完成人工校訂後，才能執行：

```bash
python3 scripts/import_curated_paper.py /absolute/path/paper-01-curated.json --mark-paper-reviewed
npm run data:publication-gate
```

寫回程式會檢查不可變更的論文身分欄位、PDF SHA-256、段落 ID、順序、頁碼、座標邊界與翻譯狀態，並以原子替換寫入單篇資料和 manifest。

## 驗證

```bash
npm run data:validate
npm run lint
npm run test:references
npx tsc --noEmit
npm run build
```

當本機開發伺服器與 Chrome DevTools Protocol 已啟動時，可在「一次性隔離瀏覽器環境」執行：

```bash
npm run test:browser
```

測試會檢查 8 篇論文書庫、校編表單、PDF 繪製、AI 草稿狀態、試讀轉場、中文翻譯、下一段導覽、圖表與正文解釋關聯、圖表說明段落跳轉、行動版圖表及翻譯切換，以及參考文獻摘要來源、本文引用關係、缺漏摘要處理與同作者同年份候選辨識。測試使用隔離的瀏覽器環境，不會觸碰一般瀏覽器的閱讀資料。

`npm run data:publication-gate` 是內容驗收門檻。在所有納入段落都為人工校訂之前，它必須失敗；這是防止草稿被誤當成完成品的設計。

## 範圍邊界

- 本階段不發布網站。
- 本階段不自動將分段或 AI 翻譯標為已校訂。
- PDF 內單一文字區塊切為兩段時，兩段暫時共用同一原文框；未來需增加字詞層座標校正。
- 圖表共讀與參考文獻功能均已納入本機驗證；自動擷取的書目、摘要摘譯與引用脈絡尚未通過全面人工校訂。
- 只有第一、第二、第三階段各自通過對應驗收，才進入 Codex skill 封裝。

## GitHub Pages 統一入口

遠端儲存庫：`Evan645test/ipbrp-experiment-framework`。根目錄為 GitHub Pages 靜態版，`論文逐段精讀器/` 保留完整來源。

```sh
READER_BASE_PATH=/ipbrp-experiment-framework/ npm run build:static
```

產出在 `dist-static/`，可複製至儲存庫根目錄；保留 `.nojekyll`、原 `experiment-map-html.html` 與 `guide-library.html`。靜態版與本機共用閱讀器，只有圖片改由原圖直接顯示；PDF、圖表、導讀與資料網址依 `paper-reader-base` 設定解析。來源 SHA、段落 ID、進度及筆記格式不變。本機與 GitHub Pages 是不同網站來源，各自保留筆記；可由閱讀器匯出與匯入。
