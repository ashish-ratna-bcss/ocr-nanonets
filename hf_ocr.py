"""ACB (Anti-Corruption Bureau, Telangana) scanned-file OCR pipeline.

Nanonets-OCR2-3B (Qwen2.5-VL based) running on an NVIDIA RTX A4000.

Industrial document-OCR practices applied:
  - High-DPI rasterisation of each PDF page.
  - OpenCV preprocessing: grayscale -> denoise -> CLAHE adaptive contrast
    -> deskew. Keeps grayscale (not binarised) because the VLM reads
    natural-looking text better than hard thresholds.
  - Greedy decoding with a mild repetition penalty.
  - Degeneration detection (repeated lines / runaway number sequences /
    low lexical diversity). On detection: one sampled retry, then the page
    is flagged NEEDS MANUAL REVIEW so fabricated text never enters the
    record silently. This matters: the source is sensitive legal evidence.
"""

import re
from collections import Counter
from pathlib import Path

import cv2
import fitz
import numpy as np
import torch
from PIL import Image
from transformers import (
    AutoProcessor,
    AutoModelForImageTextToText,
)

MODEL_ID = "nanonets/Nanonets-OCR2-3B"

# Test doc resolved relative to this script, so it works on any machine
# as long as the PDF sits next to hf_ocr.py.
PDF_PATH = str(Path(__file__).parent / "3-pages_content-1-3.pdf")

# Rasterisation DPI. 300 is the document-OCR standard; faint typed scans
# benefit from the extra resolution. matrix scale = DPI / 72.
RENDER_DPI = 300

PROMPT = (
    "This is a scanned case file from the Anti-Corruption Bureau (ACB), "
    "Government of Telangana. It contains sensitive law-enforcement "
    "content: file/crime numbers, dates, names, officer designations, "
    "statute references, monetary amounts and official endorsements. The "
    "text may be in English and/or Telugu.\n\n"
    "Transcribe ALL printed and handwritten text exactly as written, "
    "character for character, in its original language/script. Accuracy "
    "is critical because this is sensitive legal evidence.\n\n"
    "Rules:\n"
    "- Do NOT guess, paraphrase, correct, or autocomplete any word, "
    "number, name, or abbreviation. Reproduce exactly what is on the "
    "page.\n"
    "- Keep file numbers, crime numbers, dates and amounts (e.g. Rs.400/-) "
    "digit-for-digit as shown.\n"
    "- If a word or character is unreadable, output [illegible] rather than "
    "inventing text. If partly readable, transcribe the certain part and "
    "mark the rest [illegible]. Never fabricate numbers or names.\n\n"
    "LAYOUT - preserve content block positions:\n"
    "- Split the page into its distinct content blocks (note paragraphs, "
    "the boxed certificate, margin endorsements, signatures, stamps).\n"
    "- Output blocks in top-to-bottom, left-to-right spatial order.\n"
    "- Start each block with a region label on its own line in the form: "
    "[BLOCK: <position>] where position is one of top-left, top-center, "
    "top-right, middle-left, center, middle-right, bottom-left, "
    "bottom-center, bottom-right, left-margin, right-margin.\n"
    "- Keep original line breaks within each block.\n\n"
    "STAMPS AND SEALS - extract fully:\n"
    "- For every stamp, seal or boxed official endorsement, transcribe ALL "
    "text inside it verbatim.\n"
    "- Wrap it as <stamp>...full text...</stamp> and note its shape/type if "
    "clear (rectangular stamp, round seal) and the ink colour if "
    "distinguishable.\n"
    "- Include any stamped file numbers, memo numbers, dates and department "
    "names exactly.\n\n"
    "- Represent a signature/initial as <signature>name</signature>, using "
    "the name if readable or <signature>[illegible]</signature> if not. Tag "
    "each distinct signature only ONCE; do not repeat the tag or list the "
    "same mark many times.\n"
    "- Do not add commentary, summaries, or text that is not visibly "
    "present in the document."
)

# Optional grounding for THIS specific case file. Recurring proper nouns
# and reference numbers (confirmed from the clear pages) help the model
# resolve ambiguous glyphs on faint pages - e.g. read 'A.C.B.' not 'A.G.D.'
# Use ONLY for disambiguation, never to overwrite clearly different text.
# Leave as "" for an unknown document; for production, derive this per
# file from a case master-index or from the high-confidence pages.
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

# Auditable post-OCR corrections for KNOWN recurring glyph confusions in
# this case file (e.g. faint typed pages read 'D.S.R.' for 'D.S.P.'). Every
# applied change is logged into the page output so a reviewer can audit it -
# this is deterministic post-correction, NOT silent rewriting. Only put
# here terms whose correct form is confirmed from the clear pages. Do NOT
# add dates or page-unique values. Leave empty {} to disable.
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


def post_correct(text):
    """Apply the auditable correction dictionary. Returns (text, log)."""
    applied = []
    for wrong, right in CORRECTIONS.items():
        if wrong in text:
            text = text.replace(wrong, right)
            applied.append(f"{wrong}  ->  {right}")
    return text, applied


# --------------------------------------------------------------------------
# Image preprocessing (OpenCV)
# --------------------------------------------------------------------------
def deskew(gray):
    """Estimate text skew via the minimum-area rectangle of dark pixels and
    rotate to straighten. Clamped to +/-15 deg to avoid wild rotations on
    sparse pages."""
    inv = cv2.bitwise_not(gray)
    thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    if len(coords) < 50:
        return gray
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.3 or abs(angle) > 15:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, m, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def preprocess(pil_img):
    """grayscale -> denoise -> CLAHE adaptive contrast -> deskew.

    Rescues faint/low-contrast pages (which otherwise make the model bail
    or hallucinate) without binarising, which the VLM handles better.
    """
    gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = deskew(gray)
    return Image.fromarray(gray).convert("RGB")


# --------------------------------------------------------------------------
# Output quality checks
# --------------------------------------------------------------------------
def is_degenerate(text):
    """Detect decoding collapse so sensitive pages aren't trusted blindly."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    # Same line emitted many times (signature-loop style collapse).
    if Counter(lines).most_common(1)[0][1] >= 8:
        return True
    # Runaway "/NN/NN/NN/..." number explosion.
    if re.search(r"(?:\d{1,3}\s*/\s*){8,}", text):
        return True
    # Very low lexical diversity over a non-trivial amount of text.
    words = text.split()
    if len(words) > 40 and len(set(words)) / len(words) < 0.35:
        return True
    return False


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
print("Loading processor...")
processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)

print("Loading model...")
model = AutoModelForImageTextToText.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16,
    device_map="auto",
    attn_implementation="sdpa",
    trust_remote_code=True,
)
print("Model loaded successfully")


def run_ocr(image, sample=False):
    """Single OCR pass. sample=True uses low-temperature sampling, which
    often escapes a greedy degeneration loop on a retry."""
    text = PROMPT
    if CASE_CONTEXT:
        text = (
            PROMPT
            + "\n\nREFERENCE (for character disambiguation only, not ground "
            "truth):\n" + CASE_CONTEXT
        )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": text},
            ],
        }
    ]
    prompt = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(text=prompt, images=image, return_tensors="pt")
    inputs = {
        k: v.to(model.device) if hasattr(v, "to") else v
        for k, v in inputs.items()
    }

    gen_kwargs = dict(
        max_new_tokens=2048,
        repetition_penalty=1.15,
    )
    if sample:
        gen_kwargs.update(do_sample=True, temperature=0.3, top_p=0.9)
    else:
        gen_kwargs.update(do_sample=False, temperature=None,
                          top_p=None, top_k=None)

    with torch.inference_mode():
        generated_ids = model.generate(**inputs, **gen_kwargs)

    trimmed = [
        out_ids[len(in_ids):]
        for in_ids, out_ids in zip(inputs["input_ids"], generated_ids)
    ]
    return processor.batch_decode(
        trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------
doc = fitz.open(PDF_PATH)
scale = RENDER_DPI / 72.0
all_pages = []

for page_idx in range(len(doc)):
    print(f"Processing page {page_idx + 1}/{len(doc)}")

    page = doc[page_idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    image = preprocess(image)

    result = run_ocr(image, sample=False)
    flagged = False

    if is_degenerate(result):
        print(f"  page {page_idx + 1}: degenerate output, retrying (sampled)...")
        retry = run_ocr(image, sample=True)
        if is_degenerate(retry):
            flagged = True
            print(f"  page {page_idx + 1}: still degraded -> flagged for manual review")
        else:
            result = retry

    # Auditable deterministic post-correction of known recurring confusions.
    result, corrections = post_correct(result)
    if corrections:
        print(f"  page {page_idx + 1}: applied {len(corrections)} correction(s)")
        audit = "\n".join(f"- `{c}`" for c in corrections)
        result = (
            result
            + "\n\n> **Auto-corrections applied** (verify against original):\n"
            + audit
        )

    if flagged:
        result = (
            "> **NEEDS MANUAL REVIEW** - automatic OCR was unreliable for "
            "this page (faint/skewed/low-quality scan). Do not trust the "
            "text below as evidence; transcribe by hand.\n\n"
            + result
        )

    all_pages.append(result)

final_text = "\n\n---\n\n".join(
    f"## Page {i + 1}\n\n{page}" for i, page in enumerate(all_pages)
)

OUTPUT_PATH = str(Path(__file__).parent / "ocr_output.md")
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(final_text)

print("\n==============================")
print("OCR COMPLETE")
print("==============================")
print(final_text[:3000])
print(f"\nSaved to {OUTPUT_PATH}")
