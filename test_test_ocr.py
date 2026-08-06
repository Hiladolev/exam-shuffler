import io
from unittest.mock import patch

from PIL import Image

import test_ocr
from test_ocr import _group_words_into_lines, crop_question_image


def test_group_words_into_lines_joins_words_in_right_to_left_order():
    data = {
        "text": ["World", "Hello", "", "Line", "Second"],
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
        ("Hello World", 100, 120),
        ("Second Line", 148, 172),
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


def test_crop_question_image_returns_png_bytes_for_band():
    image = Image.new("RGB", (200, 300), color="white")

    png_bytes = crop_question_image(image, top_px=100, bottom_px=150, padding=5)
    cropped = Image.open(io.BytesIO(png_bytes))

    assert cropped.format == "PNG"
    assert cropped.size == (200, 60)


def test_crop_question_image_clamps_padding_to_image_bounds():
    image = Image.new("RGB", (200, 300), color="white")

    png_bytes = crop_question_image(image, top_px=2, bottom_px=298, padding=10)
    cropped = Image.open(io.BytesIO(png_bytes))

    assert cropped.size == (200, 300)


def test_extract_line_boxes_forwards_config_to_image_to_data():
    image = Image.new("RGB", (10, 10), color="white")
    fake_data = {
        "text": ["Word"],
        "left": [0],
        "top": [0],
        "width": [10],
        "height": [10],
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
    }

    with patch("test_ocr.pytesseract.image_to_data", return_value=fake_data) as mock_image_to_data:
        test_ocr.extract_line_boxes(image, config="--psm 12")

    _, kwargs = mock_image_to_data.call_args
    assert kwargs["config"] == "--psm 12"


def test_extract_line_boxes_defaults_to_empty_config():
    image = Image.new("RGB", (10, 10), color="white")
    fake_data = {
        "text": [], "left": [], "top": [], "width": [], "height": [],
        "block_num": [], "par_num": [], "line_num": [],
    }

    with patch("test_ocr.pytesseract.image_to_data", return_value=fake_data) as mock_image_to_data:
        test_ocr.extract_line_boxes(image)

    _, kwargs = mock_image_to_data.call_args
    assert kwargs["config"] == ""
