"""campus-portal (ADR-08, SRS 3.3, 4.6). MVP phuong an B (#40): FR-APP-13 toi thieu, FR-APP-14, FR-APP-16 duong lui 1 lo.

Phan quyen (FR-APP-13):
  admin  : tao don vi (kem API key --author-only cua don vi), tao tai khoan; xem moi chien dich, khong tao link
  unit   : tao/sua/dong chien dich va phat hanh the cua DON VI MINH, bang key cua don vi
  viewer : chi xem chien dich cua don vi minh
Chien dich cua don vi khac luon tra 404 (khong lo la co ton tai).
"""
import logging
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg
import redis
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import cards, db, security, storage
from .config import Config
from .shlink import Shlink, ShlinkError

log = logging.getLogger("campus-portal")
MAX_LINKS = 50        # link moi lan tao chien dich
MAX_CARDS = 300       # nguoi tham du moi lo (duong lui: 1 lo, chay dong bo)


def create_app(cfg: Config) -> FastAPI:
    app = FastAPI(title="campus-portal", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=security.session_key(cfg.secret_key),
                       session_cookie="campus_portal", same_site="lax", max_age=8 * 3600)
    tpl = Jinja2Templates(directory=__file__.rsplit("/", 1)[0] + "/templates")
    fer = security.fernet(cfg.secret_key)
    store = storage.make(cfg)
    tz = ZoneInfo(__import__("os").environ.get("TIMEZONE", "UTC"))

    def conn():
        with db.connect(cfg.db_url) as c:
            yield c

    def parse_dt(s: str) -> datetime:
        """datetime-local cua trinh duyet (gio TIMEZONE) -> datetime co mui gio."""
        return datetime.fromisoformat(s).replace(tzinfo=tz) if s else None

    def fmt(dt):
        return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M") if dt else ""

    tpl.env.filters["fmt"] = fmt

    def render(request: Request, name: str, **ctx):
        request.session.setdefault("csrf", secrets.token_urlsafe(24))
        ctx.update(request=request, user=request.session.get("user"), csrf=request.session["csrf"], tzname=str(tz))
        return tpl.TemplateResponse(request, name, ctx)

    def user(request: Request) -> dict:
        u = request.session.get("user")
        if not u:
            raise HTTPException(303, headers={"Location": "/login"})
        return u

    def check_csrf(request: Request, token: str):
        if not token or token != request.session.get("csrf"):
            raise HTTPException(400, "CSRF token sai, tai lai trang")

    def need(u: dict, *roles: str):
        if u["role"] not in roles:
            raise HTTPException(403, "Khong du quyen")

    def campaign_of(c, u: dict, cid: int) -> dict:
        row = c.execute("SELECT * FROM campaigns WHERE id = %s", (cid,)).fetchone()
        if not row or (u["role"] != "admin" and row["unit_id"] != u["unit_id"]):
            raise HTTPException(404, "Khong co chien dich nay")
        return row

    def unit_shlink(c, unit_id: int) -> Shlink:
        enc = c.execute("SELECT api_key_enc FROM units WHERE id = %s", (unit_id,)).fetchone()["api_key_enc"]
        return Shlink(cfg.shlink_api_url, fer.decrypt(enc.encode()).decode())

    # ---------- health (SRS 4.6: 200 khi DB campus_portal va Redis tra loi) ----------
    @app.get("/healthz")
    def healthz():
        checks = {}
        try:
            with db.connect(cfg.db_url) as c:
                c.execute("SELECT 1")
            checks["db"] = "pass"
        except Exception as e:  # noqa: BLE001
            checks["db"] = f"fail: {type(e).__name__}"
        try:
            r = redis.Redis.from_url(cfg.redis_servers.replace("tcp://", "redis://", 1), socket_timeout=3)
            checks["redis"] = "pass" if r.ping() else "fail"
        except Exception as e:  # noqa: BLE001
            checks["redis"] = f"fail: {type(e).__name__}"
        ok = all(v == "pass" for v in checks.values())
        return JSONResponse({"status": "pass" if ok else "fail", "checks": checks}, status_code=200 if ok else 503)

    # ---------- dang nhap ----------
    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return render(request, "login.html", error=None)

    @app.post("/login")
    def login(request: Request, username: str = Form(...), password: str = Form(...), csrf: str = Form(""), c=Depends(conn)):
        check_csrf(request, csrf)
        row = c.execute("SELECT u.*, un.name AS unit_name FROM users u LEFT JOIN units un ON un.id = u.unit_id "
                        "WHERE username = %s", (username,)).fetchone()
        if not row or not security.check_password(password, row["password_hash"]):
            return render(request, "login.html", error="Sai tên đăng nhập hoặc mật khẩu")
        request.session.clear()
        request.session["user"] = {"id": row["id"], "username": row["username"], "role": row["role"],
                                   "unit_id": row["unit_id"], "unit_name": row["unit_name"]}
        log.info("login user=%s role=%s", row["username"], row["role"])
        return RedirectResponse("/", 303)

    @app.post("/logout")
    def logout(request: Request, csrf: str = Form("")):
        check_csrf(request, csrf)
        request.session.clear()
        return RedirectResponse("/login", 303)

    @app.get("/")
    def home(u=Depends(user)):
        return RedirectResponse("/admin" if u["role"] == "admin" else "/campaigns", 303)

    # ---------- quan tri (admin) ----------
    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request, u=Depends(user), c=Depends(conn)):
        need(u, "admin")
        units = c.execute("SELECT id, name, created_at FROM units ORDER BY id").fetchall()
        users = c.execute("SELECT u.id, username, role, un.name AS unit_name FROM users u "
                          "LEFT JOIN units un ON un.id = u.unit_id ORDER BY u.id").fetchall()
        camps = c.execute("SELECT c.*, un.name AS unit_name FROM campaigns c JOIN units un ON un.id = c.unit_id "
                          "ORDER BY c.id DESC").fetchall()
        return render(request, "admin.html", units=units, users=users, campaigns=camps, msg=request.query_params.get("msg"))

    @app.post("/admin/units")
    def add_unit(request: Request, name: str = Form(...), api_key: str = Form(...), csrf: str = Form(""),
                 u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "admin")
        try:  # key phai dung duoc voi Shlink truoc khi luu
            with Shlink(cfg.shlink_api_url, api_key.strip()) as s:
                s._check(s._c.get("/rest/v3/short-urls", params={"itemsPerPage": 1}))
        except ShlinkError as e:
            raise HTTPException(400, f"API key không dùng được với Shlink ({e.status})")
        try:
            c.execute("INSERT INTO units (name, api_key_enc) VALUES (%s, %s)",
                      (name.strip(), fer.encrypt(api_key.strip().encode()).decode()))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(400, "Tên đơn vị đã có")
        log.info("admin=%s tao don vi %s", u["username"], name)
        return RedirectResponse("/admin?msg=Đã thêm đơn vị", 303)

    @app.post("/admin/users")
    def add_user(request: Request, username: str = Form(...), password: str = Form(...), role: str = Form(...),
                 unit_id: str = Form(""), csrf: str = Form(""), u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "admin")
        if role not in ("admin", "unit", "viewer") or len(password) < 8:
            raise HTTPException(400, "Vai trò sai hoặc mật khẩu dưới 8 ký tự")
        uid = None if role == "admin" else int(unit_id)
        try:
            c.execute("INSERT INTO users (username, password_hash, role, unit_id) VALUES (%s, %s, %s, %s)",
                      (username.strip(), security.hash_password(password), role, uid))
        except psycopg.errors.UniqueViolation:
            raise HTTPException(400, "Tên đăng nhập đã có")
        return RedirectResponse("/admin?msg=Đã thêm tài khoản", 303)

    # ---------- chien dich (FR-APP-14) ----------
    @app.get("/campaigns", response_class=HTMLResponse)
    def campaigns(request: Request, u=Depends(user), c=Depends(conn)):
        need(u, "unit", "viewer")
        rows = c.execute("SELECT c.*, (SELECT count(*) FROM campaign_links l WHERE l.campaign_id = c.id) AS n_links "
                         "FROM campaigns c WHERE unit_id = %s ORDER BY id DESC", (u["unit_id"],)).fetchall()
        return render(request, "campaigns.html", campaigns=rows, now=datetime.now(timezone.utc))

    @app.post("/campaigns")
    def create_campaign(request: Request, name: str = Form(...), ends_at: str = Form(...), starts_at: str = Form(""),
                        links: str = Form(""), csrf: str = Form(""), u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "unit")
        end, start = parse_dt(ends_at), parse_dt(starts_at)
        lines = [l.strip() for l in links.splitlines() if l.strip()]
        if len(lines) > MAX_LINKS:
            raise HTTPException(400, f"Tối đa {MAX_LINKS} link mỗi lần")
        with c.transaction():
            row = c.execute("INSERT INTO campaigns (unit_id, name, tag, starts_at, ends_at) VALUES (%s, %s, %s, %s, %s) "
                            "RETURNING id", (u["unit_id"], name.strip(), "tmp-" + secrets.token_hex(6), start, end)).fetchone()
            cid = row["id"]
            tag = f"campaign-{cid}"
            c.execute("UPDATE campaigns SET tag = %s WHERE id = %s", (tag, cid))
        _add_links(c, u, cid, tag, lines, start, end)
        return RedirectResponse(f"/campaigns/{cid}", 303)

    def _add_links(c, u, cid, tag, lines, start, end, batch_id=None):
        errors = []
        with unit_shlink(c, u["unit_id"]) as s:
            for line in lines:
                long_url, _, label = (p.strip() for p in line.partition("|"))
                try:
                    d = s.create(long_url, [tag], end, start, title=label or None)
                except ShlinkError as e:
                    errors.append(f"{long_url}: {e.detail}")
                    continue
                c.execute("INSERT INTO campaign_links (campaign_id, short_code, short_url, long_url, label, batch_id) "
                          "VALUES (%s, %s, %s, %s, %s, %s)", (cid, d["shortCode"], d["shortUrl"], long_url, label or None, batch_id))
        c.commit()
        if errors:
            log.warning("campaign=%s %d link loi", cid, len(errors))
        return errors

    @app.get("/campaigns/{cid}", response_class=HTMLResponse)
    def campaign(request: Request, cid: int, u=Depends(user), c=Depends(conn)):
        row = campaign_of(c, u, cid)
        links = c.execute("SELECT * FROM campaign_links WHERE campaign_id = %s AND batch_id IS NULL ORDER BY id", (cid,)).fetchall()
        batches = c.execute("SELECT * FROM card_batches WHERE campaign_id = %s ORDER BY version DESC", (cid,)).fetchall()
        visits = None
        if u["role"] != "admin":
            try:
                with unit_shlink(c, row["unit_id"]) as s:
                    visits = s.tag_visits_total(row["tag"])
            except ShlinkError:
                visits = None
        return render(request, "campaign.html", c=row, links=links, batches=batches, visits=visits,
                      now=datetime.now(timezone.utc), msg=request.query_params.get("msg"))

    @app.post("/campaigns/{cid}/links")
    def add_links(request: Request, cid: int, links: str = Form(...), csrf: str = Form(""), u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "unit")
        row = campaign_of(c, u, cid)
        if row["status"] != "open":
            raise HTTPException(400, "Chiến dịch đã đóng")
        lines = [l.strip() for l in links.splitlines() if l.strip()][:MAX_LINKS]
        errs = _add_links(c, u, cid, row["tag"], lines, row["starts_at"], row["ends_at"])
        return RedirectResponse(f"/campaigns/{cid}?msg=" + (f"{len(errs)} link lỗi: " + "; ".join(errs)[:300] if errs else "Đã thêm link"), 303)

    def _set_valid_until(c, row, until):
        with unit_shlink(c, row["unit_id"]) as s:
            for l in c.execute("SELECT short_code FROM campaign_links WHERE campaign_id = %s", (row["id"],)).fetchall():
                s.set_valid_until(l["short_code"], until)

    @app.post("/campaigns/{cid}/edit")
    def edit_campaign(request: Request, cid: int, name: str = Form(...), ends_at: str = Form(...), csrf: str = Form(""),
                      u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "unit")
        row = campaign_of(c, u, cid)
        end = parse_dt(ends_at)
        c.execute("UPDATE campaigns SET name = %s, ends_at = %s, updated_at = now() WHERE id = %s", (name.strip(), end, cid))
        c.commit()
        if row["status"] == "open" and end != row["ends_at"]:
            _set_valid_until(c, {**row, "ends_at": end}, end)
        return RedirectResponse(f"/campaigns/{cid}?msg=Đã lưu", 303)

    @app.post("/campaigns/{cid}/close")
    def close_campaign(request: Request, cid: int, csrf: str = Form(""), u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "unit")
        row = campaign_of(c, u, cid)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        _set_valid_until(c, row, now)
        c.execute("UPDATE campaigns SET status = 'closed', ends_at = %s, updated_at = now() WHERE id = %s", (now, cid))
        c.commit()
        log.info("unit=%s dong chien dich %s", u["unit_id"], cid)
        return RedirectResponse(f"/campaigns/{cid}?msg=Đã đóng chiến dịch, link không còn chuyển hướng", 303)

    # ---------- phat hanh the QR (FR-APP-16, duong lui: 1 lo, chay dong bo) ----------
    @app.post("/campaigns/{cid}/cards")
    def issue_cards(request: Request, cid: int, target_url: str = Form(...), attendees: str = Form(...),
                    csrf: str = Form(""), u=Depends(user), c=Depends(conn)):
        check_csrf(request, csrf)
        need(u, "unit")
        row = campaign_of(c, u, cid)
        if row["status"] != "open":
            raise HTTPException(400, "Chiến dịch đã đóng")
        people = []
        for line in attendees.splitlines():
            name, _, unit_label = (p.strip() for p in line.partition(","))
            if name:
                people.append((name, unit_label))
        if not people or len(people) > MAX_CARDS:
            raise HTTPException(400, f"Danh sách cần 1–{MAX_CARDS} người")
        ver = c.execute("SELECT coalesce(max(version), 0) + 1 AS v FROM card_batches WHERE campaign_id = %s", (cid,)).fetchone()["v"]
        bid = c.execute("INSERT INTO card_batches (campaign_id, version, n, status) VALUES (%s, %s, %s, 'running') RETURNING id",
                        (cid, ver, len(people))).fetchone()["id"]
        c.commit()
        try:
            out = []
            with unit_shlink(c, row["unit_id"]) as s:
                for name, unit_label in people:
                    d = s.create(target_url.strip(), [row["tag"]], row["ends_at"], row["starts_at"], title=name)
                    c.execute("INSERT INTO campaign_links (campaign_id, short_code, short_url, long_url, label, batch_id) "
                              "VALUES (%s, %s, %s, %s, %s, %s)", (cid, d["shortCode"], d["shortUrl"], target_url.strip(), name, bid))
                    c.execute("INSERT INTO attendees (batch_id, name, unit_label, short_code) VALUES (%s, %s, %s, %s)",
                              (bid, name, unit_label or None, d["shortCode"]))
                    out.append({"name": name, "unit_label": unit_label, "short_url": d["shortUrl"]})
            c.commit()
            obj = f"{cid}/v{ver}/lo-1.pdf"
            store.put(obj, cards.render(row["name"], out))
            c.execute("UPDATE card_batches SET status = 'done', object_name = %s WHERE id = %s", (obj, bid))
            c.commit()
            log.info("campaign=%s phat hanh %d the -> %s", cid, len(out), obj)
            msg = f"Đã phát hành {len(out)} thẻ"
        except Exception as e:  # noqa: BLE001
            c.rollback()
            c.execute("UPDATE card_batches SET status = 'failed', error = %s WHERE id = %s", (str(e)[:500], bid))
            c.commit()
            log.error("campaign=%s phat hanh the loi: %s", cid, e)
            msg = f"Phát hành lỗi: {e}"
        return RedirectResponse(f"/campaigns/{cid}?msg={msg}", 303)

    @app.get("/campaigns/{cid}/cards/{bid}.pdf")
    def card_pdf(cid: int, bid: int, u=Depends(user), c=Depends(conn)):
        campaign_of(c, u, cid)
        b = c.execute("SELECT * FROM card_batches WHERE id = %s AND campaign_id = %s AND status = 'done'", (bid, cid)).fetchone()
        if not b:
            raise HTTPException(404, "Chưa có file")
        return Response(store.get(b["object_name"]), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="the-qr-{cid}-v{b["version"]}.pdf"'})

    return app
