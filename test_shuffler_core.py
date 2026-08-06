import pytest

from shuffler_core import split_choices, remove_choice, shuffle_questions


def test_split_choices_n2_matches_two_way_split():
    parts = split_choices("Q", ["a", "b", "c", "d"], [2])
    assert parts == [
        {"question": "Q", "choices": ["a", "b"]},
        {"question": "", "choices": ["c", "d"]},
    ]


def test_split_choices_n3():
    parts = split_choices("Q", ["a", "b", "c", "d", "e", "f"], [2, 4])
    assert parts == [
        {"question": "Q", "choices": ["a", "b"]},
        {"question": "", "choices": ["c", "d"]},
        {"question": "", "choices": ["e", "f"]},
    ]


def test_split_choices_boundary_points():
    parts = split_choices("Q", ["a", "b", "c", "d"], [1, 3])
    assert parts == [
        {"question": "Q", "choices": ["a"]},
        {"question": "", "choices": ["b", "c"]},
        {"question": "", "choices": ["d"]},
    ]


def test_split_choices_rejects_out_of_order_points():
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [3, 1])


def test_split_choices_rejects_out_of_range_points():
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [0])
    with pytest.raises(ValueError):
        split_choices("Q", ["a", "b", "c", "d"], [4])


def test_split_choices_keeps_question_image_on_first_part_only():
    parts = split_choices("Q", ["a", "b", "c", "d"], [2], question_image=b"PNGDATA")
    assert parts[0]["question_image"] == b"PNGDATA"
    assert parts[1].get("question_image") is None


def test_split_choices_computes_image_bounds_for_matching_split_point():
    parts = split_choices(
        "Q", ["a", "b", "c", "d"], [2],
        choice_line_bounds=[(0, 20), (25, 45), (100, 120), (125, 145)],
        embedded_header_bounds={2: (60, 90)},
    )
    assert parts[1]["image_bounds"] == (90, 100)


def test_split_choices_leaves_image_bounds_unset_when_split_point_not_detected():
    parts = split_choices(
        "Q", ["a", "b", "c", "d"], [2],
        choice_line_bounds=[(0, 20), (25, 45), (100, 120), (125, 145)],
        embedded_header_bounds={},
    )
    assert parts[1].get("image_bounds") is None


def test_remove_choice_removes_item_at_index():
    result = remove_choice(["a", "b", "c", "d", "e"], 1)
    assert result == ["a", "c", "d", "e"]


def test_remove_choice_rejects_removal_at_min_choices():
    with pytest.raises(ValueError):
        remove_choice(["a", "b", "c", "d"], 0)


def test_remove_choice_allows_custom_min_choices():
    result = remove_choice(["a", "b", "c"], 0, min_choices=2)
    assert result == ["b", "c"]
    with pytest.raises(ValueError):
        remove_choice(["a", "b"], 0, min_choices=2)


def test_shuffle_questions_after_split_assigns_correct_index_to_each_part():
    parts = split_choices("Q", ["a", "b", "c", "d", "e", "f"], [2, 4])
    shuffled_parts = shuffle_questions(parts)

    assert len(shuffled_parts) == 3
    for part in shuffled_parts:
        assert "correct_index" in part
        assert 0 <= part["correct_index"] < len(part["choices"])


def test_shuffle_questions_carries_question_image_through_unchanged():
    questions = [
        {"question": "Q", "choices": ["a", "b", "c", "d"], "question_image": b"PNGDATA"},
    ]
    shuffled = shuffle_questions(questions)
    assert shuffled[0]["question_image"] == b"PNGDATA"


def test_shuffle_questions_defaults_question_image_to_none_when_absent():
    questions = [{"question": "Q", "choices": ["a", "b", "c", "d"]}]
    shuffled = shuffle_questions(questions)
    assert shuffled[0]["question_image"] is None
