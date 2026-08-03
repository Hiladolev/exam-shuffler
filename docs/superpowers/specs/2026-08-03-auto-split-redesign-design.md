# Full-auto question-boundary detection (auto-split redesign)

## Problem

The app's core purpose is a student uploading an exam PDF and getting a shuffled version back without ever seeing raw questions or answers. The intended deployment is broad and public — many students using the app entirely solo, with no group or curator fixing problems on their behalf before they see the result. For those users there is no second safety net: whatever the app doesn't handle automatically, they hit directly.

Today, whenever OCR merges two or more real questions into one block, `parse_ocr_text` (`parser.py:92`) can't tell — it only splits on a strict header match (`is_header_line`, `parser.py:16`) — so the merged block gets a choice count outside the sane range and lands in the flagged/`needs_review` screen (`app.py:157`), where a person has to manually pick split points before the exam can be shared. That defeats the app's purpose for every merged block, and it's a routine occurrence, not a rare one: on the full 8-page sample exam, 3 of 16 questions currently need a manual split. For a solo user, hitting that screen means direct, unavoidable exposure to raw, unshuffled exam content with the correct answer still identifiable — so how rarely the manual path triggers is not a nice-to-have quality bar for this redesign, it's a hard requirement.

Investigated directly against two real, different exams (the data-science sample and `sample_exams/מבחן-כלכלה.pdf`): a header can survive OCR in a garbled form (digit lost, or "שאלה" itself entirely absent) with no reliable text-side signal *at that point in the document* — but the answer-choice lettering that follows still carries information (a new run starting at א) that today's parser ignores entirely.

## Design

### 1. Three boundary signals feed `parse_ocr_text` directly

`parse_ocr_text` stops relying on strict `is_header_line` alone as the only way to find a block boundary. Three independent signals each produce candidate split points, scanned across the whole document (not scoped to already-flagged blocks):

- **Strict header** — today's existing `HEADER_PATTERN`/`POINTS_PATTERN` match (`parser.py:5-6`).
- **Loose header** — tolerates OCR mangling: the digit lost, or the word "שאלה" itself missing, as long as enough of the surrounding shape survives to be a plausible header rather than ordinary question text. Validated against both sample exams with zero false positives when scanned full-document.
- **Choice-lettering reset** — a choice letter that is ≤ the highest letter already seen in the current run (this exam format is a fixed א→ה, 5-letter cap — there is no 6th letter, so ה immediately followed by another lettered choice is an unambiguous terminal case). Catches boundaries where *no* header signal survived at all: validated against 3 of 4 such "zero header signal" cases found across both sample exams. A forward gap (a skipped letter, e.g. ג missing) is a different, already-handled problem — a missing choice within one real question — and must not trigger this signal.

All three signal functions are written as standalone predicates (not inlined into `parse_ocr_text`) so section 4 below can call the identical implementations from the pixel side.

### 2. Split first, then a per-exam quality check per segment

Every candidate boundary from any signal is split immediately — this design never withholds a split because it "looks risky." There's no OCR-derived answer key to validate a guessed split against (`shuffle_questions`, `shuffler_core.py:39`, always assumes pre-shuffle `choices[0]` is correct, purely by convention), so a wrong blind heuristic split would silently corrupt that tracking with no way to catch it. Splitting on every detected boundary and then checking the *result* is safe in a way that guessing whether to split never can be.

After splitting, each resulting segment (not each original block) is checked against a **per-exam expected choice count**:

- Compute the mode among the choice counts of all parsed segments in this exam, excluding any segment with 0 choices (0 is never a legitimate count and must not influence the mode).
- If one count is a clear majority, that's this exam's expected count — every segment must match it exactly. (These exams are uniform: a 4-choice exam has 4 everywhere, a 5-choice exam has 5 everywhere; a segment landing on a *different* count than its own exam's norm is exactly as suspicious as one landing on 0 or on 8.)
- If there's no clear majority (a tie, or too few segments share the top count to trust it as "the exam's format"), fall back to today's broader tolerance — both 4 and 5 accepted — for this exam. An unreliable derived signal must fall back to the safe broad rule rather than picking a side.

A segment that fails this check is excluded from the final output with a visible summary note (e.g. "N questions couldn't be automatically separated and were omitted") — never silently dropped (dishonest about exam completeness), and never shown raw/garbled (would corrupt trust in the correct-answer tracking). This replaces today's blanket "0 or >5 ⇒ suspicious" rule (`app.py:158`, and the equivalent in `parser.py`'s `__main__` block) everywhere it's used: the top-level clean/`needs_review` split, and this new per-segment check.

Correctly-split sibling segments from the same original block are never penalized for a still-unresolved sibling — the check runs per segment, not per original block.

### 3. Manual split/flagged screen — role, not mechanics

No change to how the flagged screen works (`find_split_suggestions`, the N-way split UI, `attach_split_part_images`). What changes is its expected frequency and framing: with signals 1-3 catching the large majority of merges automatically, this screen must become a genuine edge-case safety net, not a routine path. In a curated-group workflow, one person hitting this screen to do a one-time manual fix before sharing is harmless — they already have the raw exam in hand either way. In the actual target deployment (broad, public, largely solo students), there is no such person: whoever hits this screen *is* the end user, with no one else to fix it for them first and no other safety net protecting them. For that user, this screen isn't an inconvenience, it's the one path where the app's entire promise — never seeing raw, unshuffled content — fails outright.

So the bar here is not "should be rare" as an aspiration: if real-world usage shows this screen triggering more than rarely, that is a correctness gap in the auto-detection to be treated as a bug and fixed, not an acceptable cost of this design or a case the manual fallback can be relied on to absorb.

The clean-question review/edit screen (editable question text, editable choices via "Add"/"Remove", correct-answer radio) is unaffected — explicitly out of scope for this redesign, same as before.

### 4. Pixel-side image cropping stays in lockstep

Today, `find_question_crop_bounds`, `find_header_line_indices`, `find_choice_line_bounds`, and `find_embedded_header_bounds` (`parser.py:36-75`) all call the same strict `is_header_line` that `parse_ocr_text` used to rely on exclusively. Once `parse_ocr_text` gains the loose-header and letter-reset signals, these pixel-side functions must gain the identical signals too — reusing the exact predicate functions from section 1, not hand-reimplemented copies — or the text side will detect more boundaries than the pixel side, and `attach_question_images`'s exact-count safety check (`app.py:94`) will start falling back to `question_image = None` more often, regressing image coverage for questions that work fine today.

This doesn't guarantee identical counts between the two sides — `image_to_string` (text) and `image_to_data` (pixel) are two independent Tesseract calls over the same page image (`test_ocr.py:21`, `test_ocr.py:77`) and can still transcribe the same header differently. Shared signal functions eliminate hand-maintained logic drift, not the two-OCR-pass divergence itself.

For whatever mismatch remains after the existing sparse-retry pass (`RETRY_LINE_EXTRACTION_CONFIG`, `app.py:76-89`), `attach_question_images` changes from an all-or-nothing rule to a **safe prefix**: pair bands to questions in top-down order; the moment the pairing could be wrong from some index onward (a band missing or extra), stop pairing there. Every question before that point keeps its correct image; everything from that point onward on the page falls back to `None`, exactly as today. This never risks attaching the wrong image to a question — it only narrows how much of the page pays for one localized mismatch.

## Explicitly out of scope

- Unifying the two OCR passes (`image_to_string` and `image_to_data`) into one — would remove the root cause of pixel/text divergence entirely, but is a much larger refactor than this redesign covers. Noted as a possible future direction, not undertaken here.
- Matching pixel-side bands to text-side questions by embedded question number instead of position — would recover more of a mismatched page than the safe-prefix rule, but adds real complexity for a case expected to be rare once signals are shared; revisit if the safe-prefix rule turns out to sacrifice more of a page than expected in practice.
- Removing or simplifying today's Phase 1/2 crop/split machinery (`split_choices`'s `image_bounds`/`choice_line_bounds`/`embedded_header_bounds` params, the flagged-card UI, `find_split_suggestions`) now that most merges auto-split correctly. Left alone for this redesign; may become a separate cleanup once real usage shows how much of it is now dead path.
- Any change to `MIN_CHOICES`'s use on the flagged-screen editor (`app.py:278-284`, disabling "Remove" below 4) — that stays a fixed floor of 4 regardless of a given exam's detected expected count; not raised as part of this redesign.
- A minimum-sample-size number or exact tie definition for the per-exam mode calculation — left as an implementation-time judgment call within "no clear majority ⇒ fall back to {4,5}", not pinned down as a specific threshold in this spec.

## Testing

- `parser.py`: unit tests for each of the three boundary signals independently (strict header, loose header, letter-reset), then `parse_ocr_text` end-to-end cases combining them — including a case with zero header signal at all (letter-reset only) and a case where a forward gap (skipped letter) must NOT trigger a false boundary.
- `parser.py`/`app.py`: unit tests for the per-exam expected-count derivation — clear majority, tie, and too-few-samples cases, each checked against both the per-segment exclusion path and the top-level clean/`needs_review` split.
- `parser.py`: pixel-side functions (`find_question_crop_bounds` etc.) tested against the same loose-header and letter-reset fixtures used for the text-side signal tests, confirming identical predicate behavior on identical input lines.
- `app.py`: `attach_question_images` safe-prefix behavior — a page with a gap in the middle of its bands keeps images before the gap and falls back to `None` from the gap onward, not for the whole page.
- Manual end-to-end run against both real sample exams (data-science exam and `מבחן-כלכלה.pdf`), confirming the previously-flagged merged blocks now split automatically and the flagged screen sees only genuine edge cases, if any.
