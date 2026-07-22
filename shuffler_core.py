import random


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
