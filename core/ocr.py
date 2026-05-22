# core/ocr.py
# ─────────────────────────────────────────────────────────────
#  OCR support for image-based PDFs
#  Detects if a PDF has extractable text or is image-only,
#  then runs pytesseract on image-based pages
# ─────────────────────────────────────────────────────────────

import os
import logging

logger = logging.getLogger(__name__)

# Tesseract path — Windows default
TESSERACT_PATH = os.getenv(
    "TESSERACT_PATH",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# Poppler path — Windows default
POPPLER_PATH = os.getenv(
    "POPPLER_PATH",
    r"C:\poppler\Library\bin"
)


def _setup_tesseract():
    """Configure pytesseract path."""
    try:
        import pytesseract
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        return pytesseract
    except ImportError:
        logger.warning("[ocr] pytesseract not installed")
        return None


def is_image_based_pdf(pdf_path: str, sample_pages: int = 3) -> bool:
    """
    Check if a PDF is image-based by testing if pdfplumber
    extracts less than 50 chars per page on average.
    Image-based PDFs return almost no text from pdfplumber.
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_check = min(sample_pages, len(pdf.pages))
            total_chars    = 0
            for i in range(pages_to_check):
                text = pdf.pages[i].extract_text() or ""
                total_chars += len(text.strip())
            avg_chars = total_chars / max(pages_to_check, 1)
            is_image  = avg_chars < 50
            logger.info(
                f"[ocr] {os.path.basename(pdf_path)} — "
                f"avg {avg_chars:.0f} chars/page → "
                f"{'IMAGE-BASED' if is_image else 'text-based'}"
            )
            return is_image
    except Exception as e:
        logger.warning(f"[ocr] Could not check PDF type: {e}")
        return False


def extract_text_with_ocr(pdf_path: str, dpi: int = 200) -> str:
    """
    Convert PDF pages to images and run OCR on each.
    Returns combined text from all pages.
    DPI 200 is a good balance of speed vs accuracy.
    """
    pytesseract = _setup_tesseract()
    if not pytesseract:
        return ""

    try:
        from pdf2image import convert_from_path

        logger.info(f"[ocr] Converting {os.path.basename(pdf_path)} to images...")

        # Convert PDF to images
        kwargs = {"dpi": dpi}
        if os.path.exists(POPPLER_PATH):
            kwargs["poppler_path"] = POPPLER_PATH

        images = convert_from_path(pdf_path, **kwargs)
        logger.info(f"[ocr] {len(images)} pages to process")

        all_text = []
        for i, img in enumerate(images):
            # OCR config: assume single block of text, English + Malay
            config   = "--oem 3 --psm 6 -l eng"
            text     = pytesseract.image_to_string(img, config=config)
            cleaned  = text.strip()
            if cleaned:
                all_text.append(f"[Page {i+1}]\n{cleaned}")
                logger.info(
                    f"[ocr] Page {i+1}: {len(cleaned)} chars extracted"
                )
            else:
                logger.info(f"[ocr] Page {i+1}: no text found")

        full_text = "\n\n".join(all_text)
        logger.info(
            f"[ocr] Done — {len(full_text)} total chars from "
            f"{len(images)} pages"
        )
        return full_text

    except Exception as e:
        logger.error(f"[ocr] OCR failed for {pdf_path}: {e}")
        return ""


def extract_text_smart(pdf_path: str) -> str:
    """
    Smart extraction — tries pdfplumber first (fast),
    falls back to OCR if the PDF is image-based.
    Returns the best available text.
    """
    try:
        import pdfplumber

        # Try text extraction first
        with pdfplumber.open(pdf_path) as pdf:
            pages_text = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(f"[Page {i+1}]\n{text.strip()}")

            combined = "\n\n".join(pages_text)

            # If we got enough text, use it
            if len(combined) > 200:
                logger.info(
                    f"[ocr] {os.path.basename(pdf_path)} — "
                    f"text extraction ok ({len(combined)} chars)"
                )
                return combined

        # Not enough text — try OCR
        logger.info(
            f"[ocr] {os.path.basename(pdf_path)} — "
            f"switching to OCR mode"
        )
        return extract_text_with_ocr(pdf_path)

    except Exception as e:
        logger.error(f"[ocr] Smart extraction failed: {e}")
        return extract_text_with_ocr(pdf_path)


if __name__ == "__main__":
    # Quick test — pass a PDF path as argument
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python -m core.ocr path/to/file.pdf")
        sys.exit(1)

    pdf = sys.argv[1]
    print(f"\nTesting: {pdf}")
    print(f"Image-based: {is_image_based_pdf(pdf)}")
    print("\nExtracted text (first 500 chars):")
    text = extract_text_smart(pdf)
    print(text[:500] if text else "No text extracted")