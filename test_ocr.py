from pdf2image import convert_from_path
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Users\hilad\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

pages = convert_from_path(
    "sample_exams/data_science_test_havana.pdf",
    first_page=3,
    last_page=3,
    poppler_path=r"C:\poppler\poppler-26.02.0\Library\bin",
)

text = pytesseract.image_to_string(pages[0], lang="heb+eng")

with open("ocr_output.txt", "w", encoding="utf-8") as f:
    f.write(text)
