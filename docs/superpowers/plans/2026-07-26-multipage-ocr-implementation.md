# Generic Multi-Page OCR Processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `app.py`'s hardcoded `PAGE_NUMBER = 3` single-page OCR call with a generic loop that processes every page of an uploaded exam PDF, so the app works on exams of any page count instead of just the one it was manually tested against.

**Architecture:** `test_ocr.py` gains a new Streamlit-free generator, `run_ocr_all_pages`, that yields `(page_number, text)` for every page except page 1, using `pdf2image.pdfinfo_from_path` to learn the total page count upfront. `app.py`'s `run_pipeline` drives that generator, filters out near-empty (blank) pages with the existing `MIN_PAGE_TEXT_LENGTH` threshold, drives a `st.progress` bar as it goes, and concatenates the surviving page texts (joined by blank lines, no page markers) before handing off to the unchanged `strip_version_lines` / `parse_ocr_text` / flagging / shuffling pipeline.

**Tech Stack:** Python, Streamlit, `pdf2image` (poppler), `pytesseract` — all already in use in this project.

**Spec:** `docs/superpowers/specs/2026-07-26-multipage-ocr-design.md`

---

### Task 1: Add `run_ocr_all_pages` to `test_ocr.py`

**Files:**
- Modify: `test_ocr.py:1`, `test_ocr.py:18` (insert new function after `run_ocr`)

- [ ] **Step 1: Add the `pdfinfo_from_path` import**

In `test_ocr.py`, change line 1 from:

```python
from pdf2image import convert_from_path
```

to:

```python
from pdf2image import convert_from_path, pdfinfo_from_path
```

- [ ] **Step 2: Add the `run_ocr_all_pages` generator**

Insert this new function immediately after `run_ocr` (after line 18, before the blank lines preceding `if __name__ == "__main__":`):

```python
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

This always skips page 1 (the instructions page) by starting the range at 2. It converts pages 2..N in a single `convert_from_path` call (one poppler subprocess) rather than one call per page, since only OCR — done per-page inside the loop — needs to happen incrementally for progress reporting.

- [ ] **Step 3: Manually verify against the sample exam**

`run_ocr_all_pages` isn't unit-testable without a real PDF and a working tesseract/poppler install — same as the existing `run_ocr`, which has no test coverage either (matches this project's existing pattern: `parser.py`/`shuffler_core.py` are unit tested, the OCR I/O layer is not).

Run:

```bash
python -c "
from test_ocr import run_ocr_all_pages, MIN_PAGE_TEXT_LENGTH
pages = list(run_ocr_all_pages('sample_exams/data_science_test_havana.pdf'))
print('total yielded:', len(pages))
kept = [n for n, t in pages if len(t.strip()) >= MIN_PAGE_TEXT_LENGTH]
print('kept page numbers:', kept)
"
```

Expected output:

```
total yielded: 15
kept page numbers: [3, 5, 7, 9, 11, 13, 15]
```

(16 total pages in the sample PDF minus page 1 = 15 yielded; of those, the 7 odd pages 3–15 contain real question content and pass the `MIN_PAGE_TEXT_LENGTH` filter — the even pages are blank backs, matching the page-numbering pattern confirmed in the design doc's investigation.)

This step takes a couple of minutes since it runs real OCR on 15 pages.

- [ ] **Step 4: Commit**

```bash
git add test_ocr.py
git commit -m "Add run_ocr_all_pages generator for looping OCR across an exam's pages"
```

---

### Task 2: Rewire `app.py`'s `run_pipeline` to use `run_ocr_all_pages`

**Files:**
- Modify: `app.py:1-11` (imports), `app.py:11-25` (`run_pipeline`), `app.py:77` (call site)

Before starting: if a Streamlit server is currently running from earlier testing, stop it first — this task edits `test_ocr.py`, and per `CLAUDE.md`'s Development Workflow, a running server keeps using the old cached version of an already-imported module.

- [ ] **Step 1: Update imports and remove `PAGE_NUMBER`**

Change lines 1-8 of `app.py` from:

```python
import streamlit as st

from test_ocr import run_ocr
from parser import strip_version_lines, parse_ocr_text, find_split_suggestions
from shuffler_core import shuffle_questions, split_choices

PAGE_NUMBER = 3
UPLOAD_PATH = "uploaded_exam.pdf"
```

to:

```python
import streamlit as st
from pdf2image import pdfinfo_from_path

from test_ocr import run_ocr_all_pages, MIN_PAGE_TEXT_LENGTH, POPPLER_PATH
from parser import strip_version_lines, parse_ocr_text, find_split_suggestions
from shuffler_core import shuffle_questions, split_choices

UPLOAD_PATH = "uploaded_exam.pdf"
```

- [ ] **Step 2: Replace `run_pipeline`'s body**

Change (currently lines 11-25):

```python
def run_pipeline(pdf_path, page_number):
    raw_text = run_ocr(pdf_path, page_number)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            needs_review.append(q)
        else:
            clean_questions.append(q)

    shuffled_questions = shuffle_questions(clean_questions)
    return shuffled_questions, needs_review
```

to:

```python
def run_pipeline(pdf_path):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=POPPLER_PATH)["Pages"]
    total_to_process = total_pages - 1

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

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            needs_review.append(q)
        else:
            clean_questions.append(q)

    shuffled_questions = shuffle_questions(clean_questions)
    return shuffled_questions, needs_review
```

`total_to_process` is never zero when the loop body actually runs: `run_ocr_all_pages` returns immediately without yielding anything when `total_pages < 2`, so `progress.progress(i / total_to_process)` is only ever reached when `total_to_process >= 1`.

- [ ] **Step 3: Update the call site**

Change (currently line 77):

```python
        shuffled_questions, needs_review = run_pipeline(UPLOAD_PATH, PAGE_NUMBER)
```

to:

```python
        shuffled_questions, needs_review = run_pipeline(UPLOAD_PATH)
```

- [ ] **Step 4: Syntax-check both files**

```bash
python -m py_compile app.py test_ocr.py
```

Expected: no output, exit code 0.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "Loop OCR across all pages in app.py instead of hardcoded PAGE_NUMBER"
```

---

### Task 3: Manual end-to-end verification and docs update

**Files:**
- Modify: `CLAUDE.md:5-19` (Project Status section)
- Modify: `docs/superpowers/plans/2026-07-23-generic-split-implementation.md:317-333` (Task 5 checkboxes)

- [ ] **Step 1: Run the full pipeline against the real exam**

Start the Streamlit server:

```bash
streamlit run app.py
```

In the browser, upload `sample_exams/data_science_test_havana.pdf` and click "Process". Confirm:
- A progress bar appears, advances through 15 steps, and disappears once processing completes (matching Task 1's confirmed 15 yielded pages).
- The app doesn't error or hang.

- [ ] **Step 2: Confirm the question-18/19/20 block still splits correctly**

This is the scenario Task 5 of `docs/superpowers/plans/2026-07-23-generic-split-implementation.md` was blocked on. Find the flagged block that used to contain questions 18, 19, and 20. Confirm the split input shows auto-suggested split points (2 of them, or fewer if OCR mangling defeats detection for one boundary — expected per that plan's design doc). Adjust split points if needed so the block splits into exactly 3 parts, clean up each part's text/choices in the edit boxes, then click "Generate Final File" and confirm the download contains all 3 questions with correct, shuffled choices.

- [ ] **Step 3: Record the observed question counts**

Note how many questions were parsed clean vs. flagged into needs_review. `CLAUDE.md` documents a prior baseline of "20 real questions in, 13 parsed clean and 3 flagged" from before this change — that run concatenated pages with `=== PAGE N ===` marker lines (a corruption risk described in the design doc), so some difference from that baseline is expected and fine; write down what you actually observe for Step 5.

- [ ] **Step 4: Stop the Streamlit server**

Press `Ctrl+C` in the terminal running `streamlit run app.py`.

- [ ] **Step 5: Update `CLAUDE.md`'s Project Status section**

Replace this paragraph (currently line 17):

```markdown
Task 5 of that plan (manual end-to-end verification against the full 8-page exam, confirming the 18/19/20 block splits correctly) is **blocked**: `app.py` hardcodes `PAGE_NUMBER = 3` and only OCRs that single page (`run_pipeline` → `run_ocr(pdf_path, page_number)`), unlike `test_ocr.py`'s `__main__` which loops all pages. The app as it stands can't reproduce the full multi-page exam scenario. Fixing this (looping all pages in `app.py`'s pipeline, like `test_ocr.py` already does) is out of scope for the split-feature plan and needs its own design/plan session before Task 5 can be attempted.
```

with (filling in the `[...]` counts from Step 3):

```markdown
`app.py` no longer hardcodes a single page: `run_pipeline` now uses `test_ocr.py`'s `run_ocr_all_pages` generator to OCR every page except page 1, filtering blank pages via the existing `MIN_PAGE_TEXT_LENGTH` check and showing a `st.progress` bar as it goes. Design: `docs/superpowers/specs/2026-07-26-multipage-ocr-design.md`. Plan: `docs/superpowers/plans/2026-07-26-multipage-ocr-implementation.md`.

This unblocked Task 5 of the generic-split plan: running the full 8-page exam through the app end-to-end now works, with the 18/19/20 block still splitting correctly into 3 parts. Observed counts on this run: [...] parsed clean, [...] flagged into needs_review (see `docs/superpowers/plans/2026-07-23-generic-split-implementation.md` Task 5 for the prior baseline and why small differences from it are expected).
```

Also update the first paragraph of that section (currently line 7), which still describes the old single-page baseline:

```markdown
The core pipeline works end-to-end on a full 8-page exam (all pages with question content, out of 16 total including blank backs): 20 real questions in, 13 parsed clean and 3 flagged into needs_review.
```

Replace `20 real questions in, 13 parsed clean and 3 flagged into needs_review` with the counts observed in Step 3.

- [ ] **Step 6: Mark Task 5 done in the generic-split plan**

In `docs/superpowers/plans/2026-07-23-generic-split-implementation.md`, change the three checkboxes under "Task 5: Manual end-to-end verification with the full 8-page exam" (currently lines 321, 325, 329) from `- [ ]` to `- [x]`, and add a note above them:

```markdown
### Task 5: Manual end-to-end verification with the full 8-page exam

**Files:** none (manual verification only)

Unblocked and completed via `docs/superpowers/plans/2026-07-26-multipage-ocr-implementation.md`, which replaced `app.py`'s hardcoded `PAGE_NUMBER` with a generic all-pages loop.

- [x] **Step 1: Run the full pipeline against the real exam**
```

(leaving the rest of Steps 1-3's existing text as-is, just checking the two remaining boxes).

- [ ] **Step 7: Commit the docs update**

```bash
git add CLAUDE.md docs/superpowers/plans/2026-07-23-generic-split-implementation.md
git commit -m "Document multi-page OCR fix and mark generic-split Task 5 complete"
```

---

## Self-Review Notes

- **Spec coverage:** `run_ocr_all_pages` (Task 1) covers the spec's `test_ocr.py` component including the single-`convert_from_path`-call efficiency note. `run_pipeline`'s rewrite (Task 2) covers progress-bar semantics (denominator = `total_pages - 1`, numerator advances per page attempted including blanks), the blank-line-not-marker join decision, and removal of `PAGE_NUMBER`. Task 3 covers the spec's Testing section (manual verification against the full sample exam, unblocking Task 5 of the generic-split plan) and updates the docs the spec referenced as stale.
- **Type consistency:** `run_ocr_all_pages(pdf_path, poppler_path=POPPLER_PATH)` signature matches its use in `app.py` (`run_ocr_all_pages(pdf_path)`, relying on the default) and in Task 1's manual verification command. `run_pipeline(pdf_path)`'s new single-argument signature matches its updated call site in Task 2 Step 3.
- **No changes to `parse_ocr_text`, `strip_version_lines`, or the clean/needs_review flagging logic** — matches the spec's explicit out-of-scope list.
