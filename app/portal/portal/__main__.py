"""Diem vao container: migration DB campus_portal roi chay web (ROLE=portal).

ROLE=worker (FR-APP-21, TV4) chua co trong MVP: thoat voi ma 2 de khong chay nham.
"""
import logging
import sys

import uvicorn

from . import config, db
from .app import create_app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}')
    cfg = config.load()
    if cfg.role != "portal":
        logging.error("ROLE=%s chua ho tro trong MVP (worker: FR-APP-21)", cfg.role)
        return 2
    ver = db.migrate(cfg.db_url)
    logging.info("migration campus_portal xong, schema_version=%s", ver)
    uvicorn.run(create_app(cfg), host="0.0.0.0", port=cfg.port, proxy_headers=True, forwarded_allow_ips="*", log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
