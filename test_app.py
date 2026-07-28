import base64
from unittest.mock import patch

from PIL import Image
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


def _make_processed_app_test_with_split_card():
    at = AppTest.from_file("app.py")
    at.session_state["processed"] = True
    at.session_state["shuffled_questions"] = []
    at.session_state["needs_review"] = [
        {"question": "Merged?", "choices": ["a"] * 8}
    ]
    # Pre-seed as if "Split question" was already clicked, matching how
    # app.py stores it in st.session_state[f"review_split_result_{i}"].
    at.session_state["review_split_result_0"] = [
        {
            "question": "Part 1?",
            "choices": ["A", "B", "C", "D", "E"],
            "correct_index": 0,
        }
    ]
    at.run()
    return at


def test_flagged_screen_remove_choice_before_correct_answer_shifts_correct_index_down():
    at = _make_processed_app_test_with_split_card()

    at.radio(key="review_0_part0_v0_correct_index").set_value(2).run()
    at.button(key="review_0_part0_v0_remove_0").click().run()

    remaining = [
        at.text_input(key=f"review_0_part0_v1_choice_{j}").value for j in range(4)
    ]
    assert remaining == ["B", "C", "D", "E"]
    assert at.radio(key="review_0_part0_v1_correct_index").value == 1


def test_flagged_screen_add_choice_preserves_selected_correct_answer():
    at = _make_processed_app_test_with_split_card()

    at.radio(key="review_0_part0_v0_correct_index").set_value(2).run()
    at.button(key="review_0_part0_add_choice").click().run()

    assert at.radio(key="review_0_part0_v0_correct_index").value == 2


def test_flagged_screen_edits_flow_through_to_final_content():
    at = _make_processed_app_test_with_split_card()

    at.radio(key="review_0_part0_v0_correct_index").set_value(2).run()
    at.button(key="review_0_part0_v0_remove_0").click().run()
    at.text_input(key="review_0_part0_v1_choice_1").set_value("C-fixed").run()

    edited_review_cards = [
        {
            "question": at.text_area(key="review_0_part0_question").value,
            "choices": [
                at.text_input(key=f"review_0_part0_v1_choice_{j}").value
                for j in range(4)
            ],
            "correct_index": at.radio(key="review_0_part0_v1_correct_index").value,
        }
    ]
    result = app.build_final_content([], edited_review_cards)

    assert "  1: C-fixed" in result
    assert "Correct answer index: 1" in result


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


def test_build_final_html_renders_image_tag_when_question_image_present():
    edited_clean = [
        {
            "question": "ignored text",
            "choices": ["a", "b", "c", "d"],
            "correct_index": 1,
            "question_image": b"FAKEPNGBYTES",
        },
    ]
    result = app.build_final_html(edited_clean, [])

    expected_b64 = base64.b64encode(b"FAKEPNGBYTES").decode("ascii")
    assert f'<img src="data:image/png;base64,{expected_b64}">' in result
    assert "ignored text" not in result
    assert "<li>0: a</li>" in result
    assert "Correct answer index: 1" in result


def test_build_final_html_renders_text_fallback_when_no_question_image():
    edited_clean = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "correct_index": 0, "question_image": None},
    ]
    result = app.build_final_html(edited_clean, [])

    assert "<p>Q1</p>" in result
    assert "<img" not in result


def test_build_final_html_escapes_html_special_characters():
    edited_clean = [
        {
            "question": "What does <b>bold</b> & \"quotes\" do?",
            "choices": ["<script>alert(1)</script>", "b", "c", "d"],
            "correct_index": 0,
            "question_image": None,
        },
    ]
    result = app.build_final_html(edited_clean, [])

    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "<b>bold</b>" not in result
    assert "&lt;b&gt;bold&lt;/b&gt;" in result


def test_build_final_html_renders_review_cards_as_plain_text():
    edited_review_cards = [
        {"question": "Merged?", "choices": ["x", "y", "z", "w"], "correct_index": 2},
    ]
    result = app.build_final_html([], edited_review_cards)

    assert "<p>Merged?</p>" in result
    assert "<li>2: z</li>" in result
    assert "Correct answer index: 2" in result


def test_attach_question_images_matched_page_keeps_image_when_another_page_mismatches():
    image_a = Image.new("RGB", (100, 50), color="white")
    image_b = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
        {"question": "Q3", "choices": ["a", "b", "c", "d"], "header_line_index": 11},
    ]
    page_offsets = [(2, 0), (3, 10)]
    # Page 2 has one question and one matching band -> should get an image.
    # Page 3 has two questions but only one band -> mismatch, both fall back to None.
    page_bands = [
        (2, image_a, (5, 8)),
        (3, image_b, (12, 15)),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None
    assert parsed_questions[2]["question_image"] is None


def test_attach_question_images_handles_none_band_within_a_matched_page():
    image_a = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 5},
    ]
    page_offsets = [(2, 0)]
    page_bands = [
        (2, image_a, (5, 30)),
        (2, image_a, None),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_never_misattributes_when_per_page_miscounts_cancel_globally():
    image_a = Image.new("RGB", (100, 50), color="white")
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
        {"question": "Q2", "choices": ["a", "b", "c", "d"], "header_line_index": 10},
    ]
    page_offsets = [(2, 0), (3, 10)]
    # Page 2 has 1 question but 2 bands (a phantom extra band); page 3 has 1
    # question but 0 bands (a missing band). Globally that's 2 questions vs
    # 2 bands -- which would match under a whole-document count check, even
    # though neither page individually lines up. That's exactly the "totals
    # cancel out" scenario this per-page check exists to prevent.
    page_bands = [
        (2, image_a, (5, 8)),
        (2, image_a, (9, 12)),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is None
    assert parsed_questions[1]["question_image"] is None


def test_attach_question_images_ignores_bands_on_a_page_with_no_questions():
    parsed_questions = [
        {"question": "Q1", "choices": ["a", "b", "c", "d"], "header_line_index": 0},
    ]
    page_offsets = [(2, 0), (3, 10)]
    page_bands = [
        (2, Image.new("RGB", (100, 50)), (5, 8)),
        (3, Image.new("RGB", (100, 50)), (5, 8)),
    ]

    app.attach_question_images(parsed_questions, page_offsets, page_bands)

    assert parsed_questions[0]["question_image"] is not None


def test_page_number_for_line_index_returns_first_page_for_index_zero():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 0) == 2


def test_page_number_for_line_index_returns_correct_page_within_range():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 7) == 4


def test_page_number_for_line_index_returns_correct_page_at_exact_boundary():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 6) == 4


def test_page_number_for_line_index_returns_last_page_beyond_all_offsets():
    page_offsets = [(2, 0), (4, 6), (5, 10)]
    assert app.page_number_for_line_index(page_offsets, 15) == 5


def test_build_page_offsets_matches_worked_example_with_no_trailing_newlines():
    kept_pages = [
        (2, "l1\nl2\nl3\nl4\nl5"),
        (4, "m1\nm2\nm3"),
        (5, "n1\nn2\nn3\nn4"),
    ]
    assert app.build_page_offsets(kept_pages) == [(2, 0), (4, 6), (5, 10)]


def test_build_page_offsets_handles_trailing_newline_in_a_page():
    kept_pages = [
        (2, "a\nb\n"),
        (3, "c\nd"),
    ]
    assert app.build_page_offsets(kept_pages) == [(2, 0), (3, 4)]


def test_build_page_offsets_single_page_has_offset_zero():
    kept_pages = [(2, "a\nb\nc")]
    assert app.build_page_offsets(kept_pages) == [(2, 0)]


def test_build_page_offsets_handles_single_line_pages():
    kept_pages = [(2, "solo"), (3, "next")]
    assert app.build_page_offsets(kept_pages) == [(2, 0), (3, 2)]


def test_build_page_offsets_handles_a_page_that_stripped_to_empty():
    kept_pages = [(2, "l1\nl2"), (3, ""), (4, "m1\nm2")]
    assert app.build_page_offsets(kept_pages) == [(2, 0), (3, 3), (4, 5)]
