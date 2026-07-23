# Generic N-way Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the review screen split a flagged block into any number of parts (N ≥ 2), with split points auto-suggested from OCR-detected headers and freely editable by hand.

**Architecture:** `parser.py` gains a pure function that scans a block's `choices` list for embedded header matches and returns suggested split indices. `shuffler_core.py` gains a pure function that cuts a `{question, choices}` block into N parts at a given sorted list of indices. `app.py`'s review screen wires these together: it pre-fills a comma-separated text input with the suggestions and generalizes today's single-split button into an N-way split.

**Tech Stack:** Python, Streamlit, pytest (newly added — the project currently has zero test infrastructure).

---

## File Structure

- Create: `test_parser.py` — pytest tests for `find_split_suggestions`
- Create: `test_shuffler_core.py` — pytest tests for `split_choices`
- Modify: `parser.py` — add `find_split_suggestions(choices)`
- Modify: `shuffler_core.py` — add `split_choices(question, choices, split_points)`
- Modify: `app.py` — replace the single-split-point UI (lines 107-153) with the N-way version

---

### Task 1: Install pytest

**Files:** none (environment only)

- [ ] **Step 1: Install pytest**

Run: `pip install pytest`

- [ ] **Step 2: Verify pytest runs in this project**

Run: `python -m pytest --version`
Expected: prints a pytest version number, no error.

No commit for this task (no tracked files changed unless your `pip freeze` workflow requires updating a requirements file — this project has none today, so skip that).

---

### Task 2: `find_split_suggestions` in `parser.py`

**Files:**
- Modify: `parser.py`
- Test: `test_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `test_parser.py`:

```python
from parser import find_split_suggestions


def test_no_header_matches_returns_empty_list():
    choices = ["Paris", "London", "Berlin"]
    assert find_split_suggestions(choices) == []


def test_one_header_match_suggests_next_index():
    choices = ["Paris", "שאלה מס' 5 (2 נק') London", "Berlin"]
    assert find_split_suggestions(choices) == [2]


def test_two_header_matches_suggest_both_next_indices():
    choices = [
        "Paris",
        "שאלה מס' 5 (2 נק') London",
        "Berlin",
        "שאלה מס' 6 (3 נק') Madrid",
        "Rome",
    ]
    assert find_split_suggestions(choices) == [2, 4]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_parser.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_split_suggestions' from 'parser'`

- [ ] **Step 3: Implement `find_split_suggestions`**

In `parser.py`, add this function right after `is_header_line` (around line 15):

```python
def find_split_suggestions(choices):
    suggestions = set()
    for j, choice in enumerate(choices):
        if HEADER_PATTERN.search(choice):
            suggestions.add(j + 1)
    return sorted(suggestions)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_parser.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add parser.py test_parser.py
git commit -m "Add find_split_suggestions to detect embedded question headers in choices"
```

---

### Task 3: `split_choices` in `shuffler_core.py`

**Files:**
- Modify: `shuffler_core.py`
- Test: `test_shuffler_core.py`

- [ ] **Step 1: Write the failing tests**

Create `test_shuffler_core.py`:

```python
import pytest

from shuffler_core import split_choices


def test_split_choices_n2_matches_two_way_split():
    parts = split_choices("Q", ["a", "b", "c", "d"], [2])
    assert parts == [
        {"question": "Q", "choices": ["a", "b"]},
        {"question": "", "choices": ["c", "d"]},
    ]


def test_split_choices_n3():
    parts = split_choices("Q", ["a", "b", "c", "d", "e", "f"], [2, 4])
    assert parts == [
        {"question": "Q", "choices": ["a", "b"]},
        {"question": "", "choices": ["c", "d"]},
        {"question": "", "choices": ["e", "f"]},
    ]


def test_split_choices_boundary_points():
    parts = split_choices("Q", ["a", "b", "c", "d"], [1, 3])
    assert parts == [
        {"question": "Q", "choices": ["a"]},
        {"question": "", "choices": ["b", "c"]},
        {"question": "", "choices": ["d"]},
    ]


def test_split_choices_rejects_out_of_order_points():
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [3, 1])


def test_split_choices_rejects_out_of_range_points():
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [0])
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [4])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: FAIL with `ImportError: cannot import name 'split_choices' from 'shuffler_core'`

- [ ] **Step 3: Implement `split_choices`**

In `shuffler_core.py`, add this function after the `import random` line and before `shuffle_questions`:

```python
def split_choices(question, choices, split_points):
    n = len(choices)
    if any(not (0 < p < n) for p in split_points):
        raise ValueError(f"split points must be between 1 and {n - 1}")
    if list(split_points) != sorted(set(split_points)):
        raise ValueError("split points must be sorted, unique, and strictly increasing")

    boundaries = [0] + list(split_points) + [n]
    parts = []
    for idx in range(len(boundaries) - 1):
        start, end = boundaries[idx], boundaries[idx + 1]
        parts.append({
            "question": question if idx == 0 else "",
            "choices": choices[start:end],
        })
    return parts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add shuffler_core.py test_shuffler_core.py
git commit -m "Add split_choices to cut a flagged block into N parts at given indices"
```

---

### Task 4: Wire N-way split into the `app.py` review screen

**Files:**
- Modify: `app.py:1-5` (imports)
- Modify: `app.py:107-153` (review screen block)

- [ ] **Step 1: Update imports**

In `app.py`, change:

```python
from parser import strip_version_lines, parse_ocr_text
from shuffler_core import shuffle_questions
```

to:

```python
from parser import strip_version_lines, parse_ocr_text, find_split_suggestions
from shuffler_core import shuffle_questions, split_choices
```

- [ ] **Step 2: Replace the review screen block**

Replace `app.py:107-153` (the entire `st.header("Needs Review (flagged / merged questions)")` block through the end of the `for i, q in enumerate(...)` loop) with:

```python
    st.header("Needs Review (flagged / merged questions)")
    edited_review_cards = []
    for i, q in enumerate(st.session_state["needs_review"]):
        split_key = f"review_split_result_{i}"

        if split_key not in st.session_state:
            st.subheader(f"Flagged Question {i + 1}")
            st.write(q["question"])
            for k, choice in enumerate(q["choices"]):
                st.write(f"{k}: {choice}")

            suggestions = find_split_suggestions(q["choices"])
            suggested_value = ", ".join(str(s) for s in suggestions)
            if suggestions:
                st.caption(
                    f"Detected {len(suggestions) + 1} parts "
                    f"(suggested split points: {suggested_value})"
                )

            split_input = st.text_input(
                "Enter split points as comma-separated choice indices (e.g. 4, 9)",
                value=suggested_value,
                key=f"review_split_input_{i}",
            )
            if st.button("Split question", key=f"review_split_button_{i}"):
                tokens = [t.strip() for t in split_input.split(",") if t.strip()]
                try:
                    split_points = sorted(set(int(t) for t in tokens))
                except ValueError:
                    split_points = None

                if split_points is None:
                    st.error("Enter whole numbers separated by commas (e.g. 4, 9).")
                elif not split_points:
                    st.error("Enter at least one split point.")
                elif any(not (0 < p < len(q["choices"])) for p in split_points):
                    st.error(f"Split points must be between 1 and {len(q['choices']) - 1}.")
                else:
                    st.session_state[split_key] = split_choices(
                        q["question"], q["choices"], split_points
                    )
                    st.rerun()
        else:
            split_cards = st.session_state[split_key]
            for c, card in enumerate(split_cards):
                st.subheader(f"Flagged Question {i + 1} - Part {c + 1}")
                question_text = st.text_area(
                    "Question text",
                    value=card["question"],
                    key=f"review_{i}_part{c}_question",
                )
                choices = []
                for j, choice in enumerate(card["choices"]):
                    choice_text = st.text_input(
                        f"Choice {j}",
                        value=choice,
                        key=f"review_{i}_part{c}_choice_{j}",
                    )
                    choices.append(choice_text)
                edited_review_cards.append({"question": question_text, "choices": choices})
```

- [ ] **Step 3: Stop any running Streamlit server before testing**

Per this project's `CLAUDE.md`: if `app.py` (or a module it imports) is already running via `streamlit run app.py`, stop it now — Streamlit does not reload already-imported modules like `parser.py` and `shuffler_core.py` on their own.

- [ ] **Step 4: Start the app and smoke-test with a small case**

Run: `streamlit run app.py`

Upload any exam PDF that produces at least one flagged (needs-review) block, click "Process", and confirm in the browser:
- The split text input appears pre-filled when a header match is auto-detected inside the block's choices (or empty if none is detected).
- Typing a single index (e.g. `4`) and clicking "Split question" still produces a 2-part split, matching today's behavior.
- Typing two comma-separated indices (e.g. `4, 9`) produces a 3-part split, each part editable.
- Leaving the input empty and clicking "Split question" shows the "Enter at least one split point." error.
- Entering a non-numeric token (e.g. `4, x`) shows the "Enter whole numbers separated by commas" error.
- Entering an out-of-range index (e.g. `999`) shows the "Split points must be between 1 and N" error.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "Generalize review-screen split UI to N-way splits with auto-suggested points"
```

---

### Task 5: Manual end-to-end verification with the full 8-page exam

**Files:** none (manual verification only)

- [ ] **Step 1: Run the full pipeline against the real exam**

With the Streamlit server running (`streamlit run app.py`), upload the full 8-page exam PDF used in prior sessions (see `CLAUDE.md` — the one with the merged question 18/19/20 block) and click "Process".

- [ ] **Step 2: Check the flagged block's suggestions**

Find the flagged block that used to contain questions 18, 19, and 20. Confirm the split input shows 2 auto-suggested split points, or fewer if OCR mangling defeated header detection for one of the boundaries — this is expected per the design doc; the manual-add path covers that gap.

- [ ] **Step 3: Split into 3 parts and complete the exam end-to-end**

Adjust the split points if needed (add/remove indices in the text input) so the block splits into exactly 3 parts corresponding to questions 18, 19, and 20. Click "Split question", clean up each part's question text and choices in the edit boxes (trailing glued-on header fragments from OCR are expected and require manual trimming — this is explicitly out of scope per the design doc), then click "Generate Final File" and confirm the download contains all 3 questions with correct, shuffled choices.

No commit for this task (verification only, no code changes).

---

## Self-Review Notes

- **Spec coverage:** `find_split_suggestions` (Task 2), `split_choices` (Task 3), and the `app.py` UI changes — pre-filled suggestions, freely editable comma-separated input, generalized error handling (non-integer, out-of-range, dedup, empty-input) — are all covered (Task 4). Manual end-to-end test from the spec's Testing section is Task 5. No changes to `parse_ocr_text` or `is_header_line` are made, matching the spec's explicit out-of-scope list.
- **Type consistency:** `split_choices(question, choices, split_points)` signature matches its use in `app.py` (`split_choices(q["question"], q["choices"], split_points)`) and in all `test_shuffler_core.py` calls. `find_split_suggestions(choices)` signature matches its use in `app.py` (`find_split_suggestions(q["choices"])`) and in `test_parser.py`.
