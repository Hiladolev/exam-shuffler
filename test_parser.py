from parser import (
    find_question_crop_bounds,
    find_split_suggestions,
    parse_ocr_text,
    strip_version_lines,
    find_header_line_indices,
    is_probable_embedded_header,
    find_choice_line_bounds,
    find_embedded_header_bounds,
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


def test_is_probable_embedded_header_true_when_token_and_digit_present():
    assert is_probable_embedded_header("שאלה 'on' 19 (5 בק')") is True


def test_is_probable_embedded_header_false_without_the_token():
    assert is_probable_embedded_header("regular continuation text with 19 in it") is False


def test_is_probable_embedded_header_false_without_a_digit():
    assert is_probable_embedded_header("שאלה בלי מספר בכלל") is False


def test_find_choice_line_bounds_returns_all_choice_positions_after_header():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("question body", 25, 45),
        ("א. choice one", 50, 70),
        ("ב. choice two", 75, 95),
        ("שאלה 'on' 19 (5 בק')", 100, 120),
        ("more body", 125, 145),
        ("א. choice three", 150, 170),
    ]
    assert find_choice_line_bounds(lines, header_index=0) == [
        (50, 70), (75, 95), (150, 170),
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


def test_find_embedded_header_bounds_detects_candidate_with_digit():
    lines = [
        ("שאלה מס' 18 (5 נק')", 0, 20),
        ("א. choice one", 25, 45),
        ("ב. choice two", 50, 70),
        ("שאלה 'on' 19 (5 בק')", 75, 95),
        ("א. choice three", 100, 120),
    ]
    assert find_embedded_header_bounds(lines, header_index=0) == {2: (75, 95)}


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
