#!/usr/bin/env python3
"""Tạo dữ liệu MÔ PHỎNG để xem thử dashboard (đơn hàng, khách hàng, lịch sử trạng thái).

    python seed_demo.py                 nạp ~8 tháng dữ liệu vào cơ sở dữ liệu mặc định
    python seed_demo.py --db demo.db    ghi vào tệp khác (khuyến nghị: chạy server với HL_DB=demo.db)
    python seed_demo.py --force         xóa đơn hàng hiện có rồi nạp lại

Dữ liệu chỉ để minh họa, được đánh dấu demo_data=1 để dashboard hiện cảnh báo.
Không dùng cho cửa hàng thật: hãy dùng --force để xóa khi bắt đầu bán hàng.
"""
import argparse
import datetime as dt
import math
import os
import random
import sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.normpath(os.path.join(BASE, "..", "database"))
LOCAL = dt.timezone(dt.timedelta(hours=7))
ST = ["Chờ xác nhận", "Đã xác nhận", "Đang đóng gói", "Đã bàn giao vận chuyển", "Đang giao", "Đã giao"]

HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Phan", "Vũ", "Võ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý"]
DEM = ["Thị", "Văn", "Minh", "Ngọc", "Thanh", "Quốc", "Hồng", "Gia", "Anh", "Bảo"]
TEN = ["An", "Bình", "Châu", "Dung", "Giang", "Hà", "Hạnh", "Hiếu", "Hương", "Khoa", "Lan", "Linh", "Long", "Mai", "Nam", "Nga",
       "Phúc", "Quân", "Quyên", "Sơn", "Tâm", "Thảo", "Trang", "Trí", "Tuấn", "Uyên", "Vy", "Yến"]
PHUONG = ["Q.1", "Q.3", "Q.7", "Q.10", "Q.Bình Thạnh", "Q.Phú Nhuận", "TP.Thủ Đức", "Q.Gò Vấp", "Q.Tân Bình", "Hà Nội", "Đà Nẵng", "Cần Thơ"]
VOUCH = {"HEALTHY10": (150000, 10, 50000, None, 0), "NEWUSER": (100000, None, None, 20000, 0),
         "HEALTHYLIFE10": (0, 10, 1000000, None, 0), "FREESHIP": (200000, None, None, None, 1)}
# hũ ưa thích theo sản phẩm và cặp mua kèm
AFFINITY = {"P1": ["P2", "P5"], "P2": ["P1", "P4"], "P4": ["P5", "P3"], "P5": ["P4", "P1"], "P3": ["P2"], "P6": ["P1"], "P7": [], "P8": ["P2"], "P9": ["P2", "P6"]}
POP = {"P1": 26, "P2": 16, "P3": 12, "P4": 10, "P5": 12, "P6": 9, "P7": 7, "P8": 6, "P9": 5}


def iso(t):
    return t.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("HL_DB") or os.path.join(DB_DIR, "healthy_life.db"))
    ap.add_argument("--days", type=int, default=240)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(os.path.dirname(a.db), exist_ok=True)
    c = sqlite3.connect(a.db)
    c.row_factory = sqlite3.Row
    with open(os.path.join(DB_DIR, "schema.sql"), encoding="utf-8") as f:
        c.executescript(f.read())
    if c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
        if not a.force:
            raise SystemExit("Cơ sở dữ liệu đã có đơn hàng. Dùng --force nếu muốn xóa và nạp dữ liệu mô phỏng.")
        for t in ("order_history", "order_items", "orders", "customers", "audit_log"):
            c.execute("DELETE FROM " + t)
    prods = {r["id"]: dict(r) for r in c.execute("SELECT * FROM products")}
    ids = list(prods)

    now = dt.datetime.now(LOCAL)
    today = now.date()
    start = today - dt.timedelta(days=a.days - 1)

    # --- khách hàng: tốc độ mua, sở thích, ngày tham gia, ngày rời bỏ
    custs, phones = [], set()

    def new_cust(day):
        while True:
            ph = "09%08d" % rng.randrange(10 ** 8)
            if ph not in phones:
                phones.add(ph)
                break
        lam = max(0.08, rng.lognormvariate(math.log(0.55), 0.75))  # đơn/tháng
        pref = {p: POP.get(p, 5) * rng.uniform(0.3, 2.2) for p in ids}
        life = rng.expovariate(1 / 120.0) + 20  # ngày còn hoạt động
        return dict(phone=ph, name="%s %s %s" % (rng.choice(HO), rng.choice(DEM), rng.choice(TEN)), lam=lam, pref=pref,
                    join=day, end=day + dt.timedelta(days=life), city=rng.choices(PHUONG, [14, 12, 10, 8, 9, 6, 8, 6, 7, 6, 3, 2])[0],
                    pay=rng.choices(["cod", "qr", "wallet", "card"], [45, 30, 15, 10])[0], first=True, orders=0)

    for _ in range(40):
        custs.append(new_cust(start - dt.timedelta(days=rng.randrange(0, 60))))
    dow_f = [0.85, 0.9, 0.95, 1.0, 1.15, 1.35, 1.25]  # T2..CN
    spike, dip = today - dt.timedelta(days=36), today - dt.timedelta(days=19)
    promo = {today - dt.timedelta(days=d) for d in range(60, 63)}
    orders = []
    d = start
    while d <= today:
        growth = 1 + 0.9 * (d - start).days / a.days
        arrivals = rng.random() < 0.5 and 1 or 0
        n_new = int(rng.expovariate(1 / (0.9 * growth)) + (1.5 if d in promo else 0) + (4 if d == spike else 0))
        for _ in range(n_new):
            custs.append(new_cust(d))
        day_mult = dow_f[d.weekday()] * (1.7 if d in promo else 1) * (2.4 if d == spike else 1) * (0.15 if d == dip else 1)
        for cu in custs:
            if d < cu["join"] or d > cu["end"]:
                continue
            p = cu["lam"] / 30.0 * day_mult * 1.0
            if cu["first"] and d == cu["join"]:
                p = 1.0  # đơn đầu tiên khi tham gia
            elif d == cu["join"]:
                continue
            if rng.random() >= min(0.9, p):
                continue
            cu["first"] = False
            cu["orders"] += 1
            orders.append((d, cu))
        d += dt.timedelta(days=1)

    hour_w = [1, 1, 0, 0, 0, 1, 2, 4, 6, 7, 8, 10, 10, 7, 6, 6, 7, 8, 10, 12, 12, 10, 5, 2]
    seq = 100
    rows = []
    for d, cu in sorted(orders, key=lambda x: x[0]):
        hr = rng.choices(range(24), hour_w)[0]
        t = dt.datetime(d.year, d.month, d.day, hr, rng.randrange(60), rng.randrange(60), tzinfo=LOCAL)
        if t > now:
            t = now - dt.timedelta(minutes=rng.randrange(5, 600))
        rows.append((t, cu))
    rows.sort(key=lambda x: x[0])
    for t, cu in rows:
        seq += 1
        oid = "HL%06d" % seq
        # giỏ hàng: sản phẩm theo sở thích + mua kèm
        first = rng.choices(ids, [cu["pref"][p] for p in ids])[0]
        basket = {first: rng.choices([1, 2, 3], [70, 22, 8])[0]}
        if rng.random() < 0.5:
            for other in AFFINITY.get(first, []):
                if rng.random() < 0.55:
                    basket[other] = rng.choices([1, 2], [80, 20])[0]
        if rng.random() < 0.15:
            extra = rng.choices(ids, [cu["pref"][p] for p in ids])[0]
            basket[extra] = basket.get(extra, 0) + 1
        sub = sum(prods[p]["price"] * q for p, q in basket.items())
        code = ""
        if cu["orders"] == 1 and rng.random() < 0.6 and sub >= 100000:
            code = "NEWUSER"
        elif rng.random() < 0.2:
            code = rng.choice(["HEALTHY10", "HEALTHYLIFE10", "FREESHIP"])
        free, disc = sub >= 399000, 0
        if code:
            mn, pc, mx, off, fs = VOUCH[code]
            if sub >= mn:
                disc = min(mx or 10 ** 9, int(sub * pc / 100 + 0.5)) if pc else (off or 0)
                free = free or bool(fs)
            else:
                code = ""
        local = cu["city"] in ("Q.1", "Q.3", "Q.7", "Q.10", "Q.Bình Thạnh", "Q.Phú Nhuận", "TP.Thủ Đức", "Q.Gò Vấp", "Q.Tân Bình")
        ship = "exp" if local and rng.random() < 0.38 else "std"
        fee = 0 if free else (45000 if ship == "exp" else 25000)
        total = sub - disc + fee
        pay = cu["pay"] if rng.random() < 0.8 else rng.choice(["cod", "qr", "wallet", "card"])
        age_h = (now - t).total_seconds() / 3600.0
        hist, status, paid = [("Chờ xác nhận", t)], "Chờ xác nhận", 0
        cancel = (pay != "cod" and rng.random() < 0.04) or (pay == "cod" and rng.random() < 0.035)
        if cancel:
            if pay != "cod":
                hist.append(("Đã hủy", t + dt.timedelta(minutes=30)))
            else:
                hist += [("Đã xác nhận", t + dt.timedelta(hours=rng.uniform(0.3, 3))), ("Đã hủy", t + dt.timedelta(hours=rng.uniform(4, 30)))]
            status = "Đã hủy"
        else:
            cur = t
            if ship == "exp":
                steps = [("Đã xác nhận", rng.lognormvariate(math.log(0.15), 0.5)), ("Đang đóng gói", rng.lognormvariate(math.log(0.3), 0.4)),
                         ("Đã bàn giao vận chuyển", rng.lognormvariate(math.log(0.25), 0.4)),
                         ("Đang giao", rng.lognormvariate(math.log(0.2), 0.4)), ("Đã giao", rng.lognormvariate(math.log(0.6), 0.45))]
            else:
                steps = [("Đã xác nhận", rng.lognormvariate(math.log(1.2), 0.6)), ("Đang đóng gói", rng.lognormvariate(math.log(3), 0.5)),
                         ("Đã bàn giao vận chuyển", rng.lognormvariate(math.log(5), 0.5)),
                         ("Đang giao", rng.lognormvariate(math.log(20), 0.4)), ("Đã giao", rng.lognormvariate(math.log(30), 0.45))]
            for s, h in steps:
                nxt = cur + dt.timedelta(hours=h)
                if nxt > now:
                    break
                hist.append((s, nxt))
                cur, status = nxt, s
            if pay != "cod":
                paid = 1 if status != "Chờ xác nhận" or rng.random() < 0.7 else 0
                if paid:
                    hist.insert(1, ("Đã thu tiền", t + dt.timedelta(minutes=rng.randrange(1, 12))))
            elif status == "Đã giao":
                paid = 1
        c.execute("INSERT INTO customers(phone,name,address) VALUES(?,?,?) ON CONFLICT(phone) DO UPDATE SET name=excluded.name,address=excluded.address",
                  (cu["phone"], cu["name"], "%d Đường mẫu, %s" % (rng.randrange(1, 300), cu["city"])))
        c.execute("INSERT INTO orders(id,created_at,customer_phone,ship_address,ship_method,ship_fee,pay_method,paid,discount,voucher,points,total,status,tracking_code,needs_call) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (oid, iso(t), cu["phone"], "%s" % cu["city"], ship, fee, pay, paid, disc, code, total // 10000, total, status,
                   ("GRAB%d" % rng.randrange(10 ** 9, 10 ** 10)) if status in ("Đã bàn giao vận chuyển", "Đang giao", "Đã giao") else "",
                   1 if pay == "cod" and total >= 500000 else 0))
        for p, q in basket.items():
            c.execute("INSERT INTO order_items(order_id,product_id,name,price,qty) VALUES(?,?,?,?,?)", (oid, p, prods[p]["name"], prods[p]["price"], q))
        for s, ts in hist:
            c.execute("INSERT INTO order_history(order_id,status,at) VALUES(?,?,?)", (oid, s, iso(ts)))
    # tồn kho hiện tại: một số mặt hàng sắp hết để minh họa cảnh báo
    stock = {"P1": 14, "P2": 9, "P3": 85, "P4": 26, "P5": 5, "P6": 140, "P7": 0, "P8": 31, "P9": 22}
    for p, s in stock.items():
        c.execute("UPDATE products SET stock=? WHERE id=?", (s, p))
    c.execute("INSERT INTO settings(key,value) VALUES('order_seq',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(seq),))
    c.execute("INSERT INTO settings(key,value) VALUES('demo_data','1') ON CONFLICT(key) DO UPDATE SET value='1'")
    c.commit()
    n = c.execute("SELECT COUNT(*),COUNT(DISTINCT customer_phone),SUM(total) FROM orders").fetchone()
    print("Đã nạp %d đơn hàng của %d khách (tổng %s đ) vào %s" % (n[0], n[1], format(n[2], ","), a.db))
    print("Chạy máy chủ với dữ liệu này:  HL_DB=%s python server.py" % a.db)


if __name__ == "__main__":
    main()
