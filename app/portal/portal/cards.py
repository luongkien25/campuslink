"""Dung PDF the QR (FR-APP-16, ham dung the cua TV3). A4, 2 cot x 4 hang the moi trang.

Moi the: ten, don vi, ma QR tro toi short link rieng cua nguoi do, short link dang chu de go tay.
"""
import io
import os

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONT = "Helvetica"
for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
    if os.path.exists(path):
        pdfmetrics.registerFont(TTFont("DejaVu", path))
        _FONT = "DejaVu"  # can font TTF de in tieng Viet co dau

COLS, ROWS = 2, 4
MARGIN = 12 * mm


def _qr_png(url: str) -> ImageReader:
    img = qrcode.make(url, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def render(campaign_name: str, cards: list[dict]) -> bytes:
    """cards: [{"name", "unit_label", "short_url"}] -> bytes PDF."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"The QR - {campaign_name}")
    pw, ph = A4
    cw, ch = (pw - 2 * MARGIN) / COLS, (ph - 2 * MARGIN) / ROWS
    per_page = COLS * ROWS
    for i, card in enumerate(cards):
        if i and i % per_page == 0:
            c.showPage()
        k = i % per_page
        x = MARGIN + (k % COLS) * cw
        y = ph - MARGIN - (k // COLS + 1) * ch
        c.setDash(2, 2)
        c.rect(x + 2, y + 2, cw - 4, ch - 4)  # duong cat
        c.setDash()
        # 28 mm duoi cung danh cho chu; QR chiem phan con lai (cach mep tren 4 mm), khong de len chu
        text_h = 28 * mm
        q = min(cw * 0.5, ch - text_h - 4 * mm)
        c.drawImage(_qr_png(card["short_url"]), x + (cw - q) / 2, y + text_h, q, q)
        c.setFont(_FONT, 13)
        c.drawCentredString(x + cw / 2, y + 22 * mm, card["name"][:40])
        c.setFont(_FONT, 9)
        c.drawCentredString(x + cw / 2, y + 16.5 * mm, (card.get("unit_label") or "")[:50])
        c.drawCentredString(x + cw / 2, y + 11 * mm, card["short_url"])
        c.setFont(_FONT, 7)
        c.drawCentredString(x + cw / 2, y + 5.5 * mm, campaign_name[:60])
    c.showPage()
    c.save()
    return buf.getvalue()
