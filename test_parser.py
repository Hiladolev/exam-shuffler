from parser import (
    find_question_crop_bounds,
    find_split_suggestions,
    parse_ocr_text,
    strip_version_lines,
    find_header_line_indices,
    is_probable_embedded_header,
    find_choice_line_bounds,
    find_embedded_header_bounds,
    is_any_header_line,
    choice_letter_rank,
    find_letter_reset_indices,
    determine_expected_choice_count,
    is_choice_count_suspicious,
)


def test_no_header_matches_returns_empty_list():
    choices = ["Paris", "London", "Berlin"]
    assert find_split_suggestions(choices) == []


def test_one_header_match_suggests_next_index():
    choices = ["Paris", "שאלה מס' 5 (2 נק') London", "Berlin"]
    assert find_split_suggestions(choices) == [2]


def test_two_header_matches_suggest_both_next_indices():
    choices = [
        "Paris",
        "שאלה מס' 5 (2 נק') London",
        "Berlin",
        "שאלה מס' 6 (3 נק') Madrid",
        "Rome",
    ]
    assert find_split_suggestions(choices) == [2, 4]


def test_find_question_crop_bounds_normal_single_question():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("some question text", 25, 45),
        ("more question text", 50, 70),
        ("א. Paris", 75, 95),
        ("ב. London", 100, 120),
    ]
    assert find_question_crop_bounds(lines) == [(20, 75)]


def test_find_question_crop_bounds_header_with_no_following_choice():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("dangling question text with no choices", 25, 45),
    ]
    assert find_question_crop_bounds(lines) == [None]


def test_find_question_crop_bounds_multiple_questions_on_one_page():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("question one text", 25, 45),
        ("א. Paris", 50, 70),
        ("ב. London", 75, 95),
        ("שאלה מס' 6 (3 נק')", 100, 120),
        ("question two text", 125, 145),
        ("א. Red", 150, 170),
    ]
    assert find_question_crop_bounds(lines) == [(20, 50), (120, 150)]


def test_find_question_crop_bounds_zero_headers():
    lines = [
        ("just some prose", 0, 20),
        ("more prose", 25, 45),
    ]
    assert find_question_crop_bounds(lines) == []


def test_find_question_crop_bounds_band_shorter_than_minimum_height():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 22, 40),
    ]
    assert find_question_crop_bounds(lines) == [None]


def test_find_question_crop_bounds_consecutive_headers_with_no_choice_between():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("שאלה מס' 6 (3 נק')", 25, 45),
        ("question six text", 50, 70),
        ("א. Paris", 75, 95),
    ]
    assert find_question_crop_bounds(lines) == [None, (45, 75)]


def test_find_question_crop_bounds_recognizes_loose_header_as_anchor():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("question one text", 25, 45),
        ("א. Paris", 50, 70),
        ("שאלה 'on' 6 (3 בק')", 75, 95),
        ("question two text", 100, 120),
        ("א. Red", 125, 145),
    ]
    assert find_question_crop_bounds(lines) == [(20, 50), (95, 125)]


def test_parse_ocr_text_records_header_line_index_including_leading_block():
    text = "\n".join([
        "some leading noise",
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. Paris",
        "ב. London",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["header_line_index"] == 0
    assert questions[1]["header_line_index"] == 1
    assert questions[0]["has_real_header"] is False
    assert questions[1]["has_real_header"] is True


def test_parse_ocr_text_records_header_line_index_for_multiple_questions():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question one",
        "א. Paris",
        "שאלה מס' 2 (3 נק')",
        "question two",
        "א. Red",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["header_line_index"] == 0
    assert questions[1]["header_line_index"] == 3


def test_strip_version_lines_per_page_matches_joined_stripping():
    pages = [
        "page one text\nמספר גרסה: 5\nmore content",
        "page two text\nmore content",
    ]

    joined_then_stripped = strip_version_lines("\n\n".join(pages))
    stripped_then_joined = "\n\n".join(strip_version_lines(p) for p in pages)

    assert joined_then_stripped == stripped_then_joined


def test_strip_version_lines_handles_reversed_digits_and_trailing_garbage():
    assert strip_version_lines("0000 מספר גרסה: lr a nse") == ""
    assert strip_version_lines("0000 מספר גרסה: ras קב") == ""


def test_strip_version_lines_removes_standalone_orphaned_stamp_line():
    assert strip_version_lines("0000") == ""
    assert strip_version_lines("real text\n0000\nmore text") == "real text\n\nmore text"


def test_strip_version_lines_removes_bidi_wrapped_standalone_stamp():
    bidi_wrapped_stamp = "‏0000‎"
    assert strip_version_lines(bidi_wrapped_stamp) == ""


def test_find_header_line_indices_returns_indices_of_header_lines():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_header_line_indices(lines) == [0, 2]


def test_find_header_line_indices_empty_when_no_headers():
    lines = [("just prose", 0, 20), ("more prose", 25, 45)]
    assert find_header_line_indices(lines) == []


def test_find_header_line_indices_recognizes_loose_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה 'on' 6 (3 בק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_header_line_indices(lines) == [0, 2]


def test_is_probable_embedded_header_true_when_token_and_digit_present():
    assert is_probable_embedded_header("שאלה 'on' 19 (5 בק')") is True


def test_is_probable_embedded_header_false_without_the_token():
    assert is_probable_embedded_header("regular continuation text with 19 in it") is False


def test_is_probable_embedded_header_false_without_a_digit():
    assert is_probable_embedded_header("שאלה בלי מספר בכלל") is False


def test_find_choice_line_bounds_stops_at_loose_header_after_collecting_prior_choices():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("question body", 25, 45),
        ("א. choice one", 50, 70),
        ("ב. choice two", 75, 95),
        ("שאלה 'on' 19 (5 בק')", 100, 120),
        ("more body", 125, 145),
        ("א. choice three", 150, 170),
    ]
    # Loose header at index 4 now stops the scan (Task 3) -- "choice three"
    # belongs to the next auto-split question, not this one.
    assert find_choice_line_bounds(lines, header_index=0) == [
        (50, 70), (75, 95),
    ]


def test_find_choice_line_bounds_stops_at_next_real_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [(25, 45)]


def test_find_choice_line_bounds_empty_when_no_choices_follow():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("dangling prose, no choices", 25, 45),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == []


def test_find_choice_line_bounds_stops_at_loose_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה 'on' 6 (3 בק')", 50, 70),
        ("א. Red", 75, 95),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [(25, 45)]


def test_find_embedded_header_bounds_stops_at_loose_header_with_digit_after_multiple_choices():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("ב. choice two", 50, 70),
        ("שאלה 'on' 19 (5 בק')", 75, 95),
        ("א. choice three", 100, 120),
    ]
    # Loose header at index 3 now stops the scan and is never cataloged as an
    # embedded candidate (Task 3) -- it's a real auto-split boundary now.
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_ignores_candidate_without_digit():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("שאלה בלי מספר", 50, 70),
        ("ב. choice two", 75, 95),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_ignores_lines_before_any_choice_started():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("שאלה 19 embedded too early", 25, 45),
        ("א. choice one", 50, 70),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_stops_at_next_real_header():
    lines = [
        ("שאלה מס' 5 (2 נק')", 0, 20),
        ("א. Paris", 25, 45),
        ("שאלה מס' 6 (3 נק')", 50, 70),
        ("שאלה 19 mangled but after a different real header", 75, 95),
        ("א. Red", 100, 120),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_find_embedded_header_bounds_stops_at_loose_header_not_catalog_it():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("שאלה 'on' 19 (5 בק')", 50, 70),
        ("א. choice from next question", 75, 95),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {}


def test_parse_ocr_text_starts_new_choice_at_page_boundary_instead_of_gluing():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. choice one",
        "ב. choice two",
        "continuation from next page",
        "ג. choice three",
    ])
    page_offsets = [(2, 0), (3, 4)]

    questions = parse_ocr_text(text, page_offsets)

    assert len(questions) == 1
    assert questions[0]["choices"] == [
        "choice one",
        "choice two",
        "continuation from next page",
        "choice three",
    ]


def test_parse_ocr_text_without_page_offsets_keeps_gluing_across_pages():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question body",
        "א. choice one",
        "ב. choice two",
        "continuation from next page",
        "ג. choice three",
    ])

    questions = parse_ocr_text(text)

    assert len(questions) == 1
    assert questions[0]["choices"] == [
        "choice one",
        "choice two continuation from next page",
        "choice three",
    ]


def test_parse_ocr_text_boundary_inside_question_intro_prose_is_inert():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question line one",
        "question line two",
        "א. choice one",
    ])
    page_offsets = [(2, 0), (3, 2)]

    questions = parse_ocr_text(text, page_offsets)

    assert len(questions) == 1
    assert questions[0]["question"] == "question line one question line two"
    assert questions[0]["choices"] == ["choice one"]


def test_is_any_header_line_true_for_strict_header():
    assert is_any_header_line("שאלה מס' 5 (2 נק')") is True


def test_is_any_header_line_true_for_loose_header():
    assert is_any_header_line("שאלה 'on' 19 (5 בק')") is True


def test_is_any_header_line_false_for_ordinary_text():
    assert is_any_header_line("just a regular sentence") is False


def test_choice_letter_rank_returns_rank_for_choice_line():
    assert choice_letter_rank("א. Paris") == 0
    assert choice_letter_rank("ה. Berlin") == 4


def test_choice_letter_rank_none_for_non_choice_line():
    assert choice_letter_rank("some prose") is None


def test_find_letter_reset_indices_detects_terminal_heh_followed_by_reset():
    lines = [
        "question body",
        "א. one",
        "ב. two",
        "ג. three",
        "ד. four",
        "ה. five",
        "א. next question first choice",
    ]
    assert find_letter_reset_indices(lines, header_boundary_indices=[]) == [6]


def test_find_letter_reset_indices_ignores_forward_gap():
    lines = ["א. one", "ג. skipped bet, not a reset"]
    assert find_letter_reset_indices(lines, header_boundary_indices=[]) == []


def test_find_letter_reset_indices_resets_tracking_at_a_header_boundary():
    lines = [
        "א. one",
        "ב. two",
        "שאלה מס' 2 (2 נק')",
        "א. real next question, not a reset",
    ]
    assert find_letter_reset_indices(lines, header_boundary_indices=[2]) == []


def test_parse_ocr_text_splits_on_letter_reset_with_no_header_signal():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')",
        "question one body",
        "א. one",
        "ב. two",
        "ג. three",
        "ד. four",
        "ה. five",
        "א. next question first choice",
        "ב. next question second choice",
    ])
    questions = parse_ocr_text(text)

    assert len(questions) == 2
    assert questions[0]["choices"] == ["one", "two", "three", "four", "five"]
    assert questions[1]["choices"] == ["next question first choice", "next question second choice"]
    assert questions[1]["header_line_index"] == 7
    assert questions[1]["has_real_header"] is False


def test_parse_ocr_text_tags_real_header_questions_true():
    text = "\n".join(["שאלה מס' 1 (2 נק')", "body", "א. one"])
    questions = parse_ocr_text(text)
    assert questions[0]["has_real_header"] is True


def test_parse_ocr_text_tags_loose_header_questions_true():
    text = "\n".join([
        "שאלה מס' 1 (2 נק')", "body one", "א. a",
        "שאלה 'on' 2 (5 בק')", "body two", "א. b",
    ])
    questions = parse_ocr_text(text)
    assert len(questions) == 2
    assert questions[1]["has_real_header"] is True


def test_determine_expected_choice_count_clear_majority():
    questions = [{"choices": ["a"] * 4}] * 5 + [{"choices": ["a"] * 3}]
    assert determine_expected_choice_count(questions) == 4


def test_determine_expected_choice_count_excludes_zero_choice_questions():
    questions = [{"choices": ["a"] * 4}] * 2 + [{"choices": []}] * 5
    assert determine_expected_choice_count(questions) == 4


def test_determine_expected_choice_count_none_on_tie():
    questions = [{"choices": ["a"] * 4}] * 2 + [{"choices": ["a"] * 5}] * 2
    assert determine_expected_choice_count(questions) is None


def test_determine_expected_choice_count_none_when_top_count_too_rare():
    questions = [{"choices": ["a"] * 4}]
    assert determine_expected_choice_count(questions) is None


def test_is_choice_count_suspicious_matches_expected_count():
    assert is_choice_count_suspicious(4, expected_count=4) is False
    assert is_choice_count_suspicious(5, expected_count=4) is True


def test_is_choice_count_suspicious_falls_back_to_four_or_five_when_no_expected_count():
    assert is_choice_count_suspicious(4, expected_count=None) is False
    assert is_choice_count_suspicious(5, expected_count=None) is False
    assert is_choice_count_suspicious(3, expected_count=None) is True
    assert is_choice_count_suspicious(0, expected_count=None) is True
