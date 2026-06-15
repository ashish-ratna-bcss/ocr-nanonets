"""Core OCR logic for ACB scanned files, shared by the CLI and the worker.

Wraps Nanonets-OCR2-3B (Qwen2.5-VL based). All model handling lives in the
OCREngine class so it is loaded exactly once per process. Pure helpers
(preprocess, is_degenerate, post_correct) have no model dependency and are
unit-testable on their own.
"""

from __future__ import annotations

import re
from collections import Counter

import cv2
import fitz
import numpy as np
from PIL import Image

MODEL_ID = "nanonets/Nanonets-OCR2-3B"

# Rasterisation DPI. 300 is the document-OCR standard; faint typed scans
# benefit from the extra resolution. matrix scale = DPI / 72.
DEFAULT_DPI = 300

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

# Optional per-file grounding. Recurring proper nouns / reference numbers
# confirmed from clear pages help the model resolve ambiguous glyphs on
# faint pages. Use ONLY for disambiguation, never to overwrite clearly
# different text. Empty by default; the CLI sets it for the test file.
DEFAULT_CASE_CONTEXT = ""

# Auditable post-OCR corrections for KNOWN recurring glyph confusions.
# Every applied change is logged into the page output. Empty by default;
# set per file. Never add dates or page-unique values.
DEFAULT_CORRECTIONS: dict[str, str] = {}


# --------------------------------------------------------------------------
# Pure helpers (no model)
# --------------------------------------------------------------------------
def deskew(gray):
    """Straighten skewed text via min-area-rect of dark pixels. Clamped."""
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
    """grayscale -> denoise -> CLAHE adaptive contrast -> deskew."""
    gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = deskew(gray)
    return Image.fromarray(gray).convert("RGB")


def is_degenerate(text):
    """Detect decoding collapse so sensitive pages aren't trusted blindly."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    if Counter(lines).most_common(1)[0][1] >= 8:
        return True
    if re.search(r"(?:\d{1,3}\s*/\s*){8,}", text):
        return True
    words = text.split()
    if len(words) > 40 and len(set(words)) / len(words) < 0.35:
        return True
    return False


def post_correct(text, corrections):
    """Apply the auditable correction dict. Returns (text, log)."""
    applied = []
    for wrong, right in corrections.items():
        if wrong in text:
            text = text.replace(wrong, right)
            applied.append(f"{wrong}  ->  {right}")
    return text, applied


def render_page(doc, page_idx, dpi=DEFAULT_DPI):
    """Rasterise one PDF page (already-open fitz doc) to a PIL image."""
    scale = dpi / 72.0
    page = doc[page_idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)


def build_prompt(case_context=""):
    if case_context:
        return (
            PROMPT
            + "\n\nREFERENCE (for character disambiguation only, not ground "
            "truth):\n" + case_context
        )
    return PROMPT


# --------------------------------------------------------------------------
# Model engine (loaded once per process)
# --------------------------------------------------------------------------
class OCREngine:
    def __init__(self, model_id=MODEL_ID, dpi=DEFAULT_DPI,
                 case_context=DEFAULT_CASE_CONTEXT,
                 corrections=None):
        # Imported here so the pure helpers above stay importable without
        # torch/transformers installed (e.g. in lightweight API tests).
        import torch
        from transformers import AutoProcessor, AutoModelForImageTextToText

        self.torch = torch
        self.dpi = dpi
        self.case_context = case_context
        self.corrections = corrections or dict(DEFAULT_CORRECTIONS)

        self.processor = AutoProcessor.from_pretrained(
            model_id, trust_remote_code=True
        )
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            dtype=torch.bfloat16,
            device_map="auto",
            attn_implementation="sdpa",
            trust_remote_code=True,
        )

    def _run(self, image, sample=False):
        text = build_prompt(self.case_context)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": text},
                ],
            }
        ]
        prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=prompt, images=image, return_tensors="pt"
        )
        inputs = {
            k: v.to(self.model.device) if hasattr(v, "to") else v
            for k, v in inputs.items()
        }
        gen = dict(max_new_tokens=2048, repetition_penalty=1.15)
        if sample:
            gen.update(do_sample=True, temperature=0.3, top_p=0.9)
        else:
            gen.update(do_sample=False, temperature=None,
                       top_p=None, top_k=None)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, **gen)
        trimmed = [
            o[len(i):] for i, o in zip(inputs["input_ids"], out)
        ]
        return self.processor.batch_decode(
            trimmed, skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

    def ocr_image(self, image):
        """Full single-page pipeline: preprocess -> OCR -> degeneration
        retry -> auditable correction. Returns markdown for one page."""
        image = preprocess(image)
        result = self._run(image, sample=False)
        flagged = False

        if is_degenerate(result):
            retry = self._run(image, sample=True)
            if is_degenerate(retry):
                flagged = True
            else:
                result = retry

        result, corrections = post_correct(result, self.corrections)
        if corrections:
            audit = "\n".join(f"- `{c}`" for c in corrections)
            result += (
                "\n\n> **Auto-corrections applied** (verify against "
                "original):\n" + audit
            )
        if flagged:
            result = (
                "> **NEEDS MANUAL REVIEW** - automatic OCR was unreliable "
                "for this page (faint/skewed/low-quality scan). Do not trust "
                "the text below as evidence; transcribe by hand.\n\n"
                + result
            )
        # Free per-page activations so long jobs don't accumulate VRAM.
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
        return result

    def ocr_pdf_page(self, doc, page_idx):
        return self.ocr_image(render_page(doc, page_idx, self.dpi))
