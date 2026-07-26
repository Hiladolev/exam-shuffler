# Fix מספר גרסה OCR Noise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `VERSION_PATTERN` in `parser.py` so it catches bidi-reordered `מספר גרסה` (version-stamp) OCR noise, instead of letting it slip through `strip_version_lines` and get glued onto the preceding question's last choice.

**Architecture:** Narrow `VERSION_PATTERN` from `r"מספר\s*גרסה\s*:\s*\d+"` to `r"מספר\s*גרסה"`, dropping the colon/digit suffix requirement that was fragile under Tesseract's bidi reordering. `strip_version_lines`'s whole-line-drop behavior is unchanged — only the pattern it matches against gets broader.

**Tech Stack:** Python, `re` — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-26-version-stamp-ocr-noise-design.md`

---

### Task 1: Narrow `VERSION_PATTERN` and add test coverage

**Files:**
- Modify: `parser.py:8`
- Test: `test_parser.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_parser.py` (after the existing `find_split_suggestions` tests), and update the import at the top of the file:

Change line 1 from:

```python
from parser import find_split_suggestions
```

to:

```python
from parser import find_split_suggestions, strip_version_lines
```

Then append:

```python


def test_strip_version_lines_drops_normal_order_version_stamp():
    text = "8 מספר גרסה: 0000\nReal question text"
    assert strip_version_lines(text) == "\nReal question text"


def test_strip_version_lines_drops_bidi_reordered_version_stamp():
    text = "0000 ‏מספר גרסה:‎ ras\nReal question text"
    assert strip_version_lines(text) == "\nReal question text"


def test_strip_version_lines_drops_second_bidi_reordered_variant():
    text = "0000 ‏מספר גרסה:‎ lr\nReal question text"
    assert strip_version_lines(text) == "\nReal question text"


def test_strip_version_lines_leaves_unrelated_lines_alone():
    text = "א. Real choice text\nמספר עמוד 3"
    assert strip_version_lines(text) == "א. Real choice text\n"
```

The last test also confirms the broadened version pattern doesn't interfere with the separately-handled `מספר עמוד` page-footer substitution (that line still ends up blanked by `PAGE_NUMBER_PATTERN.sub`, same as before this change) and leaves real choice text completely untouched.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest test_parser.py -v`

Expected: the three new bidi-reordered/normal-order tests FAIL (current `VERSION_PATTERN` requires digits after the colon, so `"0000 ‏מספר גרסה:‎ ras"` and `"0000 ‏מספר גרסה:‎ lr"` aren't dropped yet), while `test_strip_version_lines_drops_normal_order_version_stamp` and `test_strip_version_lines_leaves_unrelated_lines_alone` already PASS against the current pattern.

- [ ] **Step 3: Narrow `VERSION_PATTERN`**

In `parser.py`, change line 8 from:

```python
VERSION_PATTERN = re.compile(r"מספר\s*גרסה\s*:\s*\d+")
```

to:

```python
VERSION_PATTERN = re.compile(r"מספר\s*גרסה")
```

- [ ] **Step 4: Run tests to verify they all pass**

Run: `python -m pytest test_parser.py -v`

Expected: all tests pass (7 total: 3 existing `find_split_suggestions` tests + 4 new `strip_version_lines` tests).

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -q`

Expected: all tests pass, no regressions in `test_shuffler_core.py` or `test_ocr.py`-adjacent tests.

- [ ] **Step 6: Manually verify against the full sample exam**

If a Streamlit server is running from earlier testing, stop it first. Start fresh:

```bash
streamlit run app.py
```

Upload `sample_exams/data_science_test_havana.pdf` and click "Process". Find the two questions whose choices previously ended with glued-on `מספר גרסה` noise (the last choice of the question right before page 7's content, and the last choice of the question right before page 11's content, per the design doc's investigation). Confirm their choice text is now clean, with no `מספר גרסה` / stray Latin-letter noise appended.

Stop the server once done — don't leave it running.

- [ ] **Step 7: Commit and push**

```bash
git add parser.py test_parser.py
git commit -m "Broaden VERSION_PATTERN to catch bidi-reordered מספר גרסה OCR noise"
git push
```

---

## Self-Review Notes

- **Spec coverage:** The spec's single change (narrowing `VERSION_PATTERN` to the two-word anchor) is covered by Task 1, Step 3. The spec's investigation findings (6/8 normal-order occurrences already matching, 2/8 bidi-reordered occurrences not matching) are directly encoded as test cases in Step 1, so the fix is verified against the exact real-world patterns that motivated it, not just a synthetic case.
- **Type consistency:** `strip_version_lines(text)` signature and return type (a newline-joined string) match its existing use in `parser.py`'s own `__main__` block (`raw_text = strip_version_lines(raw_text)`) and `app.py`'s `run_pipeline`. No signature change — only the module-level `VERSION_PATTERN` regex changes, which `strip_version_lines` already references by name.
- **No changes to `PAGE_NUMBER_PATTERN`, `parse_ocr_text`, or `strip_bidi_marks`** — matches the spec's explicit out-of-scope list.
