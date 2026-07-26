import streamlit as st

from test_ocr import run_ocr
from parser import strip_version_lines, parse_ocr_text, find_split_suggestions
from shuffler_core import shuffle_questions, split_choices

PAGE_NUMBER = 3
UPLOAD_PATH = "uploaded_exam.pdf"


def run_pipeline(pdf_path, page_number):
    raw_text = run_ocr(pdf_path, page_number)
    raw_text = strip_version_lines(raw_text)
    parsed_questions = parse_ocr_text(raw_text)

    clean_questions = []
    needs_review = []
    for q in parsed_questions:
        if len(q["choices"]) == 0 or len(q["choices"]) > 5:
            needs_review.append(q)
        else:
            clean_questions.append(q)

    shuffled_questions = shuffle_questions(clean_questions)
    return shuffled_questions, needs_review


def build_final_content(edited_clean, edited_review_cards):
    lines = []
    for i, q in enumerate(edited_clean, start=1):
        lines.append(f"--- Question {i} ---")
        lines.append(f"Question: {q['question']}")
        lines.append("Choices:")
        for j, choice in enumerate(q["choices"]):
            lines.append(f"  {j}: {choice}")
        lines.append(f"Correct answer index: {q['correct_index']}")
        lines.append("")

    if edited_review_cards:
        shuffled_review_cards = shuffle_questions(edited_review_cards)
        lines.append("=== Reviewed (previously flagged) Questions ===")
        for i, q in enumerate(shuffled_review_cards, start=1):
            lines.append(f"--- Question {i} ---")
            lines.append(f"Question: {q['question']}")
            lines.append("Choices:")
            for j, choice in enumerate(q["choices"]):
                lines.append(f"  {j}: {choice}")
            lines.append(f"Correct answer index: {q['correct_index']}")
            lines.append("")

    return "\n".join(lines)


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

        shuffled_questions, needs_review = run_pipeline(UPLOAD_PATH, PAGE_NUMBER)
        st.session_state["shuffled_questions"] = shuffled_questions
        st.session_state["needs_review"] = needs_review
        st.session_state["processed"] = True

if st.session_state.get("processed"):
    st.warning("OCR is not perfect - please review all questions carefully before using this in an actual exam.")

    st.header("Questions")
    edited_clean = []
    for i, q in enumerate(st.session_state["shuffled_questions"]):
        st.subheader(f"Question {i + 1}")
        question_text = st.text_area(
            "Question text", value=q["question"], key=f"clean_q_{i}"
        )
        choices = []
        for j, choice in enumerate(q["choices"]):
            choice_text = st.text_input(
                f"Choice {j}", value=choice, key=f"clean_q_{i}_choice_{j}"
            )
            choices.append(choice_text)
        st.caption(f"Correct answer index: {q['correct_index']}")
        edited_clean.append(
            {
                "question": question_text,
                "choices": choices,
                "correct_index": q["correct_index"],
            }
        )

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
                    st.session_state[split_key] = split_choices(
                        q["question"], q["choices"], split_points
                    )
                    st.rerun()
        else:
            split_cards = st.session_state[split_key]
            for c, card in enumerate(split_cards):
                st.subheader(f"Flagged Question {i + 1} - Part {c + 1}")
                question_text = st.text_area(
                    "Question text",
                    value=card["question"],
                    key=f"review_{i}_part{c}_question",
                )
                choices = []
                for j, choice in enumerate(card["choices"]):
                    choice_text = st.text_input(
                        f"Choice {j}",
                        value=choice,
                        key=f"review_{i}_part{c}_choice_{j}",
                    )
                    choices.append(choice_text)
                edited_review_cards.append({"question": question_text, "choices": choices})

    final_content = build_final_content(edited_clean, edited_review_cards)
    st.download_button(
        "Generate Final File",
        data=final_content.encode("utf-8"),
        file_name="final_exam.txt",
        mime="text/plain",
    )
