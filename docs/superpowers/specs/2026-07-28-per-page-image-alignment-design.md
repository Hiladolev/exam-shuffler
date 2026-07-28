# Per-page alignment for question-body image cropping

## Problem

Phase 1 of question-body image cropping (`docs/superpowers/specs/2026-07-28-question-image-crop-design.md`) attaches a cropped `question_image` to each parsed question by comparing two counts for the *whole document at once*: the number of crop bands found across all pages, and the number of questions `parse_ocr_text` produced. If the counts match, it zips them together in order; if not, every question in the document falls back to `question_image = None`.

This has a real gap. The two counts come from two independent OCR passes (`image_to_string` for text, `image_to_data` for line/bbox extraction) that can disagree on different pages in opposite directions — one page under-detects a header, another over-detects one. If the errors happen to cancel out, the whole-document counts still match, the zip proceeds, and every question from the first divergence onward gets paired with the wrong image — silently. That's exactly the failure mode the mechanism exists to prevent ("never guess or misattribute a crop to the wrong question").

It's also more conservative than it needs to be in the failure case: today, a single bad page zeroes out every question's image in the entire exam, even ones on pages that aligned perfectly.

This document describes narrowing the alignment check from whole-document to per-page, so a mismatch on one page only affects that page's questions, and a genuine misattribution can no longer hide behind unrelated errors canceling out elsewhere in the document.

## Why not simpler fixes

**Reintroduce page markers into the OCR text stream.** Already tried and rejected for a different reason, in `docs/superpowers/specs/2026-07-26-multipage-ocr-design.md`: a marker line that survives `strip_version_lines` and lands right after a choice line gets silently appended onto that choice's text by `parse_ocr_text`'s block loop, corrupting it without changing the choice count — so it would never trip the existing `needs_review` safety check. Any scheme that inserts a marker into the text stream inherits this exact risk, so this isn't a live option.

**Parse each page independently, then stitch continuing questions back together.** `parse_ocr_text` currently concatenates every page into a single text blob before splitting into questions, specifically so a question whose choices trail onto the next page is handled correctly, for free, by simple concatenation (per the multi-page OCR design doc). Parsing per page and reconciling cross-page continuation afterward would mean re-deriving that behavior as a separate, more error-prone post-process. Bigger change, no real benefit over the approach below.

## Design

### 1. `parser.py` stays page-agnostic, but reports where each question came from

`parse_ocr_text` gains one new field on each returned question dict: `header_line_index` — the index, within the `lines = text.splitlines()` list it already computes internally, where that question's header line was found (or `0` for the rare leading block kept before any header). This is a page-agnostic, purely textual fact; `parser.py` still has no concept of "pages." It's additive — nothing today asserts an exact key set on these dicts, and `shuffle_questions` already builds a fresh dict with only the keys it cares about, so this key is naturally dropped once it's no longer needed.

### 2. `strip_version_lines` moves from "once on the joined blob" to "once per page"

Today, `run_pipeline` joins all kept pages' texts with `"\n\n"` and *then* calls `strip_version_lines` once on the result. To know exactly which page a given line index falls on, the line-numbering space `parse_ocr_text` consumes needs to correspond exactly to page boundaries — but `strip_version_lines` drops matched lines entirely (not just blanks them), so line indices shift depending on whether stripping happens before or after joining.

The fix: apply `strip_version_lines` to each page's text individually, before joining. This is behavior-preserving — the function is purely line-local (no cross-line state, no lookahead) — but it means `run_pipeline` can now compute each page's exact post-stripping line count *before* the join happens, and use that to build precise page boundaries in the same line-numbering space `parse_ocr_text` will use.

### 3. `page_offsets` and `page_number_for_line_index`

While collecting kept pages, `run_pipeline` builds `page_offsets`: a list of `(page_number, start_line_index)` pairs, where `start_line_index` is the cumulative line count of all previously-kept pages, plus one extra line per page boundary already crossed (accounting for the blank separator line `"\n\n".join` inserts between consecutive pages' line blocks).

A new pure function in `app.py`, `page_number_for_line_index(page_offsets, line_index)`, does the reverse mapping: given a global line index, returns which real PDF page number it falls on (the page whose `start_line_index` is the largest one `<= line_index`).

Worked example: three kept pages with post-stripping line counts 5, 3, and 4, with page numbers 2, 4, 5 (page 3 was blank and skipped). `"\n\n".join` inserts exactly one blank line between each pair of kept pages' line blocks, so:
- Page 2 starts at line index `0`.
- Page 4 starts at line index `0 + 5 + 1 = 6` (5 lines of page 2, plus 1 separator line).
- Page 5 starts at line index `6 + 3 + 1 = 10` (3 lines of page 4, plus 1 separator line).

So `page_offsets = [(2, 0), (4, 6), (5, 10)]`. A question with `header_line_index = 7` maps to page 4 (the largest start index `<= 7` is `6`, belonging to page 4).

No parsed question's header can ever land exactly on one of the inserted blank separator lines (blank lines never match `is_header_line`), so this ambiguity never actually arises in practice — the function just needs to behave sensibly for it, not be exercised by real data.

### 4. `page_bands` carries real page numbers

`run_line_extraction_all_pages` already yields the real PDF page number per page; `run_pipeline`'s crop loop currently discards it (`for _, image, lines in ...`). It now keeps it, so `page_bands` becomes a list of `(page_number, image, band)` instead of the current flat `(image, band)`.

### 5. `attach_question_images` becomes per-page

Instead of one global count comparison, `attach_question_images(parsed_questions, page_offsets, page_bands)`:

1. Buckets `parsed_questions` by real page number, via `page_number_for_line_index(page_offsets, q["header_line_index"])` for each question.
2. Buckets `page_bands` by their own (already-known) page number.
3. For each page number appearing in either bucket, compares that page's question count to that page's band count. If they match, zips them in order (same crop-or-`None`-per-band logic as before) and attaches `question_image` to that page's questions. If they don't match, every question on that page falls back to `question_image = None`. A page with bands but no corresponding questions (e.g. the two OCR passes disagreeing about whether a page is blank) simply has its bands go unused — nothing to attach them to.

A mismatch on any one page no longer affects any other page's questions.

## Explicitly out of scope

- Reconciling *why* the two OCR passes might disagree about a page's blank-ness or header count — this design only bounds the blast radius of such a disagreement to the one affected page, per the original Phase 1 design's "never guess" principle. Investigating the disagreement itself is a separate concern.
- Any change to `find_question_crop_bounds` — it already operates strictly per-page and is unaffected by this design.
- Any change to how a question's *choices* can span a page boundary — that existing, deliberate behavior (unchanged since the multi-page OCR design) is preserved; this design only concerns which page a question's *header* is attributed to for image-alignment purposes.

## Testing

- `parser.py`: new tests for `header_line_index` (single question, multiple questions on different lines, the rare kept leading pre-header block defaulting to `0`). `parse_ocr_text` has no existing test coverage, so these are net-new, scoped only to the new field.
- `parser.py`: a regression test proving `strip_version_lines` applied per-page-then-joined produces identical output to the old joined-then-stripped order, for input containing a version-marker line — the load-bearing equivalence claim this whole design leans on.
- `app.py`: unit tests for `page_number_for_line_index` (normal case, exact page boundary, last page).
- `app.py`: `attach_question_images` tests are rewritten (not kept alongside the old flat-count version, since the mechanism itself is being corrected) to cover the actual point of this fix: two pages where one page's counts match and another's don't, proving the matched page keeps its image and only the mismatched page's questions fall back to `None`.
- No new test for `run_pipeline` itself — still requires a real PDF + tesseract binary, consistent with this codebase's existing convention for that function.
