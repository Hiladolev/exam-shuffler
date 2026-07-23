import pytest

from shuffler_core import split_choices


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
