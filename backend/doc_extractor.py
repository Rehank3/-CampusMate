"""
doc_extractor.py
================
Extract text from uploaded files (PDF, DOCX, images) and heuristically
parse assignment details (title, subject, deadline, priority).

Dependencies (install if needed):
    pip install pymupdf python-docx pytesseract pillow
"""

from __future__ import annotations

import io
import re
from datetime import datetime, date
from typing import Optional

# ── Extraction helpers ─────────────────────────────────────────────────────────

SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/jpg",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE_MB = 10


def _extract_pdf(data: bytes) -> str:
    """Extract plain text from a PDF using PyMuPDF."""
    try:
        import pymupdf  # preferred API (pymupdf >= 1.24)

        doc = pymupdf.open(stream=data, filetype="pdf")
        texts = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(texts)
    except ImportError:
        return "[PDF extraction unavailable: pymupdf not installed]"
    except Exception as exc:
        return f"[PDF extraction error: {exc}]"


def _extract_docx(data: bytes) -> str:
    """Extract plain text from a .docx file using python-docx."""
    try:
        import docx

        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        return "[DOCX extraction unavailable: python-docx not installed]"
    except Exception as exc:
        return f"[DOCX extraction error: {exc}]"


def _extract_image(data: bytes) -> str:
    """Extract text from an image using pytesseract (if available), else Pillow metadata."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img)
        return text if text.strip() else "[No readable text found in image]"
    except ImportError:
        # pytesseract or tesseract binary not available — return helpful message
        return (
            "[Image OCR unavailable: pytesseract/tesseract is not installed on this system.\n"
            "Please type the assignment details manually in the form below.]"
        )
    except Exception as exc:
        return f"[Image extraction error: {exc}]"


def extract_text(filename: str, data: bytes) -> tuple[str, Optional[str]]:
    """
    Extract text from the given file bytes.

    Returns:
        (text, error_message) — error_message is None on success.
    """
    fname = filename.lower()
    size_mb = len(data) / (1024 * 1024)

    if size_mb > MAX_FILE_SIZE_MB:
        return "", f"File is too large ({size_mb:.1f} MB). Maximum allowed size is {MAX_FILE_SIZE_MB} MB."

    if fname.endswith(".pdf"):
        return _extract_pdf(data), None
    elif fname.endswith(".docx"):
        return _extract_docx(data), None
    elif any(fname.endswith(ext) for ext in (".png", ".jpg", ".jpeg")):
        return _extract_image(data), None
    else:
        ext = fname.rsplit(".", 1)[-1] if "." in fname else "unknown"
        return "", f"Unsupported file type: .{ext}. Supported types: PDF, DOCX, PNG, JPG."


# ── Assignment field parsers ──────────────────────────────────────────────────

# Common keywords that precede a title/subject
_TITLE_PATTERNS = [
    r"(?:assignment|task|project|lab|homework|hw|title)[:\s]+(.{5,120})",
    r"^([A-Z][^\n]{10,100})$",  # capitalised standalone line ≥ 10 chars
]

_SUBJECT_PATTERNS = [
    r"(?:subject|course|module|class|department)[:\s]+(.{3,80})",
    r"(?:course\s*code|code)[:\s]+([A-Z]{2,6}\s*\d{3,4})",
]

_DEADLINE_PATTERNS = [
    # ISO  2024-12-31
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
    # DD Month YYYY / DD Mon YYYY
    r"\b(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b",
    # Month DD, YYYY
    r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    # MM/DD/YYYY or DD/MM/YYYY
    r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
    # "due date / submission date / deadline :" followed by a date
    r"(?:due|deadline|submission|submit\s+by)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
]

_PRIORITY_KEYWORDS = {
    "High": ["urgent", "high priority", "critical", "important", "asap", "immediately"],
    "Low": ["low priority", "optional", "whenever possible", "no rush"],
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _try_parse_date(raw: str) -> Optional[str]:
    """
    Try multiple date formats and return an ISO date string (YYYY-MM-DD),
    or None if unparseable.
    """
    fmts = [
        "%Y-%m-%d", "%Y/%m/%d",
        "%d %B %Y", "%d %b %Y",
        "%B %d %Y", "%B %d, %Y",
        "%b %d %Y", "%b %d, %Y",
        "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%m-%d-%Y",
    ]
    raw = raw.strip().replace(",", "")
    for fmt in fmts:
        try:
            parsed = datetime.strptime(raw, fmt).date()
            # Sanity-check: must be in the future (or very recent past)
            if parsed >= date.today().replace(year=date.today().year - 1):
                return parsed.isoformat()
        except ValueError:
            continue
    return None


def parse_assignment_details(text: str) -> dict:
    """
    Heuristically extract assignment fields from extracted text.

    Returns a dict with keys:
        title, subject, deadline, priority, description
    All values are strings; missing ones are empty strings.
    """
    if not text or text.startswith("["):
        # extraction failed / image OCR unavailable
        return {"title": "", "subject": "", "deadline": "", "priority": "Medium", "description": text}

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    full = " ".join(lines)

    # ── Title ────────────────────────────────────────────────────────────────
    title = ""
    for pat in _TITLE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            title = _clean(m.group(1))
            # Avoid capturing very long sentences as titles
            if len(title) > 120:
                title = title[:120]
            break
    # Fallback: use the first non-trivial line
    if not title and lines:
        title = _clean(lines[0])[:120]

    # ── Subject ──────────────────────────────────────────────────────────────
    subject = ""
    for pat in _SUBJECT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            subject = _clean(m.group(1))
            break

    # ── Deadline ─────────────────────────────────────────────────────────────
    deadline = ""
    for pat in _DEADLINE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            candidate = _try_parse_date(m.group(1) if m.lastindex else m.group())
            if candidate:
                deadline = candidate
                break
        if deadline:
            break

    # ── Priority ─────────────────────────────────────────────────────────────
    priority = "Medium"
    lower_full = full.lower()
    for level, kws in _PRIORITY_KEYWORDS.items():
        if any(kw in lower_full for kw in kws):
            priority = level
            break

    # ── Description: first 600 chars of raw text (trimmed) ──────────────────
    description = text[:600].strip()

    return {
        "title": title,
        "subject": subject,
        "deadline": deadline,
        "priority": priority,
        "description": description,
    }
