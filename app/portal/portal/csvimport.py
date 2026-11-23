"""Doc file CSV nhap link hang loat (FR-APP-15). Chi parse va kiem dinh dong; tao link nam o app.py.

Cot: long_url (bat buoc), custom_slug (tuy chon), label (tuy chon). Dong tieu de la dong 1.
Chay DONG BO trong request nen co gioi han cung: <= 1 MB va <= 1000 dong.
"""
import csv
import io
import re

from .shlink import valid_url

MAX_BYTES = 1_000_000
MAX_ROWS = 1000
_SLUG = re.compile(r"^[A-Za-z0-9_-]{1,60}$")   # slug di vao duong dan REST, nen khong cho ky tu la


class CsvError(Exception):
    """Loi ca file (khong dung dinh dang, qua lon...): khong nhap dong nao."""


def parse(raw: bytes) -> list[dict]:
    """-> [{line, long_url, slug, label, error}]. error != None: dong sai, khong goi Shlink."""
    if len(raw) > MAX_BYTES:
        raise CsvError("File quá 1 MB")
    try:
        text = raw.decode("utf-8-sig")        # utf-8-sig: bo BOM khi Excel luu "CSV UTF-8"
    except UnicodeDecodeError:
        raise CsvError("File phải mã hóa UTF-8")
    head = text.split("\n", 1)[0]
    delim = ";" if ";" in head and "," not in head else ","   # Excel vung VN hay xuat dau cham phay
    rd = csv.DictReader(io.StringIO(text, newline=""), delimiter=delim)
    rd.fieldnames = [(h or "").strip().lower() for h in (rd.fieldnames or [])]
    if "long_url" not in rd.fieldnames:
        raise CsvError("Dòng đầu phải là tiêu đề có cột long_url (tùy chọn: custom_slug, label)")
    rows = []
    for r in rd:
        cell = {k: (v or "").strip() for k, v in r.items() if k}   # bo cot khong ten / o thua cuoi dong
        if not any(cell.values()):
            continue                               # dong trong
        if len(rows) >= MAX_ROWS:
            raise CsvError(f"Tối đa {MAX_ROWS} dòng mỗi file")
        row = {"line": rd.line_num, "long_url": cell["long_url"], "slug": cell.get("custom_slug", ""),
               "label": cell.get("label", ""), "error": None}
        if not valid_url(row["long_url"]):
            row["error"] = "invalid-url"
        elif row["slug"] and not _SLUG.match(row["slug"]):
            row["error"] = "invalid-slug"
        rows.append(row)
    if not rows:
        raise CsvError("File không có dòng dữ liệu nào")
    return rows
