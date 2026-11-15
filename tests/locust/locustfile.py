"""
locustfile.py - Kich ban tai Locust cho CampusLink (SRS NFR-03: 80% redirect, 15% visits, 5% create).
TV4 so huu. Doc SHLINK_API_KEY va FIXTURE_SHORT_CODES tu tests/load/credentials.env, khong qua argv.
"""

from __future__ import annotations

import pathlib
import random
import time
from locust import HttpUser, between, task


def _load_credentials() -> dict[str, str]:
    cred_path = pathlib.Path(__file__).resolve().parent.parent / "load" / "credentials.env"
    data: dict[str, str] = {}
    if cred_path.is_file():
        for raw in cred_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
    return data


_CREDS = _load_credentials()
_API_KEY = _CREDS.get("SHLINK_API_KEY", "")
_SLUGS = [
    s for s in _CREDS.get("FIXTURE_SHORT_CODES", "tv4fix1 tv4fix2 tv4fix3").split()
    if s and not s.startswith("REPLACE_")
] or ["tv4fix1"]


class CampusLinkUser(HttpUser):
    wait_time = between(0.05, 0.2)

    @task(16)
    def redirect_short_url(self) -> None:
        slug = random.choice(_SLUGS)
        with self.client.get(
            f"/{slug}",
            allow_redirects=False,
            name="GET /{shortCode} (redirect)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 302:
                resp.success()
            else:
                resp.failure(f"Expected 302, got {resp.status_code}")

    @task(3)
    def get_short_url_visits(self) -> None:
        slug = random.choice(_SLUGS)
        self.client.get(
            f"/rest/v3/short-urls/{slug}/visits?itemsPerPage=20",
            headers={"X-Api-Key": _API_KEY},
            name="GET /rest/v3/short-urls/{slug}/visits",
        )

    @task(1)
    def create_short_url(self) -> None:
        payload = {
            "longUrl": f"https://example.org/locust?t={int(time.time()*1000)}&r={random.randint(1000,9999)}",
            "tags": ["load-test"],
        }
        self.client.post(
            "/rest/v3/short-urls",
            json=payload,
            headers={"X-Api-Key": _API_KEY},
            name="POST /rest/v3/short-urls",
        )
