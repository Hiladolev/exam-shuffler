# Crop question body as an image instead of OCR'ing it (Phase 1: clean questions)

## Problem

OCR turns tables, console screenshots, and diagrams embedded in a question's body into garbled, unreadable text. For example, on the sample exam's page 13, question 15 has a black console-screenshot table between its header and its choices; page 5 has a `describe()` dataframe table and a decision-tree diagram in the same position for two other questions. None of that renders usably as OCR'd text.

Answer choices must stay as OCR'd editable text, since they need to remain shufflable. But everything between a question's header line and its first choice line — "the question body," whether it's plain prose, a table, or a diagram — can instead be cropped directly from the source PDF page image and kept as a picture.

## Design

### 1. Per-page line + bounding-box extraction

The current pipeline (`test_ocr.py`'s `run_ocr_all_pages`) OCRs each page with `pytesseract.image_to_string`, which returns plain text with no positional information, then concatenates all pages into one string before `parser.py` splits it into questions by regex. That text pipeline stays exactly as it is today — untouched.

Separately, for each page, also call `pytesseract.image_to_data(image, lang="heb+eng", output_type=Output.DICT)`, which returns per-word rows including `block_num`/`par_num`/`line_num`/`left`/`top`/`width`/`height`. Group words sharing the same `(block_num, par_num, line_num)` into a line; a line's bounding box is the min/max of its words' pixel extents, and its text is the words joined in reading order. This produces, per page, a list of `(text, top_px, bottom_px)` tuples.

This is an additional OCR pass per page (slower, but the pipeline already shows a progress bar for multi-page OCR, so the extra time is acceptable). It was chosen over replacing `image_to_string` outright specifically so the existing, stable, well-tested text-parsing pipeline (`parse_ocr_text` and everything downstream of it) is not touched at all — eliminating the risk of subtly changing already-working parsing behavior.

### 2. `find_question_crop_bounds` — a new pure function in `parser.py`

Given one page's list of `(text, top_px, bottom_px)` lines, walk them applying the same `HEADER_PATTERN` and `CHOICE_PATTERN` regexes already used by `parse_ocr_text`. For each header line found, look for the next choice-pattern line after it (still on this page). If found, emit a crop band: `(top_px, bottom_px)` from just below the header line to just above that first choice line. If no matching choice line is found before the page's lines run out, emit nothing for that header — there is no special "cross-page" case to handle here (verified empirically against the sample exam: no genuinely-detected header/first-choice pair ever lands on different pages; the only two blocks where a page boundary appeared between a header and a choice were already broken for unrelated reasons — one had no header match at all, the other had zero choices found, both already excluded from "clean" by existing criteria). A header with no following choice on the same page just naturally produces no crop band, through the same code path as any other case where both endpoints aren't found — no special-casing required.

Skip bands under ~10px tall (no real content between header and choices).

**Alignment to parsed questions:** correlate crop bands to `parse_ocr_text`'s output by counting headers per page, not by matching text. Page 1 (in OCR order) contributes crop bands for its first N headers, page 2 the next M, and so on, matching the order `parse_ocr_text` already processes headers in (since `raw_text` is built by concatenating pages in order). If a page's header count doesn't line up with what's expected, or a given question has no crop band at all, that question's `question_image` is simply `None` — never guess or misattribute a crop to the wrong question.

### 3. Cropping

A thin function crops the full page width (not detecting column edges — the source layout is single-column with consistent margins, confirmed by inspecting sample pages) between a band's `top_px`/`bottom_px` (with a few pixels of padding to avoid clipping ascenders/descenders), returning PNG bytes. PNG (not JPEG) to keep table/diagram text legible — no lossy compression on content that's often small monospaced text or dense diagram lines.

### 4. Data model

Parsed question dicts gain an optional `question_image` field (PNG bytes, `None` when no crop band was found). The original OCR'd `question` text field stays on the dict regardless — still needed internally, and as the fallback display/export content when there's no image.

`shuffle_questions` in `shuffler_core.py` needs a one-line update: it currently rebuilds each question dict with only `question`, `choices`, `correct_index`, and must also carry `question_image` through unchanged.

### 5. UI (clean-questions screen only)

In `render_question_editor` (`app.py`): if `state.get("question_image")` is set, show it read-only via `st.image(...)` instead of the editable `st.text_area` for question text. If not set, keep today's editable text area exactly as-is — this is the graceful fallback path for whichever questions didn't get a clean crop. Choices, Add/Remove, and the correct-answer radio are unaffected either way.

The flagged/needs-review and post-split screens are unchanged in this phase — they keep showing plain OCR'd text exactly as they do today.

### 6. Output format: HTML

The final downloadable file changes from plain `.txt` to `.html`, since images can't live in a text file. New `build_final_html(edited_clean, edited_review_cards)` alongside (not replacing) the existing `build_final_content`, wired to the download button (`mime="text/html"`, filename `final_exam.html`).

- Clean questions with a `question_image`: embed as `<img src="data:image/png;base64,...">`.
- Clean questions without one (fallback case): render the question text as a paragraph, same content as today's `.txt` output.
- Choices render as a list; the correct-answer index is still shown per question, matching the existing convention that this file is an instructor-facing answer key (shuffled order + which choice is correct), not a blank student exam.
- Flagged/review cards: render as plain text, same as today.
- Reuse the app's existing RTL styling convention for consistency.

No image resizing or compression in V1 — only worth adding later if generated file size becomes a real problem.

## Explicitly out of scope (this phase)

- Flagged/needs_review and post-split question bodies staying as images — see Phase 2 below. This is a committed next step, not optional, just sequenced after Phase 1 ships and is verified.
- Any UI for manually adjusting/redrawing a crop's boundaries if auto-detection is off. A bad crop just means that question falls back to the existing text path (or gets manually noticed and reported) — no in-app correction tool in V1.
- Detecting content-column edges for cropping (multi-column layouts). The sample layout is single-column full-width.
- Image resizing/compression.

## Phase 2 (committed follow-up, not speculative)

Extend cropping to the flagged/needs_review and post-split screens. This is harder than Phase 1: those blocks exist precisely because header detection already failed once for them, and after a manual split (via the existing "Enter split points as comma-separated choice indices" UI), the boundaries are indices into the flat choices list, not regex-matched header/choice lines. Mapping those indices back to pixel positions will need the same per-page line/bbox infrastructure built in Phase 1, applied against the manual split points instead of regex matches. This needs its own follow-up design pass once Phase 1 ships and is verified manually in the browser — but it is a committed continuation of this work, not a maybe.

## Testing

- `find_question_crop_bounds`: pure function, unit-testable with fake `(text, top, bottom)` line lists — no real OCR or images needed. Cases: normal single question, header with no following choice on the page (fallback), multiple questions on one page, a page with zero headers.
- `build_final_html`: pure like `build_final_content` today — testable by passing fake image bytes and asserting both the base64 `<img>` tag path and the text-fallback path render correctly, plus that choices and correct-answer index still appear.
- The actual pixel-cropping step (PIL `.crop()`) is a thin wrapper — a smoke test is enough, no need for extensive coverage.
- No new `AppTest` coverage planned for the image display itself (a read-only `st.image`, not interactive widget logic) — verified manually in the browser, consistent with how the rest of the UI in this app is checked.
