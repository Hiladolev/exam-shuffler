# Flagged/Post-Split Image Crop (Phase 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a cropped question-body image on the flagged/needs_review screen (pre-split) and on post-split cards (parts 2+), reusing and extending Phase 1's crop infrastructure, instead of always showing plain OCR text there.

**Architecture:** Two new pure `parser.py` functions locate, per page, the pixel position of each `CHOICE_PATTERN` line and of any "embedded header" continuation line (detected via a loose `שאלה` + digit check, since the strict `HEADER_PATTERN` is proven not to survive the OCR mangling that caused the merge in the first place). `attach_question_images` (`app.py`) is extended to attach this positional data — plus the source page image — onto any question with a matching band, alongside the `question_image` it already computes (no longer suppressed for merged/flagged questions). `split_choices` (`shuffler_core.py`) grows optional parameters to carry the block's own image through to part 1 unchanged, and to compute a pixel crop region (`image_bounds`) for later parts when their split point lines up exactly with a detected embedded header. A new `attach_split_part_images` (`app.py`) turns those pixel bounds into actual cropped bytes at split time, using the same `crop_question_image` helper Phase 1 already built.

**Tech Stack:** Python, pytest (pure-function tests), `streamlit.testing.v1.AppTest`, Pillow (`Image.new`/`.crop` for test fixtures).

**Design doc:** `docs/superpowers/specs/2026-07-29-flagged-postsplit-image-crop-design.md`

---

## Before you start

The Streamlit dev server must be **stopped** for the entire duration of Tasks 1–8 (they only touch files on disk; per this repo's `CLAUDE.md`, editing a module `app.py` imports while the server is running leaves it running stale code from `sys.modules`). Only start it fresh in Task 9, the final manual check.

---

### Task 1: `find_header_line_indices` and `is_probable_embedded_header` in `parser.py`

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

`find_header_line_indices` returns the index within a page's line list of every line matching `is_header_line` — used later to locate a specific block's own header line (which, for a merged/flagged question, is always correctly detected; only the *boundaries between* its merged sub-questions failed detection). `is_probable_embedded_header` is the new looser check: a continuation line counts as a candidate embedded header if it contains the literal substring `שאלה` and at least one digit — verified against the real sample exam (page 13, live OCR) to be the one token that survives even when `"מס'"`/`"נק'"` get OCR-mangled beyond recognition, with zero false positives anywhere in the document's processed pages.

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py` (add these two names to the existing `from parser import (...)` block at the top of the file):

```python
from parser import (
    find_question_crop_bounds,
    find_split_suggestions,
    parse_ocr_text,
    strip_version_lines,
    find_header_line_indices,
    is_probable_embedded_header,
)
```

```python
def test_find_header_line_indices_returns_indices_of_header_lines():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_header_line_indices(lines) == [0, 2]


def test_find_header_line_indices_empty_when_no_headers():
    lines = [("just prose", 0, 20), ("more prose", 25, 45)]
    assert find_header_line_indices(lines) == []


def test_is_probable_embedded_header_true_when_token_and_digit_present():
    assert is_probable_embedded_header("שאלה 'on' 19 (5 בק')") is True


def test_is_probable_embedded_header_false_without_the_token():
    assert is_probable_embedded_header("regular continuation text with 19 in it") is False


def test_is_probable_embedded_header_false_without_a_digit():
    assert is_probable_embedded_header("שאלה בלי מספר בכלל") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_header_line_indices'`

- [ ] **Step 3: Implement**

In `parser.py`, add these two constants right after `MIN_CROP_BAND_HEIGHT = 10`:

```python
EMBEDDED_HEADER_TOKEN = "שאלה"
DIGIT_PATTERN = re.compile(r"\d")
```

Then add these two functions directly after `is_header_line`:

```python
def is_probable_embedded_header(line):
    return EMBEDDED_HEADER_TOKEN in line and bool(DIGIT_PATTERN.search(line))


def find_header_line_indices(lines):
    return [i for i, (text, _, _) in enumerate(lines) if is_header_line(text)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all existing tests + 5 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_header_line_indices and is_probable_embedded_header"
```

---

### Task 2: `find_choice_line_bounds` in `parser.py`

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

Given a page's lines and the index of a specific header line, walks forward collecting each `CHOICE_PATTERN` match's `(top, bottom)`, stopping at the next real header or the end of the lines. This list is parallel (by position) to that block's flattened `choices` array, in order — the same "align by count" idea `find_question_crop_bounds` already relies on.

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py` (add `find_choice_line_bounds` to the same `from parser import (...)` block used in Task 1):

```python
def test_find_choice_line_bounds_returns_all_choice_positions_after_header():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("question body", 25, 45),
        ("א. choice one", 50, 70),
        ("ב. choice two", 75, 95),
        ("שאלה 'on' 19 (5 בק')", 100, 120),
        ("more body", 125, 145),
        ("א. choice three", 150, 170),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [
        (50, 70), (75, 95), (150, 170),
    ]


def test_find_choice_line_bounds_stops_at_next_real_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [(25, 45)]


def test_find_choice_line_bounds_empty_when_no_choices_follow():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("dangling prose, no choices", 25, 45),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_choice_line_bounds'`

- [ ] **Step 3: Implement**

In `parser.py`, add directly after `find_question_crop_bounds`:

```python
def find_choice_line_bounds(lines, header_index):
    bounds = []
    for text, top, bottom in lines[header_index + 1:]:
        if is_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            bounds.append((top, bottom))
    return bounds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all existing tests + 3 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_choice_line_bounds to locate per-choice pixel positions"
```

---

### Task 3: `find_embedded_header_bounds` in `parser.py`

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

Same page-line walk as Task 2, but tracks how many choices have started so far and records `{choice_count: (top, bottom)}` whenever a candidate embedded header line (Task 1's `is_probable_embedded_header`) is seen *after* at least one real choice has started. `choice_count` at that point is exactly the split-point index that boundary corresponds to — the same number space `split_choices` already uses for `split_points`.

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py` (add `find_embedded_header_bounds` to the same import block):

```python
def test_find_embedded_header_bounds_detects_candidate_with_digit():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("ב. choice two", 50, 70),
        ("שאלה 'on' 19 (5 בק')", 75, 95),
        ("א. choice three", 100, 120),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {2: (75, 95)}


def test_find_embedded_header_bounds_ignores_candidate_without_digit():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("שאלה בלי מספר", 50, 70),
        ("ב. choice two", 75, 95),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_ignores_lines_before_any_choice_started():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("שאלה 19 embedded too early", 25, 45),
        ("א. choice one", 50, 70),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_stops_at_next_real_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("שאלה 19 mangled but after a different real header", 75, 95),
        ("א. Red", 100, 120),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_embedded_header_bounds'`

- [ ] **Step 3: Implement**

In `parser.py`, add directly after `find_choice_line_bounds`:

```python
def find_embedded_header_bounds(lines, header_index):
    bounds = {}
    choice_count = 0
    for text, top, bottom in lines[header_index + 1:]:
        if is_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            choice_count += 1
        elif choice_count > 0 and is_probable_embedded_header(text):
            bounds.setdefault(choice_count, (top, bottom))
    return bounds
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all existing tests + 4 new)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_embedded_header_bounds to locate merged-block split boundaries"
```

---

### Task 4: Extend `attach_question_images` to attach choice/embedded-header bounds

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

`attach_question_images` already buckets questions and bands per page and zips them by count. This task adds an optional `page_lines` parameter: when a page's bands match its question count (using the psm-retry-corrected lines when a retry was accepted, never the stale default-pass lines — a real correctness requirement, since retried bands live in a different pixel/segmentation space than the default pass), each question also gets `choice_line_bounds`, `embedded_header_bounds`, and `page_image` attached, using the header's position within that page's lines (found via `find_header_line_indices`, at the same index as the question's position within the page's question list — both driven by the same per-page, in-order `is_header_line` detection).

- [ ] **Step 1: Write the failing tests**

Add to `test_app.py`, add `find_header_line_indices`-style new names are not needed here (they're called internally by `app.py`, not imported into the test file). Add these tests after `test_attach_question_images_skips_retry_without_a_recorded_page_image`:

```python
def test_attach_question_images_attaches_choice_and_embedded_header_bounds():
    image_a = Image.new("RGB", (100, 300), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d", "e", "f"], "header_line_index": 0},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (20, 50))]
    lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. a", 50, 70),
        ("ב. b", 75, 95),
        ("שאלה 'on' 2 (5 בק')", 100, 120),
        ("ג. c", 130, 150),
        ("ד. d", 155, 175),
        ("ה. e", 180, 200),
        ("א. f", 205, 225),
    ]
    page_lines = {2: lines}

    app.attach_question_images(parsed_questions, page_offsets, page_bands, page_lines=page_lines)

    q = parsed_questions[0]
    assert q["question_image"] is not None
    assert q["choice_line_bounds"] == [
        (50, 70), (75, 95), (130, 150), (155, 175), (180, 200), (205, 225),
    ]
    assert q["embedded_header_bounds"] == {2: (100, 120)}
    assert q["page_image"] is image_a


def test_attach_question_images_uses_retried_lines_for_bounds_when_retry_accepted():
    image_a = Image.new("RGB", (100, 200), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 30))]
    page_images = {2: image_a}
    stale_default_lines = [("stale data that must not be used", 0, 5)]
    retried_lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. Paris", 100, 120),
        ("שאלה מס' 2 (5 נק')", 130, 150),
        ("א. Rome", 200, 220),
    ]

    with patch("app.extract_line_boxes", return_value=retried_lines):
        app.attach_question_images(
            parsed_questions, page_offsets, page_bands, page_images,
            page_lines={2: stale_default_lines},
        )

    assert parsed_questions[0]["choice_line_bounds"] == [(100, 120)]
    assert parsed_questions[1]["choice_line_bounds"] == [(200, 220)]


def test_attach_question_images_without_page_lines_matches_old_behavior():
    image_a = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 8))]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert "choice_line_bounds" not in parsed_questions[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v`
Expected: FAIL with `TypeError: attach_question_images() got an unexpected keyword argument 'page_lines'`

- [ ] **Step 3: Implement**

In `app.py`, update the `from parser import (...)` block to add the three new names:

```python
from parser import (
    strip_version_lines,
    parse_ocr_text,
    find_split_suggestions,
    find_question_crop_bounds,
    find_header_line_indices,
    find_choice_line_bounds,
    find_embedded_header_bounds,
)
```

Then replace the whole `attach_question_images` function with:

```python
def attach_question_images(parsed_questions, page_offsets, page_bands, page_images=None, page_lines=None):
    page_images = page_images or {}
    page_lines = page_lines or {}

    questions_by_page = {}
    for question in parsed_questions:
        page_number = page_number_for_line_index(page_offsets, question["header_line_index"])
        questions_by_page.setdefault(page_number, []).append(question)

    bands_by_page = {}
    for page_number, image, band in page_bands:
        bands_by_page.setdefault(page_number, []).append((image, band))

    for page_number, page_questions in questions_by_page.items():
        bands = bands_by_page.get(page_number, [])
        active_lines = page_lines.get(page_number)

        # A count mismatch on the default pass may just mean Tesseract's
        # default page segmentation dropped a header line entirely (seen in
        # practice: a clean, non-overlapping header line missing from both
        # OCR passes over the full page). Retry that one page at a sparser
        # segmentation mode, but only ever trust the retry if it finds at
        # least as many headers as the default pass did -- otherwise keep
        # the default result and fall through to the same safe None
        # fallback as before. If the retry IS accepted, its lines (not the
        # default pass's) become "active_lines" -- the retried bands live in
        # that pass's own pixel/segmentation space, not the default one's.
        if len(bands) != len(page_questions) and page_number in page_images:
            image = page_images[page_number]
            retried_lines = extract_line_boxes(image, config=RETRY_LINE_EXTRACTION_CONFIG)
            retried_bounds = find_question_crop_bounds(retried_lines)
            if len(retried_bounds) >= len(bands):
                bands = [(image, band) for band in retried_bounds]
                active_lines = retried_lines

        # Only attach images if this page's band count exactly matches its
        # question count -- otherwise we can't be sure a given band lines up
        # with the right question, so this page's questions fall back to None.
        if len(bands) == len(page_questions):
            header_indices = find_header_line_indices(active_lines) if active_lines else []
            for idx, (question, (image, band)) in enumerate(zip(page_questions, bands)):
                question["question_image"] = (
                    crop_question_image(image, band[0], band[1]) if band is not None else None
                )
                if active_lines and idx < len(header_indices):
                    header_index = header_indices[idx]
                    question["choice_line_bounds"] = find_choice_line_bounds(active_lines, header_index)
                    question["embedded_header_bounds"] = find_embedded_header_bounds(active_lines, header_index)
                    question["page_image"] = image
        else:
            for question in page_questions:
                question["question_image"] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all existing tests + 3 new)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Attach choice/embedded-header pixel bounds in attach_question_images"
```

---

### Task 5: Wire `page_lines` into `run_pipeline` and stop discarding merged questions' images

**Files:**
- Modify: `app.py`

`run_pipeline`'s line-extraction loop already builds `page_images`; this task adds the matching `page_lines` dict (using the same `MIN_PAGE_TEXT_LENGTH` filter already applied to `page_images`) and passes it to `attach_question_images`. It also removes the explicit `question_image = None` override that previously suppressed Phase 1's already-computed crop for merged (>5-choice) questions — 0-choice questions are unaffected since they never had a matching band to begin with (`find_question_crop_bounds` only emits a band when a following choice line exists).

`run_pipeline` has no existing unit tests (it needs a real PDF + tesseract binary) and this task doesn't add any — verified in Task 9's manual browser check, consistent with this codebase's existing convention for that function.

- [ ] **Step 1: Implement**

In `app.py`, replace:

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

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            # Flagged/needs-review questions always show plain OCR'd text in this
            # phase (Phase 2 will extend cropping to them) -- clear any image a
            # header/choice band happened to produce so it can never leak through.
            q["question_image"] = None
            needs_review.append(q)
        else:
            clean_questions.append(q)
```

with:

```python
    progress = st.progress(0)
    status = st.empty()
    page_bands = []
    page_images = {}
    page_lines = {}
    for i, (page_number, image, lines) in enumerate(run_line_extraction_all_pages(pdf_path), start=1):
        page_text_length = sum(len(text) for text, _, _ in lines)
        if page_text_length >= MIN_PAGE_TEXT_LENGTH:
            page_images[page_number] = image
            page_lines[page_number] = lines
            for band in find_question_crop_bounds(lines):
                page_bands.append((page_number, image, band))
        progress.progress(i / total_to_process)
        status.text(f"Extracting question images: page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    attach_question_images(parsed_questions, page_offsets, page_bands, page_images, page_lines)

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            needs_review.append(q)
        else:
            clean_questions.append(q)
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Wire page_lines into run_pipeline and stop discarding merged questions' images"
```

---

### Task 6: `split_choices` grows optional image data and per-part `question_image`/`image_bounds`

**Files:**
- Modify: `shuffler_core.py`
- Modify: `test_shuffler_core.py`

Part 0 keeps the block's own `question_image` unchanged (Task 5's free win). Parts 1+ get an `image_bounds` pixel region — `(embedded_header_bottom, first_choice_top)` — only when their exact split point has both a matching `embedded_header_bounds` entry and a matching `choice_line_bounds` entry; otherwise no `image_bounds` key is added at all, and the part falls back to today's plain-text behavior. The new parameters are optional and default to producing the exact same dict shape as before, so every existing `split_choices` test keeps passing unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `test_shuffler_core.py`:

```python
def test_split_choices_keeps_question_image_on_first_part_only():
    parts = split_choices("Q", ["a", "b", "c", "d"], [2], question_image=b"PNGDATA")
    assert parts[0]["question_image"] == b"PNGDATA"
    assert parts[1].get("question_image") is None


def test_split_choices_computes_image_bounds_for_matching_split_point():
    parts = split_choices(
        "Q", ["a", "b", "c", "d"], [2],
        choice_line_bounds=[(0, 20), (25, 45), (100, 120), (125, 145)],
        embedded_header_bounds={2: (60, 90)},
    )
    assert parts[1]["image_bounds"] == (90, 100)


def test_split_choices_leaves_image_bounds_unset_when_split_point_not_detected():
    parts = split_choices(
        "Q", ["a", "b", "c", "d"], [2],
        choice_line_bounds=[(0, 20), (25, 45), (100, 120), (125, 145)],
        embedded_header_bounds={},
    )
    assert parts[1].get("image_bounds") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: FAIL with `TypeError: split_choices() got an unexpected keyword argument 'question_image'`

- [ ] **Step 3: Implement**

In `shuffler_core.py`, replace `split_choices` with:

```python
def split_choices(question, choices, split_points, question_image=None, choice_line_bounds=None, embedded_header_bounds=None):
    n = len(choices)
    if any(not (0 < p < n) for p in split_points):
        raise ValueError(f"split points must be between 1 and {n - 1}")
    if list(split_points) != sorted(set(split_points)):
        raise ValueError("split points must be sorted, unique, and strictly increasing")

    choice_line_bounds = choice_line_bounds or []
    embedded_header_bounds = embedded_header_bounds or {}

    boundaries = [0] + list(split_points) + [n]
    parts = []
    for idx in range(len(boundaries) - 1):
        start, end = boundaries[idx], boundaries[idx + 1]
        part = {
            "question": question if idx == 0 else "",
            "choices": choices[start:end],
        }
        if idx == 0:
            if question_image is not None:
                part["question_image"] = question_image
        elif start in embedded_header_bounds and start < len(choice_line_bounds):
            header_bottom = embedded_header_bounds[start][1]
            choice_top = choice_line_bounds[start][0]
            part["image_bounds"] = (header_bottom, choice_top)
        parts.append(part)
    return parts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: PASS (all existing tests + 3 new)

- [ ] **Step 5: Commit**

```bash
git add shuffler_core.py test_shuffler_core.py
git commit -m "Carry image data through split_choices for post-split part images"
```

---

### Task 7: `attach_split_part_images` and wiring into the split button handler

**Files:**
- Modify: `app.py`
- Modify: `test_app.py`

`split_choices` only produces `image_bounds` (a pixel region), not actual image bytes — cropping needs the source page image, which `split_choices` (a pure `shuffler_core.py` function) deliberately doesn't depend on. `attach_split_part_images` does the actual crop, reusing `crop_question_image` (already imported in `app.py` since Phase 1).

- [ ] **Step 1: Write the failing tests**

Add to `test_app.py`:

```python
def test_attach_split_part_images_crops_using_bounds_and_page_image():
    page_image = Image.new("RGB", (200, 300), color="white")
    parts = [
        {"question": "Q", "choices": ["a", "b"], "question_image": b"EXISTING"},
        {"question": "", "choices": ["c", "d"], "image_bounds": (50, 100)},
    ]

    app.attach_split_part_images(parts, page_image)

    assert parts[0]["question_image"] == b"EXISTING"
    assert parts[1]["question_image"] is not None
    assert "image_bounds" not in parts[1]


def test_attach_split_part_images_leaves_question_image_unset_without_bounds():
    parts = [{"question": "", "choices": ["c", "d"]}]

    app.attach_split_part_images(parts, Image.new("RGB", (200, 300), color="white"))

    assert parts[0].get("question_image") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v`
Expected: FAIL with `AttributeError: module 'app' has no attribute 'attach_split_part_images'`

- [ ] **Step 3: Implement**

In `app.py`, add directly after `attach_question_images`:

```python
def attach_split_part_images(parts, page_image):
    for part in parts:
        bounds = part.pop("image_bounds", None)
        if bounds is not None and page_image is not None:
            part["question_image"] = crop_question_image(page_image, bounds[0], bounds[1])
```

Then, in the "Split question" button handler, replace:

```python
                else:
                    st.session_state[split_key] = shuffle_questions(
                        split_choices(q["question"], q["choices"], split_points)
                    )
                    st.rerun()
```

with:

```python
                else:
                    split_parts = split_choices(
                        q["question"],
                        q["choices"],
                        split_points,
                        question_image=q.get("question_image"),
                        choice_line_bounds=q.get("choice_line_bounds"),
                        embedded_header_bounds=q.get("embedded_header_bounds"),
                    )
                    attach_split_part_images(split_parts, q.get("page_image"))
                    st.session_state[split_key] = shuffle_questions(split_parts)
                    st.rerun()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all existing tests + 2 new)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Add attach_split_part_images and wire it into the split button handler"
```

---

### Task 8: Show the image on the pre-split flagged card

**Files:**
- Modify: `app.py`

Mirrors the "image if present, else text" branch `render_question_editor` already uses for clean questions (Phase 1). The choices list — where the split-relevant embedded header text actually lives — keeps rendering as plain text below either way, so nothing needed for deciding split points gets hidden by this change.

Per the design doc's testing section, this read-only display branch gets no new automated test (consistent with how Phase 1 handled the same kind of change) — verified manually in Task 9.

- [ ] **Step 1: Implement**

In `app.py`, replace:

```python
        if split_key not in st.session_state:
            st.subheader(f"Flagged Question {i + 1}")
            st.write(q["question"])
            for k, choice in enumerate(q["choices"]):
                st.write(f"{k}: {choice}")
```

with:

```python
        if split_key not in st.session_state:
            st.subheader(f"Flagged Question {i + 1}")
            question_image = q.get("question_image")
            if question_image:
                st.image(question_image)
            else:
                st.write(q["question"])
            for k, choice in enumerate(q["choices"]):
                st.write(f"{k}: {choice}")
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Show question_image on the pre-split flagged card when present"
```

---

### Task 9: Manual verification in the browser

**Files:** none (no code changes)

This is a manual check, run by Hila, not automated — per her stated preference (Streamlit UI checks are done by driving the browser herself) and per this plan's convention of not adding automated coverage for read-only image display.

- [ ] Start the Streamlit server fresh (it must have been stopped since before Task 1): `streamlit run app.py`
- [ ] Upload the full sample exam and click Process
- [ ] Find the flagged block containing merged questions 18/19/20. Confirm its pre-split card now shows a cropped image (Q18's real header→first-choice region) instead of plain text for the question body, while the choices still render as plain text below it
- [ ] Read the choices list to identify where the embedded (garbled) headers for 19 and 20 appear, and enter the corresponding split points (e.g. the indices right after each embedded header) in the split input, then click "Split question"
- [ ] Confirm part 1 shows an image (reusing the block's own header crop)
- [ ] Confirm parts 2/3: either show a real cropped image for that sub-question's body (if the embedded header line was detected), or fall back to the existing empty, editable question text field — never a crash, never a visibly wrong/misaligned image
- [ ] Confirm a 0-choice flagged question (if one exists in this exam) still shows fully as plain text, unaffected
- [ ] Confirm the clean-questions screen still behaves exactly as it did after Phase 1 (regression check)
- [ ] Click "Generate Final File" and confirm it still downloads and opens correctly
- [ ] Run `python -m pytest -q` one more time to confirm the full suite is green
- [ ] Stop the Streamlit server once the check is done (per Hila's preference — don't leave it running until the next test)

---

## Explicitly out of scope (matches the design doc)

- Fixing `find_split_suggestions`'s strict `HEADER_PATTERN` matching to use this phase's looser "שאלה + digit" detection — noted as a real, separate bug (it likely never fires for 13/14/18/19/20 in the real sample exam) and a genuine future improvement, but Hila asked to keep it out of this plan. When it's picked up later, it should stay suggestion-only (never auto-split without confirmation), matching how `find_split_suggestions` already works today.
- 0-choice flagged questions ever getting an image.
- Cross-page merged blocks.
- An embedded header whose text is fragmented across more than one physical OCR line.
- Detecting more than one embedded header between the same pair of real choices.
- Any change to `find_question_crop_bounds` itself, or to how clean questions are cropped.
