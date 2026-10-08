"""
PDF text extraction.

A résumé upload is the one place this app runs an uploaded file through
a parsing library, so a corrupted, password-protected or non-PDF file
must fail with a clean message rather than an unhandled exception.
"""

import io

import pytest
from pypdf import PdfWriter

from src.resume_parser import ResumeParseError, extract_text_from_pdf


def blank_pdf_bytes(encrypt_with=None):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)

    if encrypt_with:
        writer.encrypt(encrypt_with)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_valid_pdf_with_no_text_returns_empty_string():
    """A scanned PDF with no text layer is not an error — the caller
    distinguishes "no text found" from "couldn't read the file"."""

    assert extract_text_from_pdf(blank_pdf_bytes()) == ""


def test_corrupted_file_raises_clean_error():
    """
    Regression: uploading anything that isn't a real PDF — corrupted,
    truncated, or a different file type renamed to .pdf — crashed with
    an unhandled pypdf.errors.PdfStreamError instead of a message a
    student could act on.
    """

    with pytest.raises(ResumeParseError):
        extract_text_from_pdf(b"this is not a real pdf file")


def test_encrypted_pdf_raises_specific_error():
    """
    Regression: a password-protected PDF crashed with an unhandled
    pypdf.errors.FileNotDecryptedError. This case gets its own message
    distinct from "corrupted", since the fix (remove the password) is
    different.
    """

    with pytest.raises(ResumeParseError, match="password-protected"):
        extract_text_from_pdf(blank_pdf_bytes(encrypt_with="secret123"))
