# Exam Shuffler

A Streamlit web app that takes a scanned multiple-choice exam PDF and produces a version with each question's answer choices shuffled — while keeping track of the correct answer for every question.

> **Status: actively in development.** The core pipeline works end-to-end on real exam PDFs, but OCR output still requires manual review before use, and some editing features are still being expanded.

## What it does

Given a PDF exam (currently tuned for Hebrew-language, right-to-left exams), the app:

1. **Extracts text via OCR** from every page of the PDF (skipping blank backs).
2. **Parses** the raw OCR text into structured questions and answer choices, filtering out footer noise like version numbers and page numbers.
3. **Flags anything it can't parse cleanly** (e.g. questions where OCR merged two exam questions into one block) into a "needs review" queue instead of silently producing wrong output.
4. Lets you **review and fix questions in the browser** — including questions with embedded diagrams/plots, which are cropped and shown as images alongside the OCR'd text.
5. **Shuffles the answer choices** for every question and tracks the new position of the correct answer.
6. **Exports the result** as a downloadable, RTL-formatted HTML file.

## Features

- **Multi-page OCR pipeline** (`pdf2image` + `pytesseract`, Hebrew + English) with a progress bar, processing every page of the uploaded PDF.
- **Automatic question/choice parsing**, including stripping of invisible bidi marks and OCR footer noise.
- **Error-tolerant parsing**: questions with 0 or too many detected choices are flagged for manual review rather than causing a crash or silent data loss.
- **Question image cropping**: for questions containing diagrams or charts that OCR can't transcribe, the app crops and displays the original image region instead of garbled text.
- **N-way question splitting**: a review-screen tool that detects and splits OCR blocks where multiple questions were merged together, with auto-suggested split points based on detected embedded headers.
- **In-browser question editing**: edit question text and choices, add or remove answer choices, and override which choice is marked correct — for both cleanly parsed and flagged questions.
- **Shuffling with answer tracking**: each question's choices are shuffled independently, with the correct answer's new index tracked automatically.
- **Downloadable final export** as a self-contained, RTL-styled HTML file.

## Tech stack

- **Python**
- **Streamlit** — web UI
- **pdf2image** (Poppler) — PDF-to-image conversion
- **pytesseract** (Tesseract OCR) — text extraction, Hebrew + English
- **pytest** — test suite, including Streamlit's `AppTest` for UI-level tests

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI and the end-to-end processing pipeline |
| `test_ocr.py` | OCR extraction and per-line/word bounding-box utilities |
| `parser.py` | Splits OCR text into questions/choices, flags problem blocks |
| `shuffler_core.py` | Choice shuffling, question splitting, and choice removal logic |

## Development process

This project is built using [Claude Code](https://claude.com/claude-code), an AI coding agent, following a spec-driven, test-first workflow: each feature starts as a design doc and implementation plan, is built with TDD (tests written before implementation code), and goes through code review before merging.

## Known limitations

- OCR output is not perfect — the app surfaces this to the user and expects manual review before an exam is used.
- Review/editing tools (add/remove choice, correct-answer override) are being rolled out across all screens; coverage is still being expanded.
