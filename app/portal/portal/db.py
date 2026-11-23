"""DB campus_portal: ket noi va migration (viet trong Python vi .gitignore chan *.sql).

Moi migration chay trong 1 transaction, ghi so phien ban vao schema_version. Chay lai khong sao.
Nhieu replica khoi dong cung luc: pg_advisory_xact_lock de chi mot ben chay migration.
"""
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    CREATE TABLE units (
        id          serial PRIMARY KEY,
        name        text NOT NULL UNIQUE,
        api_key_enc text NOT NULL,                 -- API key Shlink --author-only, ma hoa Fernet (FR-APP-13)
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE users (
        id            serial PRIMARY KEY,
        username      text NOT NULL UNIQUE,
        password_hash text NOT NULL,
        role          text NOT NULL CHECK (role IN ('admin', 'unit', 'viewer')),
        unit_id       int REFERENCES units(id),
        created_at    timestamptz NOT NULL DEFAULT now(),
        CHECK ((role = 'admin') = (unit_id IS NULL))
    );
    CREATE TABLE campaigns (
        id          serial PRIMARY KEY,
        unit_id     int NOT NULL REFERENCES units(id),
        name        text NOT NULL,
        tag         text NOT NULL UNIQUE,          -- tag Shlink cua moi link trong chien dich
        starts_at   timestamptz,
        ends_at     timestamptz NOT NULL,          -- het han: link khong con chuyen huong (validUntil)
        status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
        created_at  timestamptz NOT NULL DEFAULT now(),
        updated_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE campaign_links (
        id          serial PRIMARY KEY,
        campaign_id int NOT NULL REFERENCES campaigns(id),
        short_code  text NOT NULL UNIQUE,
        short_url   text NOT NULL,
        long_url    text NOT NULL,
        label       text,
        batch_id    int,
        created_at  timestamptz NOT NULL DEFAULT now()
    );
    CREATE TABLE card_batches (
        id          serial PRIMARY KEY,
        campaign_id int NOT NULL REFERENCES campaigns(id),
        version     int NOT NULL,
        n           int NOT NULL,
        status      text NOT NULL CHECK (status IN ('running', 'done', 'failed')),
        object_name text,
        error       text,
        created_at  timestamptz NOT NULL DEFAULT now(),
        UNIQUE (campaign_id, version)
    );
    CREATE TABLE attendees (
        id         serial PRIMARY KEY,
        batch_id   int NOT NULL REFERENCES card_batches(id),
        name       text NOT NULL,
        unit_label text,
        short_code text
    );
    """),
    # FR-APP-20: nhat ky thao tac. Chi ghi ten nguoi dung, vai tro, hanh dong, doi tuong; KHONG ghi key/mat khau.
    # Khong co khoa ngoai toi users/units: doi hay xoa tai khoan sau nay van giu duoc dong nhat ky cu.
    (2, """
    CREATE TABLE audit_log (
        id        bigserial PRIMARY KEY,
        at        timestamptz NOT NULL DEFAULT now(),
        user_id   int,
        username  text NOT NULL,
        role      text NOT NULL,
        unit_id   int,
        action    text NOT NULL,
        target    text NOT NULL DEFAULT '',
        detail    text NOT NULL DEFAULT ''
    );
    """),
]


@contextmanager
def connect(url: str):
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=5) as conn:
        yield conn


def migrate(url: str) -> int:
    with connect(url) as conn, conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(424242)")
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["version"] for r in conn.execute("SELECT version FROM schema_version")}
        for ver, sql in MIGRATIONS:
            if ver not in done:
                conn.execute(sql)
                conn.execute("INSERT INTO schema_version (version) VALUES (%s)", (ver,))
        return max(v for v, _ in MIGRATIONS)
