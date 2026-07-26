from pdf2image import convert_from_path, pdfinfo_from_path
import pytesseract

TESSERACT_CMD = r"C:\Users\hilad\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
POPPLER_PATH = r"C:\poppler\poppler-26.02.0\Library\bin"
MIN_PAGE_TEXT_LENGTH = 10

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def run_ocr(pdf_path, page_number):
    pages = convert_from_path(
        pdf_path,
        first_page=page_number,
        last_page=page_number,
        poppler_path=POPPLER_PATH,
    )
    return pytesseract.image_to_string(pages[0], lang="heb+eng")


def run_ocr_all_pages(pdf_path, poppler_path=POPPLER_PATH):
    total_pages = pdfinfo_from_path(pdf_path, poppler_path=poppler_path)["Pages"]
    if total_pages < 2:
        return
    images = convert_from_path(
        pdf_path, first_page=2, last_page=total_pages, poppler_path=poppler_path
    )
    for page_number, image in zip(range(2, total_pages + 1), images):
        text = pytesseract.image_to_string(image, lang="heb+eng")
        yield page_number, text


if __name__ == "__main__":
    pdf_path = "sample_exams/data_science_test_havana.pdf"
    pages = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)

    page_texts = []
    for page_number, page in enumerate(pages, start=1):
        text = pytesseract.image_to_string(page, lang="heb+eng")
        if len(text.strip()) < MIN_PAGE_TEXT_LENGTH:
            continue
        page_texts.append(f"=== PAGE {page_number} ===\n{text}")

    with open("ocr_output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(page_texts))
