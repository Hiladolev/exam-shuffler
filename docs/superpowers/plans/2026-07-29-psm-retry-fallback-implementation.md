# PSM Retry Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a page's parsed-question count doesn't match its crop-band count, retry that one page's line extraction with `--psm 12` before giving up, and only accept the retry if it doesn't find fewer headers than the default pass did.

**Architecture:** `extract_line_boxes` (`test_ocr.py`) gains an optional `config` passthrough to `pytesseract.image_to_data`. `attach_question_images` (`app.py`) gains an optional `page_images` dict; on a per-page count mismatch it re-extracts that page's lines at `--psm 12`, recomputes bands via the existing `find_question_crop_bounds`, and swaps them in only if the retried band count is `>=` the default one. The existing exact-count check still gates whether images actually attach — this only gives it a second, better-informed shot before falling back to `None`.

**Tech Stack:** Python, pytesseract, pytest, `unittest.mock.patch`.

**Design doc:** `docs/superpowers/specs/2026-07-29-psm-retry-fallback-design.md`

**Commit policy:** This entire plan (Tasks 1-3) lands as **one single commit** at the very end (Task 3, Step 4), not one commit per task. The user explicitly wants this change cleanly revertible as a single unit if it causes problems elsewhere — intermediate steps stage but do not commit.

---

### Task 1: `extract_line_boxes` accepts a `config` passthrough

**Files:**
- Modify: `test_ocr.py:76-78`
- Test: `test_test_ocr.py`

- [ ] **Step 1: Write the failing test**

Add to `test_test_ocr.py`:

```python
from unittest.mock import patch

import test_ocr


def test_extract_line_boxes_forwards_config_to_image_to_data():
    image = Image.new("RGB", (10, 10), color="white")
    fake_data = {
        "text": ["Word"],
        "left": [0],
        "top": [0],
        "width": [10],
        "height": [10],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
    }

    with patch("test_ocr.pytesseract.image_to_data", return_value=fake_data) as mock_image_to_data:
        test_ocr.extract_line_boxes(image, config="--psm 12")

    _, kwargs = mock_image_to_data.call_args
    assert kwargs["config"] == "--psm 12"


def test_extract_line_boxes_defaults_to_empty_config():
    image = Image.new("RGB", (10, 10), color="white")
    fake_data = {
        "text": [], "left": [], "top": [], "width": [], "height": [],
        "block_num": [], "par_num": [], "line_num": [],
    }

    with patch("test_ocr.pytesseract.image_to_data", return_value=fake_data) as mock_image_to_data:
        test_ocr.extract_line_boxes(image)

    _, kwargs = mock_image_to_data.call_args
    assert kwargs["config"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_test_ocr.py -k config -v`
Expected: FAIL with `TypeError: extract_line_boxes() got an unexpected keyword argument` or `config` missing from `kwargs` (today `image_to_data` isn't called with a `config` kwarg at all).

- [ ] **Step 3: Write minimal implementation**

In `test_ocr.py`, change:

```python
def extract_line_boxes(image):
    data = pytesseract.image_to_data(image, lang="heb+eng", output_type=Output.DICT)
    return _group_words_into_lines(data)
```

to:

```python
def extract_line_boxes(image, config=""):
    data = pytesseract.image_to_data(image, lang="heb+eng", config=config, output_type=Output.DICT)
    return _group_words_into_lines(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_test_ocr.py -v`
Expected: PASS (all tests in the file, including the two new ones and the pre-existing ones).

- [ ] **Step 5: Stage the change (do not commit yet)**

```bash
git add test_ocr.py test_test_ocr.py
```

---

### Task 2: `attach_question_images` retries a mismatched page at `--psm 12`

**Files:**
- Modify: `app.py:46-68`
- Test: `test_app.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_app.py`:

```python
def test_attach_question_images_retries_mismatched_page_and_accepts_improved_count():
    image_a = Image.new("RGB", (100, 200), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
    ]
    page_offsets = [(2, 0)]
    # Default pass only found one band -- a mismatch against 2 questions.
    page_bands = [(2, image_a, (5, 30))]
    page_images = {2: image_a}
    retried_lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. Paris", 100, 120),
        ("שאלה מס' 2 (5 נק')", 130, 150),
        ("א. Rome", 200, 220),
    ]

    with patch("app.extract_line_boxes", return_value=retried_lines) as mock_extract:
        app.attach_question_images(parsed_questions, page_offsets, page_bands, page_images)

    mock_extract.assert_called_once_with(image_a, config=app.RETRY_LINE_EXTRACTION_CONFIG)
    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is not None


def test_attach_question_images_rejects_retry_that_finds_fewer_headers():
    image_a = Image.new("RGB", (100, 200), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
        {"question": "Q3", "choices": ["a", "b", "c", "d"], "header_line_index": 20},
    ]
    page_offsets = [(2, 0)]
    # Default pass found 2 bands against 3 questions -- a mismatch.
    page_bands = [(2, image_a, (5, 30)), (2, image_a, (35, 60))]
    page_images = {2: image_a}
    # Retry regresses to only 1 header -- must be rejected, not swapped in.
    retried_lines = [("שאלה מס' 1 (5 נק')", 0, 20), ("א. Paris", 100, 120)]

    with patch("app.extract_line_boxes", return_value=retried_lines):
        app.attach_question_images(parsed_questions, page_offsets, page_bands, page_images)

    assert parsed_questions[0]["question_image"] is None
    assert parsed_questions[1]["question_image"] is None
    assert parsed_questions[2]["question_image"] is None


def test_attach_question_images_skips_retry_without_a_recorded_page_image():
    image_a = Image.new("RGB", (100, 200), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 30))]

    with patch("app.extract_line_boxes") as mock_extract:
        app.attach_question_images(parsed_questions, page_offsets, page_bands)

    mock_extract.assert_not_called()
    assert parsed_questions[0]["question_image"] is None
    assert parsed_questions[1]["question_image"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_app.py -k "retries_mismatched or rejects_retry or skips_retry" -v`
Expected: FAIL — `attach_question_images()` doesn't accept a 4th `page_images` argument yet, and `app.RETRY_LINE_EXTRACTION_CONFIG` / `app.extract_line_boxes` don't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `app.py`, add `extract_line_boxes` to the existing `test_ocr` import:

```python
from test_ocr import (
    run_ocr_all_pages,
    run_line_extraction_all_pages,
    extract_line_boxes,
    crop_question_image,
    MIN_PAGE_TEXT_LENGTH,
    POPPLER_PATH,
)
```

Add a module-level constant near the top of `app.py`:

```python
RETRY_LINE_EXTRACTION_CONFIG = "--psm 12"
```

Replace `attach_question_images`:

```python
def attach_question_images(parsed_questions, page_offsets, page_bands, page_images=None):
    page_images = page_images or {}

    questions_by_page = {}
    for question in parsed_questions:
        page_number = page_number_for_line_index(page_offsets, question["header_line_index"])
        questions_by_page.setdefault(page_number, []).append(question)

    bands_by_page = {}
    for page_number, image, band in page_bands:
        bands_by_page.setdefault(page_number, []).append((image, band))

    for page_number, page_questions in questions_by_page.items():
        bands = bands_by_page.get(page_number, [])

        # A count mismatch on the default pass may just mean Tesseract's
        # default page segmentation dropped a header line entirely (seen in
        # practice: a clean, non-overlapping header line missing from both
        # OCR passes over the full page). Retry that one page at a sparser
        # segmentation mode, but only ever trust the retry if it finds at
        # least as many headers as the default pass did -- otherwise keep
        # the default result and fall through to the same safe None
        # fallback as before.
        if len(bands) != len(page_questions) and page_number in page_images:
            image = page_images[page_number]
            retried_lines = extract_line_boxes(image, config=RETRY_LINE_EXTRACTION_CONFIG)
            retried_bounds = find_question_crop_bounds(retried_lines)
            if len(retried_bounds) >= len(bands):
                bands = [(image, band) for band in retried_bounds]

        # Only attach images if this page's band count exactly matches its
        # question count -- otherwise we can't be sure a given band lines up
        # with the right question, so this page's questions fall back to None.
        if len(bands) == len(page_questions):
            for question, (image, band) in zip(page_questions, bands):
                question["question_image"] = (
                    crop_question_image(image, band[0], band[1]) if band is not None else None
                )
        else:
            for question in page_questions:
                question["question_image"] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_app.py -v`
Expected: PASS for all tests in the file, including the 3 new ones and every pre-existing `attach_question_images`/`page_number_for_line_index`/`build_page_offsets` test (they call `attach_question_images` with 3 positional args, which still works since `page_images` now defaults to `None`).

- [ ] **Step 5: Stage the change (do not commit yet)**

```bash
git add app.py test_app.py
```

---

### Task 3: Wire `page_images` through `run_pipeline`

**Files:**
- Modify: `app.py:91-103` (the crop-extraction loop and `attach_question_images` call site inside `run_pipeline`)

- [ ] **Step 1: Update the crop-extraction loop to also record each page's image**

Change:

```python
    progress = st.progress(0)
    status = st.empty()
    page_bands = []
    for i, (page_number, image, lines) in enumerate(run_line_extraction_all_pages(pdf_path), start=1):
        page_text_length = sum(len(text) for text, _, _ in lines)
        if page_text_length >= MIN_PAGE_TEXT_LENGTH:
            for band in find_question_crop_bounds(lines):
                page_bands.append((page_number, image, band))
        progress.progress(i / total_to_process)
        status.text(f"Extracting question images: page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    attach_question_images(parsed_questions, page_offsets, page_bands)
```

to:

```python
    progress = st.progress(0)
    status = st.empty()
    page_bands = []
    page_images = {}
    for i, (page_number, image, lines) in enumerate(run_line_extraction_all_pages(pdf_path), start=1):
        page_text_length = sum(len(text) for text, _, _ in lines)
        if page_text_length >= MIN_PAGE_TEXT_LENGTH:
            page_images[page_number] = image
            for band in find_question_crop_bounds(lines):
                page_bands.append((page_number, image, band))
        progress.progress(i / total_to_process)
        status.text(f"Extracting question images: page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    attach_question_images(parsed_questions, page_offsets, page_bands, page_images)
```

This is the only production call site of `attach_question_images`; `run_pipeline` itself has no dedicated unit test in this codebase (it needs a real PDF + tesseract binary, per existing convention), so this task has no new automated test of its own — it's covered by Task 2's unit tests plus the manual end-to-end check below.

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS, no regressions in any file.

- [ ] **Step 3: Manual verification**

Stop any running Streamlit server, start it fresh, upload the sample exam PDF, and confirm Question 1 now renders as a cropped image instead of editable text. Confirm no other previously-clean question regressed to text.

- [ ] **Step 4: Stage and create the single commit for this entire plan**

```bash
git add app.py
git status
```

Confirm the staged diff covers exactly: `test_ocr.py`, `test_test_ocr.py`, `app.py`, `test_app.py` — nothing else.

```bash
git commit -m "feat: retry mismatched-page crop extraction at --psm 12 as a fallback"
```

This is the one and only commit for the whole plan (Tasks 1-3 combined), so a single `git revert <sha>` cleanly undoes the entire change if it turns out to cause more harm than good.
