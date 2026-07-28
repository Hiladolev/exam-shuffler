import base64
import html

import streamlit as st
from pdf2image import pdfinfo_from_path

from test_ocr import (
    run_ocr_all_pages,
    run_line_extraction_all_pages,
    crop_question_image,
    MIN_PAGE_TEXT_LENGTH,
    POPPLER_PATH,
)
from parser import (
    strip_version_lines,
    parse_ocr_text,
    find_split_suggestions,
    find_question_crop_bounds,
)
from shuffler_core import shuffle_questions, split_choices, remove_choice

UPLOAD_PATH = "uploaded_exam.pdf"
MIN_CHOICES = 4


def page_number_for_line_index(page_offsets, line_index):
    result_page_number = page_offsets[0][0]
    for page_number, start_index in page_offsets:
        if start_index > line_index:
            break
        result_page_number = page_number
    return result_page_number


def attach_question_images(parsed_questions, page_offsets, page_bands):
    questions_by_page = {}
    for question in parsed_questions:
        page_number = page_number_for_line_index(page_offsets, question["header_line_index"])
        questions_by_page.setdefault(page_number, []).append(question)

    bands_by_page = {}
    for page_number, image, band in page_bands:
        bands_by_page.setdefault(page_number, []).append((image, band))

    for page_number, page_questions in questions_by_page.items():
        bands = bands_by_page.get(page_number, [])
        # Only attach images if this page's band count exactly matches its
        # question count -- otherwise we can't be sure a given band lines up
        # with the right question, so this page's questions fall back to None.
        if len(bands) == len(page_questions):
            for question, (image, band) in zip(page_questions, bands):
                question["question_image"] = (
                    crop_question_image(image, band[0], band[1]) if band is not None else None
                )
        else:
            for question in page_questions:
                question["question_image"] = None


def run_pipeline(pdf_path):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=POPPLER_PATH)["Pages"]
    total_to_process = total_pages - 1

    progress = st.progress(0)
    status = st.empty()
    raw_texts = []
    page_offsets = []
    next_line_index = 0
    for i, (page_number, text) in enumerate(run_ocr_all_pages(pdf_path), start=1):
        if len(text.strip()) >= MIN_PAGE_TEXT_LENGTH:
            stripped_text = strip_version_lines(text)
            page_offsets.append((page_number, next_line_index))
            next_line_index += len(stripped_text.splitlines()) + 1
            raw_texts.append(stripped_text)
        progress.progress(i / total_to_process)
        status.text(f"Processing page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    raw_text = "\n\n".join(raw_texts)
    parsed_questions = parse_ocr_text(raw_text)

    progress = st.progress(0)
    status = st.empty()
    page_bands = []
    for i, (page_number, image, lines) in enumerate(run_line_extraction_all_pages(pdf_path), start=1):
        page_text_length = sum(len(text) for text, _, _ in lines)
        if page_text_length >= MIN_PAGE_TEXT_LENGTH:
            for band in find_question_crop_bounds(lines):
                page_bands.append((page_number, image, band))
        progress.progress(i / total_to_process)
        status.text(f"Extracting question images: page {i} of {total_to_process}")
    progress.empty()
    status.empty()

    attach_question_images(parsed_questions, page_offsets, page_bands)

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            # Flagged/needs-review questions always show plain OCR'd text in this
            # phase (Phase 2 will extend cropping to them) -- clear any image a
            # header/choice band happened to produce so it can never leak through.
            q["question_image"] = None
            needs_review.append(q)
        else:
            clean_questions.append(q)

    shuffled_questions = shuffle_questions(clean_questions)
    return shuffled_questions, needs_review


def _format_question_lines(questions):
    lines = []
    for i, q in enumerate(questions, start=1):
        lines.append(f"--- Question {i} ---")
        lines.append(f"Question: {q['question']}")
        lines.append("Choices:")
        for j, choice in enumerate(q["choices"]):
            lines.append(f"  {j}: {choice}")
        lines.append(f"Correct answer index: {q['correct_index']}")
        lines.append("")
    return lines


def build_final_content(edited_clean, edited_review_cards):
    lines = _format_question_lines(edited_clean)

    if edited_review_cards:
        lines.append("=== Reviewed (previously flagged) Questions ===")
        lines.extend(_format_question_lines(edited_review_cards))

    return "\n".join(lines)


def _render_question_html(q, index):
    lines = [f"<h3>Question {index}</h3>"]
    if q.get("question_image"):
        b64 = base64.b64encode(q["question_image"]).decode("ascii")
        lines.append(f'<img src="data:image/png;base64,{b64}">')
    else:
        lines.append(f"<p>{html.escape(q['question'])}</p>")
    lines.append("<ul>")
    for j, choice in enumerate(q["choices"]):
        lines.append(f"<li>{j}: {html.escape(choice)}</li>")
    lines.append("</ul>")
    lines.append(f"<p>Correct answer index: {q['correct_index']}</p>")
    return "\n".join(lines)


def _render_review_card_html(q, index):
    lines = [
        f"<h3>Flagged Question {index}</h3>",
        f"<p>{html.escape(q['question'])}</p>",
        "<ul>",
    ]
    for j, choice in enumerate(q["choices"]):
        lines.append(f"<li>{j}: {html.escape(choice)}</li>")
    lines.append("</ul>")
    lines.append(f"<p>Correct answer index: {q['correct_index']}</p>")
    return "\n".join(lines)


def build_final_html(edited_clean, edited_review_cards):
    body_parts = [_render_question_html(q, i) for i, q in enumerate(edited_clean, start=1)]

    if edited_review_cards:
        body_parts.append("<h2>Reviewed (previously flagged) Questions</h2>")
        body_parts.extend(
            _render_review_card_html(q, i) for i, q in enumerate(edited_review_cards, start=1)
        )

    body = "\n".join(body_parts)
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="utf-8">
<style>
body {{ direction: rtl; font-family: sans-serif; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def render_question_editor(state, key_prefix):
    # version_key forces a fresh widget identity (new key) for choice inputs,
    # remove buttons, and the correct-answer radio whenever a choice is removed.
    # Without it, the browser can keep showing a widget's old value/selection
    # after its underlying index shifts, even though the Python-side value is
    # already correct -- AppTest's `.value` assertions can't catch that class
    # of bug since they only exercise the backend, not the real frontend.
    # Add doesn't need a bump: it only appends, so existing indices/keys stay
    # valid. The question-text key also doesn't need one: nothing ever
    # recomputes state["question"] the way Remove/Add recompute correct_index.
    version_key = f"{key_prefix}_version"
    version = st.session_state.setdefault(version_key, 0)

    question_image = state.get("question_image")
    if question_image:
        st.image(question_image)
        question_text = state["question"]
    else:
        question_text = st.text_area(
            "Question text", value=state["question"], key=f"{key_prefix}_question"
        )

    choices = []
    remove_index = None
    for j, choice in enumerate(state["choices"]):
        col1, col2 = st.columns([5, 1])
        with col1:
            choice_text = st.text_input(
                f"Choice {j}", value=choice, key=f"{key_prefix}_v{version}_choice_{j}"
            )
        with col2:
            if st.button(
                "Remove",
                key=f"{key_prefix}_v{version}_remove_{j}",
                disabled=len(state["choices"]) <= MIN_CHOICES,
            ):
                remove_index = j
        choices.append(choice_text)

    if remove_index is not None:
        state["choices"] = remove_choice(choices, remove_index, MIN_CHOICES)
        current_correct = st.session_state.get(
            f"{key_prefix}_v{version}_correct_index", state.get("correct_index", 0)
        )
        if remove_index < current_correct:
            state["correct_index"] = current_correct - 1
        elif remove_index == current_correct:
            state["correct_index"] = 0
        else:
            state["correct_index"] = current_correct
        st.session_state[version_key] = version + 1
        st.rerun()

    if st.button("Add answer choice", key=f"{key_prefix}_add_choice"):
        state["choices"].append("")
        state["correct_index"] = st.session_state.get(
            f"{key_prefix}_v{version}_correct_index", state.get("correct_index", 0)
        )
        st.rerun()

    correct_index = st.radio(
        "Correct answer",
        options=range(len(choices)),
        format_func=lambda idx: f"{idx}: {choices[idx]}",
        index=state.get("correct_index", 0),
        key=f"{key_prefix}_v{version}_correct_index",
    )

    return {
        "question": question_text,
        "choices": choices,
        "correct_index": correct_index,
        "question_image": question_image,
    }


st.title("Exam Shuffler")

st.markdown(
    """
    <style>
    textarea[aria-label="Question text"] {
        direction: rtl;
    }
    input[aria-label^="Choice "] {
        direction: rtl;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader("Upload exam PDF", type="pdf")

if uploaded_file is not None:
    if st.button("Process"):
        with open(UPLOAD_PATH, "wb") as f:
            f.write(uploaded_file.getbuffer())

        shuffled_questions, needs_review = run_pipeline(UPLOAD_PATH)
        st.session_state["shuffled_questions"] = shuffled_questions
        st.session_state["needs_review"] = needs_review
        st.session_state["processed"] = True

if st.session_state.get("processed"):
    st.warning("OCR is not perfect - please review all questions carefully before using this in an actual exam.")

    st.header("Questions")
    edited_clean = []
    for i, q in enumerate(st.session_state["shuffled_questions"]):
        st.subheader(f"Question {i + 1}")
        edited_clean.append(render_question_editor(q, key_prefix=f"clean_q_{i}"))

    st.header("Needs Review (flagged / merged questions)")
    edited_review_cards = []
    for i, q in enumerate(st.session_state["needs_review"]):
        split_key = f"review_split_result_{i}"

        if split_key not in st.session_state:
            st.subheader(f"Flagged Question {i + 1}")
            st.write(q["question"])
            for k, choice in enumerate(q["choices"]):
                st.write(f"{k}: {choice}")

            suggestions = find_split_suggestions(q["choices"])
            suggested_value = ", ".join(str(s) for s in suggestions)
            if suggestions:
                st.caption(
                    f"Detected {len(suggestions) + 1} parts "
                    f"(suggested split points: {suggested_value})"
                )

            split_input = st.text_input(
                "Enter split points as comma-separated choice indices (e.g. 4, 9)",
                value=suggested_value,
                key=f"review_split_input_{i}",
            )
            if st.button("Split question", key=f"review_split_button_{i}"):
                tokens = [t.strip() for t in split_input.split(",") if t.strip()]
                try:
                    split_points = sorted(set(int(t) for t in tokens))
                except ValueError:
                    split_points = None

                if split_points is None:
                    st.error("Enter whole numbers separated by commas (e.g. 4, 9).")
                elif not split_points:
                    st.error("Enter at least one split point.")
                elif any(not (0 < p < len(q["choices"])) for p in split_points):
                    st.error(f"Split points must be between 1 and {len(q['choices']) - 1}.")
                else:
                    st.session_state[split_key] = shuffle_questions(
                        split_choices(q["question"], q["choices"], split_points)
                    )
                    st.rerun()
        else:
            split_cards = st.session_state[split_key]
            for c, card in enumerate(split_cards):
                st.subheader(f"Flagged Question {i + 1} - Part {c + 1}")
                edited_review_cards.append(
                    render_question_editor(card, key_prefix=f"review_{i}_part{c}")
                )

    final_html = build_final_html(edited_clean, edited_review_cards)
    st.download_button(
        "Generate Final File",
        data=final_html.encode("utf-8"),
        file_name="final_exam.html",
        mime="text/html",
    )
