# Manual "Add answer choice" button for the clean-questions review screen

## Problem

Some questions in the source exam contain diagrams/plots that OCR garbles into text, gluing it onto the question text or a choice. This sometimes causes 1-2 real answer choices to be missing from the parsed `choices` list (e.g. a question that should have 4 choices ends up with only 2, with the other 2 choices' text buried inside the garbled question text). Since every question in these exams should have exactly 4 choices, a clean question with fewer than 4 is always a sign parsing went wrong — but the existing clean/needs_review split only flags 0 or >5 choices, so this case passes through as "clean" with no way to add the missing choice text back in.

## Design

On the clean-questions review screen (`app.py:96-116`), add an "Add answer choice" button per question, rendered directly below that question's existing choice edit boxes.

`q["choices"]` in the clean-question loop (`for i, q in enumerate(st.session_state["shuffled_questions"])`) is already a live reference into `st.session_state["shuffled_questions"][i]["choices"]`, since `q` is a dict inside that session-state list. Clicking the button appends an empty string to that list and calls `st.rerun()`:

```python
choices = []
for j, choice in enumerate(q["choices"]):
    choice_text = st.text_input(
        f"Choice {j}", value=choice, key=f"clean_q_{i}_choice_{j}"
    )
    choices.append(choice_text)
if st.button("Add answer choice", key=f"clean_q_{i}_add_choice"):
    q["choices"].append("")
    st.rerun()
st.caption(f"Correct answer index: {q['correct_index']}")
```

- The appended choice renders on the next run as a normal `st.text_input` with a fresh key (`clean_q_{i}_choice_{new_index}`), which doesn't exist in session state yet, so it starts empty and is independently editable like any other choice box.
- Appending at the end means `correct_index` never needs adjusting — nothing before it shifts.
- Per-question and independent: `i` scopes both the button's key and the mutation target (`q["choices"]`, i.e. `st.session_state["shuffled_questions"][i]["choices"]`), so clicking one question's button only affects that question.
- This mirrors the general pattern already used by the flagged-question split screen (`app.py:118-177`): a button handler mutates `st.session_state`, then `st.rerun()` re-executes the script so the new state renders with stable, index-derived widget keys. It's simpler here because the clean-question loop already renders directly off the list being mutated — no separate derived structure (like the split screen's `split_key`) is needed.

## Explicitly out of scope

- No change to the existing needs_review flagging logic (`len(q["choices"]) == 0 or len(q["choices"]) > 5`) — this button is a manual-editing aid on questions that already passed that check, not a way to change how flagging works.
- No cap on how many times the button can be clicked, and no re-validation against the "every question has exactly 4 choices" assumption — the button is a manual tool for the user to fix what they can see is wrong, not an enforced constraint.
- No "remove choice" counterpart — not requested; a mis-added empty choice can just be left blank or the user can retype over it, consistent with not adding unrequested features.

## Testing

- No automated test: this is a Streamlit UI interaction (button click → session-state mutation → rerun), consistent with the project's existing pattern of not unit-testing `app.py`'s UI code (the split-screen button/rerun logic it mirrors has no test coverage either).
- Manual verification: on the clean-questions screen, click "Add answer choice" for a question, confirm a new empty, editable choice box appears below the existing ones and above "Correct answer index"; type text into it; confirm other questions' choices are unaffected; confirm the typed text appears in the final downloaded file at the expected position.
