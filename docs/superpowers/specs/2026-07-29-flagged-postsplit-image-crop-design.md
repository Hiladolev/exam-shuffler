# Extend question-body image cropping to flagged/needs_review and post-split screens (Phase 2)

## Problem

Phase 1 (`docs/superpowers/specs/2026-07-28-question-image-crop-design.md`) crops a question's body as an image on the clean-questions screen only. The flagged/needs_review screen and the post-split cards it produces still show plain OCR'd text always, even though `run_pipeline` explicitly clears `question_image` to `None` for these questions today — discarding a crop band that, for the pre-split case, was already computed.

Two distinct sub-cases need covering:

1. **The pre-split flagged card** (a merged block, e.g. "Flagged Question 18" containing sub-questions 18/19/20 squashed together because the boundaries between them failed detection).
2. **Post-split cards** (parts 2, 3, ... produced by `split_choices` after Hila enters split points and clicks "Split question"). Part 1 always keeps whatever body content preceded the first split point; parts 2+ have no body text of their own today (`split_choices` sets `"question": ""` for every part after the first), because that content — the sub-question's own embedded header and prose — got silently absorbed into the tail of the previous part's last choice by `parse_ocr_text`'s continuation-joining logic.

## Investigation: why the obvious fix (reuse `HEADER_PATTERN`) doesn't work

The natural first idea for locating a post-split part's start is to scan for a line matching the same `HEADER_PATTERN`/`is_header_line` check Phase 1 already uses. This was checked against the real sample exam (page 13, live OCR run, not a cached artifact) and rejected:

- Q18's own header line OCRs cleanly: `שאלה מס' 18 (5 נק')` — matches `HEADER_PATTERN` fine.
- Q19's embedded header, one physical OCR line later, in its own clean bounding box (top 1952–1993, well separated from the choice above and the prose below): `שאלה 'on' 19 (5 בק')`. `"מס'"` OCR'd as `"'on'"`, `"נק'"` as `"בק'"` — `HEADER_PATTERN` will never match this line. This is not a line-joining artifact (the physical line is clean and isolated); it's a genuine character-level OCR misread on this specific token.

Grepping the same document's raw OCR text (pages 2+ only — page 1 is never processed by the real pipeline) for the one token that survives every header instance found, `שאלה`, shows it present in **every** header line, mangled or not (2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20), and **nowhere else**. This also revealed that questions 13 and 14 have the same `'on'` mangling as 19/20 — the bug is systemic, not unique to the 18/19/20 block.

So detection for this phase is anchored on `שאלה` plus a digit on the same line, not on `HEADER_PATTERN`.

## Design

### 1. Pre-split image: reuse Phase 1's existing band

`find_question_crop_bounds` already computes a header→first-choice band for a merged (>5-choice) flagged question's real header, exactly as it does for clean questions — that header was never the problem; only the *boundaries between* the merged sub-questions were. `run_pipeline` currently discards this by forcing `question_image = None` for anything routed to `needs_review`. That forcing is removed for the >5-choice case (0-choice questions have no choice line to bound a crop against, so they're naturally unaffected and stay text-only).

### 2. Loose embedded-header detection

A new check, independent of `HEADER_PATTERN`: a line counts as a **candidate embedded header** if it contains the substring `שאלה` and at least one digit, and it is a *continuation* line — i.e. it appears after at least one real choice has already started in the block, and it does not itself match `CHOICE_PATTERN`. Scoped this way (continuation lines only, on a page already known to contain the block's own header), the false-positive risk is effectively zero in the real document (verified above) and low in general, since ordinary answer-choice prose rarely combines this exact token with a digit.

### 3. Two new pure functions in `parser.py`

Mirroring `find_question_crop_bounds`'s existing per-page, line-walking style:

- **Choice line bounds**: given a page's lines and the index of a block's header line, walk forward collecting `(top, bottom)` for every `CHOICE_PATTERN` match, stopping at the next real header (`is_header_line`) or the end of the lines. This list is parallel to the block's flattened `choices` array, in order — the same "align by count" discipline Phase 1 uses elsewhere in this codebase.
- **Embedded header bounds**: same walk, but tracking how many choices have started so far, and recording `{choice_count: (top, bottom)}` whenever a candidate embedded header line (per #2) is seen. `choice_count` at that point is exactly the split-point index that boundary corresponds to, in the same number space `split_choices` already uses for `split_points`.

### 4. Single-page-only restriction

If a flagged block's choices continue onto a second page (the existing multi-page-choices behavior, unchanged since the multipage-OCR design), none of this phase's new positional data is computed for it — it stays fully text-only, matching Phase 1's own same-page-only restriction on crop bands. No new "which page" ambiguity is introduced.

### 5. Wiring: carrying positional data on the flagged question dict

For each merged (>5-choice), single-page flagged question, `run_pipeline` attaches (in addition to the now-unsuppressed `question_image`):
- the choice-line bounds list,
- the embedded-header bounds dict,
- a reference to that page's source image (needed later to actually crop, since cropping doesn't happen until a real split point is chosen).

0-choice flagged questions and cross-page blocks get none of this — same `question_image = None`, same plain-text rendering as today.

### 6. `split_choices` grows to attach per-part images

`split_choices` (`shuffler_core.py`) gains optional parameters carrying the page image and the two positional structures from #3. For each resulting part:
- **Part 0** keeps the block's own `question_image` unchanged (the free win from #1) — no new logic needed, it already has everything it needs.
- **Parts 1+**: only get a cropped `question_image` if the exact split point used for that part has *both* a matching embedded-header-bounds entry *and* a matching choice-line-bounds entry for the part's first choice. If either is missing (custom split point that doesn't line up, or the multi-line-fragmented-header edge case), that part's `question_image` is `None` and it falls back to today's plain-text behavior (an empty, editable question field) — never a guess, consistent with every other fallback in this codebase's crop mechanism.

### 7. UI changes (`app.py`)

- **Pre-split flagged card**: currently rendered as a plain `st.write(q["question"])` loop (not through `render_question_editor`, since it's a read-only display plus split controls, not an edit form). Add the same "image if present, else text" branch `render_question_editor` already uses for clean questions. The choices list — where the split-relevant embedded header text actually lives — keeps rendering as plain text below the image either way, so nothing needed for deciding split points gets hidden.
- **Post-split cards**: already routed through `render_question_editor`, which already knows how to display `question_image` when present (built in Phase 1) — no rendering change needed here, only needs the dict to actually carry the field, which #6 provides.
- **Split button handler**: passes the flagged question's stored page image and positional data through to `split_choices`.

## Explicitly out of scope

- **Fixing `find_split_suggestions`'s strict `HEADER_PATTERN` matching.** Noted as a real, related bug (it likely never fires for 13/14/18/19/20 in this exam, since it checks the same pattern that's proven not to survive this OCR mangling) — but it's a separate concern from image cropping, and Hila wants it scoped as a future improvement: reuse this phase's looser "שאלה + digit" detection there too, but keep it suggestion-only (never auto-split without confirmation), matching how `find_split_suggestions` already works today. Not part of this phase.
- 0-choice flagged questions ever getting an image — there's no choice line to bound a crop against, so no signal exists for them regardless of detection looseness.
- Cross-page merged blocks.
- Handling an embedded header whose text is fragmented across more than one physical OCR line — falls back to no image for that part, same as any other undetected case.
- Detecting more than one embedded header between the same pair of real choices (i.e., three or more sub-questions merged with only one split boundary apart) — out of scope; the existing multi-way split UI already handles this from the user's side by accepting multiple split points, this phase's detection just needs to find each one independently, which the per-line walk already does naturally.
- Any change to `find_question_crop_bounds` itself, or to how clean questions are cropped.

## Testing

- `parser.py`: unit tests for the two new functions using fake `(text, top, bottom)` line lists in the same style as the existing `find_question_crop_bounds` tests — cases: normal multi-choice block with one embedded header, a block with no embedded header (pure fallback), an embedded header candidate that lacks a digit (correctly ignored), a `CHOICE_PATTERN` line correctly not mistaken for an embedded header.
- `shuffler_core.py`: unit tests for `split_choices`'s new per-part image attachment — a split point with a full match gets a cropped image; a split point with no matching bounds falls back to `None`; part 0 always keeps the pre-existing `question_image` unchanged; existing `split_choices` tests (no image data passed at all) keep passing unchanged, since the new parameters are optional.
- No new test for `run_pipeline`'s wiring itself, consistent with this codebase's existing convention for that function (needs a real PDF + tesseract binary) — verified manually in the browser, per Hila's stated preference for driving Streamlit UI checks herself.
