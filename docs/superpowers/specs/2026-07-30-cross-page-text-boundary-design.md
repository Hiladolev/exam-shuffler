# Stop `parse_ocr_text` gluing choice text across a page boundary

## Problem

`parse_ocr_text`'s choice-continuation logic (the `elif in_choices:` branch) has no concept of pages — it just keeps appending any non-choice-pattern line onto the last choice's text, regardless of how many pages separate it from where that choice started. `run_pipeline` joins all kept pages' text with `"\n\n"` before calling `parse_ocr_text`, so when a merged/flagged block spans a page break, the next page's leading content (which may be another sub-question's embedded header and body text) gets silently absorbed into the tail of the previous page's last choice instead of surfacing as its own content.

This was found investigating the real sample exam: block 18/19/20 spans pages 13 and 14. Q19's last choice (`ד. accuracy הינו TIN לאיכות חיזוי קלסיפיקציה...`) ends page 13; Q20's embedded header and its actual question sentence (`שאלה 'on 20 (5 גק') מה מבצעת הפונקציה ?mask`) open page 14. Today, that page-14 text gets glued onto Q19's choice D, so post-split Part 3 (Q20) ends up with no image and no usable question text — the content isn't lost outright, but it's misattributed to the wrong choice and effectively invisible to the split-point UI.

Two candidate signals were considered for detecting the boundary and rejected/deferred:
- `"מספר גרסה"`/`"מספר עמוד"` text markers — already stripped as noise (`strip_version_lines`) before `parse_ocr_text` runs, so by the time the continuation-joining logic executes, no textual trace of the page boundary remains.
- Extending Phase 2's pixel-side lookup to also reach across pages — a materially bigger design (which page's image to crop from? stitching?), explicitly deferred; this doc covers the text-parser fix only.

## Design

### 1. New optional parameter: `page_offsets`

```python
def parse_ocr_text(text, page_offsets=None):
```

`page_offsets` is the same `[(page_number, start_line_index), ...]` list `app.py`'s `build_page_offsets` already produces — and already computes *before* calling `parse_ocr_text` in `run_pipeline`. Defaulting to `None` preserves current behavior exactly: every existing test, and the standalone `parser.py __main__` debug script (which reads a flat cached OCR dump with no page structure available), keep working unchanged.

### 2. Boundary detection: a plain index set

At the top of `parse_ocr_text`:

```python
page_boundary_starts = {start for _, start in page_offsets[1:]} if page_offsets else set()
```

`page_offsets[1:]` skips the first page's own start (always index 0 — not a "crossing"). Each remaining `start` is exactly the absolute line index of that page's first *real* content line: `build_page_offsets`'s `+2` adjustment already accounts for the blank separator line `"\n\n".join` inserts between pages, so a boundary index never lands on the blank separator itself, only on real content. Since blank lines are already skipped via `continue` before this check runs, there is no off-by-one risk between "the boundary index" and "the first non-blank line parse_ocr_text actually processes."

`parser.py` never needs to know what a page *number* is here — just whether a given line index is one of these boundary points. No page-number-resolution helper is added or duplicated.

### 3. Where the check plugs into the existing loop

The per-block loop currently iterates `for line in block_lines:`, discarding each line's absolute position within the full document. It becomes an enumerated walk so `absolute_index = start + offset` can be checked against `page_boundary_starts`:

```python
for offset, line in enumerate(block_lines):
    absolute_index = start + offset
    stripped = line.strip()
    if not stripped:
        continue

    match = CHOICE_PATTERN.match(line)
    if match:
        in_choices = True
        choices.append(match.group(2).strip())
    elif in_choices and absolute_index in page_boundary_starts:
        choices.append(stripped)
    elif in_choices:
        choices[-1] = (choices[-1] + " " + stripped).strip()
    else:
        question_lines.append(stripped)
```

The new branch only fires while `in_choices` is already `True`. A question's own intro prose (before any choice has started) is left free to span a page break unchanged — that's legitimate continuous prose for a single question, not the reported bug. Only choice-list glomming is affected.

### 4. Result for the real case

For the 18/19/20 block: today, Q19's last choice silently absorbs Q20's embedded header and its actual question sentence as trailing text. After this change, that page-14 content starts a brand-new entry in the flat `choices` list instead of being glued onto Q19's last choice — visible in the flagged card's choice list, and a natural split point, rather than buried inside another choice's text. It won't look like a real lettered choice (no `א.`/`ב.` marker) — same as today's already-accepted convention for same-page embedded headers, fixed up by hand on the review screen.

### 5. Wiring

`app.py`'s `run_pipeline` already computes `page_offsets` before calling `parse_ocr_text`. The call site changes from:

```python
parsed_questions = parse_ocr_text(raw_text)
```

to:

```python
parsed_questions = parse_ocr_text(raw_text, page_offsets)
```

No other call site has `page_offsets` available (the `parser.py __main__` debug block calls `parse_ocr_text(raw_text)` with one argument), so it's unaffected and keeps its current behavior via the new parameter's default.

### 6. Interaction with Phase 2's pixel-side safety (no regression)

This is a text-only change — it doesn't touch `find_choice_line_bounds` or `find_embedded_header_bounds`, which still only scan the single page containing a block's header. After this fix, a cross-page block's flat `choices` list will typically grow by one entry (the newly-separated boundary text) while the pixel-side bounds list stays exactly as short as before. `split_choices`'s existing guard (`start in embedded_header_bounds and start < len(choice_line_bounds)`) already requires an *exact* match on both structures before attaching an image — a split point landing on this new boundary entry simply has no matching pixel bound, so it safely falls back to plain (now correctly separated, no longer misattributed) text. No wrong-image risk is introduced by this change.

## Explicitly out of scope

- Cropping an image for parts whose content originates on a later page (the Phase 2 pixel-side gap) — still deferred; this doc is the text-parser fix only.
- A single choice's text spanning three or more pages — not observed in the real exam. The per-line boundary check happens to handle it correctly anyway (each new boundary crossed always starts a fresh entry, regardless of how many boundaries occur), but this design doesn't specifically verify that case.
- Any change to how `question_lines` (pre-choice question prose) accumulates across a page break — unaffected, left as today's behavior.
- Any change to `find_split_suggestions`'s strict `HEADER_PATTERN` matching, or to how `strip_version_lines` filters noise — unrelated to this fix.

## Testing

- `parser.py`: new tests for `parse_ocr_text` with a `page_offsets` argument —
  - a block whose choices are split across a page boundary gets a new choice entry at the boundary instead of glued text;
  - behavior is unchanged when `page_offsets` is omitted (regression coverage for every existing call site, including the zero-argument case);
  - a page boundary falling inside question-intro prose (before any choice has started) does not split anything, confirming the fix is scoped to choices only.
- No new test for the `app.py` wiring change itself beyond what already exists, consistent with this codebase's existing convention for `run_pipeline` (needs a real PDF + tesseract binary) — verified manually against the real exam in the browser, per Hila's stated preference for driving Streamlit UI checks herself.
