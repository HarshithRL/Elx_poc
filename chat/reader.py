import tempfile
import uuid
from io import BytesIO

import pandas as pd
import PyPDF2
import pytesseract
from django.conf import settings
from pdf2image import convert_from_bytes
from PyPDF2 import PdfReader, PdfWriter
from tabula.io import read_pdf
from vectordb import vectordb

from cairnaibot.utils import Utilities


class ReaderUtils:
    def __init__(self):
        pass

    def convert_dataframe_to_strings(self, df):
        """Convert DataFrame rows to formatted strings."""
        rows_as_string = []
        for index, row in df.iterrows():
            row_components = []
            for col in df.columns:
                value = row[col]
                col_name = col if "Unnamed" not in col else ""
                if pd.notna(value):
                    row_components.append(f"{col_name}: {value}")
            row_string = ", ".join(row_components).strip(", ")
            row_string = f'"{row_string}"'
            rows_as_string.append(row_string)
        return " ".join(rows_as_string)

    def parse_pdf_tables(self, page_binary):
        """Extract tables from the given PDF binary data."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as temp_pdf:
            temp_pdf.write(page_binary)  # Write the PDF content to a temporary file
            temp_pdf_path = temp_pdf.name

        # Extract tables from the temporary PDF file
        tables = read_pdf(temp_pdf_path, pages="1", multiple_tables=True, stream=True)
        temp_table_string = ""

        # Use convert_dataframe_to_strings to format each table
        for table in tables:
            temp_table_string += self.convert_dataframe_to_strings(table) + " "

        return temp_table_string.strip()

    def process_document_without_ocr(self, content, file_name):
        """Process the PDF document without OCR and extract text and tables page by page."""
        try:
            pdf_reader = PdfReader(BytesIO(content))
            pages_content = []

            for page_num, page in enumerate(pdf_reader.pages, start=1):
                # Extract text from the page
                page_text = page.extract_text() or ""

                # Create a temporary PDF containing only the current page
                with tempfile.NamedTemporaryFile(
                    suffix=".pdf", delete=False
                ) as temp_pdf:
                    writer = PdfWriter()  # Create a PDF writer object
                    writer.add_page(page)  # Add the current page to the writer
                    writer.write(temp_pdf)  # Write the page to the temporary PDF file

                    temp_pdf_path = temp_pdf.name  # Get the path of the temporary PDF

                # Read the binary content of the temporary PDF for the current page
                with open(temp_pdf_path, "rb") as temp_pdf_read:
                    page_binary = temp_pdf_read.read()

                # Extract tables from the temporary PDF containing only the current page
                tables_content = self.parse_pdf_tables(page_binary)

                # Construct the page data dictionary
                page_data = {
                    "page_number": page_num,
                    "content": page_text.strip().replace("\n", " "),
                    "tables_content": tables_content,
                    "file_name": file_name,
                }
                if len(page_data["content"]) > 1:
                    pages_content.append(page_data)  # Append page data to the list

            return pages_content
        except Exception as e:
            print(f"Error processing document without OCR: {e}")
            return []

    # -----NEW----#
    def process_document_with_ocr(self, content, file_name):
        # Configure Tesseract path based on the environment
        try:
            if settings.DEBUG:
                pytesseract.pytesseract.tesseract_cmd = (
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                )
                images = convert_from_bytes(content)
            else:
                images = convert_from_bytes(content, poppler_path="/usr/bin/")

            pages_content = []
            for page_num, image in enumerate(images, start=1):
                page_text = pytesseract.image_to_string(image)
                page_data = {
                    "page_number": page_num,
                    "content": page_text.strip(),
                    "tables_content": "",
                    "file_name": file_name,
                }
                pages_content.append(page_data)

            return pages_content
        except:
            return []


class DocumentReader:
    def __init__(self, content: bytes, user_id, session_id, is_cloud=False):
        self.chat_history = []
        self.utils = Utilities
        self.text = self.extract_text(content)
        self.chunks = self.chunk_text(self.text)
        if not is_cloud:
            self.retriver = self.vectorize_chunks(self.chunks, user_id, session_id)

    def extract_text(self, content: bytes) -> str:
        try:
            pdf_reader = PyPDF2.PdfReader(BytesIO(content))
            text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
            if text.strip():
                return text.strip().replace("\n", " ")
        except Exception as e:
            print(e)
            pass  # Fall back to OCR if text extraction fails

        try:
            if settings.DEBUG:
                pytesseract.pytesseract.tesseract_cmd = (
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
                )
                images = convert_from_bytes(content)
            else:
                images = convert_from_bytes(content, poppler_path="/usr/bin/")
            return "".join(
                pytesseract.image_to_string(image) for image in images
            ).strip()
        except Exception as e:
            raise ValueError(f"Error extracting text: {e}")
