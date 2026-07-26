# Manual correct-answer override on the clean-questions review screen

## Problem

`shuffler_core.py`'s `shuffle_questions` hardcodes the assumption that whatever is at position 0 of a question's pre-shuffle `choices` list is the correct answer — there's no separate answer key anywhere in this codebase:

```python
def shuffle_questions(questions):
    result = []
    for q in questions:
        indices = list(range(len(q["choices"])))
        random.shuffle(indices)
        shuffled_choices = [q["choices"][i] for i in indices]
        correct_index = indices.index(0)
        ...
```

When OCR garbles a diagram/plot into the question text and drags 1-2 real answer choices along with it (see `docs/superpowers/specs/2026-07-26-add-answer-choice-design.md`), the choice that should have been at position 0 (the real correct answer) can be the one that's missing. The truncated list's new "position 0" — some other, wrong choice — then silently becomes the tracked "correct" answer through shuffling. This can happen even to questions that pass the existing clean/needs_review split (which only flags 0 or >5 choices), so a question can look clean and still carry a wrong `correct_index`.

## Investigation findings

Where `correct_index` lives in the review UI today (`app.py`):

- **Clean questions:** `correct_index` is set once at Process time (inside `run_pipeline` → `shuffle_questions`, before any manual editing happens) and is frozen from then on. The clean-question loop only displays it read-only (`st.caption(f"Correct answer index: {q['correct_index']}")`, currently `app.py:115`) and passes it straight through unchanged into `edited_clean` — there is currently no widget and no way to change it.
- **Flagged/needs_review questions work differently and are unaffected by this problem:** `split_choices` produces cards with no `correct_index` at all. Whatever the user types into the choice boxes at final-generation time gets run through `shuffle_questions` again inside `build_final_content`, which re-derives `correct_index` fresh from "whatever is at position 0 of the edited list" at that point — already correct by construction, since the user's final edit is what gets used.

So the gap is specific to clean questions: there's currently zero mechanism to override which choice is correct once `run_pipeline` has picked one.

## Design

Replace the read-only caption in the clean-question loop with an editable `st.radio`, defaulting to the existing `q['correct_index']` so nothing changes unless actively touched, and use the radio's live value (not the frozen `q['correct_index']`) when building `edited_clean`:

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

- `format_func` labels each radio option with a live preview of that choice's current text (e.g. `"1: London"`), read from `choices[idx]` — the same list just built by the text-input loop above it in the same iteration — so the user can judge correctness from the actual choice text, not a bare index.
- `index=q["correct_index"]` sets the default selection only on first render. Streamlit widgets with a stable `key` keep whatever the user picked on subsequent reruns and ignore the `index=` argument from then on — the same mechanism that already lets edited choice text survive reruns — satisfying "nothing changes unless I actively pick a different one."
- Works correctly together with "Add answer choice": appending a new empty choice grows `choices` and the radio's option range, but never shifts any existing index, so a previously-made selection (explicit or default) stays valid and pointed at the same choice after an append.
- `edited_clean` now uses the radio's live value instead of blindly forwarding the frozen `q['correct_index']` — this is the actual fix, since it's what lets a wrong auto-derived index be corrected.

## Explicitly out of scope

- No change to the flagged/needs_review path — `build_final_content`'s re-derivation of `correct_index` for reviewed cards already reflects the user's final edits correctly, since it shuffles from the edited choice list at generation time rather than trusting a frozen value.
- No change to `shuffle_questions` or how `correct_index` is initially derived at Process time — this spec adds a manual override on top, it doesn't change the automatic (still assumption-based) initial guess.
- No cross-question validation (e.g. warning if a question's choices look incomplete) — this is a manual correction tool for a problem the user has already visually identified, not an automated detector.

## Testing

- No automated test: this is a Streamlit UI interaction (radio selection persisting across reruns via session-state key), consistent with the project's existing pattern of not unit-testing `app.py`'s UI code.
- Manual verification: on the clean-questions screen, confirm each question shows a "Correct answer" radio pre-selected to match the question's original correct answer text; change the selection for one question and confirm the final downloaded file reflects the new `correct_index` for that question only; click "Add answer choice" on a question, confirm the correct-answer radio gains a new option without disturbing the current selection, and confirm selecting the newly-added choice as correct also flows through to the final file correctly.
