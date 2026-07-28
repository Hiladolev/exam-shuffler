# Per-Page Crop-Band/Question Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Narrow the question-image alignment safety check (added in the question-image-crop Phase 1 work) from a whole-document count comparison down to a per-page one, so a mismatch between the two independent OCR passes on one page can no longer be masked by an unrelated mismatch elsewhere in the document, and only the affected page's questions lose their image instead of the whole exam's.

**Architecture:** `parser.py` stays page-agnostic but starts reporting, per parsed question, the line index (within the text it was given) where that question's header appeared. `app.py` — which already drives the per-page OCR loops and therefore already knows real PDF page numbers — moves `strip_version_lines` to run per-page (instead of once on the joined blob) so it can compute exact per-page line counts, builds a `page_offsets` table from those counts, and uses a new pure function to map a line index back to a real page number. `attach_question_images` then buckets both questions and crop bands by real page number and applies the count-check-and-attach logic independently per page.

**Tech Stack:** Python, pytest. No new external dependencies.

**Design doc:** `docs/superpowers/specs/2026-07-28-per-page-image-alignment-design.md`

---

## Before you start

The Streamlit dev server must be **stopped** for the entire duration of this plan (per this repo's `CLAUDE.md`, editing a module `app.py` imports while the server is running leaves it running stale code from `sys.modules`). Only start it in Task 6, the final manual check.

This plan builds directly on the question-image-crop Phase 1 work already implemented earlier on this same branch (`question-image-crop`, not yet merged to `master`) — `parser.py` already has `find_question_crop_bounds`/`MIN_CROP_BAND_HEIGHT`, and `app.py` already has `attach_question_images`, `run_pipeline`'s two OCR-pass loops, and the rest of the image-cropping pipeline from that earlier plan.

---

### Task 1: `parse_ocr_text` records each question's header line index

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

`parse_ocr_text` already computes, for each question block, a `start` value — the index (in the `lines` list it builds internally) where that block begins. For any block that follows a detected header, `start` *is* the header's own line index; for the rare leading block kept before any header, `start` is `0`. This task just keeps that value around on the returned dict as `header_line_index`, whether or not anything reads it yet. This is additive — nothing today asserts an exact key set on these dicts, and `shuffle_questions` already builds a fresh dict with only the keys it cares about, so this key is naturally dropped once it's no longer needed.

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py`:

```python
from parser import find_question_crop_bounds, find_split_suggestions, parse_ocr_text
```

(replace the existing `from parser import find_question_crop_bounds, find_split_suggestions` import line with the line above)

```python
def test_parse_ocr_text_records_header_line_index_including_leading_block():
    text = "\n".join([
        "some leading noise",
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. Paris",
        "ב. London",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["header_line_index"] == 0
    assert questions[1]["header_line_index"] == 1


def test_parse_ocr_text_records_header_line_index_for_multiple_questions():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question one",
        "א. Paris",
        "שאלה מס' 2 (3 נק')",
        "question two",
        "א. Red",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["header_line_index"] == 0
    assert questions[1]["header_line_index"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `KeyError: 'header_line_index'`

- [ ] **Step 3: Implement**

In `parser.py`, replace:

```python
        question_text = " ".join(question_lines).strip()
        if question_text or choices:
            questions.append({"question": question_text, "choices": choices})
```

with:

```python
        question_text = " ".join(question_lines).strip()
        if question_text or choices:
            questions.append({
                "question": question_text,
                "choices": choices,
                "header_line_index": start,
            })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (11 tests: 9 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Record each question's header line index in parse_ocr_text"
```

---

### Task 2: Prove `strip_version_lines` per-page equals join-then-strip

**Files:**
- Modify: `test_parser.py`

No production code changes in this task — `strip_version_lines` is already purely line-local (no cross-line state, no lookahead), so applying it to each page's text individually and then joining should produce identical output to joining first and stripping once, which is what `app.py`'s `run_pipeline` does today. This task proves that equivalence with a test before Task 5 relies on it, since it's the load-bearing assumption the rest of this plan builds on.

- [ ] **Step 1: Write the test**

Add to `test_parser.py`:

```python
from parser import (
    find_question_crop_bounds,
    find_split_suggestions,
    parse_ocr_text,
    strip_version_lines,
)
```

(replace the existing `from parser import find_question_crop_bounds, find_split_suggestions, parse_ocr_text` import line with the line above)

```python
def test_strip_version_lines_per_page_matches_joined_stripping():
    pages = [
        "page one text\nמספר גרסה: 5\nmore content",
        "page two text\nmore content",
    ]

    joined_then_stripped = strip_version_lines("\n\n".join(pages))
    stripped_then_joined = "\n\n".join(strip_version_lines(p) for p in pages)

    assert joined_then_stripped == stripped_then_joined
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest test_parser.py -v`
Expected: PASS immediately (this pins existing correct behavior — `strip_version_lines` doesn't need to change for this to hold)

- [ ] **Step 3: Commit**

```bash
git add test_parser.py
git commit -m "Add test proving strip_version_lines is safe to apply per-page"
```

---

### Task 3: `page_number_for_line_index` — map a line index back to a real page number

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

A pure function: given a `page_offsets` list of `(page_number, start_line_index)` pairs (sorted by `start_line_index` ascending) and a line index, returns the page number whose `start_line_index` is the largest one `<= line_index`. A simple linear scan is enough — page counts here are small (dozens at most), so there's no need for `bisect`.

- [ ] **Step 1: Write the failing tests**

Add to `test_app.py`:

```python
def test_page_number_for_line_index_returns_first_page_for_index_zero():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 0) == 2


def test_page_number_for_line_index_returns_correct_page_within_range():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 7) == 4


def test_page_number_for_line_index_returns_correct_page_at_exact_boundary():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 6) == 4


def test_page_number_for_line_index_returns_last_page_beyond_all_offsets():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 15) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v`
Expected: FAIL with `AttributeError: module 'app' has no attribute 'page_number_for_line_index'`

- [ ] **Step 3: Implement**

In `app.py`, add this function right before `attach_question_images`:

```python
def page_number_for_line_index(page_offsets, line_index):
    result_page_number = page_offsets[0][0]
    for page_number, start_index in page_offsets:
        if start_index > line_index:
            break
        result_page_number = page_number
    return result_page_number
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all existing tests + 4 new)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Add page_number_for_line_index to map a line index to a real page number"
```

---

### Task 4: `attach_question_images` buckets by real page number

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

`attach_question_images` currently compares one whole-document count. This task changes it to bucket both `parsed_questions` (via `page_number_for_line_index` on each question's `header_line_index`, from Task 1) and `page_bands` (which will carry a real page number once Task 5 wires it up) by page number, then apply the existing count-check-and-attach logic independently within each page's bucket. `page_bands`'s shape changes from `(image, band)` to `(page_number, image, band)` — Task 5 is what actually starts producing bands in this new shape from `run_pipeline`; this task only changes what `attach_question_images` expects to receive, and updates its tests accordingly.

The 2 existing tests for the old whole-document behavior are replaced (not kept alongside) since the mechanism itself is being corrected, not extended.

- [ ] **Step 1: Write the failing tests**

In `test_app.py`, replace:

```python
def test_attach_question_images_matches_bands_to_questions_in_order():
    image_a = Image.new("RGB", (100, 50), color="white")
    image_b = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"]},
        {"question": "Q2", "choices": ["a", "b", "c", "d"]},
    ]
    page_bands = [(image_a, (10, 30)), (image_b, None)]

    app.attach_question_images(parsed_questions, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_falls_back_to_none_on_count_mismatch():
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"]},
        {"question": "Q2", "choices": ["a", "b", "c", "d"]},
    ]
    page_bands = [(Image.new("RGB", (100, 50)), (10, 30))]

    app.attach_question_images(parsed_questions, page_bands)

    assert parsed_questions[0]["question_image"] is None
    assert parsed_questions[1]["question_image"] is None
```

with:

```python
def test_attach_question_images_matched_page_keeps_image_when_another_page_mismatches():
    image_a = Image.new("RGB", (100, 50), color="white")
    image_b = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
        {"question": "Q3", "choices": ["a", "b", "c", "d"], "header_line_index": 11},
    ]
    page_offsets = [(2, 0), (3, 10)]
    # Page 2 has one question and one matching band -> should get an image.
    # Page 3 has two questions but only one band -> mismatch, both fall back to None.
    page_bands = [
        (2, image_a, (5, 8)),
        (3, image_b, (12, 15)),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None
    assert parsed_questions[2]["question_image"] is None


def test_attach_question_images_handles_none_band_within_a_matched_page():
    image_a = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 5},
    ]
    page_offsets = [(2, 0)]
    page_bands = [
        (2, image_a, (5, 30)),
        (2, image_a, None),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_ignores_bands_on_a_page_with_no_questions():
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
    ]
    page_offsets = [(2, 0), (3, 10)]
    page_bands = [
        (2, Image.new("RGB", (100, 50)), (5, 8)),
        (3, Image.new("RGB", (100, 50)), (5, 8)),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v`
Expected: FAIL — old signature only takes 2 arguments, new tests call it with 3 (`TypeError`)

- [ ] **Step 3: Implement**

In `app.py`, replace:

```python
def attach_question_images(parsed_questions, page_bands):
    # Only attach images if the page-ordered band count exactly matches the
    # parsed-question count -- otherwise we can't be sure a given band lines
    # up with the right question, so every question falls back to None.
    if len(page_bands) == len(parsed_questions):
        for question, (image, band) in zip(parsed_questions, page_bands):
            question["question_image"] = (
                crop_question_image(image, band[0], band[1]) if band is not None else None
            )
    else:
        for question in parsed_questions:
            question["question_image"] = None
```

with:

```python
def attach_question_images(parsed_questions, page_offsets, page_bands):
    questions_by_page = {}
    for question in parsed_questions:
        page_number = page_number_for_line_index(page_offsets, question["header_line_index"])
        questions_by_page.setdefault(page_number, []).append(question)

    bands_by_page = {}
    for page_number, image, band in page_bands:
        bands_by_page.setdefault(page_number, []).append((image, band))

    for page_number, page_questions in questions_by_page.items():
        bands = bands_by_page.get(page_number, [])
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all tests except `run_pipeline`-dependent ones; note `test_app.py` doesn't call `attach_question_images` from within `run_pipeline` in any test, so this is isolated)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Make attach_question_images bucket questions and bands by real page number"
```

---

### Task 5: Wire per-page tracking into `run_pipeline`

**Files:**
- Modify: `app.py`

This task connects Tasks 1-4: `run_pipeline`'s text loop applies `strip_version_lines` per page (instead of once on the joined blob) and builds `page_offsets` while doing so; the crop loop stops discarding the real page number; `attach_question_images` is called with the new 3-argument signature.

`run_pipeline` has no existing unit tests (it needs a real PDF + tesseract binary) and this task doesn't add any — it's verified in Task 6's manual browser check, consistent with how the rest of the pipeline wiring in this file is handled.

- [ ] **Step 1: Update the text-OCR loop and remove the old whole-blob stripping call**

In `app.py`, replace:

```python
    progress = st.progress(0)
    status = st.empty()
    raw_texts = []
    for i, (page_number, text) in enumerate(run_ocr_all_pages(pdf_path), start=1):
        if len(text.strip()) >= MIN_PAGE_TEXT_LENGTH:
            raw_texts.append(text)
        progress.progress(i / total_to_process)
        status.text(f"Processing page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    raw_text = "\n\n".join(raw_texts)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)
```

with:

```python
    progress = st.progress(0)
    status = st.empty()
    raw_texts = []
    page_offsets = []
    next_line_index = 0
    for i, (page_number, text) in enumerate(run_ocr_all_pages(pdf_path), start=1):
        if len(text.strip()) >= MIN_PAGE_TEXT_LENGTH:
            stripped_text = strip_version_lines(text)
            page_offsets.append((page_number, next_line_index))
            next_line_index += len(stripped_text.splitlines()) + 1
            raw_texts.append(stripped_text)
        progress.progress(i / total_to_process)
        status.text(f"Processing page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    raw_text = "\n\n".join(raw_texts)
    parsed_questions = parse_ocr_text(raw_text)
```

- [ ] **Step 2: Keep the real page number in the crop loop and call the new `attach_question_images` signature**

Replace:

```python
    progress = st.progress(0)
    status = st.empty()
    page_bands = []
    for i, (_, image, lines) in enumerate(run_line_extraction_all_pages(pdf_path), start=1):
        page_text_length = sum(len(text) for text, _, _ in lines)
        if page_text_length >= MIN_PAGE_TEXT_LENGTH:
            for band in find_question_crop_bounds(lines):
                page_bands.append((image, band))
        progress.progress(i / total_to_process)
        status.text(f"Extracting question images: page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    attach_question_images(parsed_questions, page_bands)
```

with:

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

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "Wire per-page offset tracking into run_pipeline"
```

---

### Task 6: Manual verification in the browser

**Files:** none (no code changes)

Manual check, run by Hila — per her stated preference for driving Streamlit UI checks herself, and because `run_pipeline`'s wiring can't be unit-tested without a real PDF and tesseract binary.

- [ ] Start the Streamlit server fresh (it must have been stopped since before Task 1): `streamlit run app.py`
- [ ] Upload the full 8-page sample exam and click Process
- [ ] Confirm clean questions still show cropped images exactly as before this plan (this fix shouldn't change anything visible when both OCR passes agree, which is the case for this sample exam) — e.g. page 13's question 15 (console-screenshot table), page 5's `describe()` dataframe table and decision-tree diagram
- [ ] Confirm the flagged/needs_review screen and post-split cards still show plain OCR'd text, unaffected
- [ ] Click "Generate Final File" and confirm `final_exam.html` still downloads and renders correctly
- [ ] Stop the Streamlit server once the check is done

---

## Explicitly out of scope (matches the design doc)

- Reconciling *why* the two OCR passes might disagree about a page's blank-ness or header count — this plan only bounds the blast radius of such a disagreement to the one affected page.
- Any change to `find_question_crop_bounds` — it already operates strictly per-page and is unaffected by this plan.
- Any change to how a question's choices can span a page boundary — that existing, deliberate behavior is preserved; this plan only concerns which page a question's header is attributed to for image-alignment purposes.
