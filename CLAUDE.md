# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

The core pipeline works end-to-end on a full 8-page exam (all pages with question content, out of 16 total including blank backs): 20 real questions in, 13 parsed clean and 3 flagged into needs_review.
- `test_ocr.py` — OCR extraction from an exam PDF (pdf2image + pytesseract), looping all pages and skipping ones with under ~10 characters of text (blank backs).
- `parser.py` — splits OCR text into questions/choices, strips version/page-number footer lines and invisible bidi marks, flags questions with 0 or >5 choices into needs_review instead of crashing.
- `shuffler_core.py` — shuffles a question's choices and tracks the new correct-answer index.
- `app.py` — Streamlit UI: upload a PDF, review/edit clean and flagged questions, download the final shuffled exam.

The review-screen split tool (`app.py`) previously only supported splitting a flagged block into 2 questions. On the full exam, the block flagged around question 18 actually contains **3** merged questions (18, 19, and 20) — their headers were OCR-mangled (e.g. "מס'" and "נק'" misread) so `parser.py` never detected the boundaries between them.

This has been generalized to support an arbitrary number of splits: `parser.py` now has `find_split_suggestions` (auto-detects likely split points from embedded headers) and `shuffler_core.py` now has `split_choices` (cuts a block into N parts). Design: `docs/superpowers/specs/2026-07-23-generic-split-design.md`. Plan: `docs/superpowers/plans/2026-07-23-generic-split-implementation.md`. Tasks 1-4 (pytest setup, `find_split_suggestions`, `split_choices`, and the N-way split UI in `app.py`) are done, tested, and committed on branch `generic-split`.

Task 5 of that plan (manual end-to-end verification against the full 8-page exam, confirming the 18/19/20 block splits correctly) is **blocked**: `app.py` hardcodes `PAGE_NUMBER = 3` and only OCRs that single page (`run_pipeline` → `run_ocr(pdf_path, page_number)`), unlike `test_ocr.py`'s `__main__` which loops all pages. The app as it stands can't reproduce the full multi-page exam scenario. Fixing this (looping all pages in `app.py`'s pipeline, like `test_ocr.py` already does) is out of scope for the split-feature plan and needs its own design/plan session before Task 5 can be attempted.

Known bug (not yet fixed, noted for a future session): on the review screen, editing a `text_area` (question text) and then immediately clicking "Generate Final File" without first clicking/tabbing away from the field causes the edit to not register in the final output. Streamlit only commits a `text_area`'s value to session state on blur, so the in-progress edit is lost. Affects both the clean-question and flagged-question edit loops in `app.py`.

## Project Goal

A Python web app (Streamlit) that takes a multiple-choice exam PDF as input and outputs a version with shuffled answer choices.

## Development Workflow

When the Streamlit server (`app.py`) is already running and you need to edit a module it imports (`parser.py`, `shuffler_core.py`, etc.), saving the file to disk is not enough — the running server keeps using the old version of that module already loaded in memory (Python caches imports in `sys.modules`; Streamlit's autorerun re-executes `app.py`'s top level but does not reload already-imported modules).

Always fully stop the running Streamlit server before editing an imported module, and only start it fresh again after the edits are saved.
