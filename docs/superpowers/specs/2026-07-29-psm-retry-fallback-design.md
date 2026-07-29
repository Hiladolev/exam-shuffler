# Second-pass `--psm` retry for mismatched pages

## Problem

Investigated via `docs/superpowers/specs/2026-07-28-per-page-image-alignment-design.md`'s mechanism: on the sample exam, Question 1's header (`"שאלה מס' 1 (5 נק')"`) is visibly clean and non-overlapping in the source PDF, but Tesseract's default full-page layout segmentation (`--psm 3`, pytesseract's default) drops that line entirely from *both* OCR passes (`image_to_string` and `image_to_data`) on that page. Verified directly against the real uploaded PDF, not a cached dump.

Consequence, traced through the existing per-page mechanism: `parse_ocr_text` has no header to split on, so Question 1's real body/choices become a "leading block" (`header_line_index = 0`). `find_question_crop_bounds` produces no band for the missing header. That page now has one more parsed question than crop bands, so `attach_question_images`'s exact-count safety check (correctly) falls back to `question_image = None` for every question on that page.

Cropping just that header's row and re-running Tesseract on it in isolation recovers the text, proving it's a segmentation issue, not an image-quality one. Sweeping `--psm` mode 1/3/4/6/11/12 across the whole page found `--psm 12` (sparse text with OSD) is the only one that recovers the header — but it *also* fragments the k-means table on the same page into broken pieces, and further splinters Question 3's already-mangled header on the same page into three one-word line fragments. So `--psm 12` is not a strict improvement over the default; it trades one failure for others, and switching the whole pipeline to it is rejected.

## Design

A targeted, bounded second-pass retry, gated so it can only help a page and can never make a working page worse:

1. `extract_line_boxes(image, config="")` (`test_ocr.py`) gains a `config` parameter, forwarded to `pytesseract.image_to_data`. Default `config=""` is behavior-preserving.
2. `run_pipeline` (`app.py`) additionally records `page_images: dict[page_number, image]` for every page kept by the line-extraction pass (the same filter that currently populates `page_bands`), and passes it to `attach_question_images`.
3. `attach_question_images` gains an optional `page_images` parameter (default `None`, treated as `{}`). For each page where `len(bands) != len(page_questions)` (the existing mismatch trigger) *and* that page's image is available:
   - Re-run line extraction on that one page's image with `RETRY_LINE_EXTRACTION_CONFIG = "--psm 12"`.
   - Recompute bands via the existing `find_question_crop_bounds`.
   - **Accept the retry's bands only if `len(retried_bands) >= len(bands)`** (never regresses the header count found by the default pass). If accepted, the retried bands wholesale replace the default ones for that page (no mixing of coordinates from two different OCR runs).
4. The existing exact-count check (`len(bands) == len(page_questions)`) still gates whether images actually get attached — using either the default or the retried bands, whichever is in play. If the retry doesn't get the counts to line up, the page still falls back to `None`, exactly as today. **Nothing about this design ever bypasses the "never guess" safety net** — it just gives the count-matching check one more, better-informed data point to work with before giving up.

## Why this is low-risk

- **Strictly opt-in.** The retry only runs on pages that are *already* mismatched (i.e. already producing `question_image = None` today). A page that already matches by default never triggers a retry, so this change is a no-op for every currently-working question — including all of this exam's other 12 clean questions. There is no code path where this change makes a previously-working page worse.
- **No change to text parsing.** `parse_ocr_text` and the `header_line_index` mechanism are untouched. The fix only ever touches which crop bands get computed for a page, never which questions get parsed or how they're split.
- **Same coincidental-match risk as the rest of the design, not a new one.** Like the existing per-page count-matching check itself, it's theoretically possible for a retry to produce a *wrong* band that happens to make the counts line up. This is the same accepted risk already inherent to "compare counts, then zip" everywhere in this codebase (see the per-page design's own rationale for narrowing blast radius rather than eliminating this risk outright) — not a new category introduced here.
- **Narrow scope.** This recovers cases where a page's *first* kept-page header is missing (because the resulting "leading block" happens to preserve correct document order against the corrected band list). It does **not** recover a header miss occurring mid-document — that manifests as two real questions merging into one parsed dict, a different failure mode this design does not address. Worth calling out explicitly rather than overclaiming.

## Explicitly out of scope

- Retrying the *text* OCR pass (`image_to_string`) — not needed for this failure mode, since the "leading block" already preserves correct ordering; and doing so would require re-deriving `parse_ocr_text`'s block-splitting per page, which the per-page design doc already rejected as unnecessary complexity for a different reason.
- Trying additional `--psm` modes beyond 12, or making the retry config configurable — YAGNI until a real case shows `--psm 12` isn't sufficient.
- Any change to `find_question_crop_bounds` itself — it stays page-agnostic and psm-agnostic; it just receives whichever lines it's given.

## Testing

- `test_ocr.py`: `extract_line_boxes` forwards `config` to `pytesseract.image_to_data` (mocked at the `pytesseract` boundary, no real OCR).
- `test_app.py`: new `attach_question_images` cases — retry recovers a mismatched page and attaches images; retry that finds *fewer* headers than the default is rejected; a mismatched page with no recorded image never attempts a retry. Existing `attach_question_images` tests are unchanged (new parameter is optional and defaults to a no-retry no-op).
- No new test for `run_pipeline` itself, consistent with this codebase's existing convention for that function (needs a real PDF + tesseract binary).
