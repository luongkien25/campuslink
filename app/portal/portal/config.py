"""Cau hinh portal theo SRS 4.6: secret chi doc qua bien *_FILE, khong nhan secret truc tiep qua env."""
import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None:
        raise RuntimeError(f"thieu bien moi truong {name}")
    return v


def _secret(name: str) -> str:
    """Doc gia tri tu file trong bien <name>_FILE (vd /run/secrets/...), cat khoang trang cuoi."""
    path = _env(f"{name}_FILE")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


@dataclass(frozen=True)
class Config:
    role: str
    port: int
    shlink_api_url: str
    db_url: str
    secret_key: str
    redis_servers: str
    qr_storage: str            # local | swift
    qr_local_dir: str
    os_auth_url: str
    swift_url: str
    swift_container_qr: str
    swift_container_reports: str
    swift_app_cred_file: str


def load() -> Config:
    storage = _env("QR_STORAGE", "local")
    return Config(
        role=_env("ROLE", "portal"),
        port=int(_env("PORTAL_PORT", "8081")),
        shlink_api_url=_env("SHLINK_API_URL", "http://127.0.0.1:8080").rstrip("/"),
        db_url=_secret("PORTAL_DB_URL"),
        secret_key=_secret("PORTAL_SECRET_KEY"),
        redis_servers=_secret("REDIS_SERVERS"),
        qr_storage=storage,
        qr_local_dir=_env("QR_LOCAL_DIR", "/data/qr"),
        os_auth_url=_env("OS_AUTH_URL", "http://10.11.0.10/identity").rstrip("/"),
        swift_url=_env("SWIFT_URL", "") if storage == "swift" else "",
        swift_container_qr=_env("SWIFT_CONTAINER_QR", "campus-qr"),
        swift_container_reports=_env("SWIFT_CONTAINER_REPORTS", "campus-reports"),
        swift_app_cred_file=_env("SWIFT_APP_CRED_FILE", "") if storage == "swift" else "",
    )
