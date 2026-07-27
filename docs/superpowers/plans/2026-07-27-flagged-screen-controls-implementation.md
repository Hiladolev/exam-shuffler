# Flagged-screen choice controls and remove-choice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the flagged/split-question review screen up to parity with the clean-questions screen (add-choice, correct-answer override), add a remove-choice control to both screens, and fix the flagged-screen bug where a second shuffle at file-generation time discarded any correct-answer choice.

**Architecture:** A pure `remove_choice()` helper joins the existing `split_choices()`/`shuffle_questions()` in `shuffler_core.py`. Split cards get shuffled once, immediately after splitting (mirroring how clean questions are shuffled once up front), instead of being reshuffled a second time in `build_final_content`. The clean-screen's per-question editing widgets (question text, choices with add/remove, correct-answer radio) are extracted into one `render_question_editor()` function in `app.py`, reused by both screens.

**Tech Stack:** Python, Streamlit 1.60.0, pytest.

**Note on the spec's contingency:** The spec flagged a risk that `app.py` might not be importable in tests (it runs Streamlit UI code at module level) and that `build_final_content` might need to move to `shuffler_core.py` as a result. This was checked before writing this plan — `import app` and `from app import build_final_content` both work cleanly outside a running Streamlit server (only harmless "missing ScriptRunContext" warnings on stderr, no exception). **The contingency is not needed; `build_final_content` stays in `app.py`.**

---

### Task 1: `remove_choice()` in `shuffler_core.py`

**Files:**
- Modify: `shuffler_core.py` (add function after `split_choices`, before `shuffle_questions`)
- Test: `test_shuffler_core.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_shuffler_core.py`, updating the import line at the top from:
```python
from shuffler_core import split_choices
```
to:
```python
from shuffler_core import split_choices, remove_choice
```

Then add:
```python
def test_remove_choice_removes_item_at_index():
    result = remove_choice(["a", "b", "c", "d", "e"], 1)
    assert result == ["a", "c", "d", "e"]


def test_remove_choice_rejects_removal_at_min_choices():
    with pytest.raises(ValueError):
        remove_choice(["a", "b", "c", "d"], 0)


def test_remove_choice_allows_custom_min_choices():
    result = remove_choice(["a", "b", "c"], 0, min_choices=2)
    assert result == ["b", "c"]
    with pytest.raises(ValueError):
        remove_choice(["a", "b"], 0, min_choices=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: FAIL — `ImportError: cannot import name 'remove_choice' from 'shuffler_core'`

- [ ] **Step 3: Implement `remove_choice`**

In `shuffler_core.py`, add after `split_choices` (after line 19, before the blank lines preceding `def shuffle_questions`):
```python
def remove_choice(choices, index, min_choices=4):
    if len(choices) <= min_choices:
        raise ValueError(f"cannot remove choice: at least {min_choices} choices required")
    return choices[:index] + choices[index + 1:]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 5: Commit and push**

```bash
git add shuffler_core.py test_shuffler_core.py
git commit -m "Add remove_choice with a minimum-choices floor"
git push
```

---

### Task 2: Characterization test — split cards carry `correct_index` after shuffling

**Files:**
- Test: `test_shuffler_core.py`

This composes two existing functions (`split_choices`, `shuffle_questions`) with no new production code. It documents/locks in the behavior Task 3 will rely on: shuffling a freshly-split list of parts gives every part a `correct_index`.

- [ ] **Step 1: Write the test**

Update the import line in `test_shuffler_core.py` to:
```python
from shuffler_core import split_choices, remove_choice, shuffle_questions
```

Add:
```python
def test_shuffle_questions_after_split_assigns_correct_index_to_each_part():
    parts = split_choices("Q", ["a", "b", "c", "d", "e", "f"], [2, 4])
    shuffled_parts = shuffle_questions(parts)

    assert len(shuffled_parts) == 3
    for part in shuffled_parts:
        assert "correct_index" in part
        assert 0 <= part["correct_index"] < len(part["choices"])
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `python -m pytest test_shuffler_core.py -v`
Expected: PASS immediately — no production code changes needed for this step, since `shuffle_questions` already computes `correct_index` for any list of `{"question", "choices"}` dicts.

- [ ] **Step 3: Commit and push**

```bash
git add test_shuffler_core.py
git commit -m "Add characterization test for shuffling split question parts"
git push
```

---

### Task 3: Shuffle split cards immediately after splitting

**Files:**
- Modify: `app.py` (split-button handler, currently around lines 167-171)

**Files:**
- [ ] **Step 1: Update the split-button handler**

In `app.py`, find:
```python
                else:
                    st.session_state[split_key] = split_choices(
                        q["question"], q["choices"], split_points
                    )
                    st.rerun()
```
Replace with:
```python
                else:
                    st.session_state[split_key] = shuffle_questions(
                        split_choices(q["question"], q["choices"], split_points)
                    )
                    st.rerun()
```
`shuffle_questions` is already imported on line 6 (`from shuffler_core import shuffle_questions, split_choices`) — no import change needed.

- [ ] **Step 2: Verify nothing broke**

Run: `python -m pytest -q`
Expected: PASS (8 existing + 4 new tests from Tasks 1-2 = 12 passed)

Run: `python -c "import app; print('IMPORT_OK')"`
Expected: prints `IMPORT_OK` (only harmless Streamlit "missing ScriptRunContext" warnings on stderr)

- [ ] **Step 3: Commit and push**

```bash
git add app.py
git commit -m "Shuffle split question parts immediately after splitting"
git push
```

---

### Task 4: Stop double-shuffling review cards in `build_final_content`

**Files:**
- Modify: `app.py:42-65`
- Test: Create `test_app.py`

- [ ] **Step 1: Write the failing test**

Create `test_app.py`:
```python
from unittest.mock import patch

import app


def test_build_final_content_does_not_reshuffle_review_cards():
    edited_review_cards = [
        {"question": "Q1", "choices": ["x", "y", "z"], "correct_index": 2},
    ]

    with patch("app.shuffle_questions") as mock_shuffle:
        result = app.build_final_content([], edited_review_cards)

    mock_shuffle.assert_not_called()
    assert "Question: Q1" in result
    assert "  0: x" in result
    assert "  1: y" in result
    assert "  2: z" in result
    assert "Correct answer index: 2" in result
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest test_app.py -v`
Expected: FAIL — `build_final_content` still calls `shuffle_questions(edited_review_cards)` internally, so the mock gets called (and, since the mock returns a `MagicMock` instead of a real list, the subsequent `enumerate(...)` loop raises `TypeError`, which also fails the test).

- [ ] **Step 3: Implement the fix**

In `app.py`, replace lines 42-65:
```python
def build_final_content(edited_clean, edited_review_cards):
    lines = []
    for i, q in enumerate(edited_clean, start=1):
        lines.append(f"--- Question {i} ---")
        lines.append(f"Question: {q['question']}")
        lines.append("Choices:")
        for j, choice in enumerate(q["choices"]):
            lines.append(f"  {j}: {choice}")
        lines.append(f"Correct answer index: {q['correct_index']}")
        lines.append("")

    if edited_review_cards:
        shuffled_review_cards = shuffle_questions(edited_review_cards)
        lines.append("=== Reviewed (previously flagged) Questions ===")
        for i, q in enumerate(shuffled_review_cards, start=1):
            lines.append(f"--- Question {i} ---")
            lines.append(f"Question: {q['question']}")
            lines.append("Choices:")
            for j, choice in enumerate(q["choices"]):
                lines.append(f"  {j}: {choice}")
            lines.append(f"Correct answer index: {q['correct_index']}")
            lines.append("")

    return "\n".join(lines)
```
with:
```python
def _format_question_lines(questions):
    lines = []
    for i, q in enumerate(questions, start=1):
        lines.append(f"--- Question {i} ---")
        lines.append(f"Question: {q['question']}")
        lines.append("Choices:")
        for j, choice in enumerate(q["choices"]):
            lines.append(f"  {j}: {choice}")
        lines.append(f"Correct answer index: {q['correct_index']}")
        lines.append("")
    return lines


def build_final_content(edited_clean, edited_review_cards):
    lines = _format_question_lines(edited_clean)

    if edited_review_cards:
        lines.append("=== Reviewed (previously flagged) Questions ===")
        lines.extend(_format_question_lines(edited_review_cards))

    return "\n".join(lines)
```
`shuffle_questions` is still used elsewhere in `app.py` (in `run_pipeline` and the split handler from Task 3), so keep the import.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest test_app.py -v`
Expected: PASS

Run: `python -m pytest -q`
Expected: PASS (all tests)

- [ ] **Step 5: Commit and push**

```bash
git add app.py test_app.py
git commit -m "Stop reshuffling review cards at file-generation time"
git push
```

---

### Task 5: Shared `render_question_editor` helper, used on the clean-questions screen

**Files:**
- Modify: `app.py` (import line 6, new constant + function, clean-questions loop currently around lines 100-128)

No automated test for this task — it's Streamlit widget wiring (button click → session-state mutation → rerun), consistent with the project's existing pattern of not unit-testing `app.py`'s UI interactions (per the design doc's testing section). Verified manually in Task 7.

- [ ] **Step 1: Update the import line**

Change:
```python
from shuffler_core import shuffle_questions, split_choices
```
to:
```python
from shuffler_core import shuffle_questions, split_choices, remove_choice
```

- [ ] **Step 2: Add the `MIN_CHOICES` constant**

Change:
```python
UPLOAD_PATH = "uploaded_exam.pdf"
```
to:
```python
UPLOAD_PATH = "uploaded_exam.pdf"
MIN_CHOICES = 4
```

- [ ] **Step 3: Add `render_question_editor`**

Insert this new function after `build_final_content` (after its closing `return "\n".join(lines)` line and before `st.title("Exam Shuffler")`):
```python
def render_question_editor(state, key_prefix):
    question_text = st.text_area(
        "Question text", value=state["question"], key=f"{key_prefix}_question"
    )

    choices = []
    for j, choice in enumerate(state["choices"]):
        col1, col2 = st.columns([5, 1])
        with col1:
            choice_text = st.text_input(
                f"Choice {j}", value=choice, key=f"{key_prefix}_choice_{j}"
            )
        with col2:
            if st.button(
                "Remove",
                key=f"{key_prefix}_remove_{j}",
                disabled=len(state["choices"]) <= MIN_CHOICES,
            ):
                state["choices"] = remove_choice(state["choices"], j, MIN_CHOICES)
                st.rerun()
        choices.append(choice_text)

    if st.button("Add answer choice", key=f"{key_prefix}_add_choice"):
        state["choices"].append("")
        st.rerun()

    correct_index = st.radio(
        "Correct answer",
        options=range(len(choices)),
        format_func=lambda idx: f"{idx}: {choices[idx]}",
        index=state.get("correct_index", 0),
        key=f"{key_prefix}_correct_index",
    )

    return {"question": question_text, "choices": choices, "correct_index": correct_index}
```

- [ ] **Step 4: Use it in the clean-questions loop**

Replace:
```python
    edited_clean = []
    for i, q in enumerate(st.session_state["shuffled_questions"]):
        st.subheader(f"Question {i + 1}")
        question_text = st.text_area(
            "Question text", value=q["question"], key=f"clean_q_{i}"
        )
        choices = []
        for j, choice in enumerate(q["choices"]):
            choice_text = st.text_input(
                f"Choice {j}", value=choice, key=f"clean_q_{i}_choice_{j}"
            )
            choices.append(choice_text)
        if st.button("Add answer choice", key=f"clean_q_{i}_add_choice"):
            q["choices"].append("")
            st.rerun()
        correct_index = st.radio(
            "Correct answer",
            options=range(len(choices)),
            format_func=lambda idx: f"{idx}: {choices[idx]}",
            index=q["correct_index"],
            key=f"clean_q_{i}_correct_index",
        )
        edited_clean.append(
            {
                "question": question_text,
                "choices": choices,
                "correct_index": correct_index,
            }
        )
```
with:
```python
    edited_clean = []
    for i, q in enumerate(st.session_state["shuffled_questions"]):
        st.subheader(f"Question {i + 1}")
        edited_clean.append(render_question_editor(q, key_prefix=f"clean_q_{i}"))
```

- [ ] **Step 5: Verify nothing broke**

Run: `python -m pytest -q`
Expected: PASS (all tests — this task touches no tested code path)

Run: `python -c "import app; print('IMPORT_OK')"`
Expected: prints `IMPORT_OK`

- [ ] **Step 6: Commit and push**

```bash
git add app.py
git commit -m "Extract render_question_editor and add remove-choice to the clean-questions screen"
git push
```

---

### Task 6: Use `render_question_editor` on the post-split flagged screen

**Files:**
- Modify: `app.py` (post-split rendering branch, currently around lines 172-189)

No automated test for this task, same reasoning as Task 5. Verified manually in Task 7.

- [ ] **Step 1: Replace the post-split rendering loop**

Replace:
```python
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
with:
```python
        else:
            split_cards = st.session_state[split_key]
            for c, card in enumerate(split_cards):
                st.subheader(f"Flagged Question {i + 1} - Part {c + 1}")
                edited_review_cards.append(
                    render_question_editor(card, key_prefix=f"review_{i}_part{c}")
                )
```

- [ ] **Step 2: Verify nothing broke**

Run: `python -m pytest -q`
Expected: PASS (all tests)

Run: `python -c "import app; print('IMPORT_OK')"`
Expected: prints `IMPORT_OK`

- [ ] **Step 3: Commit and push**

```bash
git add app.py
git commit -m "Add answer-choice, remove-choice, and correct-answer controls to the flagged screen"
git push
```

---

### Task 7: Manual verification

**Files:** none (verification only)

Per project convention (`CLAUDE.md`), the Streamlit server must be fully stopped before editing an imported module and only restarted after — all edits are done as of Task 6, so this is the point to start it fresh.

- [ ] **Step 1: Start the server**

Run: `streamlit run app.py`

- [ ] **Step 2: Hand off for manual browser verification**

Ask the user to upload the sample exam PDF, click Process, and check:
- Clean-questions screen: "Add answer choice" still works; a "Remove" button appears next to each choice and is disabled once only 4 choices remain; the "Correct answer" radio still works.
- Flagged screen: after clicking "Split question" on a merged block, each resulting part now shows the same question text box, per-choice inputs with "Remove" buttons, "Add answer choice" button, and "Correct answer" radio as the clean screen.
- Click "Generate Final File" and confirm the downloaded file reflects: added/removed choices, and the chosen correct-answer index, correctly for both a clean question and a flagged/split question.

Do not use browser automation for this check — the user drives it themselves.

- [ ] **Step 3: Stop the server**

Once the user confirms the check is done, stop the `streamlit run app.py` process immediately (don't leave it running).

---

## Plan Self-Review

**Spec coverage:**
- §1 (shuffle split cards immediately, stop double-shuffling) → Tasks 3-4.
- §2 (shared `render_question_editor`) → Task 5.
- §3 (`remove_choice`, remove button on both screens) → Tasks 1, 5, 6.
- §4 (dedup `build_final_content`) → Task 4.
- §5 (contingency: move `build_final_content` if unimportable) → checked before writing this plan; not needed, noted at the top.
- Testing section → Tasks 1, 2, 4 (automated); Task 7 (manual, both screens).

**Placeholder scan:** none found — every step has literal code or an exact command with expected output.

**Type consistency:** `render_question_editor(state, key_prefix)` is defined once in Task 5 and used identically (same parameter names/order) in Task 5 (clean screen) and Task 6 (flagged screen). `remove_choice(choices, index, min_choices=4)` defined in Task 1 matches its call site in Task 5 (`remove_choice(state["choices"], j, MIN_CHOICES)`). `_format_question_lines(questions)` defined and used only within Task 4.
