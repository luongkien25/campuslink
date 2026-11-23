"""Dung file CSV bao cao chien dich (FR-APP-19): moi link mot dong (ma, short URL, dich, nhan, so luot) va dong tong."""
import csv
import io

HEADER = ("short_code", "short_url", "long_url", "label", "visits")


def _cell(v) -> str:
    """Chong 'CSV injection': o bat dau bang = + - @ bi Excel hieu thanh cong thuc, nen them dau ' phia truoc."""
    v = v or ""
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def build(links: list[dict]) -> tuple[bytes, int]:
    """links: ket qua Shlink.links_by_tag. Tra (noi dung CSV, tong luot).
    UTF-8 co BOM de Excel doc dung tieng Viet. Dong tong co short_code rong va nhan 'Tổng'."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    total = 0
    for l in sorted(links, key=lambda x: (x["dateCreated"], x["shortCode"])):
        n = l["visitsSummary"]["total"]
        total += n
        w.writerow([l["shortCode"], l["shortUrl"], _cell(l["longUrl"]), _cell(l.get("title")), n])
    w.writerow(["", "", "", "Tổng", total])
    return ("\ufeff" + buf.getvalue()).encode("utf-8"), total
