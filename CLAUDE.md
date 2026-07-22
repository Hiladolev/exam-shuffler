# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

The core pipeline works end-to-end on a full 8-page exam (all pages with question content, out of 16 total including blank backs): 20 real questions in, 13 parsed clean and 3 flagged into needs_review.
- `test_ocr.py` — OCR extraction from an exam PDF (pdf2image + pytesseract), looping all pages and skipping ones with under ~10 characters of text (blank backs).
- `parser.py` — splits OCR text into questions/choices, strips version/page-number footer lines and invisible bidi marks, flags questions with 0 or >5 choices into needs_review instead of crashing.
- `shuffler_core.py` — shuffles a question's choices and tracks the new correct-answer index.
- `app.py` — Streamlit UI: upload a PDF, review/edit clean and flagged questions, download the final shuffled exam.

Open task for next session: the review-screen split tool (`app.py`) only supports splitting a flagged block into 2 questions. On the full exam, the block flagged around question 18 actually contains **3** merged questions (18, 19, and 20) — their headers were OCR-mangled (e.g. "מס'" and "נק'" misread) so `parser.py` never detected the boundaries between them. Need to extend the split UI to handle an arbitrary number of splits, not just one split point into 2 parts.

## Project Goal

A Python web app (Streamlit) that takes a multiple-choice exam PDF as input and outputs a version with shuffled answer choices.

## Development Workflow

When the Streamlit server (`app.py`) is already running and you need to edit a module it imports (`parser.py`, `shuffler_core.py`, etc.), saving the file to disk is not enough — the running server keeps using the old version of that module already loaded in memory (Python caches imports in `sys.modules`; Streamlit's autorerun re-executes `app.py`'s top level but does not reload already-imported modules).

Always fully stop the running Streamlit server before editing an imported module, and only start it fresh again after the edits are saved.
