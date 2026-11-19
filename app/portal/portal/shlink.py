"""Goi REST v3 cua Shlink bang key --author-only cua don vi (SRS 4.1, ADR-08). Key khong bao gio ghi log."""
from datetime import datetime

import httpx


class ShlinkError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"Shlink {status}: {detail}")
        self.status, self.detail = status, detail


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
               valid_since: datetime | None = None, slug: str | None = None, title: str | None = None) -> dict:
        body = {"longUrl": long_url, "tags": tags, "validUntil": _iso(valid_until), "findIfExists": False}
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
