from pdf2image import convert_from_path
import pytesseract

TESSERACT_CMD = r"C:\Users\hilad\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def run_ocr(pdf_path, page_number):
    pages = convert_from_path(
        pdf_path,
        first_page=page_number,
        last_page=page_number,
        poppler_path=POPPLER_PATH,
    )
    return pytesseract.image_to_string(pages[0], lang="heb+eng")


if __name__ == "__main__":
    text = run_ocr("sample_exams/data_science_test_havana.pdf", page_number=3)

    with open("ocr_output.txt", "w", encoding="utf-8") as f:
        f.write(text)
