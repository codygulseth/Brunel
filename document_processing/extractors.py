"""Deterministic text and PDF page extractors."""

from io import BytesIO

from pypdf import PdfReader

from .errors import DocumentExtractionError, EmptyDocumentError, UnsupportedFileTypeError
from .interfaces import PageExtractor
from .loaders import LoadedFile
from .models import DocumentPage, FileType


class PlainTextExtractor:
    def __init__(self, file_type: FileType) -> None:
        if file_type not in {FileType.TEXT, FileType.MARKDOWN}:
            raise ValueError("PlainTextExtractor supports only TXT and Markdown")
        self.file_type = file_type

    def extract(self, loaded: LoadedFile, document_id: str) -> tuple[DocumentPage, ...]:
        try:
            content = loaded.content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(f"{loaded.filename} is not valid UTF-8 text") from exc
        if not content.strip():
            raise EmptyDocumentError(f"No extractable text found in {loaded.filename}")
        return (DocumentPage(document_id=document_id, page_number=1, content=content),)


class PdfPageExtractor:
    file_type = FileType.PDF

    def extract(self, loaded: LoadedFile, document_id: str) -> tuple[DocumentPage, ...]:
        try:
            reader = PdfReader(BytesIO(loaded.content))
        except Exception as exc:
            raise DocumentExtractionError(f"Unable to open PDF: {loaded.filename}") from exc

        pages: list[DocumentPage] = []
        for page_number, pdf_page in enumerate(reader.pages, start=1):
            warnings: list[str] = []
            try:
                content = pdf_page.extract_text() or ""
            except Exception as exc:  # damaged pages should not abort the remaining document
                content = ""
                warnings.append(
                    f"Page {page_number}: text extraction failed ({type(exc).__name__})"
                )
            if not content.strip():
                warnings.append(
                    f"Page {page_number}: no extractable text; page may be empty or image-only"
                )
            pages.append(
                DocumentPage(
                    document_id=document_id,
                    page_number=page_number,
                    content=content,
                    extraction_warnings=tuple(warnings),
                )
            )
        return tuple(pages)


class ExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[FileType, PageExtractor] = {
            FileType.PDF: PdfPageExtractor(),
            FileType.TEXT: PlainTextExtractor(FileType.TEXT),
            FileType.MARKDOWN: PlainTextExtractor(FileType.MARKDOWN),
        }

    def get(self, file_type: FileType) -> PageExtractor:
        try:
            return self._extractors[file_type]
        except KeyError as exc:
            raise UnsupportedFileTypeError(f"No extractor registered for {file_type}") from exc
