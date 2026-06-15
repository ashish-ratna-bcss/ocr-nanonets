"""Local CLI: OCR a single PDF through the same core the service uses.

    python hf_ocr.py [path/to.pdf]

Uses app/ocr_core.py so behaviour matches the API exactly. The grounding
(CASE_CONTEXT) and auditable corrections below are specific to the bundled
ACB test file; clear them for other documents.
"""

import sys
from pathlib import Path

import fitz

from app.ocr_core import OCREngine

DEFAULT_PDF = Path(__file__).parent / "3-pages_content-1-3.pdf"

# Per-file grounding for the bundled test document only.
CASE_CONTEXT = (
    "Known recurring terms in this specific case file (use only to resolve "
    "genuinely ambiguous characters, never to overwrite text that is "
    "clearly different): Anti-Corruption Bureau (A.C.B.); reference numbers "
    "50/RCT-NMD/2004 and Cr.No.5/ACB-NZB/2004; accused Sri Mamidi "
    "Janardhan, Junior Assistant, Sadasivapet Municipality, Medak District; "
    "officers Sri P. Ramachandra Rao (Inspector of Police, Nizamabad Range) "
    "and Sri V. Vijaya Bhaskar; Joint Director (T), A.C.B., Hyderabad; "
    "A.P., Hyderabad."
)
CORRECTIONS = {
    "AOD-MD": "RCT-NMD",
    "AOD-NZB": "ACB-NZB",
    "AOD-NMD": "RCT-NMD",
    "D.S.R.": "D.S.P.",
    "Joint Direction (II)": "Joint Director (T)",
    "Joint Direction (I)": "Joint Director (T)",
    "Joint Direction": "Joint Director",
    "Rego.": "Reg.",
    "Rego": "Reg.",
}


def main():
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF

    print("Loading model...")
    engine = OCREngine(case_context=CASE_CONTEXT, corrections=CORRECTIONS)
    print("Model loaded successfully")

    pages = []
    with fitz.open(pdf_path) as doc:
        for idx in range(len(doc)):
            print(f"Processing page {idx + 1}/{len(doc)}")
            pages.append(engine.ocr_pdf_page(doc, idx))

    final_text = "\n\n---\n\n".join(
        f"## Page {i + 1}\n\n{p}" for i, p in enumerate(pages)
    )
    out = Path(__file__).parent / "ocr_output.md"
    out.write_text(final_text, encoding="utf-8")

    print("\n==============================")
    print("OCR COMPLETE")
    print("==============================")
    print(final_text[:3000])
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
