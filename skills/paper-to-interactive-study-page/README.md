# 論文互動導讀單頁 Skill

`paper-to-interactive-study-page` 將**一篇學術 PDF**整理成一個繁體中文互動導讀 HTML：可點擊的研究架構圖、名詞解釋、統計方法白話說明、四部分論文討論，以及可調整字級的易讀解說。它源自 [I-PBRP 論文導讀網站](https://evan645test.github.io/ipbrp-experiment-framework/) 的製作流程，適合把同一種閱讀方式用於其他論文。

這份 skill 產生的是**單篇導讀頁**。連結中的網站目前還有多篇首頁、逐段精讀、筆記等功能；這些網站功能不包含在本 skill 的產出中。

## 主要能力

- 依原始 PDF 逐頁核對研究目的、設計、樣本、測量、分析、結果與限制，並在說明中標出 PDF 檢視器頁碼。
- 依研究類型調整 Mermaid 架構圖；點選節點即可閱讀說明與證據位置。
- 區分論文報告的結果、作者的解釋與導讀者的審慎推論；不替未報告的內容補造資料。
- 產生一個可分享的 HTML。Mermaid 無法載入時，文字導讀仍可閱讀，架構區會顯示文字流程與重試控制。
- 預設只在本機產生檔案；發布或覆寫線上頁面須另有使用者指示。

## 安裝到 Codex

在 Codex 對話中貼上以下要求。這個儲存庫也保存網站素材；指定 Git 模式可只取 skill 目錄，避免下載整個網站封存檔：

```text
請使用 skill-installer 的 Git 模式（--method git），只安裝這個 skill：
https://github.com/Evan645test/ipbrp-experiment-framework/tree/main/skills/paper-to-interactive-study-page
```

Codex 的 skill installer 支援 GitHub 儲存庫內的 skill 路徑；若已安裝同名 skill，安裝器會停止，避免覆寫既有版本。安裝後開啟新對話，附上論文 PDF 並要求使用 `$paper-to-interactive-study-page` 製作導讀頁。

## 使用方式

對 Codex 說明目標即可，例如：

```text
使用 $paper-to-interactive-study-page，將我附上的學術 PDF 製成繁體中文互動導讀 HTML。請逐頁核對研究設計、數值與頁碼，先儲存在本機。
```

Skill 會依 [`SKILL.md`](SKILL.md) 的流程閱讀 PDF、準備結構化資料、建置 HTML 並檢查手機與桌機版面。輸入 PDF 不會自動上傳到外部服務。

若要自行執行建置器，先複製 [`references/example-input.json`](references/example-input.json) 並將**所有測試文字**換成目標論文的真實證據，再執行：

```bash
cd /path/to/paper-to-interactive-study-page
python3 scripts/build_study_page.py /path/to/input.json --validate-only
python3 scripts/build_study_page.py /path/to/input.json /path/to/output.html
```

建置器使用 Python 3 標準函式庫，無須安裝 Python 套件。產出的 HTML 會從 jsDelivr 或 unpkg 載入 Mermaid 11.17.2；沒有網路時，研究文字及架構圖的文字備援仍可閱讀。建置器預設拒絕覆寫既有輸出；確認要取代時才使用 `--force`。

## 檔案結構

| 路徑 | 用途 |
| --- | --- |
| `SKILL.md` | 觸發條件、證據標準與完整工作流程 |
| `scripts/build_study_page.py` | 驗證 JSON 並產生 HTML |
| `assets/integrated-study-template.html` | 響應式導讀頁模板 |
| `references/content-schema.md` | 輸入格式與論文證據要求 |
| `references/example-input.json` | 僅供格式與建置測試的虛構資料 |
| `references/publishing-and-qa.md` | 發布與瀏覽器驗收規則 |

## 使用界線

產出的導讀是輔助閱讀材料，不能取代原始論文。數值、引文、研究設計與頁碼都須回到 PDF 核對；掃描檔的 OCR 結果尤其需要人工複查。這份 skill 不會把單篇 HTML 自動加入既有多篇網站，也不會自動發布 GitHub Pages。
