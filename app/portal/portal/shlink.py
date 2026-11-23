"""Goi REST v3 cua Shlink bang key --author-only cua don vi (SRS 4.1, ADR-08). Key khong bao gio ghi log."""
from datetime import datetime
from urllib.parse import quote, urlsplit

import httpx


class ShlinkError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"Shlink {status}: {detail}")
        self.status, self.detail = status, detail


def valid_url(u: str) -> bool:
    """Dich chuyen huong phai la http(s) co ten mien (dung cho luat chuyen huong va nhap CSV)."""
    p = urlsplit(u)
    return p.scheme in ("http", "https") and bool(p.netloc) and len(u) <= 2048


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


class Shlink:
    def __init__(self, base_url: str, api_key: str):
        self._c = httpx.Client(base_url=base_url, timeout=10,
                               headers={"X-Api-Key": api_key, "Accept": "application/json"})

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._c.close()

    def _check(self, r: httpx.Response) -> dict:
        if r.status_code >= 400:
            try:
                d = r.json()
                detail = d.get("type", "").rsplit("/", 1)[-1] or d.get("detail", "")
            except ValueError:
                detail = r.text[:200]
            raise ShlinkError(r.status_code, detail)
        return r.json() if r.content else {}

    def create(self, long_url: str, tags: list[str], valid_until: datetime,
               valid_since: datetime | None = None, slug: str | None = None, title: str | None = None,
               find_if_exists: bool = False) -> dict:
        body = {"longUrl": long_url, "tags": tags, "validUntil": _iso(valid_until), "findIfExists": find_if_exists}
        if valid_since:
            body["validSince"] = _iso(valid_since)
        if slug:
            body["customSlug"] = slug
        if title:
            body["title"] = title
        return self._check(self._c.post("/rest/v3/short-urls", json=body))

    def set_valid_until(self, short_code: str, valid_until: datetime) -> dict:
        return self._check(self._c.patch(f"/rest/v3/short-urls/{short_code}", json={"validUntil": _iso(valid_until)}))

    def get(self, short_code: str) -> dict:
        return self._check(self._c.get(f"/rest/v3/short-urls/{short_code}"))

    def tag_visits_total(self, tag: str) -> int:
        d = self._check(self._c.get(f"/rest/v3/tags/{tag}/visits", params={"itemsPerPage": 1}))
        return int(d["visits"]["pagination"]["totalItems"])

    # Luat chuyen huong (FR-APP-17). Shlink luu ca bo luat cua mot link: POST la THAY CA BO, nen
    # portal doc bo luat hien co, sua tren danh sach roi gui lai ca danh sach. Thu tu trong danh sach = do uu tien.
    def redirect_rules(self, short_code: str) -> list[dict]:
        d = self._check(self._c.get(f"/rest/v3/short-urls/{quote(short_code, safe='')}/redirect-rules"))
        return d.get("redirectRules", [])

    def set_redirect_rules(self, short_code: str, rules: list[dict]) -> list[dict]:
        """rules: [{"longUrl": ..., "conditions": [{"type", "matchKey", "matchValue"}]}], tu tren xuong uu tien giam dan."""
        d = self._check(self._c.post(f"/rest/v3/short-urls/{quote(short_code, safe='')}/redirect-rules", json={"redirectRules": rules}))
        return d.get("redirectRules", [])
