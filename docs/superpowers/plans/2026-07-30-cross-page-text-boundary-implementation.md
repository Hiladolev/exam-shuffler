# Stop `parse_ocr_text` Gluing Choice Text Across Page Boundaries — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a merged/flagged question block spans two OCR'd pages, `parse_ocr_text` should stop silently gluing the next page's leading content onto the last choice accumulated on the previous page, and instead start a new choice entry at the page boundary.

**Architecture:** `parse_ocr_text` grows an optional `page_offsets` parameter (the same `[(page_number, start_line_index), ...]` list `app.py`'s `build_page_offsets` already produces, and already computes before calling `parse_ocr_text`). Internally it derives a plain set of "line indices where a new page starts" and checks each line's absolute position against it while walking a block's choices — no page-number-resolution logic is added, just index-set membership. The choice-continuation loop is changed from a plain `for line in block_lines` to an enumerated walk so each line's absolute position in the full document is available for that check.

**Tech Stack:** Python, pytest (pure-function tests).

**Design doc:** `docs/superpowers/specs/2026-07-30-cross-page-text-boundary-design.md`

---

## Before you start

The Streamlit dev server must be **stopped** for the entire duration of Task 1 (it edits `parser.py`, a module `app.py` imports; per this repo's `CLAUDE.md`, editing a module `app.py` imports while the server is running leaves it serving stale code from `sys.modules`). It can stay stopped through Task 2 as well (`app.py` itself is fine to edit live, since Streamlit re-executes its top level on every rerun, but `parser.py` won't be re-imported either way until a restart). Only start it fresh again for Task 3, the final manual check.

---

### Task 1: `parse_ocr_text` grows an optional `page_offsets` parameter

**Files:**
- Modify: `parser.py`
- Modify: `test_parser.py`

- [ ] **Step 0: Stop the Streamlit dev server**

If a `streamlit run app.py` process is running from an earlier session, stop it now (it must stay stopped through this task, since it edits `parser.py`).

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py`, at the end of the file:

```python
def test_parse_ocr_text_starts_new_choice_at_page_boundary_instead_of_gluing():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. choice one",
        "ב. choice two",
        "continuation from next page",
        "א. choice three",
    ])
    page_offsets = [(2, 0), (3, 4)]

    questions = parse_ocr_text(text, page_offsets)

    assert len(questions) == 1
    assert questions[0]["choices"] == [
        "choice one",
        "choice two",
        "continuation from next page",
        "choice three",
    ]


def test_parse_ocr_text_without_page_offsets_keeps_gluing_across_pages():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. choice one",
        "ב. choice two",
        "continuation from next page",
        "א. choice three",
    ])

    questions = parse_ocr_text(text)

    assert len(questions) == 1
    assert questions[0]["choices"] == [
        "choice one",
        "choice two continuation from next page",
        "choice three",
    ]


def test_parse_ocr_text_boundary_inside_question_intro_prose_is_inert():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question line one",
        "question line two",
        "א. choice one",
    ])
    page_offsets = [(2, 0), (3, 2)]

    questions = parse_ocr_text(text, page_offsets)

    assert len(questions) == 1
    assert questions[0]["question"] == "question line one question line two"
    assert questions[0]["choices"] == ["choice one"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v -k "page_boundary or page_offsets"`
Expected: `test_parse_ocr_text_starts_new_choice_at_page_boundary_instead_of_gluing` and `test_parse_ocr_text_boundary_inside_question_intro_prose_is_inert` FAIL (their asserted `choices`/`question` don't match today's glued-together output); `test_parse_ocr_text_without_page_offsets_keeps_gluing_across_pages` PASSES already (it exercises today's existing behavior, and `parse_ocr_text` already accepts one positional argument) — that's expected, it's the regression-coverage test for Step 4.

- [ ] **Step 3: Implement**

In `parser.py`, replace the `parse_ocr_text` function:

```python
def parse_ocr_text(text):
    text = strip_bidi_marks(text)
    lines = text.splitlines()

    header_indices = [i for i, line in enumerate(lines) if is_header_line(line)]
    block_starts = [0] + header_indices
    block_bounds = [
        (start, block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines))
        for idx, start in enumerate(block_starts)
    ]

    questions = []
    for start, end in block_bounds:
        block_lines = lines[start:end]
        if start in header_indices:
            block_lines = block_lines[1:]

        question_lines = []
        choices = []
        in_choices = False

        for line in block_lines:
            stripped = line.strip()
            if not stripped:
                continue

            match = CHOICE_PATTERN.match(line)
            if match:
                in_choices = True
                choices.append(match.group(2).strip())
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
            })

    return questions
```

with:

```python
def parse_ocr_text(text, page_offsets=None):
    text = strip_bidi_marks(text)
    lines = text.splitlines()

    page_boundary_starts = {start for _, start in page_offsets[1:]} if page_offsets else set()

    header_indices = [i for i, line in enumerate(lines) if is_header_line(line)]
    block_starts = [0] + header_indices
    block_bounds = [
        (start, block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines))
        for idx, start in enumerate(block_starts)
    ]

    questions = []
    for start, end in block_bounds:
        block_lines = lines[start:end]
        content_start = start
        if start in header_indices:
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
            })

    return questions
```

Note the `content_start` tracking: `block_lines` has its header line sliced off (`block_lines[1:]`) when the block starts with a real header, which shifts every subsequent line's position by one relative to `start`. `content_start` accounts for that shift so `absolute_index` always matches the line's true position in the original `lines` list — the same numbering `page_offsets` was built against.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: PASS (all existing tests + 3 new)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Stop parse_ocr_text gluing choice text across a page boundary"
```

---

### Task 2: Wire `page_offsets` into `run_pipeline`'s call to `parse_ocr_text`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Implement**

In `app.py`, `run_pipeline` currently has (around line 127-129):

```python
    page_offsets = build_page_offsets(kept_pages)
    raw_text = "\n\n".join(text for _, text in kept_pages)
    parsed_questions = parse_ocr_text(raw_text)
```

Replace the last line with:

```python
    page_offsets = build_page_offsets(kept_pages)
    raw_text = "\n\n".join(text for _, text in kept_pages)
    parsed_questions = parse_ocr_text(raw_text, page_offsets)
```

(`page_offsets` is already computed on the line directly above — this task only adds it as the second argument.)

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "Pass page_offsets into parse_ocr_text so cross-page blocks stop gluing"
```

---

### Task 3: Manual verification in the browser

**Files:** none (no code changes)

This is a manual check, run by Hila, not automated — per her stated preference (Streamlit UI checks are done by driving the browser herself) and per this plan's convention of not adding automated coverage for `run_pipeline` itself.

- [ ] Start the Streamlit server fresh (it must have been stopped since before Task 1): `streamlit run app.py`
- [ ] Upload the full sample exam and click Process
- [ ] Find "Flagged Question 3" (the merged 18/19/20 block spanning pages 13/14). Confirm its choices list now shows Q20's embedded header + question sentence (`שאלה 'on 20 (5 גק') מה מבצעת הפונקציה ?mask`) as its **own** entry in the list, separate from Q19's last choice — not glued onto the end of it as before
- [ ] Enter split points that place a boundary right before that new entry, click "Split question", and confirm the resulting part's choices list starts cleanly with that entry (still shown as plain text — no image is expected for it, per this plan's text-only scope) rather than as a fragment stuck onto the previous part's last choice
- [ ] Confirm "Flagged Question 1" (Part 2's empty-text-field fallback, from the earlier investigation) is unaffected — it's a same-page case, not a cross-page one, so this change shouldn't alter it
- [ ] Confirm the clean-questions screen still behaves exactly as before (regression check)
- [ ] Click "Generate Final File" and confirm it still downloads and opens correctly, including the now-separated Q20 header text appearing as its own line rather than buried in Q19's last choice
- [ ] Run `python -m pytest -q` one more time to confirm the full suite is green
- [ ] Stop the Streamlit server once the check is done (per Hila's preference — don't leave it running until the next test)

---

## Explicitly out of scope (matches the design doc)

- Cropping an image for parts whose content originates on a later page (the Phase 2 pixel-side gap) — still deferred.
- A single choice's text spanning three or more pages — not observed in the real exam; the per-line boundary check happens to handle it correctly anyway, but this plan doesn't add a test for it.
- Any change to how `question_lines` (pre-choice question prose) accumulates across a page break.
- Any change to `find_split_suggestions`'s strict `HEADER_PATTERN` matching, or to `strip_version_lines`.
