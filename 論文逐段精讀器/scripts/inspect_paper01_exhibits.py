#!/usr/bin/env python3
"""Render a read-only contact sheet from original PDF regions for visual QA."""
import json
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent.parent
CORRECTED = {12: [37, 433, 510.51, 582], 13: [37, 286, 510.51, 442]}

def main():
    paper = json.loads((ROOT / "public/data/paper-01.json").read_text())
    source = fitz.open(ROOT / "public/papers/paper-01.pdf")
    sheet = fitz.open()
    figures = [e for e in paper["exhibits"] if e["kind"] == "figure"]
    for start in range(0, len(figures), 6):
        page = sheet.new_page(width=1080, height=1200)
        for i, e in enumerate(figures[start:start+6]):
            bbox = CORRECTED.get(int(e["number"]), e["bbox"][:])
            if bbox[1] < 45:
                bbox[1] = 45
            pix = source[e["page"]-1].get_pixmap(dpi=160, clip=fitz.Rect(bbox), alpha=False)
            x, y = (i % 2)*540, (i//2)*400
            page.insert_text((x+15, y+22), f'{e["label"]} / PDF {e["page"]}', fontsize=15)
            page.insert_image(fitz.Rect(x+10, y+35, x+530, y+385), stream=pix.tobytes("png"))
        path = Path(f"/private/tmp/paper01-exhibit-check-{start//6+1}.png")
        page.get_pixmap().save(path)
        print(path)
    source.close()
    sheet.close()

if __name__ == "__main__":
    main()
