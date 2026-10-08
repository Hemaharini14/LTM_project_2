import io

from pypdf import PdfReader
from pypdf.errors import PyPdfError


class ResumeParseError(Exception):
    """A résumé file that could not be read as a PDF at all — corrupted,
    password-protected, or not actually a PDF. Distinct from simply
    finding no text (a scanned PDF with no text layer), which the
    caller already handles by checking for an empty result."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))

        if reader.is_encrypted:
            raise ResumeParseError(
                "This PDF is password-protected. Remove the password "
                "and upload it again."
            )

        pages = [
            page.extract_text() or ""
            for page in reader.pages
        ]

    except ResumeParseError:
        raise
    except PyPdfError:
        raise ResumeParseError(
            "That file couldn't be read as a PDF — it may be corrupted, "
            "or not actually a PDF."
        )

    return "\n".join(pages).strip()
