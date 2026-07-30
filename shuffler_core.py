import random


def split_choices(question, choices, split_points, question_image=None, choice_line_bounds=None, embedded_header_bounds=None):
    n = len(choices)
    if any(not (0 < p < n) for p in split_points):
        raise ValueError(f"split points must be between 1 and {n - 1}")
    if list(split_points) != sorted(set(split_points)):
        raise ValueError("split points must be sorted, unique, and strictly increasing")

    choice_line_bounds = choice_line_bounds or []
    embedded_header_bounds = embedded_header_bounds or {}

    boundaries = [0] + list(split_points) + [n]
    parts = []
    for idx in range(len(boundaries) - 1):
        start, end = boundaries[idx], boundaries[idx + 1]
        part = {
            "question": question if idx == 0 else "",
            "choices": choices[start:end],
        }
        if idx == 0:
            if question_image is not None:
                part["question_image"] = question_image
        elif start in embedded_header_bounds and start < len(choice_line_bounds):
            header_bottom = embedded_header_bounds[start][1]
            choice_top = choice_line_bounds[start][0]
            part["image_bounds"] = (header_bottom, choice_top)
        parts.append(part)
    return parts


def remove_choice(choices, index, min_choices=4):
    if len(choices) <= min_choices:
        raise ValueError(f"cannot remove choice: at least {min_choices} choices required")
    return choices[:index] + choices[index + 1:]


def shuffle_questions(questions):
    result = []
    for q in questions:
        indices = list(range(len(q["choices"])))
        random.shuffle(indices)
        shuffled_choices = [q["choices"][i] for i in indices]
        correct_index = indices.index(0)
        result.append({
            "question": q["question"],
            "choices": shuffled_choices,
            "correct_index": correct_index,
            "question_image": q.get("question_image"),
        })
    return result


if __name__ == "__main__":
    sample_questions = [
        {
            "question": "What is the capital of France?",
            "choices": ["Paris", "London"],
        },
        {
            "question": "Which of these is a primary color?",
            "choices": ["Red", "Green", "Purple"],
        },
        {
            "question": "Which planet is known as the Red Planet?",
            "choices": ["Mars", "Venus", "Jupiter", "Saturn"],
        },
    ]

    shuffled = shuffle_questions(sample_questions)

    for q in shuffled:
        print(q["question"])
        for i, choice in enumerate(q["choices"]):
            print(f"  {i}: {choice}")
        print(f"Correct answer index: {q['correct_index']}")
        print()
