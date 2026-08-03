# Full-Auto Question-Boundary Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-split OCR-merged exam questions using loose-header and choice-lettering-reset signals, so the manual-split screen becomes a genuine rarity instead of a routine path.

**Architecture:** Two new boundary signals (`is_any_header_line` = strict-or-loose header match, and `find_letter_reset_indices` = a choice letter resetting mid-run) feed `parse_ocr_text` directly, each parsed question tagged with whether it came from a real header line (`has_real_header`). A per-exam expected choice count (mode of non-zero segment counts, falling back to today's {4,5} tolerance when unreliable) replaces the old "0 or >5" flagging rule. The same `is_any_header_line` signal is reused verbatim in the four pixel-side crop/bound functions so text and pixel detection can't drift apart. `attach_question_images` excludes `has_real_header=False` questions from its band-count check entirely (they structurally never have a band) instead of letting them cause whole-page mismatches.

**Tech Stack:** Python, pytest, Streamlit (`streamlit.testing.v1.AppTest`).

Spec: `docs/superpowers/specs/2026-08-03-auto-split-redesign-design.md`

---

### Task 1: Boundary signals + `parse_ocr_text` integration

**Files:**
- Modify: `parser.py:1-25` (constants/predicates), `parser.py:92-142` (`parse_ocr_text`)
- Test: `test_parser.py`

- [ ] **Step 1: Write failing tests for the new predicates and `parse_ocr_text` integration**

Add to `test_parser.py`:

```python
from parser import (
    find_question_crop_bounds,
    find_split_suggestions,
    parse_ocr_text,
    strip_version_lines,
    find_header_line_indices,
    is_probable_embedded_header,
    find_choice_line_bounds,
    find_embedded_header_bounds,
    is_any_header_line,
    choice_letter_rank,
    find_letter_reset_indices,
    determine_expected_choice_count,
    is_choice_count_suspicious,
)


def test_is_any_header_line_true_for_strict_header():
    assert is_any_header_line("שאלה מס' 5 (2 נק')") is True


def test_is_any_header_line_true_for_loose_header():
    assert is_any_header_line("שאלה 'on' 19 (5 בק')") is True


def test_is_any_header_line_false_for_ordinary_text():
    assert is_any_header_line("just a regular sentence") is False


def test_choice_letter_rank_returns_rank_for_choice_line():
    assert choice_letter_rank("א. Paris") == 0
    assert choice_letter_rank("ה. Berlin") == 4


def test_choice_letter_rank_none_for_non_choice_line():
    assert choice_letter_rank("some prose") is None


def test_find_letter_reset_indices_detects_terminal_heh_followed_by_reset():
    lines = [
        "question body",
        "א. one",
        "ב. two",
        "ג. three",
        "ד. four",
        "ה. five",
        "א. next question first choice",
    ]
    assert find_letter_reset_indices(lines, header_boundary_indices=[]) == [6]


def test_find_letter_reset_indices_ignores_forward_gap():
    lines = ["א. one", "ג. skipped bet, not a reset"]
    assert find_letter_reset_indices(lines, header_boundary_indices=[]) == []


def test_find_letter_reset_indices_resets_tracking_at_a_header_boundary():
    lines = [
        "א. one",
        "ב. two",
        "שאלה מס' 2 (2 נק')",
        "א. real next question, not a reset",
    ]
    assert find_letter_reset_indices(lines, header_boundary_indices=[2]) == []


def test_parse_ocr_text_splits_on_letter_reset_with_no_header_signal():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question one body",
        "א. one",
        "ב. two",
        "ג. three",
        "ד. four",
        "ה. five",
        "א. next question first choice",
        "ב. next question second choice",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["choices"] == ["one", "two", "three", "four", "five"]
    assert questions[1]["choices"] == ["next question first choice", "next question second choice"]
    assert questions[1]["header_line_index"] == 7
    assert questions[1]["has_real_header"] is False


def test_parse_ocr_text_tags_real_header_questions_true():
    text = "\n".join(["שאלה מס' 1 (2 נק')", "body", "א. one"])
    questions = parse_ocr_text(text)
    assert questions[0]["has_real_header"] is True


def test_parse_ocr_text_tags_loose_header_questions_true():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')", "body one", "א. a",
        "שאלה 'on' 2 (5 בק')", "body two", "א. b",
    ])
    questions = parse_ocr_text(text)
    assert len(questions) == 2
    assert questions[1]["has_real_header"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v -k "is_any_header_line or choice_letter_rank or letter_reset or tags_real_header or tags_loose_header"`
Expected: FAIL (`ImportError` — the new names don't exist yet)

- [ ] **Step 3: Implement the new predicates in `parser.py`**

Add near the top of `parser.py`, after the existing constants (after line 13):

```python
CHOICE_LETTER_ORDER = "אבגדה"
CHOICE_LETTER_RANK = {letter: rank for rank, letter in enumerate(CHOICE_LETTER_ORDER)}
```

Add right after `is_probable_embedded_header` (after line 21):

```python
def is_any_header_line(line):
    return is_header_line(line) or is_probable_embedded_header(line)


def choice_letter_rank(line):
    match = CHOICE_PATTERN.match(line)
    if not match:
        return None
    return CHOICE_LETTER_RANK[match.group(1)]


def find_letter_reset_indices(lines, header_boundary_indices):
    header_boundary_set = set(header_boundary_indices)
    indices = []
    max_rank_seen = -1
    for i, line in enumerate(lines):
        if i in header_boundary_set:
            max_rank_seen = -1
            continue
        rank = choice_letter_rank(line)
        if rank is None:
            continue
        if rank <= max_rank_seen:
            indices.append(i)
        max_rank_seen = rank
    return indices
```

- [ ] **Step 4: Rewrite `parse_ocr_text`'s boundary detection**

Replace `parse_ocr_text` (`parser.py:92-142`) with:

```python
def parse_ocr_text(text, page_offsets=None):
    text = strip_bidi_marks(text)
    lines = text.splitlines()

    page_boundary_starts = {start for _, start in page_offsets[1:]} if page_offsets else set()

    header_indices = [i for i, line in enumerate(lines) if is_any_header_line(line)]
    header_index_set = set(header_indices)
    letter_reset_indices = find_letter_reset_indices(lines, header_indices)
    all_boundaries = sorted(header_index_set | set(letter_reset_indices))

    block_starts = [0] + all_boundaries
    block_bounds = [
        (start, block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines))
        for idx, start in enumerate(block_starts)
    ]

    questions = []
    for start, end in block_bounds:
        block_lines = lines[start:end]
        content_start = start
        has_real_header = start in header_index_set
        if has_real_header:
            block_lines = block_lines[1:]
            content_start = start + 1

        question_lines = []
        choices = []
        in_choices = False

        for offset, line in enumerate(block_lines):
            absolute_index = content_start + offset
            stripped = line.strip()
            if not stripped:
                continue

            match = CHOICE_PATTERN.match(line)
            if match:
                in_choices = True
                choices.append(match.group(2).strip())
            elif in_choices and absolute_index in page_boundary_starts:
                choices.append(stripped)
            elif in_choices:
                choices[-1] = (choices[-1] + " " + stripped).strip()
            else:
                question_lines.append(stripped)

        question_text = " ".join(question_lines).strip()
        if question_text or choices:
            questions.append({
                "question": question_text,
                "choices": choices,
                "header_line_index": start,
                "has_real_header": has_real_header,
            })

    return questions
```

Note: a leading block with no signal at all (content before the very first detected boundary) also gets `has_real_header = False` — correct, since it has no header line either.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all tests, including every pre-existing `test_parse_ocr_text_*` and `test_find_question_crop_bounds_*` case — this step must not touch pixel-side functions or existing text-side behavior for inputs with no letter-reset)

- [ ] **Step 6: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add loose-header and choice-letter-reset boundary signals to parse_ocr_text"
```

---

### Task 2: Per-exam expected choice count

**Files:**
- Modify: `parser.py` (new functions), `app.py:155-164` (classification)
- Test: `test_parser.py`, `test_app.py`

- [ ] **Step 1: Write failing tests**

Add to `test_parser.py`:

```python
def test_determine_expected_choice_count_clear_majority():
    questions = [{"choices": ["a"] * 4}] * 5 + [{"choices": ["a"] * 3}]
    assert determine_expected_choice_count(questions) == 4


def test_determine_expected_choice_count_excludes_zero_choice_questions():
    questions = [{"choices": ["a"] * 4}] * 2 + [{"choices": []}] * 5
    assert determine_expected_choice_count(questions) == 4


def test_determine_expected_choice_count_none_on_tie():
    questions = [{"choices": ["a"] * 4}] * 2 + [{"choices": ["a"] * 5}] * 2
    assert determine_expected_choice_count(questions) is None


def test_determine_expected_choice_count_none_when_top_count_too_rare():
    questions = [{"choices": ["a"] * 4}]
    assert determine_expected_choice_count(questions) is None


def test_is_choice_count_suspicious_matches_expected_count():
    assert is_choice_count_suspicious(4, expected_count=4) is False
    assert is_choice_count_suspicious(5, expected_count=4) is True


def test_is_choice_count_suspicious_falls_back_to_four_or_five_when_no_expected_count():
    assert is_choice_count_suspicious(4, expected_count=None) is False
    assert is_choice_count_suspicious(5, expected_count=None) is False
    assert is_choice_count_suspicious(3, expected_count=None) is True
    assert is_choice_count_suspicious(0, expected_count=None) is True
```

Add to `test_app.py`:

```python
def test_classify_questions_flags_count_that_does_not_match_exam_expected_count():
    parsed_questions = [
        {"question": "Q1", "choices": ["a"] * 4},
        {"question": "Q2", "choices": ["a"] * 4},
        {"question": "Q3", "choices": ["a"] * 3},
    ]
    clean, needs_review = app.classify_questions(parsed_questions)
    assert [q["question"] for q in clean] == ["Q1", "Q2"]
    assert [q["question"] for q in needs_review] == ["Q3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py test_app.py -v -k "expected_choice_count or is_choice_count_suspicious or classify_questions"`
Expected: FAIL (`ImportError`/`AttributeError` — none of these names exist yet)

- [ ] **Step 3: Implement `determine_expected_choice_count` and `is_choice_count_suspicious` in `parser.py`**

Add near the top of `parser.py`, alongside the other constants:

```python
from collections import Counter

MIN_EXPECTED_COUNT_SAMPLES = 2
FALLBACK_ACCEPTABLE_COUNTS = {4, 5}
```

Add near the bottom of `parser.py`, before the `if __name__ == "__main__":` block:

```python
def determine_expected_choice_count(questions):
    counts = [len(q["choices"]) for q in questions if len(q["choices"]) > 0]
    if not counts:
        return None
    tally = Counter(counts).most_common()
    top_count, top_freq = tally[0]
    if top_freq < MIN_EXPECTED_COUNT_SAMPLES:
        return None
    if len(tally) > 1 and tally[1][1] == top_freq:
        return None
    return top_count


def is_choice_count_suspicious(choice_count, expected_count):
    if expected_count is None:
        return choice_count not in FALLBACK_ACCEPTABLE_COUNTS
    return choice_count != expected_count
```

- [ ] **Step 4: Add `classify_questions` to `app.py` and use it in `run_pipeline`**

Add the import in `app.py`'s existing `from parser import (...)` block (`app.py:15-23`):

```python
from parser import (
    strip_version_lines,
    parse_ocr_text,
    find_split_suggestions,
    find_question_crop_bounds,
    find_header_line_indices,
    find_choice_line_bounds,
    find_embedded_header_bounds,
    determine_expected_choice_count,
    is_choice_count_suspicious,
)
```

Add this function right before `run_pipeline` (before `app.py:117`):

```python
def classify_questions(parsed_questions):
    expected_count = determine_expected_choice_count(parsed_questions)
    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if is_choice_count_suspicious(len(q["choices"]), expected_count):
            needs_review.append(q)
        else:
            clean_questions.append(q)
    return clean_questions, needs_review
```

Replace the classification block in `run_pipeline` (`app.py:155-164`):

```python
    clean_questions, needs_review = classify_questions(parsed_questions)
    shuffled_questions = shuffle_questions(clean_questions)
    return shuffled_questions, needs_review
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest test_parser.py test_app.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Commit**

```bash
git add parser.py app.py test_parser.py test_app.py
git commit -m "Replace 0-or->5 flagging rule with a per-exam expected choice count"
```

---

### Task 3: Pixel-side lockstep

**Files:**
- Modify: `parser.py:36-75` (`find_question_crop_bounds`, `find_header_line_indices`, `find_choice_line_bounds`, `find_embedded_header_bounds`)
- Test: `test_parser.py`

- [ ] **Step 1: Write failing tests for loose-header recognition on the pixel side**

Add to `test_parser.py`:

```python
def test_find_header_line_indices_recognizes_loose_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה 'on' 6 (3 בק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_header_line_indices(lines) == [0, 2]


def test_find_question_crop_bounds_recognizes_loose_header_as_anchor():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("question one text", 25, 45),
        ("א. Paris", 50, 70),
        ("שאלה 'on' 6 (3 בק')", 75, 95),
        ("question two text", 100, 120),
        ("א. Red", 125, 145),
    ]
    assert find_question_crop_bounds(lines) == [(20, 50), (95, 125)]


def test_find_choice_line_bounds_stops_at_loose_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה 'on' 6 (3 בק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [(25, 45)]


def test_find_embedded_header_bounds_stops_at_loose_header_not_catalog_it():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("שאלה 'on' 19 (5 בק')", 50, 70),
        ("א. choice from next question", 75, 95),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}
```

Note: the last test's expectation changes on purpose — once a loose header is a real auto-split boundary (Task 1), it must stop the pixel-side scan too, not get cataloged as "embedded within this question." A loose header inside an *already-flagged* block being manually reviewed is a different, unaffected path (that block never reached `parse_ocr_text`'s auto-split as a single clean unit in the first place).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v -k "loose_header"`
Expected: FAIL (`find_header_line_indices` returns `[0]` not `[0, 2]`; `find_question_crop_bounds` returns a shorter list; `find_embedded_header_bounds` returns `{2: (50, 70)}` not `{}`)

- [ ] **Step 3: Update the four pixel-side functions**

In `parser.py`, replace all four functions (`parser.py:36-75`):

```python
def find_question_crop_bounds(lines):
    bounds = []
    for i, (text, _, header_bottom) in enumerate(lines):
        if not is_any_header_line(text):
            continue

        band = None
        for choice_text, choice_top, _ in lines[i + 1:]:
            if is_any_header_line(choice_text):
                break
            if CHOICE_PATTERN.match(choice_text):
                if choice_top - header_bottom >= MIN_CROP_BAND_HEIGHT:
                    band = (header_bottom, choice_top)
                break
        bounds.append(band)

    return bounds


def find_choice_line_bounds(lines, header_index):
    bounds = []
    for text, top, bottom in lines[header_index + 1:]:
        if is_any_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            bounds.append((top, bottom))
    return bounds


def find_embedded_header_bounds(lines, header_index):
    bounds = {}
    choice_count = 0
    for text, top, bottom in lines[header_index + 1:]:
        if is_any_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            choice_count += 1
        elif choice_count > 0 and is_probable_embedded_header(text):
            bounds.setdefault(choice_count, (top, bottom))
    return bounds
```

And update `find_header_line_indices` (`parser.py:24-25`):

```python
def find_header_line_indices(lines):
    return [i for i, (text, _, _) in enumerate(lines) if is_any_header_line(text)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all tests, including the pre-existing embedded-header tests using strict headers only — those are unaffected since a strict header also satisfies `is_any_header_line`)

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Recognize loose headers in pixel-side crop and bound detection"
```

---

### Task 4: Tag-based safe fallback in `attach_question_images`

**Files:**
- Modify: `app.py:56-108` (`attach_question_images`)
- Test: `test_app.py`

- [ ] **Step 1: Write failing tests**

Add to `test_app.py`:

```python
def test_attach_question_images_letter_reset_question_gets_none_without_affecting_siblings():
    image_a = Image.new("RGB", (100, 200), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0, "has_real_header": True},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10, "has_real_header": False},
    ]
    page_offsets = [(2, 0)]
    # Only one band exists -- for Q1, the only has_real_header question. Q2 has
    # no real header so it must never be compared against band count at all.
    page_bands = [(2, image_a, (5, 30))]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_defaults_has_real_header_true_when_key_absent():
    image_a = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
    ]
    page_offsets = [(2, 0)]
    page_bands = [(2, image_a, (5, 8))]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_app.py -v -k "letter_reset_question or defaults_has_real_header"`
Expected: FAIL (`parsed_questions[0]["question_image"]` is `None` in the first test today, because the whole-page count check sees 1 band vs. 2 questions and blanks both)

- [ ] **Step 3: Update `attach_question_images`**

Replace `attach_question_images`'s body from the `questions_by_page` loop onward (`app.py:69-107`):

```python
    for page_number, page_questions in questions_by_page.items():
        bands = bands_by_page.get(page_number, [])
        active_lines = page_lines.get(page_number)

        header_based_questions = [q for q in page_questions if q.get("has_real_header", True)]
        for question in page_questions:
            if not question.get("has_real_header", True):
                question["question_image"] = None

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
        if len(bands) != len(header_based_questions) and page_number in page_images:
            image = page_images[page_number]
            retried_lines = extract_line_boxes(image, config=RETRY_LINE_EXTRACTION_CONFIG)
            retried_bounds = find_question_crop_bounds(retried_lines)
            if len(retried_bounds) >= len(bands):
                bands = [(image, band) for band in retried_bounds]
                active_lines = retried_lines

        # Questions with no real header (letter-reset or leading-block splits)
        # are excluded above -- they structurally never have a crop band, so
        # they must never count against this page's match check. Only
        # header-based questions are compared against bands here.
        if len(bands) == len(header_based_questions):
            header_indices = find_header_line_indices(active_lines) if active_lines else []
            for idx, (question, (image, band)) in enumerate(zip(header_based_questions, bands)):
                question["question_image"] = (
                    crop_question_image(image, band[0], band[1]) if band is not None else None
                )
                if active_lines and idx < len(header_indices):
                    header_index = header_indices[idx]
                    question["choice_line_bounds"] = find_choice_line_bounds(active_lines, header_index)
                    question["embedded_header_bounds"] = find_embedded_header_bounds(active_lines, header_index)
                    question["page_image"] = image
        else:
            for question in header_based_questions:
                question["question_image"] = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_app.py -v`
Expected: PASS (all tests, including every pre-existing `test_attach_question_images_*` case — those all use `has_real_header`-absent fixtures, which default to `True` and preserve today's exact behavior)

- [ ] **Step 5: Commit**

```bash
git add app.py test_app.py
git commit -m "Exclude headerless questions from attach_question_images's band-count check"
```

---

### Task 5: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest -v`
Expected: PASS (all tests across `test_parser.py`, `test_app.py`, `test_shuffler_core.py`, `test_ocr.py`, `test_test_ocr.py`)

- [ ] **Step 2: Start the app and run both real sample exams through it**

Follow this project's existing manual-verification convention (Hila drives the Streamlit UI herself — see `CLAUDE.md`'s development workflow note on restarting the server after editing an imported module). Start `streamlit run app.py`, upload the data-science sample exam, and separately `sample_exams/מבחן-כלכלה.pdf`. For each:
- Confirm the previously-3-flagged questions (data-science exam) now split automatically.
- Confirm the flagged/needs_review screen shows few or no questions on both exams.
- Confirm images are still attached correctly for ordinary, non-merged questions (spot-check a few).

- [ ] **Step 3: Stop the server**

Per existing project convention: stop the Streamlit dev server right after this manual check.

- [ ] **Step 4: Report results**

Summarize actual counts observed (e.g. "N flagged before, M flagged after") back to Hila before considering this plan complete. No commit for this task — it's verification only.

---

## Explicitly out of scope (matches the spec)

- No change to `find_split_suggestions`, `split_choices`, or `attach_split_part_images` — the manual-split screen's mechanics are untouched, only its expected frequency changes.
- No unification of the two OCR passes.
- No matching pixel-side bands to text-side questions by embedded question number.
- No change to `MIN_CHOICES`'s use in the flagged-screen editor.
