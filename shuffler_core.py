import random


def split_choices(question, choices, split_points):
    n = len(choices)
    if any(not (0 < p < n) for p in split_points):
        raise ValueError(f"split points must be between 1 and {n - 1}")
    if list(split_points) != sorted(set(split_points)):
        raise ValueError("split points must be sorted, unique, and strictly increasing")

    boundaries = [0] + list(split_points) + [n]
    parts = []
    for idx in range(len(boundaries) - 1):
        start, end = boundaries[idx], boundaries[idx + 1]
        parts.append({
            "question": question if idx == 0 else "",
            "choices": choices[start:end],
        })
    return parts


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
