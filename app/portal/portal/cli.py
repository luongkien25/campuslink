"""Lenh quan tri chay trong container portal (khong in secret):

  python -m portal.cli create-admin <username>              # mat khau doc tu stdin
  python -m portal.cli create-unit <ten> <file-api-key>     # key --author-only tao bang: shlink api-key:generate --author-only
  python -m portal.cli create-user <username> <unit|viewer> <ten-don-vi>   # mat khau doc tu stdin
"""
import sys

from . import config, db, security


def main(argv: list[str]) -> int:
    cfg = config.load()
    db.migrate(cfg.db_url)
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    with db.connect(cfg.db_url) as c:
        if cmd == "create-admin" and len(args) == 1:
            pw = sys.stdin.readline().strip()
            assert len(pw) >= 8, "mat khau toi thieu 8 ky tu"
            c.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')", (args[0], security.hash_password(pw)))
        elif cmd == "create-unit" and len(args) == 2:
            key = open(args[1], encoding="utf-8").read().strip()
            c.execute("INSERT INTO units (name, api_key_enc) VALUES (%s, %s)", (args[0], security.fernet(cfg.secret_key).encrypt(key.encode()).decode()))
        elif cmd == "create-user" and len(args) == 3 and args[1] in ("unit", "viewer"):
            pw = sys.stdin.readline().strip()
            assert len(pw) >= 8, "mat khau toi thieu 8 ky tu"
            unit = c.execute("SELECT id FROM units WHERE name = %s", (args[2],)).fetchone()
            assert unit, f"khong co don vi {args[2]}"
            c.execute("INSERT INTO users (username, password_hash, role, unit_id) VALUES (%s, %s, %s, %s)",
                      (args[0], security.hash_password(pw), args[1], unit["id"]))
        else:
            print(__doc__)
            return 1
    print(f"OK {cmd} {args[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
