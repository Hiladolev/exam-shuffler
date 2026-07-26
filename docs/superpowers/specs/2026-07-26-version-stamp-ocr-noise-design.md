# Fix `מספר גרסה` OCR noise slipping past `strip_version_lines`

## Problem

`parser.py`'s `strip_version_lines` drops any line matching `VERSION_PATTERN`, meant to remove the exam's internal version-stamp text (e.g. `"מספר גרסה: 0000"`) before parsing. In the full 8-page sample exam, two of the eight version-stamp occurrences survive this filter and end up glued onto the end of the preceding question's last choice, corrupting it.

## Investigation findings

`VERSION_PATTERN` is defined as `r"מספר\s*גרסה\s*:\s*\d+"` — it requires the digits to appear immediately after the colon, in that fixed order. Checking every `גרסה` occurrence in the sample exam's OCR output (`ocr_output.txt`, 8 total, all version-stamp noise — none are real question/choice content):

- 6 of 8 are in normal left-to-right order (e.g. `"8 מספר גרסה: 0000"`) and match `VERSION_PATTERN` correctly — the whole line gets dropped, including harmless stray noise characters (like the leading `"8"`) that happened to share the line.
- 2 of 8 are bidi-reordered by Tesseract: `"0000 ‏מספר גרסה:‎ ras"` and `"0000 ‏מספר גרסה:‎ lr"`. The digits land *before* `מספר גרסה:` instead of after, and garbled OCR noise (`ras`, `lr`) sits where digits should be after the colon. `\d+` never matches in that position, so `VERSION_PATTERN` fails silently on these two lines.

Both undetected lines appear at the very top of a page's OCR text, immediately after the previous page's last real choice line. Since `parse_ocr_text` only starts a new block on a question-header match, and these lines aren't headers, they land inside the still-open previous block while `in_choices` is `True` — so `choices[-1] = (choices[-1] + " " + stripped).strip()` glues the noise onto that choice's text. This is the same block-gluing mechanism that motivated dropping `=== PAGE N ===` markers in `docs/superpowers/specs/2026-07-26-multipage-ocr-design.md`, and it affects `app.py`'s real (marker-free) pipeline today, not just the old `test_ocr.py`-generated `ocr_output.txt`.

The colon+digit suffix was never actually necessary to identify these lines as noise — it was incidental specificity that turned out to be fragile under bidi reordering. The two Hebrew words `מספר` and `גרסה` never appear reordered relative to each other in any of the 8 samples; only the separate LTR digit run around them gets bidi-reordered by Tesseract.

## Design

Narrow `VERSION_PATTERN` to just the two-word anchor, dropping the colon/digit requirement entirely:

`parser.py:8`, change:

```python
VERSION_PATTERN = re.compile(r"מספר\s*גרסה\s*:\s*\d+")
```

to:

```python
VERSION_PATTERN = re.compile(r"מספר\s*גרסה")
```

`strip_version_lines`'s whole-line-drop behavior is unchanged (`if VERSION_PATTERN.search(line): continue`) — it was already correct for lines that matched; the bug was purely that the pattern was too narrow to match real-world OCR variants of the same noise.

This stays safe against false positives: `מספר עמוד` (page number, handled separately by `PAGE_NUMBER_PATTERN`) also contains the word `מספר`, but never `גרסה`, so requiring both words together won't cause the broadened pattern to accidentally swallow page-number lines. No occurrence of `גרסה` anywhere in the sample exam's OCR output is real question/choice content, so unconditionally dropping any line containing `מספר גרסה` remains safe.

## Explicitly out of scope

- No change to `PAGE_NUMBER_PATTERN` or its substitute-not-drop behavior — it already handles every observed `מספר עמוד` variant correctly.
- No change to `parse_ocr_text`'s block-gluing logic (the mechanism that turns an unfiltered noise line into corrupted choice text) — narrowing the filter so the noise line is reliably caught upstream is sufficient; changing the gluing logic itself is a separate, broader concern already noted as out of scope in the multi-page OCR design doc.
- No general-purpose bidi-reordering fix — this addresses the one specific, confirmed noise pattern, not bidi/OCR robustness in general.

## Testing

- Add unit tests for `strip_version_lines` in `test_parser.py` (currently has no coverage for this function): normal-order version-stamp lines are still dropped, the two confirmed bidi-reordered variants (`"0000 ‏מספר גרסה:‎ ras"`, `"0000 ‏מספר גרסה:‎ lr"`) are now also dropped, and an unrelated line (e.g. a real choice, or a `מספר עמוד` page-footer line) is left untouched.
- Manual verification: re-run the full 8-page sample exam through the app and confirm the two previously-corrupted choices no longer contain glued-on `מספר גרסה` noise text.
