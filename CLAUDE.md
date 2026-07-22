# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

The core pipeline is implemented:
- `test_ocr.py` — OCR extraction from an exam PDF (pdf2image + pytesseract).
- `parser.py` — splits OCR text into questions/choices, strips version and page-number footer lines.
- `shuffler_core.py` — shuffles a question's choices and tracks the new correct-answer index.
- `app.py` — Streamlit UI: upload a PDF, review/edit clean and flagged questions, download the final shuffled exam.

## Project Goal

A Python web app (Streamlit) that takes a multiple-choice exam PDF as input and outputs a version with shuffled answer choices.

## Development Workflow

When the Streamlit server (`app.py`) is already running and you need to edit a module it imports (`parser.py`, `shuffler_core.py`, etc.), saving the file to disk is not enough — the running server keeps using the old version of that module already loaded in memory (Python caches imports in `sys.modules`; Streamlit's autorerun re-executes `app.py`'s top level but does not reload already-imported modules).

Always fully stop the running Streamlit server before editing an imported module, and only start it fresh again after the edits are saved.
