# Crop Question-Body Images (Phase 1: Clean Questions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crop a question's body (the region between its header line and its first choice line) directly out of the source PDF page image and show it as a picture on the clean-questions review screen, instead of showing OCR-mangled text — while leaving choices, the existing `.txt`-based `build_final_content` path, and the flagged/needs_review screen untouched.

**Architecture:** A second, separate OCR pass (`pytesseract.image_to_data`) extracts per-line pixel bounding boxes per page. A new pure function, `find_question_crop_bounds`, walks those lines with the same header/choice regexes `parse_ocr_text` already uses and emits one crop band (or `None`) per header found on that page. `run_pipeline` (`app.py`) aligns the flattened, page-ordered list of bands against `parse_ocr_text`'s flattened list of questions purely by count — if the counts don't match, every question falls back to `question_image = None`, never guessing. Parsed question dicts gain an optional `question_image` (PNG bytes) field that flows unchanged through `shuffle_questions`. The clean-questions editor shows `st.image` instead of the editable text area when a question has one. The download button switches from `.txt` to a new `build_final_html`, which embeds images as base64 `<img>` tags and keeps everything else — flagged cards, choices, correct-answer index — as plain text, exactly as `build_final_content` renders it today.

**Tech Stack:** Python, pytesseract (`image_to_data`), Pillow (`Image.crop`, PNG encoding), Streamlit (`st.image`), pytest, `streamlit.testing.v1.AppTest`.

**Design doc:** `docs/superpowers/specs/2026-07-28-question-image-crop-design.md`

---

## Before you start

The Streamlit dev server must be **stopped** for the entire duration of this plan (Tasks 1–10 only touch files on disk; per this repo's `CLAUDE.md`, editing a module `app.py` imports while the server is running leaves it running stale code from `sys.modules`). Only start the server in Task 11, the final manual check.

---

### Task 1: `_group_words_into_lines` — turn `image_to_data`'s dict into per-line boxes

**Files:**
- Modify: `test_ocr.py`
- Create: `test_test_ocr.py`

`pytesseract.image_to_data(..., output_type=Output.DICT)` returns one dict of parallel lists (one entry per detected *word*, not line): `text`, `left`, `top`, `width`, `height`, `block_num`, `par_num`, `line_num`, among others. `_group_words_into_lines` groups words that share `(block_num, par_num, line_num)` into a line, joins their text left-to-right, and computes the line's bounding box as the min/max pixel extents of its words. This is pure dict-in, list-out logic — no image or tesseract binary needed to test it.

- [ ] **Step 1: Write the failing tests**

Create `test_test_ocr.py`:

```python
from test_ocr import _group_words_into_lines


def test_group_words_into_lines_joins_words_and_computes_bounding_box():
    data = {
        "text": ["Hello", "world", "", "Second", "line"],
        "left": [10, 60, 0, 10, 70],
        "top": [100, 102, 0, 150, 148],
        "width": [40, 50, 0, 45, 40],
        "height": [20, 18, 0, 22, 20],
        "block_num": [1, 1, 1, 1, 1],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 2, 2],
    }

    result = _group_words_into_lines(data)

    assert result == [
        ("Hello world", 100, 120),
        ("Second line", 148, 172),
    ]


def test_group_words_into_lines_skips_empty_words():
    data = {
        "text": ["", "Real"],
        "left": [0, 5],
        "top": [0, 10],
        "width": [0, 30],
        "height": [0, 15],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
    }

    assert _group_words_into_lines(data) == [("Real", 10, 25)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_test_ocr.py -v`
Expected: FAIL with `ImportError: cannot import name '_group_words_into_lines'`

- [ ] **Step 3: Implement**

In `test_ocr.py`, add near the top (after the existing imports):

```python
from pytesseract import Output
```

Then add the function after `run_ocr_all_pages` (before the `if __name__ == "__main__":` block):

```python
def _group_words_into_lines(data):
    lines = {}
    order = []
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word:
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        top = data["top"][i]
        bottom = top + data["height"][i]
        if key not in lines:
            lines[key] = {"words": [], "top": top, "bottom": bottom}
            order.append(key)

        entry = lines[key]
        entry["words"].append((data["left"][i], word))
        entry["top"] = min(entry["top"], top)
        entry["bottom"] = max(entry["bottom"], bottom)

    result = []
    for key in order:
        entry = lines[key]
        text = " ".join(word for _, word in sorted(entry["words"], key=lambda pair: pair[0]))
        result.append((text, entry["top"], entry["bottom"]))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_test_ocr.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add test_ocr.py test_test_ocr.py
git commit -m "Add _group_words_into_lines to turn image_to_data output into per-line boxes"
```

---

### Task 2: `extract_line_boxes` — thin per-page wrapper around `image_to_data`

**Files:**
- Modify: `test_ocr.py`

A thin wrapper calling the real `pytesseract.image_to_data` on one page image and passing its output through `_group_words_into_lines`. Like `run_ocr`/`run_ocr_all_pages` today, this needs a real tesseract binary and isn't unit-tested — it's exercised through the manual browser check in Task 11.

- [ ] **Step 1: Implement**

In `test_ocr.py`, add directly after `_group_words_into_lines`:

```python
def extract_line_boxes(image):
    data = pytesseract.image_to_data(image, lang="heb+eng", output_type=Output.DICT)
    return _group_words_into_lines(data)
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS (all existing tests, no new ones added by this task)

- [ ] **Step 3: Commit**

```bash
git add test_ocr.py
git commit -m "Add extract_line_boxes wrapper for per-page line bounding boxes"
```

---

### Task 3: `crop_question_image` — crop a page image to a pixel band and return PNG bytes

**Files:**
- Modify: `test_ocr.py`
- Modify: `test_test_ocr.py`

A thin PIL wrapper: crops the full page width between `top_px`/`bottom_px` with a few pixels of padding (clamped to the image's actual bounds), and returns PNG-encoded bytes. This one needs no tesseract binary — just PIL — so it's cheap to give a real (if minimal) smoke test.

- [ ] **Step 1: Write the failing tests**

Add to `test_test_ocr.py`:

```python
import io

from PIL import Image

from test_ocr import _group_words_into_lines, crop_question_image
```

(replace the existing single-line `from test_ocr import _group_words_into_lines` import with the block above)

```python
def test_crop_question_image_returns_png_bytes_for_band():
    image = Image.new("RGB", (200, 300), color="white")

    png_bytes = crop_question_image(image, top_px=100, bottom_px=150, padding=5)
    cropped = Image.open(io.BytesIO(png_bytes))

    assert cropped.format == "PNG"
    assert cropped.size == (200, 60)


def test_crop_question_image_clamps_padding_to_image_bounds():
    image = Image.new("RGB", (200, 300), color="white")

    png_bytes = crop_question_image(image, top_px=2, bottom_px=298, padding=10)
    cropped = Image.open(io.BytesIO(png_bytes))

    assert cropped.size == (200, 300)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_test_ocr.py -v`
Expected: FAIL with `ImportError: cannot import name 'crop_question_image'`

- [ ] **Step 3: Implement**

In `test_ocr.py`, add `import io` to the top of the file (with the other imports), then add the function after `extract_line_boxes`:

```python
def crop_question_image(image, top_px, bottom_px, padding=5):
    width, height = image.size
    top = max(0, top_px - padding)
    bottom = min(height, bottom_px + padding)
    cropped = image.crop((0, top, width, bottom))
    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG")
    return buffer.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_test_ocr.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add test_ocr.py test_test_ocr.py
git commit -m "Add crop_question_image to crop a page band into PNG bytes"
```

---

### Task 4: `run_line_extraction_all_pages` — the second OCR pass, wired per-page

**Files:**
- Modify: `test_ocr.py`

Mirrors `run_ocr_all_pages`'s existing structure exactly (same page range, same poppler args) but yields the page image and its extracted lines instead of plain text. This keeps `run_ocr_all_pages` and the text pipeline it feeds completely untouched, per the design doc. Like `run_ocr_all_pages`, this is pipeline wiring and isn't unit-tested directly.

- [ ] **Step 1: Implement**

In `test_ocr.py`, add directly after `run_ocr_all_pages`:

```python
def run_line_extraction_all_pages(pdf_path, poppler_path=POPPLER_PATH):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)["Pages"]
    if total_pages < 2:
        return
    images = convert_from_path(
        pdf_path, first_page=2, last_page=total_pages, poppler_path=poppler_path
    )
    for page_number, image in zip(range(2, total_pages + 1), images):
        lines = extract_line_boxes(image)
        yield page_number, image, lines
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add test_ocr.py
git commit -m "Add run_line_extraction_all_pages generator for the per-page crop pass"
```

---

### Task 5: `find_question_crop_bounds` — the pure crop-band-detection function

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

Given one page's list of `(text, top_px, bottom_px)` lines, walk them using the same `is_header_line` check and `CHOICE_PATTERN` regex `parse_ocr_text` already uses. For each header line found (in page order), look for the next choice-pattern line after it on the same page. If found and the gap is at least `MIN_CROP_BAND_HEIGHT` pixels tall, emit `(header_bottom, choice_top)`; otherwise emit `None` for that header. The function always returns exactly one entry per header found on the page (never fewer) — this is what lets `run_pipeline` later line the per-page results up against `parse_ocr_text`'s questions purely by count.

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py`:

```python
from parser import find_question_crop_bounds, find_split_suggestions
```

(replace the existing `from parser import find_split_suggestions` import line with the line above)

```python
def test_find_question_crop_bounds_normal_single_question():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("some question text", 25, 45),
        ("more question text", 50, 70),
        ("א. Paris", 75, 95),
        ("ב. London", 100, 120),
    ]
    assert find_question_crop_bounds(lines) == [(20, 75)]


def test_find_question_crop_bounds_header_with_no_following_choice():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("dangling question text with no choices", 25, 45),
    ]
    assert find_question_crop_bounds(lines) == [None]


def test_find_question_crop_bounds_multiple_questions_on_one_page():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("question one text", 25, 45),
        ("א. Paris", 50, 70),
        ("ב. London", 75, 95),
        ("שאלה מס' 6 (3 נק')", 100, 120),
        ("question two text", 125, 145),
        ("א. Red", 150, 170),
    ]
    assert find_question_crop_bounds(lines) == [(20, 50), (120, 150)]


def test_find_question_crop_bounds_zero_headers():
    lines = [
        ("just some prose", 0, 20),
        ("more prose", 25, 45),
    ]
    assert find_question_crop_bounds(lines) == []


def test_find_question_crop_bounds_band_shorter_than_minimum_height():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 22, 40),
    ]
    assert find_question_crop_bounds(lines) == [None]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_question_crop_bounds'`

- [ ] **Step 3: Implement**

In `parser.py`, add the constant next to the other pattern constants at the top of the file:

```python
MIN_CROP_BAND_HEIGHT = 10
```

Then add the function after `find_split_suggestions`:

```python
def find_question_crop_bounds(lines):
    bounds = []
    for i, (text, _, header_bottom) in enumerate(lines):
        if not is_header_line(text):
            continue

        band = None
        for choice_text, choice_top, _ in lines[i + 1:]:
            if CHOICE_PATTERN.match(choice_text):
                if choice_top - header_bottom >= MIN_CROP_BAND_HEIGHT:
                    band = (header_bottom, choice_top)
                break
        bounds.append(band)

    return bounds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (8 tests: 3 existing + 5 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_question_crop_bounds to detect crop bands between header and first choice"
```

---

### Task 6: Carry `question_image` through `shuffle_questions`

**Files:**
- Modify: `shuffler_core.py`
- Modify: `test_shuffler_core.py`

`shuffle_questions` currently rebuilds each question dict with only `question`, `choices`, and `correct_index`, dropping any other key. It needs to carry `question_image` through unchanged (defaulting to `None` when absent, e.g. for post-split cards from `split_choices`, which never set it).

- [ ] **Step 1: Write the failing tests**

Add to `test_shuffler_core.py`:

```python
def test_shuffle_questions_carries_question_image_through_unchanged():
    questions = [
        {"question": "Q", "choices": ["a", "b", "c", "d"], "question_image": b"PNGDATA"},
    ]
    shuffled = shuffle_questions(questions)
    assert shuffled[0]["question_image"] == b"PNGDATA"


def test_shuffle_questions_defaults_question_image_to_none_when_absent():
    questions = [{"question": "Q", "choices": ["a", "b", "c", "d"]}]
    shuffled = shuffle_questions(questions)
    assert shuffled[0]["question_image"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: FAIL with `KeyError: 'question_image'`

- [ ] **Step 3: Implement**

In `shuffler_core.py`, update `shuffle_questions`:

```python
def shuffle_questions(questions):
    result = []
    for q in questions:
        indices = list(range(len(q["choices"])))
        random.shuffle(indices)
        shuffled_choices = [q["choices"][i] for i in indices]
        correct_index = indices.index(0)
        result.append({
            "question": q["question"],
            "choices": shuffled_choices,
            "correct_index": correct_index,
            "question_image": q.get("question_image"),
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: PASS (11 tests: 9 existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add shuffler_core.py test_shuffler_core.py
git commit -m "Carry question_image through shuffle_questions unchanged"
```

---

### Task 7: Wire the crop pass into `run_pipeline`

**Files:**
- Modify: `app.py`

After `parse_ocr_text` produces `parsed_questions` (the existing text pipeline, untouched), run the second OCR pass page-by-page, collect one `(image, band)` pair per header found (in the same page order `parse_ocr_text` processes headers in), and attach `question_image` to each parsed question **only if the counts line up exactly** — otherwise every question gets `question_image = None`. This happens before the clean/needs_review split, so both clean and flagged questions get the field (flagged ones just never display it, per Task 8's scope).

`run_pipeline` has no existing unit tests (it needs a real PDF + tesseract binary) and this task doesn't add any — it's verified in Task 11's manual browser check, consistent with how the rest of the pipeline wiring in this file is handled.

- [ ] **Step 1: Update imports**

In `app.py`, replace:

```python
from test_ocr import run_ocr_all_pages, MIN_PAGE_TEXT_LENGTH, POPPLER_PATH
from parser import strip_version_lines, parse_ocr_text, find_split_suggestions
```

with:

```python
from test_ocr import (
    run_ocr_all_pages,
    run_line_extraction_all_pages,
    crop_question_image,
    MIN_PAGE_TEXT_LENGTH,
    POPPLER_PATH,
)
from parser import (
    strip_version_lines,
    parse_ocr_text,
    find_split_suggestions,
    find_question_crop_bounds,
)
```

- [ ] **Step 2: Attach crop bands in `run_pipeline`**

Replace:

```python
    raw_text = "\n\n".join(raw_texts)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)

    clean_questions = []
```

with:

```python
    raw_text = "\n\n".join(raw_texts)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)

    page_bands = []
    for _, image, lines in run_line_extraction_all_pages(pdf_path):
        for band in find_question_crop_bounds(lines):
            page_bands.append((image, band))

    if len(page_bands) == len(parsed_questions):
        for question, (image, band) in zip(parsed_questions, page_bands):
            question["question_image"] = (
                crop_question_image(image, band[0], band[1]) if band is not None else None
            )
    else:
        for question in parsed_questions:
            question["question_image"] = None

    clean_questions = []
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS (`run_pipeline` isn't directly exercised by the test suite, but nothing else should break)

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "Wire the crop pass into run_pipeline, attaching question_image by header count"
```

---

### Task 8: Show the image instead of the text area on the clean-questions screen

**Files:**
- Modify: `app.py`

In `render_question_editor`, if the question has a `question_image`, show it read-only via `st.image` instead of the editable text area; otherwise keep today's editable text area exactly as-is. The returned dict must keep carrying `question_image` through unchanged so `build_final_html` (Task 9) can use it later. This only affects clean questions in practice: post-split review cards always have `question_image = None` (from Task 6's default), so they keep hitting the existing text-area branch — no separate flag is needed to preserve the flagged-screen scope boundary from the design doc.

Per the design doc's testing section, the image-vs-text-area branch itself gets **no new automated test** — it's a read-only `st.image`, not interactive widget logic, and is verified manually in the browser in Task 11, consistent with how the rest of this app's UI is checked.

- [ ] **Step 1: Implement**

In `app.py`, replace:

```python
    question_text = st.text_area(
        "Question text", value=state["question"], key=f"{key_prefix}_question"
    )
```

with:

```python
    question_image = state.get("question_image")
    if question_image:
        st.image(question_image)
        question_text = state["question"]
    else:
        question_text = st.text_area(
            "Question text", value=state["question"], key=f"{key_prefix}_question"
        )
```

Then replace the function's return statement:

```python
    return {"question": question_text, "choices": choices, "correct_index": correct_index}
```

with:

```python
    return {
        "question": question_text,
        "choices": choices,
        "correct_index": correct_index,
        "question_image": question_image,
    }
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS (existing `test_app.py` fixtures don't set `question_image`, so `state.get("question_image")` is `None` and every existing test keeps hitting the text-area branch unchanged)

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Show question_image via st.image on the clean-questions screen when present"
```

---

### Task 9: `build_final_html` — render the answer key as HTML with embedded images

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

A new function alongside (not replacing) `build_final_content`. Clean questions with a `question_image` embed it as a base64 `data:image/png;base64,...` `<img>` tag; clean questions without one render the question text as a paragraph, matching today's `.txt` content. Choices and the correct-answer index render the same way as `_format_question_lines` does today. Flagged/review cards always render as plain text (they never carry a real `question_image` in this phase, per Task 6/8, but the review-card renderer doesn't even look at the key, matching the design doc's "flagged/review cards: render as plain text, same as today").

- [ ] **Step 1: Write the failing tests**

Add to `test_app.py`:

```python
import base64
```

(add this import at the top of the file, alongside `from unittest.mock import patch`)

```python
def test_build_final_html_renders_image_tag_when_question_image_present():
    edited_clean = [
        {
            "question": "ignored text",
            "choices": ["a", "b", "c", "d"],
            "correct_index": 1,
            "question_image": b"FAKEPNGBYTES",
        },
    ]
    result = app.build_final_html(edited_clean, [])

    expected_b64 = base64.b64encode(b"FAKEPNGBYTES").decode("ascii")
    assert f'<img src="data:image/png;base64,{expected_b64}">' in result
    assert "ignored text" not in result
    assert "<li>0: a</li>" in result
    assert "Correct answer index: 1" in result


def test_build_final_html_renders_text_fallback_when_no_question_image():
    edited_clean = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "correct_index": 0, "question_image": None},
    ]
    result = app.build_final_html(edited_clean, [])

    assert "<p>Q1</p>" in result
    assert "<img" not in result


def test_build_final_html_renders_review_cards_as_plain_text():
    edited_review_cards = [
        {"question": "Merged?", "choices": ["x", "y", "z", "w"], "correct_index": 2},
    ]
    result = app.build_final_html([], edited_review_cards)

    assert "<p>Merged?</p>" in result
    assert "<li>2: z</li>" in result
    assert "Correct answer index: 2" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v`
Expected: FAIL with `AttributeError: module 'app' has no attribute 'build_final_html'`

- [ ] **Step 3: Implement**

In `app.py`, add `import base64` and `import html` at the top of the file (alongside `import streamlit as st`), then add these functions after `build_final_content`:

```python
def _render_question_html(q, index):
    lines = [f"<h3>Question {index}</h3>"]
    if q.get("question_image"):
        b64 = base64.b64encode(q["question_image"]).decode("ascii")
        lines.append(f'<img src="data:image/png;base64,{b64}">')
    else:
        lines.append(f"<p>{html.escape(q['question'])}</p>")
    lines.append("<ul>")
    for j, choice in enumerate(q["choices"]):
        lines.append(f"<li>{j}: {html.escape(choice)}</li>")
    lines.append("</ul>")
    lines.append(f"<p>Correct answer index: {q['correct_index']}</p>")
    return "\n".join(lines)


def _render_review_card_html(q, index):
    lines = [
        f"<h3>Flagged Question {index}</h3>",
        f"<p>{html.escape(q['question'])}</p>",
        "<ul>",
    ]
    for j, choice in enumerate(q["choices"]):
        lines.append(f"<li>{j}: {html.escape(choice)}</li>")
    lines.append("</ul>")
    lines.append(f"<p>Correct answer index: {q['correct_index']}</p>")
    return "\n".join(lines)


def build_final_html(edited_clean, edited_review_cards):
    body_parts = [_render_question_html(q, i) for i, q in enumerate(edited_clean, start=1)]

    if edited_review_cards:
        body_parts.append("<h2>Reviewed (previously flagged) Questions</h2>")
        body_parts.extend(
            _render_review_card_html(q, i) for i, q in enumerate(edited_review_cards, start=1)
        )

    body = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<style>
body {{ direction: rtl; font-family: sans-serif; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all existing tests + 3 new)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Add build_final_html to render the answer key with embedded question images"
```

---

### Task 10: Switch the download button from `.txt` to `.html`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Implement**

Replace:

```python
    final_content = build_final_content(edited_clean, edited_review_cards)
    st.download_button(
        "Generate Final File",
        data=final_content.encode("utf-8"),
        file_name="final_exam.txt",
        mime="text/plain",
    )
```

with:

```python
    final_html = build_final_html(edited_clean, edited_review_cards)
    st.download_button(
        "Generate Final File",
        data=final_html.encode("utf-8"),
        file_name="final_exam.html",
        mime="text/html",
    )
```

`build_final_content` stays in the file, unused by the UI now but still imported by `test_app.py`'s existing tests — do not delete it.

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Wire the download button to build_final_html and export final_exam.html"
```

---

### Task 11: Manual verification in the browser

**Files:** none (no code changes)

This is a manual check, run by Hila, not automated — per her stated preference (Streamlit UI checks are done by driving the browser herself, not via browser-automation tooling), and per the design doc's explicit note that the image-display UI has no automated coverage.

- [ ] Start the Streamlit server fresh (it must have been stopped since before Task 1, per the note at the top of this plan): `streamlit run app.py`
- [ ] Upload the full 8-page sample exam and click Process
- [ ] Confirm the clean-questions screen shows a cropped image (not garbled OCR text) for at least one of the known image-bearing questions (page 13's question 15 with the console-screenshot table; page 5's `describe()` dataframe table and decision-tree diagram)
- [ ] Confirm questions that never had a table/diagram still show the normal editable text area
- [ ] Confirm the flagged/needs_review screen and post-split cards still show plain OCR'd text exactly as before (no images)
- [ ] Click "Generate Final File", confirm it downloads `final_exam.html`, and open it in a browser to confirm images render inline and text-only questions/choices/correct-answer-index still appear
- [ ] Stop the Streamlit server once the check is done (per Hila's preference — don't leave it running until the next test)

---

## Explicitly out of scope (matches the design doc)

- Phase 2 (cropping for flagged/needs_review and post-split screens) — a committed follow-up, sequenced after this phase ships and is manually verified, needing its own design pass first.
- Any in-app UI for manually adjusting a crop's boundaries.
- Multi-column layout detection.
- Image resizing/compression.
