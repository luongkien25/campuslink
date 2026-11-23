"""Nhat ky thao tac cua portal (FR-APP-20): ai, lam gi, doi tuong nao, luc nao.

Moi thao tac tao/sua/dong/nhap CSV/dat luat/xoa luat goi record() MOT lan sau khi thao tac thanh cong.
Quy tac: chi truyen ten, ma, so luong vao `target`/`detail`; KHONG BAO GIO truyen API key, mat khau, secret.
"""
LIMIT = 200  # so dong trang nhat ky hien thi (moi nhat truoc)


def record(c, u: dict, action: str, target: str = "", detail: str = "") -> None:
    c.execute("INSERT INTO audit_log (user_id, username, role, unit_id, action, target, detail) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s)",
              (u.get("id"), u["username"], u["role"], u.get("unit_id"), action, target[:200], detail[:500]))
    c.commit()


def latest(c) -> list[dict]:
    return c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT %s", (LIMIT,)).fetchall()
