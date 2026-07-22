import re

from shuffler_core import shuffle_questions

HEADER_PATTERN = re.compile(r"שאלה\s*מס['’].*\d")
POINTS_PATTERN = re.compile(r"\(\s*\d+\s*נק['’]\s*\)")
CHOICE_PATTERN = re.compile(r"^\s*([אבגדה])\.\s*(.*)$")
VERSION_PATTERN = re.compile(r"מספר\s*גרסה\s*:\s*\d+")
PAGE_NUMBER_PATTERN = re.compile(r"מספר\s*עמוד\s*:?\s*\d+")


def is_header_line(line):
    return bool(HEADER_PATTERN.search(line)) or bool(POINTS_PATTERN.search(line))


def strip_version_lines(text):
    lines = text.splitlines()
    return "\n".join(
        line
        for line in lines
        if not VERSION_PATTERN.search(line) and not PAGE_NUMBER_PATTERN.search(line)
    )


def parse_ocr_text(text):
    lines = text.splitlines()

    header_indices = [i for i, line in enumerate(lines) if is_header_line(line)]
    block_starts = [0] + header_indices
    block_bounds = [
        (start, block_starts[idx + 1] if idx + 1 < len(block_starts) else len(lines))
        for idx, start in enumerate(block_starts)
    ]

    questions = []
    for start, end in block_bounds:
        block_lines = lines[start:end]
        if start in header_indices:
            block_lines = block_lines[1:]

        question_lines = []
        choices = []
        in_choices = False

        for line in block_lines:
            stripped = line.strip()
            if not stripped:
                continue

            match = CHOICE_PATTERN.match(line)
            if match:
                in_choices = True
                choices.append(match.group(2).strip())
            elif in_choices:
                choices[-1] = (choices[-1] + " " + stripped).strip()
            else:
                question_lines.append(stripped)

        question_text = " ".join(question_lines).strip()
        if question_text or choices:
            questions.append({"question": question_text, "choices": choices})

    return questions


if __name__ == "__main__":
    with open("ocr_output.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    raw_text = strip_version_lines(raw_text)

    parsed_questions = parse_ocr_text(raw_text)

    clean_questions = []
    needs_review = []

    for i, q in enumerate(parsed_questions, start=1):
        if len(q["choices"]) > 5:
            print(f"WARNING: Question {i} has {len(q['choices'])} choices - likely merged with a following question, needs manual review")
            needs_review.append(q)
        else:
            clean_questions.append(q)

    with open("parser_output.txt", "w", encoding="utf-8") as f:
        for i, q in enumerate(parsed_questions, start=1):
            f.write(f"--- Question {i} ---\n")
            f.write(f"Question: {q['question']}\n")
            f.write("Choices:\n")
            for j, choice in enumerate(q["choices"]):
                f.write(f"  {j}: {choice}\n")
            f.write("\n")

    shuffled_questions = shuffle_questions(clean_questions)

    with open("shuffled_output.txt", "w", encoding="utf-8") as f:
        for i, q in enumerate(shuffled_questions, start=1):
            f.write(f"--- Question {i} ---\n")
            f.write(f"Question: {q['question']}\n")
            f.write("Choices:\n")
            for j, choice in enumerate(q["choices"]):
                f.write(f"  {j}: {choice}\n")
            f.write(f"Correct answer index: {q['correct_index']}\n")
            f.write("\n")

    with open("needs_review.txt", "w", encoding="utf-8") as f:
        for i, q in enumerate(needs_review, start=1):
            f.write(f"--- Question {i} ---\n")
            f.write(f"Question: {q['question']}\n")
            f.write("Choices:\n")
            for j, choice in enumerate(q["choices"]):
                f.write(f"  {j}: {choice}\n")
            f.write("\n")
