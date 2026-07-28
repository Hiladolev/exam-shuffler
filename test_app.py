from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import app


def _make_processed_app_test():
    at = AppTest.from_file("app.py")
    at.session_state["processed"] = True
    at.session_state["shuffled_questions"] = [
        {
            "question": "Sample question?",
            "choices": ["A", "B", "C", "D", "E"],
            "correct_index": 0,
        }
    ]
    at.session_state["needs_review"] = []
    at.run()
    return at


def test_remove_middle_choice_keeps_correct_text_at_correct_positions():
    at = _make_processed_app_test()

    at.button(key="clean_q_0_v0_remove_1").click().run()

    remaining = [
        at.text_input(key=f"clean_q_0_v1_choice_{j}").value for j in range(4)
    ]
    assert remaining == ["A", "C", "D", "E"]


def test_remove_choice_preserves_unsaved_edit_to_another_choice():
    at = _make_processed_app_test()

    at.text_input(key="clean_q_0_v0_choice_0").set_value("A-fixed").run()
    at.button(key="clean_q_0_v0_remove_4").click().run()

    remaining = [
        at.text_input(key=f"clean_q_0_v1_choice_{j}").value for j in range(4)
    ]
    assert remaining == ["A-fixed", "B", "C", "D"]


def test_add_choice_preserves_selected_correct_answer():
    at = _make_processed_app_test()

    at.radio(key="clean_q_0_v0_correct_index").set_value(2).run()
    at.button(key="clean_q_0_add_choice").click().run()

    assert at.radio(key="clean_q_0_v0_correct_index").value == 2


def test_remove_choice_preserves_selected_correct_answer():
    at = _make_processed_app_test()

    at.radio(key="clean_q_0_v0_correct_index").set_value(2).run()
    at.button(key="clean_q_0_v0_remove_4").click().run()

    assert at.radio(key="clean_q_0_v1_correct_index").value == 2


def test_remove_choice_before_correct_answer_shifts_correct_index_down():
    at = _make_processed_app_test()

    at.radio(key="clean_q_0_v0_correct_index").set_value(2).run()
    at.button(key="clean_q_0_v0_remove_0").click().run()

    remaining = [
        at.text_input(key=f"clean_q_0_v1_choice_{j}").value for j in range(4)
    ]
    assert remaining == ["B", "C", "D", "E"]
    assert at.radio(key="clean_q_0_v1_correct_index").value == 1


def test_remove_the_correct_choice_itself_resets_correct_index_to_zero():
    at = _make_processed_app_test()

    at.radio(key="clean_q_0_v0_correct_index").set_value(2).run()
    at.button(key="clean_q_0_v0_remove_2").click().run()

    assert at.radio(key="clean_q_0_v1_correct_index").value == 0


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
