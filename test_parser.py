from parser import find_split_suggestions


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
