"""Source readers: bytes → schedule text/rows for the deterministic parser.

PDF keeps a real text layer (pypdf); XLSX reads every sheet's rows. IMAGE and
scanned PDFs have no local text — those flow to the vision_ocr capability
through the AI gateway, debited under the org's wallet."""

from __future__ import annotations

from io import BytesIO


def _pdf_pages(content: bytes) -> list[list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    return [(page.extract_text() or "").splitlines() for page in reader.pages]


def pdf_text(content: bytes) -> str:
    return "\n".join(line for page in _pdf_pages(content) for line in page)


def xlsx_rows(content: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows: list[list[object]] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
    workbook.close()
    return rows


def extract(kind: str, content: bytes) -> tuple[str, list[list[object]] | None]:
    """Return (text, rows|None) the schedule parser understands."""
    if kind == "PDF":
        return pdf_text(content), None
    if kind == "XLSX":
        sheet_rows = xlsx_rows(content)
        text = "\n".join(
            " ".join(str(cell) for cell in row if cell is not None and str(cell).strip())
            for row in sheet_rows
        )
        return text, sheet_rows
    return "", None


def _csv_lines(content: bytes) -> list[str]:
    import csv
    import io

    text = content.decode("utf-8-sig", errors="replace")
    return [
        " ".join(cell.strip() for cell in row if cell and cell.strip())
        for row in csv.reader(io.StringIO(text))
    ]


def extract_tagged(kind: str, content: bytes) -> list[tuple[str, str]] | None:
    """(line, source-ref) pairs for review evidence; None when the source has
    no direct text layer (image / scan — those go through the AI compile)."""
    if kind == "PDF":
        pairs: list[tuple[str, str]] = []
        for page_number, page_lines in enumerate(_pdf_pages(content), start=1):
            pairs.extend(
                (line, f"página {page_number}") for line in page_lines if line.strip()
            )
        return pairs
    if kind == "XLSX":
        pairs = []
        for index, row in enumerate(xlsx_rows(content), start=1):
            joined = " ".join(
                str(cell) for cell in row if cell is not None and str(cell).strip()
            )
            if joined:
                pairs.append((joined, f"fila {index}"))
        return pairs
    if kind == "CSV":
        return [
            (line, f"fila {index}")
            for index, line in enumerate(_csv_lines(content), start=1)
            if line
        ]
    return None


def safe_file_name(file_name: str) -> bool:
    """Storage-key safety: the name becomes a segment of the object's path, so
    separators, traversal or control characters would escape the org prefix.
    The multipart transport supplies this value verbatim — never trust it."""
    if file_name != file_name.strip():
        # Edge whitespace would fail the canonical key check after upload
        # validation already passed — refuse the name, not the stored object.
        return False
    name = file_name
    if not name or name in (".", ".."):
        return False
    if "/" in name or "\\" in name:
        return False
    # "%" would be re-encoded by the canonical storage key at read time — a
    # name accepted here must remain the literal object segment it uploaded as.
    if "%" in file_name:
        return False
    # Control bytes scan the raw name — an edge space never masks a \t inside.
    return not any(ord(character) < 32 for character in file_name)


def kind_for(file_name: str) -> str | None:
    lowered = file_name.lower()
    if lowered.endswith(".pdf"):
        return "PDF"
    if lowered.endswith(".xlsx") or lowered.endswith(".xlsm"):
        return "XLSX"
    if lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
        return "IMAGE"
    if lowered.endswith(".csv"):
        return "CSV"
    return None


_KIND_MAGIC = {
    "PDF": (b"%PDF-",),
    "XLSX": (b"PK\x03\x04",),  # xlsx is a zip container
    "IMAGE": (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"),
}


def sniffed_kind(kind: str, content: bytes) -> bool:
    """Content must match its declared kind — the file goes to a provider or
    a parser, so extension alone can't be the authority. CSV carries no
    signature; the schedule parser's own structure check is the gate."""
    if kind == "CSV":
        return True
    if kind == "IMAGE":
        if content.startswith(b"RIFF"):
            return len(content) >= 12 and content[8:12] == b"WEBP"
        return any(content.startswith(magic) for magic in _KIND_MAGIC["IMAGE"])
    return any(content.startswith(magic) for magic in _KIND_MAGIC.get(kind, ()))
