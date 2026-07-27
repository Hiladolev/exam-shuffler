from unittest.mock import patch

import app


def test_build_final_content_does_not_reshuffle_review_cards():
    edited_review_cards = [
        {"question": "Q1", "choices": ["x", "y", "z"], "correct_index": 2},
    ]

    with patch("app.shuffle_questions") as mock_shuffle:
        result = app.build_final_content([], edited_review_cards)

    mock_shuffle.assert_not_called()
    assert "Question: Q1" in result
    assert "  0: x" in result
    assert "  1: y" in result
    assert "  2: z" in result
    assert "Correct answer index: 2" in result
