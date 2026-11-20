#!/usr/bin/env python3
"""Healthy Life - máy chủ web + REST API (chỉ dùng thư viện chuẩn của Python 3.8+).

Chạy:  python server.py [cổng]     (mặc định 8000)
API:   GET  /api/state    đọc sản phẩm, đơn hàng, nhật ký
       PUT  /api/state    ghi lại dữ liệu (kiểm tra hợp lệ rồi lưu vào SQLite)
       GET  /api/backup   tải bản sao lưu cơ sở dữ liệu (.db)
"""
import datetime
import json
import os
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.normpath(os.path.join(BASE, "..", "frontend"))
DB_DIR = os.path.normpath(os.path.join(BASE, "..", "database"))
DB_FILE = os.path.join(DB_DIR, "healthy_life.db")
MAX_BODY = 2_000_000


def conn():
    c = sqlite3.connect(DB_FILE)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    """Tạo bảng từ schema.sql và sao lưu tự động mỗi ngày (giữ trong database/backups)."""
    os.makedirs(os.path.join(DB_DIR, "backups"), exist_ok=True)
    c = conn()
    with open(os.path.join(DB_DIR, "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    c.commit()
    dst = os.path.join(DB_DIR, "backups", "healthy_life_%s.db" % datetime.date.today().isoformat())
    if not os.path.exists(dst):
        b = sqlite3.connect(dst)
        c.backup(b)
        b.close()
    c.close()


def get_state():
    c = conn()
    products = [dict(id=r["id"], name=r["name"], cat=r["category"], price=r["price"], stock=r["stock"],
                     emoji=r["emoji"], desc=r["description"], on=bool(r["active"]))
                for r in c.execute("SELECT * FROM products ORDER BY rowid")]
    orders = []
    for o in c.execute("SELECT * FROM orders ORDER BY created_at DESC, id DESC").fetchall():
        cu = c.execute("SELECT name FROM customers WHERE phone=?", (o["customer_phone"],)).fetchone()
        items = [dict(id=i["product_id"], name=i["name"], price=i["price"], qty=i["qty"])
                 for i in c.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],))]
        hist = [dict(st=h["status"], at=h["at"])
                for h in c.execute("SELECT * FROM order_history WHERE order_id=? ORDER BY rowid", (o["id"],))]
        orders.append(dict(
            id=o["id"], at=o["created_at"],
            cust=dict(name=cu["name"] if cu else "", phone=o["customer_phone"], addr=o["ship_address"]),
            items=items, ship=dict(m=o["ship_method"], fee=o["ship_fee"]),
            pay=dict(m=o["pay_method"], paid=bool(o["paid"])), total=o["total"], disc=o["discount"],
            voucher=o["voucher"] or "", pts=o["points"], st=o["status"], track=o["tracking_code"] or "",
            flag=bool(o["needs_call"]), hist=hist))
    log = [dict(at=r["at"], m=r["message"]) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 60")]
    row = c.execute("SELECT value FROM settings WHERE key='order_seq'").fetchone()
    c.close()
    return dict(products=products, orders=orders, log=log, seq=int(row["value"]) if row else 100)


def put_state(d):
    """Kiểm tra dữ liệu rồi ghi vào các bảng quan hệ trong một giao dịch (all-or-nothing)."""
    if not isinstance(d, dict) or not isinstance(d.get("products"), list) or not isinstance(d.get("orders"), list):
        raise ValueError("Dữ liệu không hợp lệ")
    c = conn()
    try:
        c.execute("BEGIN")
        for t in ("order_history", "order_items", "orders", "products", "audit_log"):
            c.execute("DELETE FROM " + t)
        for p in d["products"]:
            c.execute("INSERT INTO products(id,name,category,price,stock,emoji,description,active) VALUES(?,?,?,?,?,?,?,?)",
                      (str(p["id"])[:40], str(p["name"])[:120], str(p["cat"])[:60], int(p["price"]), int(p["stock"]),
                       str(p.get("emoji", ""))[:8], str(p.get("desc", ""))[:300], 1 if p.get("on") else 0))
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
        for l in reversed(d.get("log", [])[:60]):
            c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (str(l["at"]), str(l["m"])[:300]))
        c.execute("INSERT INTO settings(key,value) VALUES('order_seq',?) "
                  "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(int(d.get("seq", 100))),))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=WEB, **k)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        if self.path == "/api/state":
            return self._json(200, get_state())
        if self.path == "/api/backup":
            tmp = os.path.join(DB_DIR, "_download.db")
            c, b = conn(), sqlite3.connect(tmp)
            c.backup(b)
            b.close()
            c.close()
            with open(tmp, "rb") as f:
                data = f.read()
            os.remove(tmp)
            return self._send(200, data, "application/octet-stream",
                              {"Content-Disposition": "attachment; filename=healthy_life_backup.db"})
        return super().do_GET()

    def do_PUT(self):
        if self.path != "/api/state":
            return self._json(404, {"error": "Không tìm thấy"})
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_BODY:
            return self._json(413, {"error": "Dữ liệu quá lớn"})
        try:
            put_state(json.loads(self.rfile.read(n)))
            self._json(200, {"ok": True})
        except (ValueError, KeyError, TypeError, sqlite3.Error) as e:
            self._json(400, {"error": "Dữ liệu không hợp lệ: %s" % e})


if __name__ == "__main__":
    init_db()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("Healthy Life đang chạy tại http://localhost:%d  (Ctrl+C để dừng)" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
