from parser import find_question_crop_bounds, find_split_suggestions


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
