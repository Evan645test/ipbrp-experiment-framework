# Integrated study-page content schema

Read this before preparing the builder input. All human-readable strings must be paraphrases grounded in the paper. Page fields use one-based PDF-viewer pages such as `PDF第6頁` or `PDF第6、8頁（文獻頁123）`.

For a complete builder-valid starting point, use [example-input.json](example-input.json) and replace every sample claim with evidence from the target paper.

## Required JSON shape

```json
{
  "page_title": "研究名稱｜互動導讀",
  "title": "研究名稱：互動導讀",
  "subtitle": "架構圖、名詞、核心討論與易讀解說",
  "source_note": "內容依據原始論文整理；頁碼為PDF檢視器頁碼。",
  "mermaid": "flowchart TD\nA[\"研究目的\"] --> B[\"研究對象\"]",
  "node_details": {
    "A": {
      "title": "研究目的",
      "summary": "作者想回答的核心問題。",
      "explanation": "白話說明這個節點及其研究角色。",
      "page": "PDF第1頁",
      "color": "#315F91"
    }
  },
  "statistics": [
    {
      "name": "線性混合效應模型",
      "label": "LMM",
      "meaning": "這個方法在本文回答什麼問題。",
      "reason": "為什麼適合本文的資料結構。",
      "caution": "最重要的解讀限制。",
      "color": "#4F46E5"
    }
  ],
  "glossary": [
    {
      "term": "CT",
      "full_name": "Computational Thinking／運算思維",
      "explanation": "本文如何界定或使用這個名詞。",
      "page": "PDF第2頁",
      "color": "#315F91"
    }
  ],
  "discussions": [
    {
      "title": "研究目的、重要性與過去嘗試",
      "question": "這篇論文的主要目的為何，為什麼重要，過去有哪些研究成果？",
      "blocks": [
        {"type": "subheading", "text": "研究目的"},
        {"type": "paragraph", "text": "以論文證據回答。"},
        {"type": "bullets", "items": ["重要性一", "過去嘗試一"]}
      ],
      "page": "PDF第1至5頁"
    },
    {
      "title": "研究不足、策略與理論",
      "question": "既有研究有何不足，本文提出什麼策略，其理論基礎為何？",
      "blocks": [{"type": "paragraph", "text": "依據文獻回顧與理論架構回答。"}],
      "page": "PDF第3至6頁"
    },
    {
      "title": "研究問題與研究設計",
      "question": "作者提出哪些研究問題，如何蒐集資料並回答？",
      "blocks": [{"type": "paragraph", "text": "整理對象、分組、測量與流程。"}],
      "page": "PDF第6至10頁"
    },
    {
      "title": "研究結果與作者解釋",
      "question": "研究得到什麼結果，作者如何解釋？",
      "blocks": [{"type": "paragraph", "text": "區分直接結果、作者解釋與合理保留。"}],
      "page": "PDF第11至17頁"
    }
  ],
  "easy_read": {
    "intro": "用一小段話交代原文、研究背景與閱讀定位。",
    "sections": [
      {
        "title": "先說結論",
        "blocks": [
          {"type": "paragraph", "text": "用白話先回答研究的核心問題。"},
          {"type": "note", "text": "提醒結果的適用範圍。"}
        ]
      }
    ]
  }
}
```

Every top-level key is required. `statistics` and `glossary` may be empty arrays only when the paper genuinely has no applicable entries. `discussions` must contain four core entries and may contain one optional fifth reflection entry. `easy_read.sections` must not be empty.

## Content blocks

The same safe block format is used by discussions and easy-read sections. Do not put HTML in strings; the builder escapes and renders text.

- Paragraph: `{"type":"paragraph","text":"..."}`
- Subheading: `{"type":"subheading","text":"..."}`
- Caution/note: `{"type":"note","text":"..."}`
- Bullets: `{"type":"bullets","items":["...","..."]}`
- Numbered list: `{"type":"numbered","items":["...","..."]}`
- Table: `{"type":"table","headers":["欄一","欄二"],"rows":[["值一","值二"]]}`

Tables require two or more headers, at least one row, and the same cell count in every row.

## Evidence rules

- Include exact sample sizes, analytic sample, attrition, setting, age or grade, and recruitment when reported.
- Describe allocation exactly as reported. If the abstract and method conflict, state the conflict rather than resolving it silently.
- Record intervention duration, frequency, instructor, materials, sequence, comparison condition, and fidelity when applicable.
- Identify every measurement occasion and instrument, what higher/lower scores mean, and reported reliability.
- For results, specify the exact comparison, direction, magnitude, uncertainty, and time point. Do not convert a within-group p-value into evidence of treatment superiority.
- Mark mechanisms such as reduced cognitive load or stronger knowledge integration as author interpretation unless directly measured.
- Keep direct quotation minimal; paraphrase without changing technical meaning.

## Stable visual colors

- Common research stages and general concepts: `#315F91`
- Ambiguity, reporting conflict, or caution: `#A14A3C`
- Intervention or focal strategy: `#D97706`
- Comparison condition: `#16865B`
- Behavioral, process, or qualitative data: `#7956A8`
- Findings: `#4F46E5`

## Final content audit

- Every documented Mermaid node has a matching declaration, and every visible reader-relevant node has a detail entry.
- Central claims contain page evidence; page ranges match the PDF viewer.
- Group counts reconcile with total and attrition.
- Research questions align with measures and analyses.
- Results, author explanations, and your inference are visibly distinct.
- Contradictions and likely typographical errors are described cautiously and checked against the relevant table or figure.
