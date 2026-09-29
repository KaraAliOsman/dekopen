#!/usr/bin/env python3
"""Phase-14 document audit: rasterize every page of emitted PDFs and flag defects.

Usage: python3 /home/ubuntu/phase14-doc-audit.py <pdf_dir> <out_dir>
System python3.10 has pymupdf+pillow. Renders each page at 110 dpi PNG,
reports page count, blank/ near-blank pages, and mojibake-prone text issues.
"""
import sys, os
import pymupdf

def main(pdf_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    report = []
    for name in sorted(os.listdir(pdf_dir)):
        if not name.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, name)
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            report.append(f"{name}: OPEN-FAIL {e}")
            continue
        n = doc.page_count
        blanks, issues = [], []
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(dpi=110)
            out = os.path.join(out_dir, f"{name[:-4]}-p{i+1:02d}.png")
            pix.save(out)
            text = page.get_text().strip()
            # near-blank detection: <40 chars of text and tiny drawn area
            if len(text) < 40 and not page.get_images(full=True) and len(page.get_drawings()) < 5:
                blanks.append(i + 1)
            for bad in ("Ã", "â€", "ï¿", "Â", "Ã©"):
                if bad in text:
                    issues.append(f"p{i+1}:mojibake '{bad}'")
                    break
        report.append(
            f"{name}: {n}p" + (f" near-blank:{blanks}" if blanks else "")
            + (f" issues:{issues}" if issues else "")
        )
        doc.close()
    print("\n".join(report))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
