from test_ocr import _group_words_into_lines


def test_group_words_into_lines_joins_words_and_computes_bounding_box():
    data = {
        "text": ["Hello", "world", "", "Second", "line"],
        "left": [10, 60, 0, 10, 70],
        "top": [100, 102, 0, 150, 148],
        "width": [40, 50, 0, 45, 40],
        "height": [20, 18, 0, 22, 20],
        "block_num": [1, 1, 1, 1, 1],
        "par_num": [1, 1, 1, 1, 1],
        "line_num": [1, 1, 1, 2, 2],
    }

    result = _group_words_into_lines(data)

    assert result == [
        ("Hello world", 100, 120),
        ("Second line", 148, 172),
    ]


def test_group_words_into_lines_skips_empty_words():
    data = {
        "text": ["", "Real"],
        "left": [0, 5],
        "top": [0, 10],
        "width": [0, 30],
        "height": [0, 15],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 1],
    }

    assert _group_words_into_lines(data) == [("Real", 10, 25)]
