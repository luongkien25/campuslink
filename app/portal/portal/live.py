"""Du lieu trang theo doi chien dich (FR-APP-18, dang polling REST Shlink, khong dung Redis pub/sub hay SSE).

Ham thuan: nhan ket qua REST da doc san, tra dict de trang /campaigns/<id>/live ve bang JS.
"""
from datetime import datetime, timedelta, tzinfo

WINDOW = 60   # so cot (phut) cua bieu do
TOP = 5


def window_start(now: datetime, tz: tzinfo) -> datetime:
    """Dau phut cua cot dau tien: WINDOW phut tinh den het phut hien tai."""
    return now.astimezone(tz).replace(second=0, microsecond=0) - timedelta(minutes=WINDOW - 1)


def build(links: list[dict], card_codes: list[str], times: list[datetime], truncated: bool,
          now: datetime, tz: tzinfo) -> dict:
    """links: Shlink.links_by_tag (kem visitsSummary); card_codes: ma link cua the QR ca nhan (bang campaign_links, batch_id);
    times: thoi diem cac luot truy cap tu window_start."""
    visits = {l["shortCode"]: l["visitsSummary"]["total"] for l in links}
    start = window_start(now, tz)
    counts = [0] * WINDOW
    for t in times:
        i = int((t.astimezone(tz).replace(second=0, microsecond=0) - start).total_seconds() // 60)
        if 0 <= i < WINDOW:
            counts[i] += 1
    top = sorted((l for l in links if l["visitsSummary"]["total"] > 0), key=lambda l: -l["visitsSummary"]["total"])[:TOP]
    return {
        "checked_in": sum(1 for code in card_codes if visits.get(code, 0) > 0),   # the co it nhat 1 luot = nguoi da check-in
        "cards": len(card_codes),
        "total_visits": sum(visits.values()),
        "per_minute": [{"t": (start + timedelta(minutes=i)).strftime("%H:%M"), "n": n} for i, n in enumerate(counts)],
        "top": [{"short_code": l["shortCode"], "short_url": l["shortUrl"], "label": l.get("title") or "",
                 "visits": l["visitsSummary"]["total"]} for l in top],
        "truncated": truncated,   # true: co hon LIVE_MAX_VISITS luot trong 60 phut, cot theo phut chi tinh phan moi nhat
        "updated_at": now.astimezone(tz).strftime("%H:%M:%S"),
    }
