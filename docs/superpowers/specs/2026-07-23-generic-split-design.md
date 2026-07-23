# Generic N-way split for flagged review blocks

## Problem

The review screen's split tool (`app.py:107-153`) only splits a flagged block into exactly 2 parts, at one choice index the user types in. On the full 8-page exam, one flagged block actually contains 3 merged questions (18, 19, 20) — their OCR-mangled headers ("מס'" and "נק'" misread) never registered as block boundaries in `parser.py`, so they all landed in a single flagged block. The split tool needs to support splitting into N parts (N ≥ 2), with the split points suggested automatically and editable by hand.

## Data model constraint

A flagged block is `{"question": <one string>, "choices": <flat list of strings>}`. `parser.py`'s line-by-line parsing (`parser.py:52-64`) already discards original line breaks: any line that isn't a recognized choice line gets appended onto `choices[-1]` while `in_choices` is `True`.

This means when a question header dodges `is_header_line` at the top-level block-detection pass but is still readable within a block, its text ends up glued onto the **end of the previous choice**, not the start of the next one. A detected header match inside `choices[j]` implies the new part actually starts at `choices[j+1]`; `choices[j]` keeps a trailing text fragment that needs manual trimming in the existing edit box (expected — this project already assumes messy OCR needs manual cleanup, not a new failure mode).

Split points are therefore indices into the existing `choices` list, matching today's single `split_at` semantics generalized to a sorted list.

## Components

1. **`parser.py` — `find_split_suggestions(choices)`**
   Reuses the existing `HEADER_PATTERN` (already matches "שאלה מס' N") to scan each string in `choices`. For every match found in `choices[j]`, suggests split index `j + 1`. Returns a sorted list of suggested indices (may be empty). No changes to `parse_ocr_text` or `is_header_line`.

2. **`shuffler_core.py` — `split_choices(question, choices, split_points)`**
   Takes a sorted list of indices (each strictly between `0` and `len(choices)`) and returns `N = len(split_points) + 1` parts as a list of `{"question": ..., "choices": ...}` dicts. First part keeps `question`; the rest get `""`. This generalizes today's hardcoded 2-way cut (`app.py:131-134`) into a loop over `[0] + split_points + [len(choices)]` boundary pairs. Lives here rather than `parser.py` because it operates on already-parsed data, consistent with `shuffle_questions` in the same file.

3. **`app.py` review screen**
   - When a flagged block first renders (no `split_key` in session state yet), call `find_split_suggestions(q["choices"])` and use the result to pre-fill a text input (comma-separated indices, e.g. `4, 9`) with a caption like "Detected 3 parts".
   - Replace the current single-integer `text_input` with this pre-filled, freely editable string input — user can accept the suggestion, edit it, add points, or remove all of them.
   - "Split" button parses the string into a sorted list of ints and calls `split_choices`. N=2 is just one number in the box, so today's most common case looks and behaves the same as now.
   - The existing per-part edit loop (`app.py:136-153`) already iterates over `split_cards` generically — no change needed there regardless of how many parts come back.

## Error handling

Same pattern as today's validation (`app.py:123-129`), generalized:
- Non-integer tokens in the input → `st.error`.
- Any index not strictly between `0` and `len(choices)` → `st.error`.
- Duplicate indices → silently deduplicated (sorted + deduped before splitting), since a repeated index typed by mistake shouldn't block an otherwise valid split.
- Empty input after removing all suggestions → `st.error` ("enter at least one split point"), since the button is explicitly "split" — splitting into 1 part is a no-op the user can get by not touching the block at all.

## Testing

- `find_split_suggestions`: unit tests with 0, 1, and 2 header-pattern matches embedded in a `choices` list, confirming correct `j+1` indices.
- `split_choices`: unit tests for N=2 (matches today's existing behavior/tests if any), N=3, split points at the boundaries (index 1 and index `len(choices)-1`), and invalid inputs (out of order, out of range).
- Manual test in the running app: re-upload the full 8-page exam, confirm the question-18/19/20 block now suggests 2 split points (or fewer, if OCR mangling defeats detection — expected, manual add covers that gap) and that manual entry of all 3 parts still works end-to-end through to the final download.

## Explicitly out of scope

- No change to `parse_ocr_text`'s top-level block detection or `is_header_line`.
- No attempt to auto-clean trailing glued-on header fragments in `choices[j]` — left to the existing manual edit step.
- No raw-text/line-number-based split model (considered and rejected in favor of the choices-list-index model, to stay minimal and backward compatible).
