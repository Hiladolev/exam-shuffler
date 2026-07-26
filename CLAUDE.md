# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

The core pipeline works end-to-end on a full 8-page exam (all pages with question content, out of 16 total including blank backs): 20 real questions in, 13 parsed clean and 3 flagged into needs_review.
- `test_ocr.py` — OCR extraction from an exam PDF (pdf2image + pytesseract), looping all pages and skipping ones with under ~10 characters of text (blank backs).
- `parser.py` — splits OCR text into questions/choices, strips version/page-number footer lines and invisible bidi marks, flags questions with 0 or >5 choices into needs_review instead of crashing.
- `shuffler_core.py` — shuffles a question's choices and tracks the new correct-answer index.
- `app.py` — Streamlit UI: upload a PDF, review/edit clean and flagged questions, download the final shuffled exam.

The review-screen split tool (`app.py`) previously only supported splitting a flagged block into 2 questions. On the full exam, the block flagged around question 18 actually contains **3** merged questions (18, 19, and 20) — their headers were OCR-mangled (e.g. "מס'" and "נק'" misread) so `parser.py` never detected the boundaries between them.

This has been generalized to support an arbitrary number of splits: `parser.py` now has `find_split_suggestions` (auto-detects likely split points from embedded headers) and `shuffler_core.py` now has `split_choices` (cuts a block into N parts). Design: `docs/superpowers/specs/2026-07-23-generic-split-design.md`. Plan: `docs/superpowers/plans/2026-07-23-generic-split-implementation.md`. Tasks 1-4 (pytest setup, `find_split_suggestions`, `split_choices`, and the N-way split UI in `app.py`) are done and tested; merged into `master` via PR #1 (branch `generic-split`, now deleted).

`app.py` no longer hardcodes a single page: `run_pipeline` now uses `test_ocr.py`'s `run_ocr_all_pages` generator to OCR every page except page 1, filtering blank pages via the existing `MIN_PAGE_TEXT_LENGTH` check and showing a `st.progress` bar (with a "Processing page X of Y" status line) as it goes. Design: `docs/superpowers/specs/2026-07-26-multipage-ocr-design.md`. Plan: `docs/superpowers/plans/2026-07-26-multipage-ocr-implementation.md`.

This unblocked Task 5 of the generic-split plan: running the full 8-page exam through the app end-to-end now works, with the 18/19/20 block still splitting correctly into 3 parts. Observed counts on this run: 13 parsed clean, 3 flagged into needs_review — matching the prior single-page baseline, so removing the `=== PAGE N ===` markers (see the multi-page OCR design doc) didn't change the split in this exam's case.

The clean-questions review screen now has an "Add answer choice" button per question (appends an empty, editable choice — fixes cases where OCR dragged a real choice into garbled question text alongside a diagram/plot) and an editable "Correct answer" radio defaulting to the question's original `correct_index` (fixes `shuffle_questions`'s pre-shuffle-`choices[0]`-is-correct assumption silently tracking the wrong choice when the real correct one went missing). Design: `docs/superpowers/specs/2026-07-26-add-answer-choice-design.md` and `docs/superpowers/specs/2026-07-26-correct-answer-override-design.md`. Plans: `docs/superpowers/plans/2026-07-26-add-answer-choice-implementation.md` and `docs/superpowers/plans/2026-07-26-correct-answer-override-implementation.md`. Both done, tested, and committed on branch `add-answer-choice`.

Follow-up tasks noted during that testing, not yet designed or fixed:
- **New OCR noise pattern not filtered:** "מספר גרסה" (version number) text is glued into answer choices in at least two questions of the full sample exam. `parser.py`'s `strip_version_lines`/`VERSION_PATTERN` already handles this text when it's OCR'd as its own clean line, but here it's ending up merged onto a choice's text instead — same family of issue as the `=== PAGE N ===` marker-corruption risk described in the multi-page OCR design doc, but a distinct root cause (not yet investigated).
- **Scope gap — flagged/needs_review screen:** the new "Add answer choice" button and "Correct answer" radio only exist on the clean-questions screen. The same missing-choice problem can happen on the flagged/needs_review screen too (e.g. right after a split), but there's currently no way to fix it there.
- **No "remove answer choice" option:** there's currently no way to delete a choice added by mistake (e.g. an extra empty one from clicking "Add answer choice" too many times) — only adding is supported.

Known bug (not yet fixed, noted for a future session): on the review screen, editing a `text_area` (question text) and then immediately clicking "Generate Final File" without first clicking/tabbing away from the field causes the edit to not register in the final output. Streamlit only commits a `text_area`'s value to session state on blur, so the in-progress edit is lost. Affects both the clean-question and flagged-question edit loops in `app.py`.

## Project Goal

A Python web app (Streamlit) that takes a multiple-choice exam PDF as input and outputs a version with shuffled answer choices.

## Development Workflow

When the Streamlit server (`app.py`) is already running and you need to edit a module it imports (`parser.py`, `shuffler_core.py`, etc.), saving the file to disk is not enough — the running server keeps using the old version of that module already loaded in memory (Python caches imports in `sys.modules`; Streamlit's autorerun re-executes `app.py`'s top level but does not reload already-imported modules).

Always fully stop the running Streamlit server before editing an imported module, and only start it fresh again after the edits are saved.
