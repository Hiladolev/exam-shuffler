# Generic multi-page OCR processing in app.py

## Problem

`app.py` hardcodes `PAGE_NUMBER = 3` and calls `run_ocr(pdf_path, page_number)` for that single page only. `test_ocr.py`'s `__main__` block already loops all pages and skips blank ones, but nobody updated `app.py` to use that logic when it was added — `app.py` still predates it. The app therefore can't process a full exam PDF or handle exams with a different page count/layout than the one it was manually tested against.

## Investigation findings

- `PAGE_NUMBER = 3` was a leftover from early manual testing, not a deliberate choice. `app.py` (commit `17b23e4`) was written *before* `test_ocr.py` gained its multi-page loop (commit `4908d60`); at the time, `run_ocr` only supported one page, so `3` was hand-picked as "the first page with real question content" in the one sample exam being tested against.
- Page-numbering assumptions (verified against `ocr_output.txt` from the full 16-page/8-content-page sample exam):
  - PDF page 1 is the instructions page.
  - Even PDF pages are blank backs (double-sided printing).
  - The exam's printed footer page number is offset from the PDF's physical page index by exactly one "printed page" (e.g. PDF page 3's footer reads "עמוד 2"). This offset doesn't need to be parsed or relied on directly — skipping page 1 and filtering near-empty pages achieves the same result generically.
- PDF library: `pdf2image` (poppler) + `pytesseract`, already in use.
  - `pdf2image.pdfinfo_from_path(pdf_path, poppler_path=...)` returns total page count via its `'Pages'` key — confirmed against the sample PDF (`Pages: 16`). Cheap, no image conversion needed.
  - No cheap way to detect a blank page without OCR: `pdftotext` (poppler) was tested directly against the sample PDF and returned nothing — these PDFs have no embedded text layer (image-based scans). OCR and blank-detection are the same operation here (`test_ocr.py`'s existing `MIN_PAGE_TEXT_LENGTH = 10` check already does this: OCR every page, discard ones under 10 chars).

## Design

Run OCR across all pages except page 1, in order, updating a progress bar as each page is attempted — including pages that turn out blank, which just process quickly and get discarded by the existing `MIN_PAGE_TEXT_LENGTH` check. No separate blank-detection pre-pass.

### `test_ocr.py` — `run_ocr_all_pages`

New generator function, kept free of any Streamlit dependency (matches `parser.py`/`shuffler_core.py`'s existing pattern — OCR/PDF handling stays separate from UI concerns):

```python
from pdf2image import convert_from_path, pdfinfo_from_path
import pytesseract

def run_ocr_all_pages(pdf_path, poppler_path=POPPLER_PATH):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)["Pages"]
    if total_pages < 2:
        return
    images = convert_from_path(
        pdf_path, first_page=2, last_page=total_pages, poppler_path=poppler_path
    )
    for page_number, image in zip(range(2, total_pages + 1), images):
        text = pytesseract.image_to_string(image, lang="heb+eng")
        yield page_number, text
```

Converts pages 2..N in a single `convert_from_path` call (one poppler subprocess) rather than one call per page, since rasterization doesn't need to happen incrementally — only OCR (the slow step, done per-page inside the loop) needs to drive progress updates.

The existing single-page `run_ocr(pdf_path, page_number)` is unchanged and still used elsewhere; no removal.

### `app.py` — `run_pipeline`

Owns the loop, the progress bar, and blank-page filtering — the same orchestration role it already has:

```python
from pdf2image import pdfinfo_from_path
from test_ocr import run_ocr_all_pages, MIN_PAGE_TEXT_LENGTH, POPPLER_PATH

def run_pipeline(pdf_path):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=POPPLER_PATH)["Pages"]
    total_to_process = max(total_pages - 1, 0)

    progress = st.progress(0)
    raw_texts = []
    for i, (page_number, text) in enumerate(run_ocr_all_pages(pdf_path), start=1):
        if len(text.strip()) >= MIN_PAGE_TEXT_LENGTH:
            raw_texts.append(text)
        progress.progress(i / total_to_process)
    progress.empty()

    raw_text = "\n\n".join(raw_texts)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)
    # ... rest unchanged (clean/needs_review split, shuffle) ...
```

- `PAGE_NUMBER = 3` constant removed. Call site changes from `run_pipeline(UPLOAD_PATH, PAGE_NUMBER)` to `run_pipeline(UPLOAD_PATH)`.
- Progress denominator is `total_pages - 1` (all pages except page 1), known upfront via `pdfinfo_from_path`. Numerator advances once per page attempted, whether or not it turns out blank.
- Downstream logic (clean/needs_review split via choice-count check, shuffling, `build_final_content`) is unchanged.

### Page joining: no `=== PAGE N ===` markers

Kept pages are joined with `"\n\n"`, not the `=== PAGE N ===` marker line that `test_ocr.py`'s `__main__` writes to `ocr_output.txt`.

Reason: `strip_version_lines`'s `PAGE_NUMBER_PATTERN` only matches the Hebrew "מספר עמוד" footer text, not an English marker line — so a marker would survive stripping and land right after the previous page's content. If it lands right after a choice line, `parse_ocr_text`'s block loop (`in_choices` still `True`, line is non-empty and doesn't match `CHOICE_PATTERN`) appends it onto that choice's text, corrupting it without changing the choice count — meaning it wouldn't trip the `needs_review` flag and could go unnoticed.

`app.py` never had markers before (it only ever OCR'd one page), so omitting them isn't a behavior change — it avoids introducing this corruption risk. A blank-line separator is safe in both directions: `parse_ocr_text` skips blank lines without resetting `in_choices` or starting a new block, so a question whose choices genuinely continue across a page boundary still parses correctly.

## Error handling

No new error handling for malformed PDFs. `st.file_uploader(type="pdf")` is the existing validation boundary; `pdfinfo_from_path`/OCR failures on a genuinely broken upload weren't handled before this change either, and aren't part of this problem.

## Testing

- `run_ocr_all_pages` isn't easily unit-testable without a real PDF and tesseract install — consistent with the project's existing pattern of testing `parser.py`/`shuffler_core.py` but not the OCR I/O layer (`run_ocr` has no test coverage today either).
- Manual verification: run the app against `sample_exams/data_science_test_havana.pdf` (the full 16-page/8-content-page exam). This unblocks Task 5 of the generic-split implementation plan (`docs/superpowers/plans/2026-07-23-generic-split-implementation.md`), which was waiting on exactly this limitation to confirm the question-18/19/20 split against the full exam.

## Explicitly out of scope

- No footer-page-number parsing/reconciliation — skipping page 1 plus the existing blank-page filter achieves the same result without depending on the printed-vs-physical offset.
- No cheap pre-OCR blank-page heuristic (e.g. image-based whitespace check) — investigated and rejected; no embedded text layer exists to check cheaply, and an image-based heuristic would be new complexity not covered by this problem.
- No change to `parse_ocr_text`, `strip_version_lines`, or the clean/needs_review flagging logic.
