# Manual Correct-Answer Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the clean-questions review screen override which choice is correct, defaulting to the existing `correct_index` so nothing changes unless actively picked — fixing cases where `shuffle_questions`'s "pre-shuffle choices[0] is correct" assumption silently tracked the wrong choice because OCR dragged the real correct answer into garbled question text.

**Architecture:** Replace the read-only `st.caption` showing `correct_index` in the clean-question loop with an `st.radio` offering every current choice (labeled with a live text preview), defaulting to `q['correct_index']`. Use the radio's live value — not the frozen `q['correct_index']` — when building `edited_clean`, so a manual override actually reaches `build_final_content`.

**Tech Stack:** Python, Streamlit — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-26-correct-answer-override-design.md`

**Note:** This plan's Task 1 also commits `app.py`'s "Add answer choice" button (`docs/superpowers/plans/2026-07-26-add-answer-choice-implementation.md`'s Task 1), which was implemented but left uncommitted when this correctness bug was found mid-verification. Both changes live in the same loop and should be verified together.

---

### Task 1: Add the correct-answer radio to the clean-question loop

**Files:**
- Modify: `app.py:112-121`

- [ ] **Step 1: Replace the read-only caption with an editable radio**

In `app.py`, change (currently lines 112-121):

```python
        if st.button("Add answer choice", key=f"clean_q_{i}_add_choice"):
            q["choices"].append("")
            st.rerun()
        st.caption(f"Correct answer index: {q['correct_index']}")
        edited_clean.append(
            {
                "question": question_text,
                "choices": choices,
                "correct_index": q["correct_index"],
            }
        )
```

to:

```python
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

- [ ] **Step 2: Syntax-check the file**

```bash
python -m py_compile app.py
```

Expected: no output, exit code 0.

- [ ] **Step 3: Manually verify in the running app**

Stop any Streamlit server left running from earlier testing first (check for a process on port 8501), then start fresh:

```bash
streamlit run app.py
```

Upload any exam PDF and click "Process". On the "Questions" section, for each clean question confirm:
- A "Correct answer" radio appears below the "Add answer choice" button, with one option per current choice, each labeled `"{index}: {choice text}"`.
- The pre-selected option matches that question's original correct answer (cross-check against the same question's choice text and index shown before this change, e.g. via `st.caption` in a previous run, or by re-running the pipeline and comparing `q['correct_index']`).
- Selecting a different option for one question doesn't change the pre-selected option on any other question.
- Click "Add answer choice" on a question that already has a non-default correct-answer selection: confirm the radio gains a new numbered option at the end and the existing selection is preserved (not reset to the new blank choice, not reset to the original default).
- Select the newly-added choice as correct for that question, type some text into it, then click "Generate Final File" and confirm the downloaded file's `Correct answer index` for that question matches the newly-added choice's position.
- For a question you didn't touch the radio on, confirm the downloaded file's `Correct answer index` still matches the original default.

Stop the server once done (`Ctrl+C` or kill the process on port 8501) — don't leave it running.

- [ ] **Step 4: Commit both this change and the earlier Add answer choice button**

```bash
git add app.py
git commit -m "Add manual correct-answer override to clean-questions review screen"
git push
```

---

## Self-Review Notes

- **Spec coverage:** The spec's single component (replacing the caption with a radio at `app.py:112-121`, defaulting to `q['correct_index']`, using the live value in `edited_clean`) is fully covered by Task 1. The spec's out-of-scope items (no change to the flagged/needs_review path, no change to `shuffle_questions`'s initial guess, no automated incompleteness detection) require no additional tasks since they describe things *not* to build.
- **Type consistency:** `st.radio`'s `format_func=lambda idx: f"{idx}: {choices[idx]}"` closes over `choices`, the same list built by the text-input loop directly above it in the same iteration of `for i, q in enumerate(...)` — called synchronously within that same `st.radio(...)` invocation before `choices` is rebound on the next loop iteration, so there's no late-binding closure bug. `correct_index` (the radio's return value) is used directly as the dict value for `edited_clean`'s `"correct_index"` key, matching the type (`int`) `q['correct_index']` already had.
