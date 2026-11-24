"""Luu PDF the QR (FR-APP-16) va CSV bao cao chien dich (FR-APP-19). Ten object theo SRS 4.6:
the <campaign_id>/v<phien ban>/lo-<n>.pdf, bao cao <campaign_id>/<yyyymmddThhmmZ>.csv.

local: thu muc QR_LOCAL_DIR (Compose); bao cao nam trong thu muc con reports/ cua no.
swift: container campus-qr (the) va campus-reports (bao cao), cung application credential campus-svc
(SWIFT_APP_CRED_FILE, 2 dong id= va secret=, ADR-10/H3b). Credential khong co quyen DELETE; ten co dinh nen chay lai thi ghi de.
"""
import os

import httpx


class LocalStorage:
    def __init__(self, root: str):
        self.root = root

    def put(self, name: str, data: bytes, content_type: str = "") -> None:   # content_type chi de Swift dung
        path = os.path.join(self.root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)

    def get(self, name: str) -> bytes:
        with open(os.path.join(self.root, name), "rb") as f:
            return f.read()


class SwiftStorage:
    def __init__(self, auth_url: str, swift_url: str, container: str, cred_file: str):
        self.auth_url, self.swift_url, self.container, self.cred_file = auth_url, swift_url.rstrip("/"), container, cred_file

    def _token(self) -> str:
        cred = dict(l.strip().split("=", 1) for l in open(self.cred_file, encoding="utf-8") if "=" in l)
        body = {"auth": {"identity": {"methods": ["application_credential"],
                                      "application_credential": {"id": cred["id"], "secret": cred["secret"]}}}}
        r = httpx.post(f"{self.auth_url}/v3/auth/tokens", json=body, timeout=20)
        if r.status_code != 201:
            raise RuntimeError(f"Keystone tra {r.status_code}")
        return r.headers["X-Subject-Token"]

    def put(self, name: str, data: bytes, content_type: str = "application/pdf") -> None:
        r = httpx.put(f"{self.swift_url}/{self.container}/{name}", content=data, timeout=120,
                      headers={"X-Auth-Token": self._token(), "Content-Type": content_type})
        if r.status_code != 201:
            raise RuntimeError(f"Swift PUT {name} tra {r.status_code}")

    def get(self, name: str) -> bytes:
        r = httpx.get(f"{self.swift_url}/{self.container}/{name}", timeout=120, headers={"X-Auth-Token": self._token()})
        if r.status_code != 200:
            raise RuntimeError(f"Swift GET {name} tra {r.status_code}")
        return r.content


def make(cfg, reports: bool = False):
    """Kho the QR, hoac kho bao cao (reports=True)."""
    if cfg.qr_storage == "swift":
        container = cfg.swift_container_reports if reports else cfg.swift_container_qr
        return SwiftStorage(cfg.os_auth_url, cfg.swift_url, container, cfg.swift_app_cred_file)
    return LocalStorage(os.path.join(cfg.qr_local_dir, "reports") if reports else cfg.qr_local_dir)
