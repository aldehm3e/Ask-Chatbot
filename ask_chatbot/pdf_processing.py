import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

import fitz


MAX_CHUNK_CHARS = 1800
CHUNK_OVERLAP_CHARS = 250
MIN_TEXT_CHARS_BEFORE_OCR = 40
OCR_DPI = 200
OCR_TIMEOUT_SECONDS = 120


@dataclass
class DocumentChunk:
    file_name: str
    page_number: int
    chunk_index: int
    text: str

    @property
    def source_key(self):
        return f"{self.file_name}:p{self.page_number}:c{self.chunk_index}"

    @property
    def display_name(self):
        return f"{self.file_name}, page {self.page_number}"


@dataclass
class PdfFileSummary:
    path: str
    file_name: str
    page_count: int = 0
    extracted_chars: int = 0
    ocr_chars: int = 0
    chunk_count: int = 0
    errors: list = field(default_factory=list)


@dataclass
class PdfExtractionResult:
    files: list = field(default_factory=list)
    chunks: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    ocr_requested: bool = False
    ocr_available: bool = False

    @property
    def total_pages(self):
        return sum(file_summary.page_count for file_summary in self.files)

    @property
    def total_chars(self):
        return sum(file_summary.extracted_chars for file_summary in self.files)

    @property
    def total_ocr_chars(self):
        return sum(file_summary.ocr_chars for file_summary in self.files)

    @property
    def file_count(self):
        return len(self.files)


def normalize_pdf_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text, max_chars=MAX_CHUNK_CHARS, overlap_chars=CHUNK_OVERLAP_CHARS):
    text = normalize_pdf_text(text)
    if not text:
        return []

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + max_chars, text_length)
        if end < text_length:
            lower_bound = start + int(max_chars * 0.55)
            candidates = [
                text.rfind("\n\n", lower_bound, end),
                text.rfind(". ", lower_bound, end),
                text.rfind(" ", lower_bound, end),
            ]
            split_at = max(candidates)
            if split_at > start:
                end = split_at + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        next_start = max(end - overlap_chars, start + 1)
        while next_start < text_length and text[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks


def chunks_for_page(file_name, page_number, text):
    return [
        DocumentChunk(file_name=file_name, page_number=page_number, chunk_index=index + 1, text=chunk)
        for index, chunk in enumerate(chunk_text(text))
    ]


def tesseract_available():
    return shutil.which("tesseract") is not None


def ocr_page_with_tesseract(page, language):
    with tempfile.TemporaryDirectory(prefix="ask_chatbot_ocr_") as temp_dir:
        image_path = os.path.join(temp_dir, "page.png")
        pixmap = page.get_pixmap(dpi=OCR_DPI, alpha=False)
        pixmap.save(image_path)

        result = subprocess.run(
            ["tesseract", image_path, "stdout", "-l", language, "--psm", "6"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=OCR_TIMEOUT_SECONDS,
        )

    if result.returncode != 0:
        message = result.stderr.strip() or "Tesseract failed without an error message."
        return "", message

    return normalize_pdf_text(result.stdout), None


def extract_pdf_file(pdf_path, use_ocr=False, ocr_language="eng", progress_callback=None, ocr_available=None):
    file_name = os.path.basename(pdf_path)
    summary = PdfFileSummary(path=pdf_path, file_name=file_name)
    chunks = []
    doc = None
    can_ocr = tesseract_available() if ocr_available is None else ocr_available

    try:
        doc = fitz.open(pdf_path)
        summary.page_count = doc.page_count

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            if progress_callback:
                progress_callback(file_name, page_number, summary.page_count)

            page_text = normalize_pdf_text(page.get_text("text"))
            should_ocr = use_ocr and can_ocr and len(page_text) < MIN_TEXT_CHARS_BEFORE_OCR

            if should_ocr:
                ocr_text, ocr_error = ocr_page_with_tesseract(page, ocr_language)
                if ocr_text:
                    page_text = ocr_text
                    summary.ocr_chars += len(ocr_text)
                elif ocr_error:
                    summary.errors.append(f"{file_name} page {page_number}: OCR failed: {ocr_error}")

            page_chunks = chunks_for_page(file_name, page_number, page_text)
            chunks.extend(page_chunks)
            summary.extracted_chars += len(page_text)

        summary.chunk_count = len(chunks)
    except subprocess.TimeoutExpired:
        summary.errors.append(f"Error reading {file_name}: OCR timed out.")
    except Exception as exc:
        summary.errors.append(f"Error reading {file_name}: {exc}")
    finally:
        if doc is not None:
            doc.close()

    return summary, chunks


def extract_pdf_files(file_paths, use_ocr=False, ocr_language="eng", progress_callback=None):
    can_ocr = tesseract_available()
    result = PdfExtractionResult(ocr_requested=use_ocr, ocr_available=can_ocr)

    if use_ocr and not can_ocr:
        result.errors.append("OCR was requested, but Tesseract was not found in PATH. Selectable text was still extracted.")

    for pdf_path in file_paths:
        summary, chunks = extract_pdf_file(
            pdf_path,
            use_ocr=use_ocr,
            ocr_language=ocr_language,
            progress_callback=progress_callback,
            ocr_available=can_ocr,
        )
        result.files.append(summary)
        result.chunks.extend(chunks)
        result.errors.extend(summary.errors)

    return result


def format_extracted_text(chunks):
    parts = []
    for chunk in chunks:
        header = f"File: {chunk.file_name} | Page: {chunk.page_number} | Chunk: {chunk.chunk_index}"
        parts.append(f"{header}\n{chunk.text}")
    return "\n\n".join(parts)
