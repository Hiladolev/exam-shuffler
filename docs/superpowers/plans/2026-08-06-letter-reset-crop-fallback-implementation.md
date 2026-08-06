# Letter-Reset Crop Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a letter-reset-created question (`has_real_header=False`, not the leading block) ends up with a completely empty stem, attach a cropped image of the page region between the preceding choice-lettered line and this question's own first choice line, instead of leaving it blank.

**Architecture:** A new pixel-side function `find_letter_reset_crop_bounds` in `parser.py` scans a page's OCR line boxes for choice-letter-rank resets (mirroring `find_letter_reset_indices`'s tracking, but on pixel `(text, top, bottom)` tuples instead of plain text lines) and emits one crop band per detected reset. `attach_question_images` in `app.py` gets a second pairing pass, after the existing header-based one, that pairs genuine letter-reset questions to these bands in page order and only attaches an image when the question's `question` text is empty.

**Tech Stack:** Python, pytest, existing `parser.py`/`app.py`/`test_ocr.py` modules — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-06-letter-reset-crop-fallback-design.md`

---

### Task 1: `find_letter_reset_crop_bounds` in `parser.py`

**Files:**
- Modify: `parser.py` (add function after `find_question_crop_bounds`, currently ending at line 86)
- Test: `test_parser.py` (add tests; extend the existing `from parser import (...)` block at the top)

- [ ] **Step 1: Write the failing tests**

Add to the `from parser import (...)` block at the top of `test_parser.py`:

```python
    find_letter_reset_crop_bounds,
```

(insert it as its own line inside the existing import parentheses, alongside `find_question_crop_bounds` etc.)

Append these tests to `test_parser.py`:

```python
def test_find_letter_reset_crop_bounds_basic_reset_returns_band():
    lines = [
        ("א. one", 0, 20),
        ("ב. two", 25, 45),
        ("א. next question first choice", 200, 220),
    ]
    assert find_letter_reset_crop_bounds(lines) == [(45, 200)]


def test_find_letter_reset_crop_bounds_chained_resets_anchor_off_previous_reset():
    lines = [
        ("א. Q_prev choice one", 0, 20),
        ("ב. Q_prev choice two", 25, 45),
        ("א. Q_next1 first choice", 200, 220),
        ("ב. Q_next1 second choice", 225, 245),
        ("א. Q_next2 first choice", 400, 420),
    ]
    # The second reset must anchor off Q_next1's own last choice (245), not
    # Q_prev's (45) -- confirms chained headerless questions need no special
    # "walk back through the chain" code, just continuous tracking.
    assert find_letter_reset_crop_bounds(lines) == [(45, 200), (245, 400)]


def test_find_letter_reset_crop_bounds_skips_non_choice_lines_when_anchoring():
    lines = [
        ("א. Q_prev last real choice", 0, 20),
        ("mangled header attempt gibberish", 25, 45),
        ("garbled intro sentence text", 50, 70),
        ("א. Q_next first choice", 200, 220),
    ]
    # Reproduces the verified Q2/Q3 shape: the mangled-header-attempt and
    # garbled-intro-sentence lines were transcribed by OCR but must not be
    # used as the anchor -- the band still starts at Q_prev's real last
    # choice (20), not at either skipped line's position.
    assert find_letter_reset_crop_bounds(lines) == [(20, 200)]


def test_find_letter_reset_crop_bounds_band_shorter_than_minimum_height_returns_none():
    lines = [
        ("א. one", 0, 20),
        ("ב. two", 25, 45),
        ("א. next", 47, 65),
    ]
    assert find_letter_reset_crop_bounds(lines) == [None]


def test_find_letter_reset_crop_bounds_no_reset_present_returns_empty_list():
    lines = [
        ("א. one", 0, 20),
        ("ב. two", 25, 45),
    ]
    assert find_letter_reset_crop_bounds(lines) == []


def test_find_letter_reset_crop_bounds_resets_tracking_at_header_boundary():
    lines = [
        ("א. one", 0, 20),
        ("ב. two", 25, 45),
        ("שאלה מס' 2 (2 נק')", 50, 70),
        ("א. real next question, not a reset", 75, 95),
    ]
    # A real header line resets the rank tracking, so the following
    # legitimate א. start is correctly NOT flagged as a reset.
    assert find_letter_reset_crop_bounds(lines) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_parser.py -k find_letter_reset_crop_bounds -v`
Expected: FAIL with `ImportError: cannot import name 'find_letter_reset_crop_bounds'`

- [ ] **Step 3: Implement `find_letter_reset_crop_bounds`**

In `parser.py`, insert this function immediately after `find_question_crop_bounds` (which currently ends at line 86, right before `def find_choice_line_bounds`):

```python
def find_letter_reset_crop_bounds(lines):
    bounds = []
    max_rank_seen = -1
    last_choice_bottom = None
    for text, top, bottom in lines:
        if is_any_header_line(text):
            max_rank_seen = -1
            continue
        rank = choice_letter_rank(text)
        if rank is None:
            continue
        if rank <= max_rank_seen:
            band = (last_choice_bottom, top) if top - last_choice_bottom >= MIN_CROP_BAND_HEIGHT else None
            bounds.append(band)
        max_rank_seen = rank
        last_choice_bottom = bottom
    return bounds
```

Note: a reset can only fire once `max_rank_seen` has already been set away from its initial `-1`, which only happens after a real `CHOICE_PATTERN` line has already been seen in this same call -- so `last_choice_bottom` is guaranteed non-`None` whenever the reset branch runs. This also means a reset whose true anchor lives on the *previous* page (pixel-side extraction is per-page, so this function is called fresh per page with no carried-over state) is never detected as a reset at all here -- it simply produces no bounds entry for that page, one fewer than the number of genuine letter-reset questions expected there. That undercount is exactly what Task 2's safe-prefix pairing is built to absorb safely (falls back to no image for that one question), so no explicit "no anchor" sentinel is needed in this function's return value.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_parser.py -k find_letter_reset_crop_bounds -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full parser test suite**

Run: `pytest test_parser.py -v`
Expected: PASS (all tests, no regressions)

- [ ] **Step 6: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_letter_reset_crop_bounds for pixel-side letter-reset boundaries"
```

---

### Task 2: Wire the fallback into `attach_question_images` in `app.py`

**Files:**
- Modify: `app.py` (import block at top; `attach_question_images`, currently lines 58-124)
- Test: `test_app.py`

- [ ] **Step 1: Write the failing tests**

Append these tests to `test_app.py`:

```python
def test_attach_question_images_letter_reset_empty_stem_question_gets_crop_fallback_image():
    image_a = Image.new("RGB", (100, 300), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d", "e"], "header_line_index": 0, "has_real_header": True},
        {"question": "", "choices": ["f", "g"], "header_line_index": 10, "has_real_header": False},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 30))]
    lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. a", 50, 70),
        ("ב. b", 75, 95),
        ("ג. c", 100, 120),
        ("ד. d", 125, 145),
        ("ה. e", 150, 170),
        ("א. f", 250, 270),
        ("ב. g", 275, 295),
    ]
    page_lines = {2: lines}
    page_images = {2: image_a}

    app.attach_question_images(parsed_questions, page_offsets, page_bands, page_images, page_lines)

    assert parsed_questions[1]["question_image"] is not None


def test_attach_question_images_letter_reset_nonempty_stem_question_keeps_text_no_image():
    image_a = Image.new("RGB", (100, 300), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d", "e"], "header_line_index": 0, "has_real_header": True},
        {"question": "some recovered stem text", "choices": ["f", "g"], "header_line_index": 10, "has_real_header": False},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 30))]
    lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. a", 50, 70),
        ("ב. b", 75, 95),
        ("ג. c", 100, 120),
        ("ד. d", 125, 145),
        ("ה. e", 150, 170),
        ("א. f", 250, 270),
        ("ב. g", 275, 295),
    ]
    page_lines = {2: lines}
    page_images = {2: image_a}

    app.attach_question_images(parsed_questions, page_offsets, page_bands, page_images, page_lines)

    # Even though the band paired successfully, a question that already has
    # recovered stem text must never have that text hidden behind an image.
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_letter_reset_stops_pairing_when_pixel_side_finds_fewer_resets():
    image_a = Image.new("RGB", (100, 400), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d", "e"], "header_line_index": 0, "has_real_header": True},
        {"question": "", "choices": ["f", "g"], "header_line_index": 10, "has_real_header": False},
        {"question": "", "choices": ["h", "i"], "header_line_index": 15, "has_real_header": False},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 30))]
    # Text side detected two genuine letter-reset questions on this page, but
    # the pixel side only finds one real choice-letter reset (א after ה) --
    # "ג. h"/"ד. i" continue the same run instead of restarting at א. This
    # simulates the pixel side undercounting relative to the text side.
    lines = [
        ("שאלה מס' 1 (5 נק')", 0, 20),
        ("א. a", 50, 70),
        ("ב. b", 75, 95),
        ("ג. c", 100, 120),
        ("ד. d", 125, 145),
        ("ה. e", 150, 170),
        ("א. f", 250, 270),
        ("ב. g", 275, 295),
        ("ג. h", 300, 320),
        ("ד. i", 325, 345),
    ]
    page_lines = {2: lines}
    page_images = {2: image_a}

    app.attach_question_images(parsed_questions, page_offsets, page_bands, page_images, page_lines)

    assert parsed_questions[1]["question_image"] is not None
    assert parsed_questions[2]["question_image"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_app.py -k letter_reset -v`
Expected: the three new tests FAIL (first two on `assert ... is not None` / `is None` mismatches since no crop fallback exists yet; the pre-existing `test_attach_question_images_letter_reset_question_gets_none_without_affecting_siblings` test should still PASS unaffected)

- [ ] **Step 3: Add the import**

In `app.py`, in the `from parser import (...)` block (currently lines 15-25), add `find_letter_reset_crop_bounds,` after `find_question_crop_bounds,`:

```python
from parser import (
    strip_version_lines,
    parse_ocr_text,
    find_split_suggestions,
    find_question_crop_bounds,
    find_letter_reset_crop_bounds,
    find_header_line_indices,
    find_choice_line_bounds,
    find_embedded_header_bounds,
    determine_expected_choice_count,
    is_choice_count_suspicious,
)
```

- [ ] **Step 4: Add the pairing pass to `attach_question_images`**

In `app.py`, find this block (the end of `attach_question_images`, currently lines 121-124):

```python
        else:
            for question in header_based_questions:
                question["question_image"] = None
```

Replace it with:

```python
        else:
            for question in header_based_questions:
                question["question_image"] = None

        genuine_letter_reset_questions = [q for q in page_questions if not is_band_eligible(q)]
        if genuine_letter_reset_questions and active_lines:
            reset_image = page_images.get(page_number)
            reset_bounds = find_letter_reset_crop_bounds(active_lines)
            for question, band in zip(genuine_letter_reset_questions, reset_bounds):
                if band is not None and reset_image is not None and question["question"].strip() == "":
                    question["question_image"] = crop_question_image(reset_image, band[0], band[1])
```

This runs after the header-based block so it sees whichever `active_lines` that block settled on (default pass or accepted psm-12 retry). `zip` naturally implements the safe-prefix rule: pairing stops at the shorter of the two lists, so any question beyond that point simply keeps the `question_image=None` it was already given earlier in this same loop iteration (line ~86, the `is_band_eligible` exclusion block).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest test_app.py -k letter_reset -v`
Expected: PASS (all 4: the 3 new tests plus the pre-existing one)

- [ ] **Step 6: Run the full app test suite**

Run: `pytest test_app.py -v`
Expected: PASS (all tests, no regressions)

- [ ] **Step 7: Commit**

```bash
git add app.py test_app.py
git commit -m "Attach crop fallback image to empty-stem letter-reset questions"
```

---

### Task 3: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: PASS, all tests across `test_parser.py`, `test_app.py`, `test_shuffler_core.py`, `test_ocr.py`, `test_test_ocr.py`

- [ ] **Step 2: Push**

```bash
git push
```

---

## Explicitly out of scope (carried from the spec)

- Cross-page anchor carry-over (a reset whose true anchor lives on the previous page stays a no-image fallback, per Task 1 Step 3's note).
- A dedicated retry pass keyed on reset-count mismatches, separate from the existing header-retry trigger.
- Any change to non-empty-stem letter-reset questions' existing text-only rendering.
- Issue #2 from the auto-split-redesign spec (corrupted text landing on a valid choice count) -- unrelated, no fix attempted here.
