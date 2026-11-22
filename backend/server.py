#!/usr/bin/env python3
"""HEALTHY LIFE - máy chủ web + REST API (chỉ dùng thư viện chuẩn của Python 3.8+).

Chạy:  python server.py [cổng]     (mặc định 8000)

Công khai
  POST /api/orders              tạo đơn (máy chủ tự tính giá, tồn kho, mã giảm giá, phí ship); có phiên đăng nhập thì gắn vào tài khoản
  POST /api/orders/lookup       tra cứu đơn theo mã đơn + số điện thoại
  POST /api/orders/claim        khách báo đã chuyển khoản
  GET  /api/state               sản phẩm (quản trị đăng nhập thì kèm đơn hàng, nhật ký)
  GET  /api/recommend?ids=P1,P2 gợi ý mua kèm cho giỏ hàng
  POST /api/webhook/payment     đối soát thanh toán tự động (cần PAYMENT_WEBHOOK_SECRET)
Tài khoản khách
  POST /api/auth/register | /api/auth/login | /api/auth/logout | /api/auth/profile | /api/auth/password
  GET  /api/auth/me             người dùng hiện tại      GET /api/me/orders   đơn hàng của tôi
Quản trị (cần phiên quản trị: POST /api/auth/admin-login)
  PUT  /api/state               ghi sản phẩm (thêm ?full=1 để khôi phục toàn bộ từ bản sao lưu)
  GET  /api/analytics?range=90  số liệu và dự báo cho dashboard (xem analytics.py)
  GET  /api/backup              tải bản sao lưu cơ sở dữ liệu (.db)
  POST /api/admin/orders/<mã>/<next|cancel|paid>     đổi trạng thái đơn
  POST /api/admin/orders/<mã>/assign                 gán xe cho đơn
  GET  /api/admin/live          xe + lịch sử đường đi      GET /api/stream   luồng sự kiện thời gian thực (SSE)
  GET|POST /api/admin/vehicles[...]                  quản lý đội xe
Thiết bị xe (Authorization: Bearer <mã xe>)
  POST /api/vehicle/location    gửi vị trí      GET /api/vehicle/me   đơn đang giao
  POST /api/vehicle/orders/<mã>/<pick|deliver>       bắt đầu giao / giao xong
Biến môi trường: HL_DB (tệp SQLite khác), HL_ADMIN_PASSWORD + HL_ADMIN_TOTP_SECRET (bật quản trị),
HL_DEMO=1 (tài khoản demo admin123 / 123456, chỉ để trình diễn), HL_COOKIE_SECURE=1, HL_TRUST_PROXY=1 (lấy IP từ X-Forwarded-For), HL_SIM=1 (xe chạy mô phỏng), HL_SIM_SPEED (hệ số tăng tốc, mặc định 10).
"""
import datetime
import hmac
import http.cookies
import json
import os
import queue
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import traceback
from urllib.parse import parse_qs, urlparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class Srv(ThreadingHTTPServer):
    # Windows: SO_REUSEADDR cho phép hai máy chủ cùng mở một cổng mà không báo lỗi.
    # Tắt tùy chọn này trên Windows để máy chủ thứ hai báo lỗi rõ ràng.
    allow_reuse_address = os.name != "nt"

import analytics
import auth
import fleet

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(BASE, "..", "frontend"))
DB_DIR = os.path.normpath(os.path.join(BASE, "..", "database"))
DB_FILE = os.environ.get("HL_DB") or os.path.join(DB_DIR, "healthy_life.db")
MAX_BODY = 2_000_000
# Chính sách bảo mật nội dung: chỉ tải script/style/ảnh/font từ chính trang và các dịch vụ đang dùng
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https://tile.openstreetmap.org https://img.vietqr.io; "
       "connect-src 'self'; frame-src https://www.google.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


def conn():
    c = sqlite3.connect(DB_FILE, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def migrate(c):
    """Nâng cấp cơ sở dữ liệu cũ: thêm cột và chỉ mục mới cho bảng orders."""
    have = {r["name"] for r in c.execute("PRAGMA table_info(orders)")}
    for col, typ in (("user_id", "INTEGER"), ("vehicle_id", "TEXT"), ("dest_lat", "REAL"), ("dest_lng", "REAL")):
        if col not in have:
            c.execute("ALTER TABLE orders ADD COLUMN %s %s" % (col, typ))
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_orders_vehicle ON orders(vehicle_id)")
    c.commit()


def init_db():
    """Tạo bảng từ schema.sql, nâng cấp, tạo tài khoản quản trị và sao lưu tự động mỗi ngày (database/backups)."""
    os.makedirs(os.path.join(DB_DIR, "backups"), exist_ok=True)
    c = conn()
    with open(os.path.join(DB_DIR, "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    c.commit()
    migrate(c)
    c.execute("PRAGMA journal_mode=WAL")
    admin_ready = auth.ensure_admin(c)
    if fleet.SIM:
        fleet.seed_demo_fleet(c)
    dst = os.path.join(DB_DIR, "backups", "healthy_life_%s.db" % datetime.date.today().isoformat())
    if not os.path.exists(dst):
        b = sqlite3.connect(dst)
        c.backup(b)
        b.close()
    c.close()
    return admin_ready


class Err(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


SHIP = {"std": 25000, "exp": 45000}
FREESHIP = 399000
PAYS = ("cod", "qr", "wallet", "card")
HOLD_MIN = 30  # phút giữ đơn chưa thanh toán online
STATUSES = ["Chờ xác nhận", "Đã xác nhận", "Đang đóng gói", "Đã bàn giao vận chuyển", "Đang giao", "Đã giao"]
CANCEL = "Đã hủy"
CLAIM = "Khách báo đã chuyển khoản"
LOOKUP, VAUTH = auth.Limiter(15, 600), auth.Limiter(20, 600)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def expire_orders():
    """Tự hủy đơn thanh toán online quá hạn mà chưa thu tiền, hoàn lại tồn kho."""
    c = conn()
    done = []
    try:
        limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=HOLD_MIN)
        c.execute("BEGIN IMMEDIATE")
        for o in c.execute("SELECT id,created_at FROM orders WHERE paid=0 AND pay_method!='cod' AND status='Chờ xác nhận'").fetchall():
            try:
                t = datetime.datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if t < limit:
                for i in c.execute("SELECT product_id,qty FROM order_items WHERE order_id=?", (o["id"],)).fetchall():
                    c.execute("UPDATE products SET stock=stock+? WHERE id=?", (i["qty"], i["product_id"]))
                c.execute("UPDATE orders SET status='Đã hủy' WHERE id=?", (o["id"],))
                c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (o["id"], "Đã hủy", now()))
                c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (now(), "Tự hủy đơn %s do quá hạn thanh toán" % o["id"]))
                done.append(o["id"])
        c.commit()
        for oid in done:
            fleet.HUB.publish("order", order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()))
    except Exception:
        c.rollback()
    finally:
        c.close()


def create_order(d, user_id=None):
    """Tạo đơn ở phía máy chủ: giá, tồn kho, mã giảm giá và phí ship đều tính lại từ cơ sở dữ liệu."""
    cu, ship, pay = d["cust"], str(d["ship"]), str(d["pay"])
    name, phone, addr = str(cu["name"]).strip()[:80], str(cu["phone"]).strip(), str(cu["addr"]).strip()[:250]
    if not name or not addr or not re.fullmatch(r"0\d{9}", phone):
        raise ValueError("Thông tin giao hàng không hợp lệ")
    if ship not in SHIP or pay not in PAYS or not isinstance(d["items"], list) or not d["items"]:
        raise ValueError("Đơn hàng không hợp lệ")
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        sub, rows = 0, []
        for it in d["items"]:
            qty = int(it["qty"])
            r = c.execute("SELECT * FROM products WHERE id=? AND active=1", (str(it["id"]),)).fetchone()
            if not r or qty < 1:
                raise ValueError("Sản phẩm không hợp lệ")
            if r["stock"] < qty:
                raise ValueError('"%s" chỉ còn %d sản phẩm' % (r["name"], r["stock"]))
            rows.append((r, qty))
            sub += r["price"] * qty
        code, disc, free = str(d.get("voucher") or "").upper(), 0, sub >= FREESHIP
        if code:
            v = c.execute("SELECT * FROM vouchers WHERE code=?", (code,)).fetchone()
            if not v or sub < v["min_order"]:
                raise ValueError("Mã giảm giá không hợp lệ")
            disc = min(v["max_discount"] or 10 ** 9, int(sub * v["percent"] / 100 + 0.5)) if v["percent"] else (v["amount_off"] or 0)
            free = free or bool(v["free_ship"])
        fee = 0 if free else SHIP[ship]
        total = sub - disc + fee
        seq = int(c.execute("SELECT value FROM settings WHERE key='order_seq'").fetchone()[0]) + 1
        oid, ts = "HL%06d" % seq, now()
        c.execute("UPDATE settings SET value=? WHERE key='order_seq'", (str(seq),))
        c.execute("INSERT INTO customers(phone,name,address) VALUES(?,?,?) ON CONFLICT(phone) DO UPDATE SET name=excluded.name,address=excluded.address", (phone, name, addr))
        g = fleet.guess_dest(addr) or (None, None)
        c.execute("INSERT INTO orders(id,created_at,customer_phone,ship_address,ship_method,ship_fee,pay_method,paid,discount,voucher,points,total,status,tracking_code,needs_call,user_id,dest_lat,dest_lng) "
                  "VALUES(?,?,?,?,?,?,?,0,?,?,?,?,?,'',?,?,?,?)",
                  (oid, ts, phone, addr, ship, fee, pay, disc, code if disc or code else "", total // 10000, total, "Chờ xác nhận", 1 if pay == "cod" and total >= 500000 else 0, user_id, g[0], g[1]))
        for r, qty in rows:
            c.execute("INSERT INTO order_items(order_id,product_id,name,price,qty) VALUES(?,?,?,?,?)", (oid, r["id"], r["name"], r["price"], qty))
            c.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (qty, r["id"], qty))
        c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (oid, "Chờ xác nhận", ts))
        c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (ts, "Đơn mới %s – %d đ" % (oid, total)))
        c.commit()
        od = order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    fleet.HUB.publish("order", od)
    return od


def payment_webhook(d, auth):
    """Nhận thông báo biến động số dư (kiểu SePay/Casso): tự đối soát theo mã đơn trong nội dung chuyển khoản.
    Bảo vệ bằng biến môi trường PAYMENT_WEBHOOK_SECRET, gửi trong header Authorization: Apikey <secret>."""
    secret = os.environ.get("PAYMENT_WEBHOOK_SECRET", "")
    if not secret or not hmac.compare_digest((auth or "").replace("Apikey ", "").strip(), secret):
        raise PermissionError("Sai khóa xác thực")
    m = re.search(r"HL\d{6}", str(d.get("content") or d.get("description") or "").upper())
    amount = int(d.get("amount") or d.get("transferAmount") or 0)
    if not m:
        return {"ok": True, "matched": False}
    c = conn()
    try:
        o = c.execute("SELECT * FROM orders WHERE id=?", (m.group(0),)).fetchone()
        if not o or o["paid"] or o["status"] == "Đã hủy" or amount < o["total"]:
            return {"ok": True, "matched": False}
        c.execute("UPDATE orders SET paid=1 WHERE id=?", (o["id"],))
        c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (o["id"], "Đã thu tiền", now()))
        c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (now(), "Webhook: đã thu %d đ cho đơn %s" % (amount, o["id"])))
        c.commit()
        fleet.HUB.publish("order", order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (o["id"],)).fetchone()))
        return {"ok": True, "matched": True, "order": o["id"]}
    finally:
        c.close()


def order_to_dict(c, o):
    cu = c.execute("SELECT name FROM customers WHERE phone=?", (o["customer_phone"],)).fetchone()
    items = [dict(id=i["product_id"], name=i["name"], price=i["price"], qty=i["qty"])
             for i in c.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],))]
    hist = [dict(st=h["status"], at=h["at"]) for h in c.execute("SELECT * FROM order_history WHERE order_id=? ORDER BY rowid", (o["id"],))]
    return dict(
        id=o["id"], at=o["created_at"],
        cust=dict(name=cu["name"] if cu else "", phone=o["customer_phone"], addr=o["ship_address"]),
        items=items, ship=dict(m=o["ship_method"], fee=o["ship_fee"]),
        pay=dict(m=o["pay_method"], paid=bool(o["paid"])), total=o["total"], disc=o["discount"],
        voucher=o["voucher"] or "", pts=o["points"], st=o["status"], track=o["tracking_code"] or "",
        flag=bool(o["needs_call"]), hist=hist, veh=o["vehicle_id"] or "",
        dest=[o["dest_lat"], o["dest_lng"]] if o["dest_lat"] is not None else None)


def get_state(admin=False):
    """Khách chỉ thấy sản phẩm; đơn hàng và nhật ký chỉ trả cho phiên quản trị."""
    expire_orders()
    c = conn()
    products = [dict(id=r["id"], name=r["name"], cat=r["category"], price=r["price"], stock=r["stock"],
                     emoji=r["emoji"], desc=r["description"], on=bool(r["active"]))
                for r in c.execute("SELECT * FROM products ORDER BY rowid")]
    if not admin:
        c.close()
        return dict(products=products, orders=[], log=[], seq=0, full=False)
    orders = [order_to_dict(c, o) for o in c.execute("SELECT * FROM orders ORDER BY created_at DESC, id DESC").fetchall()]
    log = [dict(at=r["at"], m=r["message"]) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 60")]
    row = c.execute("SELECT value FROM settings WHERE key='order_seq'").fetchone()
    c.close()
    return dict(products=products, orders=orders, log=log, seq=int(row["value"]) if row else 100, full=True)


def _clean_product(p):
    """Kiểm tra một sản phẩm gửi từ trang quản trị trước khi ghi vào CSDL."""
    if not isinstance(p, dict):
        raise ValueError("Dữ liệu sản phẩm không hợp lệ")
    pid = str(p.get("id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", pid):
        raise ValueError("Mã sản phẩm không hợp lệ")
    name = str(p.get("name", "")).strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Tên sản phẩm phải từ 1 đến 120 ký tự")
    try:
        price, stock = int(p.get("price")), int(p.get("stock"))
    except (TypeError, ValueError):
        raise ValueError("Giá hoặc tồn kho không hợp lệ")
    if not (0 <= price <= 100_000_000 and 0 <= stock <= 1_000_000):
        raise ValueError("Giá hoặc tồn kho không hợp lệ")
    return (pid, name, str(p.get("cat", ""))[:60], price, stock,
            str(p.get("emoji", ""))[:8], str(p.get("desc", ""))[:300], 1 if p.get("on") else 0)


def put_state(d, full=False):
    """Ghi sản phẩm (và nhật ký) trong một giao dịch. Đơn hàng chỉ bị ghi đè khi khôi phục (full=True),
    còn bình thường đơn được đổi qua /api/admin/orders/... để không đè lên đơn khách vừa đặt."""
    if not isinstance(d, dict) or not isinstance(d.get("products"), list) or (full and not isinstance(d.get("orders"), list)):
        raise ValueError("Dữ liệu không hợp lệ")
    if len(d["products"]) > 500:
        raise ValueError("Quá nhiều sản phẩm")
    rows = [_clean_product(p) for p in d["products"]]  # kiểm tra toàn bộ trước khi mở giao dịch
    c = conn()
    try:
        c.execute("BEGIN")
        extra = {}
        if full:
            extra = {r["id"]: (r["user_id"], r["vehicle_id"], r["dest_lat"], r["dest_lng"])
                     for r in c.execute("SELECT id,user_id,vehicle_id,dest_lat,dest_lng FROM orders")}
            for t in ("order_history", "order_items", "orders"):
                c.execute("DELETE FROM " + t)
        c.execute("DELETE FROM products")
        for row in rows:
            c.execute("INSERT INTO products(id,name,category,price,stock,emoji,description,active) VALUES(?,?,?,?,?,?,?,?)", row)
        if full:
            for o in d["orders"]:
                cu = o["cust"]
                c.execute("INSERT INTO customers(phone,name,address) VALUES(?,?,?) "
                          "ON CONFLICT(phone) DO UPDATE SET name=excluded.name,address=excluded.address",
                          (str(cu["phone"])[:15], str(cu["name"])[:80], str(cu["addr"])[:250]))
                c.execute("INSERT INTO orders(id,created_at,customer_phone,ship_address,ship_method,ship_fee,pay_method,paid,"
                          "discount,voucher,points,total,status,tracking_code,needs_call) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (str(o["id"])[:20], str(o["at"]), str(cu["phone"])[:15], str(cu["addr"])[:250], str(o["ship"]["m"]),
                           int(o["ship"]["fee"]), str(o["pay"]["m"]), 1 if o["pay"]["paid"] else 0, int(o.get("disc", 0)),
                           str(o.get("voucher", "")), int(o.get("pts", 0)), int(o["total"]), str(o["st"]),
                           str(o.get("track", "")), 1 if o.get("flag") else 0))
                for i in o["items"]:
                    c.execute("INSERT INTO order_items(order_id,product_id,name,price,qty) VALUES(?,?,?,?,?)",
                              (str(o["id"]), str(i["id"]), str(i["name"])[:120], int(i["price"]), int(i["qty"])))
                for h in o["hist"]:
                    c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (str(o["id"]), str(h["st"]), str(h["at"])))
                if str(o["id"]) in extra:
                    c.execute("UPDATE orders SET user_id=?,vehicle_id=?,dest_lat=?,dest_lng=? WHERE id=?", extra[str(o["id"])] + (str(o["id"]),))
            c.execute("INSERT INTO settings(key,value) VALUES('order_seq',?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(d.get("seq", 100))),))
        # nhật ký: chỉ thêm các dòng chưa có, không xóa dòng máy chủ đã ghi
        for l in reversed(d.get("log", [])[:60]):
            at, m = str(l["at"]), str(l["m"])[:300]
            if not c.execute("SELECT 1 FROM audit_log WHERE at=? AND message=?", (at, m)).fetchone():
                c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (at, m))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def order_action(oid, action, actor="Quản trị", vehicle=None):
    """Đổi trạng thái đơn ở phía máy chủ. action: next | cancel | paid (quản trị), pick | deliver (tài xế)."""
    c = conn()
    try:
        c.execute("BEGIN IMMEDIATE")
        o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o:
            raise Err(404, "Không tìm thấy đơn hàng")
        if vehicle and o["vehicle_id"] != vehicle:
            raise Err(403, "Đơn này không được giao cho xe của bạn")
        st, ts = o["status"], now()
        if action == "paid":
            if o["paid"] or st == CANCEL:
                raise ValueError("Đơn đã thu tiền hoặc đã hủy")
            c.execute("UPDATE orders SET paid=1 WHERE id=?", (oid,))
            hist, msg = "Đã thu tiền", "%s xác nhận đã thu %d đ đơn %s" % (actor, o["total"], oid)
        elif action == "cancel":
            if st in (CANCEL, STATUSES[-1]):
                raise ValueError("Đơn đã hoàn tất hoặc đã hủy")
            for i in c.execute("SELECT product_id,qty FROM order_items WHERE order_id=?", (oid,)).fetchall():
                c.execute("UPDATE products SET stock=stock+? WHERE id=?", (i["qty"], i["product_id"]))
            c.execute("UPDATE orders SET status=? WHERE id=?", (CANCEL, oid))
            hist, msg = CANCEL, "%s hủy đơn %s" % (actor, oid)
        elif action in ("next", "pick", "deliver"):
            if st not in STATUSES or st == STATUSES[-1]:
                raise ValueError("Đơn đã hoàn tất hoặc đã hủy, không thể chuyển tiếp")
            if action == "pick" and st != "Đã bàn giao vận chuyển":
                raise ValueError("Đơn chưa sẵn sàng để lấy hàng")
            if action == "deliver" and st != "Đang giao":
                raise ValueError("Hãy bấm 'Bắt đầu giao' trước")
            if not o["paid"] and o["pay_method"] != "cod":
                raise ValueError("Đơn chưa thanh toán: hãy xác nhận đã thu tiền trước")
            nxt = STATUSES[STATUSES.index(st) + 1]
            track = o["tracking_code"] or ""
            if nxt == "Đã bàn giao vận chuyển" and not track:
                track = ("GRAB" if o["ship_method"] == "exp" else "SPXVN") + str(1_000_000_000 + secrets.randbelow(9_000_000_000))
            paid = 1 if (nxt == "Đã giao" and o["pay_method"] == "cod") else o["paid"]
            c.execute("UPDATE orders SET status=?,tracking_code=?,paid=? WHERE id=?", (nxt, track, paid, oid))
            hist, msg = nxt, "%s: đơn %s → %s" % (actor, oid, nxt)
        else:
            raise ValueError("Thao tác không hợp lệ")
        c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (oid, hist, ts))
        c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (ts, msg))
        c.commit()
        od = order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone())
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    fleet.HUB.publish("order", od)
    return od


def lookup_order(oid, phone, ip):
    if LOOKUP.blocked(ip):
        raise Err(429, "Tra cứu quá nhiều lần. Hãy thử lại sau ít phút.")
    c = conn()
    try:
        o = c.execute("SELECT * FROM orders WHERE id=? AND customer_phone=?", (str(oid).strip().upper(), str(phone).strip())).fetchone()
        if not o:
            LOOKUP.hit(ip)
            raise Err(404, "Không tìm thấy đơn. Kiểm tra lại mã đơn và số điện thoại.")
        return order_to_dict(c, o)
    finally:
        c.close()


def claim_order(oid, phone, ip):
    od = lookup_order(oid, phone, ip)
    if od["st"] == CANCEL or od["pay"]["paid"] or od["pay"]["m"] == "cod":
        return od
    c = conn()
    try:
        if not c.execute("SELECT 1 FROM order_history WHERE order_id=? AND status=?", (od["id"], CLAIM)).fetchone():
            c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (od["id"], CLAIM, now()))
            c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (now(), "Khách báo đã chuyển khoản đơn %s" % od["id"]))
            c.commit()
        od = order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (od["id"],)).fetchone())
    finally:
        c.close()
    fleet.HUB.publish("order", od)
    return od


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    # ---- tiện ích
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # tiêu đề bảo mật cho mọi phản hồi, kể cả tệp tĩnh
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")  # OSM chặn tile nếu không có Referer
        self.send_header("Permissions-Policy", "geolocation=(self), camera=(), microphone=(), payment=()")
        if self._https():
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        if not self.path.startswith("/api/"):  # tệp tĩnh: luôn kiểm tra bản mới, tránh trình duyệt giữ bản cũ
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def list_directory(self, path):  # không liệt kê nội dung thư mục tĩnh
        self.send_error(404)  # thông báo mặc định, ASCII: dòng trạng thái HTTP không nhận tiếng Việt
        return None

    def _https(self):
        return os.environ.get("HL_COOKIE_SECURE") == "1" or self.headers.get("X-Forwarded-Proto") == "https"

    def _json(self, code, obj, extra=None):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), extra=extra)

    def _ip(self):
        if os.environ.get("HL_TRUST_PROXY") == "1":
            fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
            if fwd:
                return fwd
        return self.client_address[0]

    def _token(self):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            m = http.cookies.SimpleCookie(raw).get(auth.COOKIE)
        except http.cookies.CookieError:
            return None
        return m.value if m else None

    def _user(self):
        if getattr(self, "_uc", None) is None:
            self._uc = False
            t = self._token()
            if t:
                c = conn()
                try:
                    self._uc = auth.session_user(c, t) or False
                finally:
                    c.close()
        return self._uc or None

    def _need_user(self):
        u = self._user()
        if not u:
            raise Err(401, "Vui lòng đăng nhập")
        return u

    def _need_admin(self):
        u = self._need_user()
        if u["role"] != "admin":
            raise Err(403, "Chỉ quản trị viên được truy cập")
        return u

    def _cookie(self, token, max_age):
        secure = self._https()
        return {"Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s" % (auth.COOKIE, token, max_age, "; Secure" if secure else "")}

    def _body(self):
        o = self.headers.get("Origin")  # chống CSRF: yêu cầu ghi chỉ chấp nhận từ chính trang này
        if o and urlparse(o).netloc != (self.headers.get("Host") or ""):
            raise Err(403, "Nguồn yêu cầu không hợp lệ")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise Err(413, "Dữ liệu quá lớn")
        if n == 0:
            return {}
        if "json" not in (self.headers.get("Content-Type") or "").lower():
            raise Err(415, "Dữ liệu phải ở dạng JSON")
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            raise Err(400, "JSON không hợp lệ")

    def _vehicle(self):
        ip = self._ip()
        if VAUTH.blocked(ip):
            raise Err(429, "Sai mã xe quá nhiều lần")
        h = self.headers.get("Authorization") or ""
        c = conn()
        try:
            v = fleet.auth_vehicle(c, h[7:].strip() if h.lower().startswith("bearer ") else "")
        finally:
            c.close()
        if not v:
            VAUTH.hit(ip)
            raise Err(401, "Mã xe không hợp lệ")
        if not v["active"]:
            raise Err(403, "Xe đang tạm ngưng")
        return v

    def _fail(self, e):
        if isinstance(e, Err):
            return self._json(e.code, {"error": str(e)})
        if isinstance(e, auth.RateLimited):
            return self._json(429, {"error": str(e)})
        if isinstance(e, PermissionError):
            return self._json(401, {"error": str(e)})
        if isinstance(e, (ValueError, KeyError, TypeError, sqlite3.Error)):
            return self._json(400, {"error": str(e) if isinstance(e, ValueError) else "Dữ liệu không hợp lệ"})
        self.log_error("%s", traceback.format_exc())
        return self._json(500, {"error": "Lỗi máy chủ"})

    # ---- luồng thời gian thực (SSE)
    def _stream(self):
        self._need_admin()
        q = fleet.HUB.subscribe()
        self.send_response(200)
        for k, v in (("Content-Type", "text/event-stream; charset=utf-8"), ("Cache-Control", "no-store"),
                     ("X-Accel-Buffering", "no"), ("X-Content-Type-Options", "nosniff")):
            self.send_header(k, v)
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(b"retry: 3000\n\n")
            while True:
                try:
                    ev, data = q.get(timeout=15)
                    self.wfile.write(("event: %s\ndata: %s\n\n" % (ev, json.dumps(data, ensure_ascii=False))).encode("utf-8"))
                except queue.Empty:
                    c = conn()  # nhịp tim; đồng thời đóng luồng khi phiên hết hạn hoặc bị đăng xuất
                    try:
                        u = auth.session_user(c, self._token())
                    finally:
                        c.close()
                    if not u or u["role"] != "admin":
                        break
                    self.wfile.write(b": ping\n\n")
        except OSError:
            pass
        finally:
            fleet.HUB.unsubscribe(q)

    # ---- GET
    def do_GET(self):
        self._uc = None
        u = urlparse(self.path)
        p = u.path
        try:
            if p == "/api/auth/me":
                return self._json(200, {"user": self._user()})
            if p == "/api/state":
                usr = self._user()
                return self._json(200, get_state(bool(usr and usr["role"] == "admin")))
            if p == "/api/recommend":
                ids = [i for i in (parse_qs(u.query).get("ids") or [""])[0].split(",") if i][:20]
                c = conn()
                try:
                    return self._json(200, {"items": analytics.recommend(c, ids)})
                finally:
                    c.close()
            if p == "/api/me/orders":
                usr = self._need_user()
                c = conn()
                try:
                    rows = c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC, id DESC", (usr["id"],)).fetchall()
                    return self._json(200, {"orders": [order_to_dict(c, o) for o in rows]})
                finally:
                    c.close()
            if p == "/api/analytics":
                self._need_admin()
                try:
                    days = int((parse_qs(u.query).get("range") or ["90"])[0])
                except ValueError:
                    days = 90
                c = conn()
                try:
                    return self._json(200, analytics.get(c, days if days in (30, 90, 180, 365) else 90))
                finally:
                    c.close()
            if p == "/api/backup":
                self._need_admin()
                fd, tmp = tempfile.mkstemp(suffix=".db")
                os.close(fd)
                try:
                    c, b = conn(), sqlite3.connect(tmp)
                    c.backup(b)
                    b.execute("DELETE FROM sessions")  # bản tải về không chứa phiên đăng nhập đang hoạt động
                    b.commit()
                    b.close()
                    c.close()
                    with open(tmp, "rb") as f:
                        data = f.read()
                finally:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                return self._send(200, data, "application/octet-stream", {"Content-Disposition": "attachment; filename=healthy_life_backup.db"})
            if p == "/api/stream":
                return self._stream()
            if p == "/api/admin/live":
                self._need_admin()
                c = conn()
                try:
                    return self._json(200, {"vehicles": fleet.list_vehicles(c), "sim": fleet.SIM, "store": fleet.STORE})
                finally:
                    c.close()
            if p == "/api/admin/vehicles":
                self._need_admin()
                c = conn()
                try:
                    return self._json(200, {"vehicles": fleet.list_vehicles(c)})
                finally:
                    c.close()
            if p == "/api/vehicle/me":
                v = self._vehicle()
                c = conn()
                try:
                    row = c.execute(fleet._Q + "WHERE v.id=?", (v["id"],)).fetchone()
                    return self._json(200, {"vehicle": fleet.vdict(row), "orders": fleet.driver_orders(c, v["id"])})
                finally:
                    c.close()
        except Exception as e:
            return self._fail(e)
        return super().do_GET()

    # ---- POST
    def do_POST(self):
        self._uc = None
        p, ip = urlparse(self.path).path, self._ip()
        try:
            body = self._body()
            if not isinstance(body, dict):
                raise Err(400, "Dữ liệu không hợp lệ")
            # --- tài khoản
            if p == "/api/auth/register":
                c = conn()
                try:
                    usr, tok = auth.register(c, body, ip)
                finally:
                    c.close()
                return self._json(200, {"ok": True, "user": usr}, self._cookie(tok, auth.CUSTOMER_TTL))
            if p == "/api/auth/login":
                c = conn()
                try:
                    usr, tok = auth.login(c, body.get("id"), body.get("password"), ip)
                finally:
                    c.close()
                return self._json(200, {"ok": True, "user": usr}, self._cookie(tok, auth.CUSTOMER_TTL))
            if p == "/api/auth/admin-login":
                c = conn()
                try:
                    usr, tok = auth.admin_login(c, body.get("password"), body.get("otp"), ip)
                finally:
                    c.close()
                return self._json(200, {"ok": True, "user": usr}, self._cookie(tok, auth.ADMIN_TTL))
            if p == "/api/auth/logout":
                c = conn()
                try:
                    auth.destroy_session(c, self._token())
                finally:
                    c.close()
                return self._json(200, {"ok": True}, self._cookie("", 0))
            if p == "/api/auth/profile":
                usr = self._need_user()
                c = conn()
                try:
                    return self._json(200, {"ok": True, "user": auth.update_profile(c, usr["id"], body)})
                finally:
                    c.close()
            if p == "/api/auth/password":
                usr = self._need_user()
                c = conn()
                try:
                    auth.change_password(c, usr["id"], body.get("old"), body.get("new"), self._token())
                finally:
                    c.close()
                return self._json(200, {"ok": True})
            # --- đơn hàng của khách
            if p == "/api/orders":
                usr = self._user()
                od = create_order(body, usr["id"] if usr and usr["role"] == "customer" else None)
                return self._json(200, {"ok": True, "id": od["id"], "order": od})
            if p == "/api/orders/lookup":
                return self._json(200, {"ok": True, "order": lookup_order(body.get("id"), body.get("phone"), ip)})
            if p == "/api/orders/claim":
                return self._json(200, {"ok": True, "order": claim_order(body.get("id"), body.get("phone"), ip)})
            if p == "/api/webhook/payment":
                return self._json(200, payment_webhook(body, self.headers.get("Authorization")))
            # --- quản trị: đơn hàng
            m = re.fullmatch(r"/api/admin/orders/(HL\d{6})/(next|cancel|paid)", p)
            if m:
                self._need_admin()
                return self._json(200, {"ok": True, "order": order_action(m.group(1), m.group(2))})
            m = re.fullmatch(r"/api/admin/orders/(HL\d{6})/assign", p)
            if m:
                self._need_admin()
                c = conn()
                try:
                    fleet.assign(c, m.group(1), str(body.get("vehicle") or ""))
                    od = order_to_dict(c, c.execute("SELECT * FROM orders WHERE id=?", (m.group(1),)).fetchone())
                finally:
                    c.close()
                fleet.HUB.publish("order", od)
                return self._json(200, {"ok": True, "order": od})
            # --- quản trị: đội xe
            if p == "/api/admin/vehicles":
                self._need_admin()
                c = conn()
                try:
                    vid, tok = fleet.create_vehicle(c, body)
                finally:
                    c.close()
                return self._json(200, {"ok": True, "id": vid, "token": tok})
            m = re.fullmatch(r"/api/admin/vehicles/(XE\d{2,})/(token|active|delete)", p)
            if m:
                self._need_admin()
                c = conn()
                try:
                    if m.group(2) == "token":
                        return self._json(200, {"ok": True, "id": m.group(1), "token": fleet.rotate_token(c, m.group(1))})
                    if m.group(2) == "active":
                        fleet.set_active(c, m.group(1), bool(body.get("on")))
                    else:
                        fleet.delete_vehicle(c, m.group(1))
                finally:
                    c.close()
                return self._json(200, {"ok": True})
            # --- thiết bị xe
            if p == "/api/vehicle/location":
                v = self._vehicle()
                c = conn()
                try:
                    fleet.set_location(c, v["id"], body.get("lat"), body.get("lng"), body.get("speed"), body.get("heading"))
                finally:
                    c.close()
                return self._json(200, {"ok": True})
            m = re.fullmatch(r"/api/vehicle/orders/(HL\d{6})/(pick|deliver)", p)
            if m:
                v = self._vehicle()
                return self._json(200, {"ok": True, "order": order_action(m.group(1), m.group(2), "Tài xế %s" % v["plate"], v["id"])})
            return self._json(404, {"error": "Không tìm thấy"})
        except Exception as e:
            self._fail(e)

    def do_PUT(self):
        self._uc = None
        p = urlparse(self.path)
        try:
            if p.path != "/api/state":
                raise Err(404, "Không tìm thấy")
            self._need_admin()
            put_state(self._body(), "full" in parse_qs(p.query))
            self._json(200, {"ok": True})
        except Exception as e:
            self._fail(e)


def _sim_act(oid, action, actor, vehicle):
    return order_action(oid, action, actor, vehicle)


if __name__ == "__main__":
    fleet.SIM = os.environ.get("HL_SIM") == "1"
    demo, admin_ready = init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("HEALTHY LIFE đang chạy tại http://localhost:%d  (Ctrl+C để dừng)" % port)
    if demo:
        print("CẢNH BÁO: đang bật tài khoản demo (HL_DEMO=1: admin123 / 123456). Không dùng khi mở ra Internet.")
    elif not admin_ready:
        print("Quản trị đang TẮT: đặt HL_ADMIN_PASSWORD và HL_ADMIN_TOTP_SECRET để bật (hoặc HL_DEMO=1 để dùng tài khoản demo).")
    if fleet.SIM:
        print("Chế độ mô phỏng đội xe đang bật (HL_SIM=1): vị trí xe là giả lập.")
        threading.Thread(target=fleet.sim_loop, args=(conn, _sim_act, float(os.environ.get("HL_SIM_SPEED", "10"))), daemon=True).start()
    try:
        httpd = Srv(("127.0.0.1", port), Handler)
    except OSError:
        print("LỖI: cổng %d đang được chương trình khác dùng. Tắt server cũ, hoặc chạy cổng khác: python server.py 8002" % port)
        sys.exit(1)
    httpd.serve_forever()
