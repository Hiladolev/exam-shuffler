# Crop-based fallback for empty-stem letter-reset questions

## Problem

`parse_ocr_text` (`parser.py`) can create a question via a choice-letter-lettering reset (`find_letter_reset_indices`) when no header signal survived OCR at all. These questions carry `has_real_header=False`. Today, `attach_question_images` (`app.py`) unconditionally sets `question_image=None` for every such question except the one leading-block exception (`header_line_index == 0`), so the review UI falls back to showing raw `question["question"]` text.

For most letter-reset questions that's fine — some stem text usually survived. But sometimes the stem is completely empty: verified concretely on the data-science sample exam's Q3, where OCR transcribed nothing at all for the question's content, even though a stats table clearly occupies that space on the page (verified pixel gap: Q2's last real choice bottom at 1162px, Q3's first real choice top at 1808px — a 646px gap). In that case the review UI currently shows a blank question with no way for the reviewer to know what content they're being asked to judge.

This is distinct from issue #2 in the auto-split-redesign spec (`docs/superpowers/specs/2026-08-03-auto-split-redesign-design.md`), which is about corrupted text silently passing a valid choice count. This design is narrower: it only fires when the stem is *entirely* empty, and it doesn't try to recover or validate text — it surfaces the untranscribable page region as an image instead.

## Design

### 1. Pixel-side reset-boundary detection: `find_letter_reset_crop_bounds`

A new function in `parser.py`, structurally parallel to the existing `find_question_crop_bounds`, but driven by choice-letter-rank resets instead of header lines:

- Scan a page's pixel-side lines (the `(text, top, bottom)` tuples from `extract_line_boxes`) once, left to right in page order.
- Track `max_rank_seen` and the bottom of the most recent line matching `CHOICE_PATTERN` — mirroring `find_letter_reset_indices`'s tracking exactly: `max_rank_seen` resets to `-1` at a real/loose header line, but a non-choice line (a mangled header attempt, stray prose) is simply skipped (`continue`) and never disturbs either piece of tracked state.
- At each point where a `CHOICE_PATTERN` line's rank is `<=` the currently tracked `max_rank_seen` (a reset), emit a band `(last_choice_bottom, reset_line_top)` — gated by the existing `MIN_CROP_BAND_HEIGHT`, same degenerate-gap guard `find_question_crop_bounds` already uses. If the gap doesn't meet the minimum, emit `None` for that reset (nothing meaningful to show).
- Critically, `last_choice_bottom` tracking is *not* reset at a reset point itself — only at real header lines. This means chained resets (two headerless questions back to back) anchor correctly off each other automatically: by the time a second reset fires, the tracked `last_choice_bottom` is already that page's most recent choice line, whichever question it logically belongs to. No explicit "walk back through the chain" logic is needed.
- If a reset point has no preceding `CHOICE_PATTERN` line at all within the current page's line list — its true anchor would be on the previous page, and `extract_line_boxes` runs per page in `run_line_extraction_all_pages` with no cross-page state — emit `None`. Cross-page anchor carry-over is out of scope (see below).

This reproduces the verified Q2→Q3 band (1162→1808), correctly excluding the interspersed mangled-header-attempt and garbled-intro-sentence lines from anchoring (they get skipped as non-choice lines) while still including them *inside* the resulting cropped image, which is the point — that's exactly the content OCR couldn't transcribe as usable text.

### 2. Wiring into `attach_question_images`

Add a second pairing pass after the existing header-based block, covering exactly the questions `is_band_eligible` currently excludes (`has_real_header=False` and `header_line_index != 0` — genuine letter-resets, not leading blocks):

- Per page, collect these questions in text/page order, and `find_letter_reset_crop_bounds`'s bands (using the page's already-resolved `active_lines` — see "reuse" note below) in pixel order.
- Pair 1:1 top-down using the same safe-prefix rule the header pass already uses: stop pairing at the first count mismatch between the two lists; everything paired before that point gets its band, everything from that point on keeps `question_image=None`.
- Pair against **all** genuine letter-reset questions on the page, not just empty-stem ones — this keeps the positional correspondence structurally correct, since the reset boundary is a purely structural signal independent of whether the resulting stem happened to end up empty.
- Only actually attach `question_image` when `question["question"].strip() == ""`. A letter-reset question that recovered some real stem text keeps showing that text and never gets an image, even when its band paired successfully — showing an image would silently hide legitimately recovered text.

**Line-extraction reuse.** This pass reuses whichever `active_lines` the header-pairing block already settled on for that page (default pass, or the psm-12 retry if the header pass accepted it). There's no separate retry decision keyed on reset-count mismatches specifically. This is a deliberate simplification: re-running Tesseract per page multiple times is expensive, and it's not yet known whether the header-retry criterion also happens to fix reset mismatches in practice. Revisit if real usage shows this pass needs its own retry trigger.

## Explicitly out of scope

- **Cross-page anchor carry-over.** A reset point whose true anchor (last choice line before it) lives on the previous page falls back to no-image, per the confirmed decision. Threading "last choice line + its bottom pixel" as state across the per-page loop in `run_line_extraction_all_pages` would fix this, but the current one-image-per-band model doesn't support a band spanning two different page images, and this is expected to be a rare case. Revisit if it turns out to matter in practice.
- **A dedicated retry pass for reset-count mismatches**, separate from the existing header-retry trigger. See "Line-extraction reuse" above.
- **Any change to non-empty-stem letter-reset questions' handling.** They already show their recovered text today and continue to do so; this design only changes behavior for the completely-empty-stem case.
- **Issue #2 from the auto-split-redesign spec** (corrupted text landing on a valid choice count) — a distinct problem with no agreed fix yet, unrelated to this design's narrower empty-stem trigger.

## Testing

`test_parser.py`, unit tests for `find_letter_reset_crop_bounds`:
- Basic single reset with a clean gap (reproduces the verified Q2/Q3 numbers in shape, if not exact pixel values).
- Chained resets (two headerless questions back to back) — confirms continuous anchor tracking without explicit chain-walking.
- Non-choice lines interspersed between the anchor and the reset point — confirms they're skipped for anchoring purposes but implicitly included in the resulting band.
- No preceding `CHOICE_PATTERN` line within the page — confirms `None`.
- Gap under `MIN_CROP_BAND_HEIGHT` — confirms `None`.

`test_app.py`, for the new `attach_question_images` pass:
- An empty-stem letter-reset question with a correctly paired band gets `question_image` attached.
- A non-empty-stem letter-reset question with a correctly paired band does *not* get `question_image` attached (keeps showing its recovered text).
- A page with a count mismatch between empty-stem questions and detected reset bounds stops pairing at the right point (safe-prefix), leaving later questions on that page with `question_image=None`.
