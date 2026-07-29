import re

from shuffler_core import shuffle_questions

HEADER_PATTERN = re.compile(r"שאלה\s*מס['’].*\d")
POINTS_PATTERN = re.compile(r"\(\s*\d+\s*נק['’]\s*\)")
CHOICE_PATTERN = re.compile(r"^\s*([אבגדה])\.\s*(.*)$")
VERSION_PATTERN = re.compile(r"מספר\s*גרסה\s*:\s*\d+")
PAGE_NUMBER_PATTERN = re.compile(r"מספר\s*עמוד\s*:?\s*\d+")
BIDI_MARK_PATTERN = re.compile(r"[‎‏‪-‮⁦-⁩]")
MIN_CROP_BAND_HEIGHT = 10
EMBEDDED_HEADER_TOKEN = "שאלה"
DIGIT_PATTERN = re.compile(r"\d")


def is_header_line(line):
    return bool(HEADER_PATTERN.search(line)) or bool(POINTS_PATTERN.search(line))


def is_probable_embedded_header(line):
    return EMBEDDED_HEADER_TOKEN in line and bool(DIGIT_PATTERN.search(line))


def find_header_line_indices(lines):
    return [i for i, (text, _, _) in enumerate(lines) if is_header_line(text)]


def find_split_suggestions(choices):
    suggestions = set()
    for j, choice in enumerate(choices):
        if HEADER_PATTERN.search(choice):
            suggestions.add(j + 1)
    return sorted(suggestions)


def find_question_crop_bounds(lines):
    bounds = []
    for i, (text, _, header_bottom) in enumerate(lines):
        if not is_header_line(text):
            continue

        band = None
        for choice_text, choice_top, _ in lines[i + 1:]:
            if is_header_line(choice_text):
                break
            if CHOICE_PATTERN.match(choice_text):
                if choice_top - header_bottom >= MIN_CROP_BAND_HEIGHT:
                    band = (header_bottom, choice_top)
                break
        bounds.append(band)

    return bounds


def find_choice_line_bounds(lines, header_index):
    bounds = []
    for text, top, bottom in lines[header_index + 1:]:
        if is_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            bounds.append((top, bottom))
    return bounds


def find_embedded_header_bounds(lines, header_index):
    bounds = {}
    choice_count = 0
    for text, top, bottom in lines[header_index + 1:]:
        if is_header_line(text):
            break
        if CHOICE_PATTERN.match(text):
            choice_count += 1
        elif choice_count > 0 and is_probable_embedded_header(text):
            bounds.setdefault(choice_count, (top, bottom))
    return bounds


def strip_bidi_marks(text):
    return BIDI_MARK_PATTERN.sub("", text)


def strip_version_lines(text):
    lines = text.splitlines()
    result_lines = []
    for line in lines:
        if VERSION_PATTERN.search(line):
            continue
        result_lines.append(PAGE_NUMBER_PATTERN.sub("", line))
    return "\n".join(result_lines)


def parse_ocr_text(text):
    text = strip_bidi_marks(text)
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
            questions.append({
                "question": question_text,
                "choices": choices,
                "header_line_index": start,
            })

    return questions


if __name__ == "__main__":
    with open("ocr_output.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    raw_text = strip_version_lines(raw_text)

    parsed_questions = parse_ocr_text(raw_text)

    clean_questions = []
    needs_review = []

    for i, q in enumerate(parsed_questions, start=1):
        if len(q["choices"]) == 0:
            print(f"WARNING: Question {i} has 0 choices - likely a parsing failure, needs manual review")
            needs_review.append(q)
        elif len(q["choices"]) > 5:
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
