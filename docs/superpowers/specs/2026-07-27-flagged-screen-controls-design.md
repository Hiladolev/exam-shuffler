# Add/remove-choice and correct-answer controls on the flagged screen; remove-choice on both screens

## Problem

The clean-questions review screen has an "Add answer choice" button and an editable "Correct answer" radio (added in a prior session), but the flagged/needs_review screen does not. The same missing-choice problem (OCR garbling a diagram into a choice, dropping real choice text) can happen there too, especially right after splitting a merged block — and there is currently no way to fix it, or to record which choice is actually correct for a flagged/split question at all.

There is also no way to remove a choice on either screen, so an extra empty choice added by mis-clicking "Add answer choice" can't be deleted.

Separately, the flagged screen has a shuffle-timing bug that this work needs to account for: split cards are shown in their original (unshuffled) parsed order, and `build_final_content` calls `shuffle_questions()` on them a second time at file-generation time, which re-derives `correct_index` from the "original index 0 is correct" convention and discards anything else. If a "correct answer" control is added to the flagged screen without addressing this, the user's choice would not reliably survive into the final file.

## Design

### 1. Shuffle split cards immediately after splitting, not at generation time

In the split-button handler (`app.py`, `review_split_button_{i}`), wrap the split result in `shuffle_questions()` before storing it:

```python
st.session_state[split_key] = shuffle_questions(split_choices(q["question"], q["choices"], split_points))
```

This mirrors how clean questions are shuffled once in `run_pipeline`, before the user ever sees them. Each part now carries a `correct_index` (per the existing "original index 0 was correct" convention — a known-approximate default the user is expected to check, same as clean questions today) instead of no `correct_index` at all.

`build_final_content` then writes `edited_review_cards` straight out, the same way it already writes `edited_clean`, instead of reshuffling them again. This removes the second `shuffle_questions()` call, fixing the bug where a user's correct-answer choice on the flagged screen would otherwise be discarded.

### 2. Shared question-editor helper

Extract the current clean-screen editing block into one function in `app.py`:

```python
MIN_CHOICES = 4

def render_question_editor(state, key_prefix):
    """Renders question text, per-choice inputs with remove buttons, an add-choice
    button, and a correct-answer radio. Mutates state["choices"] in place on
    add/remove (matching the existing session-state mutation + st.rerun() pattern)
    and returns the edited {question, choices, correct_index} dict."""
```

Used by both:
- the clean-questions loop (`for i, q in enumerate(st.session_state["shuffled_questions"])`)
- the post-split flagged-card loop (`for c, card in enumerate(split_cards)`)

`state` is a dict (an item of `st.session_state["shuffled_questions"]`, or a split-card dict inside `st.session_state[split_key]`) — in both cases a live reference, so in-place mutation on add/remove persists across reruns exactly like the existing clean-screen "Add answer choice" button does today.

The correct-answer radio defaults to `state.get("correct_index", 0)` (all callers will have `correct_index` set per §1, but the fallback keeps the function safe to reuse).

### 3. Remove-choice button and `remove_choice()`

New pure function in `shuffler_core.py`:

```python
def remove_choice(choices, index, min_choices=4):
    if len(choices) <= min_choices:
        raise ValueError(f"cannot remove choice: at least {min_choices} choices required")
    return choices[:index] + choices[index + 1:]
```

`MIN_CHOICES = 4` reflects that every question in these exams has 4 or 5 answer choices, so a question should never be edited down below 4.

In `render_question_editor`, each choice gets a "Remove" button next to its text input, disabled when `len(state["choices"]) <= MIN_CHOICES`. Clicking it calls `remove_choice(state["choices"], j, MIN_CHOICES)`, assigns the result back to `state["choices"]`, and reruns — same button→mutate→rerun pattern as "Add answer choice".

This appears on both screens automatically, since both use `render_question_editor`.

### 4. Dedup line-building in `build_final_content`

Both the clean-questions and reviewed-questions sections currently build the same per-question line block twice. Factor that into one small helper, `_format_question_lines(questions)`, used for both, now that both sections write their `correct_index` directly (§1) instead of one of them going through a second shuffle.

### 5. Contingency: `build_final_content` may move to `shuffler_core.py`

`app.py` runs Streamlit UI code at module level (`st.title(...)`, `st.file_uploader(...)`, etc.), which executes on `import app`. If that makes `build_final_content` impractical to unit-test directly (import errors or unwanted side effects under pytest), `build_final_content` (and its new line-building helper) will be moved into `shuffler_core.py` instead, so it can be tested without importing the Streamlit script. **This would be a structural change beyond what was originally scoped** and will be called out explicitly in the implementation summary if it happens — not folded in silently.

## Explicitly out of scope

- No change to the needs_review flagging logic (`len(q["choices"]) == 0 or len(q["choices"]) > 5`) or to the pre-split raw flagged-block view — controls are only added to the post-split per-part editor, per the existing scope-gap note ("e.g. right after a split").
- No re-validation enforcing exactly 4-5 choices on add; the 4-choice floor only gates removal.
- No change to `find_split_suggestions` or the split-point input UI.

## Testing

- `test_shuffler_core.py`:
  - `remove_choice` removes the choice at the given index and returns the shortened list.
  - `remove_choice` raises `ValueError` when `len(choices) <= min_choices`.
  - `shuffle_questions(split_choices(...))` — each resulting part carries a `correct_index` key.
- `test_app.py` (new, or `test_shuffler_core.py` if `build_final_content` moves per §5):
  - `build_final_content` writes a review card's `correct_index` and choice order through unchanged (proving the double-shuffle is gone).
- No automated test for the Streamlit widget wiring itself (button click → session-state mutation → rerun), consistent with the project's existing pattern for `app.py`'s UI code — verified manually instead: on both screens, add a choice, remove a choice (confirm the button disables at 4 remaining), change the correct-answer selection, and confirm the final downloaded file reflects all of it correctly for both clean and flagged/split questions.
