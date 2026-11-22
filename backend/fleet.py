"""Đội xe giao hàng và theo dõi vị trí thời gian thực (chỉ dùng thư viện chuẩn).

- Mỗi xe có mã thiết bị (token) riêng; điện thoại tài xế gửi vị trí qua POST /api/vehicle/location
  (trang driver.html làm sẵn việc này bằng GPS của trình duyệt).
- Mọi thay đổi vị trí và đơn hàng được phát qua HUB tới trang quản trị bằng Server-Sent Events.
- Điểm giao hàng chỉ là ước lượng theo quận/huyện trong địa chỉ (chưa dùng dịch vụ geocoding thật).
- Chế độ mô phỏng (HL_SIM=1) cho xe chạy giả lập để xem thử khi chưa có thiết bị thật.
"""
import collections
import datetime
import hashlib
import math
import queue
import random
import re
import secrets
import threading
import time
import unicodedata

STORE = (10.7746, 106.6857)  # 128 Nguyễn Đình Chiểu, Q.3 (xấp xỉ)
ONLINE_SEC = 90  # quá thời gian này không có vị trí mới thì coi là mất tín hiệu
TRAIL_LEN = 40
BOX = (8.0, 24.5, 102.0, 110.5)  # khung tọa độ Việt Nam, loại dữ liệu rác
KINDS = ("bike", "van", "truck")
DONE = ("Đã giao", "Đã hủy")
SIM = False


class Hub:
    """Phát sự kiện tới các kết nối SSE đang mở (mỗi kết nối một hàng đợi)."""

    def __init__(self):
        self.subs, self.lock = set(), threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.subs.discard(q)

    def publish(self, event, data):
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            try:
                q.put_nowait((event, data))
            except queue.Full:
                self.unsubscribe(q)  # client chậm: bỏ kết nối, trình duyệt sẽ tự nối lại và đồng bộ lại


HUB = Hub()
TRAILS = {}
_tlock = threading.Lock()


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t=None):
    return (t or utcnow()).isoformat().replace("+00:00", "Z")


def _th(token):
    return hashlib.sha256(token.encode()).hexdigest()


# ------------------------------------------------------------------ địa lý
def haversine(a, b):
    r = math.pi / 180
    dl, dn = (b[0] - a[0]) * r, (b[1] - a[1]) * r
    x = math.sin(dl / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin(dn / 2) ** 2
    return 12742.0 * math.asin(math.sqrt(x))  # km


def bearing(a, b):
    r = math.pi / 180
    y = math.sin((b[1] - a[1]) * r) * math.cos(b[0] * r)
    x = math.cos(a[0] * r) * math.sin(b[0] * r) - math.sin(a[0] * r) * math.cos(b[0] * r) * math.cos((b[1] - a[1]) * r)
    return (math.atan2(y, x) / r + 360) % 360


DIST_NUM = {"1": (10.7769, 106.7009), "2": (10.7873, 106.7498), "3": (10.7843, 106.6844), "4": (10.7578, 106.7013),
            "5": (10.7540, 106.6634), "6": (10.7481, 106.6352), "7": (10.7340, 106.7220), "8": (10.7240, 106.6280),
            "9": (10.8428, 106.8287), "10": (10.7746, 106.6667), "11": (10.7629, 106.6500), "12": (10.8672, 106.6414)}
DIST_NAME = {"binh thanh": (10.8106, 106.7091), "go vap": (10.8386, 106.6652), "phu nhuan": (10.7992, 106.6803),
             "tan binh": (10.8014, 106.6526), "tan phu": (10.7915, 106.6280), "binh tan": (10.7654, 106.6035),
             "thu duc": (10.8494, 106.7537), "nha be": (10.6953, 106.7370), "binh chanh": (10.6874, 106.5936),
             "hoc mon": (10.8830, 106.5920), "cu chi": (10.9733, 106.4930)}


def _norm(s):
    s = unicodedata.normalize("NFD", str(s).lower().replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def guess_dest(addr):
    """Ước lượng điểm giao (lat, lng) theo quận/huyện ghi trong địa chỉ; không nhận ra thì trả None."""
    n = _norm(addr or "")
    m = re.search(r"\b(?:quan|q|district)\s*\.?\s*(\d{1,2})\b", n)
    if m and m.group(1) in DIST_NUM:
        return DIST_NUM[m.group(1)]
    for k, v in DIST_NAME.items():
        if k in n:
            return v
    return None


# ------------------------------------------------------------------ xe
def vdict(r):
    online = False
    if r["updated_at"]:
        try:
            age = (utcnow() - datetime.datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))).total_seconds()
            online = age <= ONLINE_SEC
        except ValueError:
            pass
    busy = r["busy"] if "busy" in r.keys() else 0
    return dict(id=r["id"], plate=r["plate"], kind=r["kind"], driver=r["driver"], phone=r["phone"] or "", active=bool(r["active"]),
                lat=r["lat"], lng=r["lng"], speed=r["speed"], heading=r["heading"], at=r["updated_at"], online=online, busy=busy)


_Q = ("SELECT v.*, (SELECT COUNT(*) FROM orders o WHERE o.vehicle_id=v.id AND o.status NOT IN ('Đã giao','Đã hủy')) AS busy "
      "FROM vehicles v ")


def list_vehicles(c):
    out = []
    for r in c.execute(_Q + "ORDER BY v.id"):
        d = vdict(r)
        with _tlock:
            d["trail"] = list(TRAILS.get(r["id"], []))
        out.append(d)
    return out


def create_vehicle(c, d):
    plate = str(d.get("plate") or "").strip().upper()[:20]
    driver = str(d.get("driver") or "").strip()[:60]
    phone = str(d.get("phone") or "").strip()[:15]
    kind = str(d.get("kind") or "bike")
    if not plate or not driver:
        raise ValueError("Cần nhập biển số và tên tài xế")
    if kind not in KINDS:
        raise ValueError("Loại xe không hợp lệ")
    if phone and not re.fullmatch(r"0\d{9}", phone):
        raise ValueError("Số điện thoại tài xế không hợp lệ")
    if c.execute("SELECT 1 FROM vehicles WHERE plate=?", (plate,)).fetchone():
        raise ValueError("Biển số này đã có trong đội xe")
    nums = [int(r["id"][2:]) for r in c.execute("SELECT id FROM vehicles") if r["id"][2:].isdigit()]
    vid, token = "XE%02d" % (max(nums, default=0) + 1), "hlv_" + secrets.token_urlsafe(24)
    c.execute("INSERT INTO vehicles(id,plate,kind,driver,phone,token_hash,active) VALUES(?,?,?,?,?,?,1)",
              (vid, plate, kind, driver, phone, _th(token)))
    c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (iso(), "Thêm xe %s (%s) – tài xế %s" % (vid, plate, driver)))
    c.commit()
    return vid, token


def rotate_token(c, vid):
    if not c.execute("SELECT 1 FROM vehicles WHERE id=?", (vid,)).fetchone():
        raise ValueError("Không tìm thấy xe")
    token = "hlv_" + secrets.token_urlsafe(24)
    c.execute("UPDATE vehicles SET token_hash=? WHERE id=?", (_th(token), vid))
    c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (iso(), "Cấp lại mã thiết bị xe %s" % vid))
    c.commit()
    return token


def set_active(c, vid, on):
    c.execute("UPDATE vehicles SET active=? WHERE id=?", (1 if on else 0, vid))
    c.commit()


def delete_vehicle(c, vid):
    if c.execute("SELECT 1 FROM orders WHERE vehicle_id=? AND status NOT IN ('Đã giao','Đã hủy')", (vid,)).fetchone():
        raise ValueError("Xe đang được gán cho đơn chưa hoàn tất. Hãy gỡ gán hoặc hoàn tất đơn trước.")
    c.execute("UPDATE orders SET vehicle_id=NULL WHERE vehicle_id=?", (vid,))
    c.execute("DELETE FROM vehicles WHERE id=?", (vid,))
    c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (iso(), "Xóa xe %s" % vid))
    c.commit()
    with _tlock:
        TRAILS.pop(vid, None)


def auth_vehicle(c, token):
    if not token or len(token) > 100:
        return None
    return c.execute("SELECT * FROM vehicles WHERE token_hash=?", (_th(token),)).fetchone()


def set_location(c, vid, lat, lng, speed=None, heading=None):
    try:
        lat, lng = float(lat), float(lng)
        speed = None if speed is None else max(0.0, min(160.0, float(speed)))
        heading = None if heading is None else float(heading) % 360
    except (TypeError, ValueError):
        raise ValueError("Tọa độ không hợp lệ")
    if not (BOX[0] <= lat <= BOX[1] and BOX[2] <= lng <= BOX[3]):
        raise ValueError("Tọa độ nằm ngoài lãnh thổ Việt Nam")
    with _tlock:
        tr = TRAILS.setdefault(vid, collections.deque(maxlen=TRAIL_LEN))
        prev = tr[-1] if tr else None
        if heading is None and prev and haversine(prev, (lat, lng)) > 0.005:
            heading = bearing(prev, (lat, lng))
        tr.append([round(lat, 6), round(lng, 6)])
    ts = iso()
    c.execute("UPDATE vehicles SET lat=?,lng=?,speed=?,heading=?,updated_at=? WHERE id=?", (lat, lng, speed, heading, ts, vid))
    c.commit()
    ev = dict(id=vid, lat=lat, lng=lng, speed=speed, heading=heading, at=ts, online=True)
    HUB.publish("vehicle", ev)
    return ev


def assign(c, oid, vid):
    """Gán (hoặc gỡ gán nếu vid rỗng) xe cho đơn. Tự ước lượng điểm giao theo địa chỉ nếu chưa có."""
    o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o:
        raise ValueError("Không tìm thấy đơn hàng")
    if o["status"] in DONE:
        raise ValueError("Đơn đã kết thúc, không thể đổi xe")
    if vid:
        v = c.execute("SELECT * FROM vehicles WHERE id=? AND active=1", (vid,)).fetchone()
        if not v:
            raise ValueError("Không tìm thấy xe hoặc xe đang tạm ngưng")
        if o["dest_lat"] is None:
            g = guess_dest(o["ship_address"])
            if g is None and SIM:  # chỉ ở chế độ mô phỏng: chọn ngẫu nhiên một quận để xe có chỗ chạy tới
                g = random.choice(list(DIST_NUM.values()))
            if g:
                c.execute("UPDATE orders SET dest_lat=?,dest_lng=? WHERE id=?", (g[0], g[1], oid))
        msg = "Gán xe %s (%s) cho đơn %s" % (v["id"], v["plate"], oid)
    else:
        msg = "Gỡ xe khỏi đơn %s" % oid
    c.execute("UPDATE orders SET vehicle_id=? WHERE id=?", (vid or None, oid))
    c.execute("INSERT INTO audit_log(at,message) VALUES(?,?)", (iso(), msg))
    c.commit()


def driver_orders(c, vid):
    out = []
    for o in c.execute("SELECT * FROM orders WHERE vehicle_id=? AND status NOT IN ('Đã giao','Đã hủy') ORDER BY created_at", (vid,)):
        cu = c.execute("SELECT name FROM customers WHERE phone=?", (o["customer_phone"],)).fetchone()
        items = ", ".join("%s × %d" % (i["name"], i["qty"]) for i in c.execute("SELECT * FROM order_items WHERE order_id=?", (o["id"],)))
        out.append(dict(id=o["id"], st=o["status"], name=cu["name"] if cu else "", phone=o["customer_phone"], addr=o["ship_address"],
                        items=items, total=o["total"], collect=o["total"] if o["pay_method"] == "cod" and not o["paid"] else 0,
                        dest=[o["dest_lat"], o["dest_lng"]] if o["dest_lat"] is not None else None, call=bool(o["needs_call"])))
    return out


def seed_demo_fleet(c):
    """Chế độ mô phỏng: tạo sẵn vài xe nếu đội xe còn trống."""
    if c.execute("SELECT 1 FROM vehicles").fetchone():
        return
    for plate, kind, name, phone in (("59X1-123.45", "bike", "Nguyễn Văn Hải", "0901000001"), ("59P2-678.90", "bike", "Trần Quốc Bảo", "0901000002"),
                                     ("51D-456.78", "van", "Lê Minh Tuấn", "0901000003")):
        create_vehicle(c, dict(plate=plate, kind=kind, driver=name, phone=phone))


def sim_loop(connf, act, factor=10.0):
    """Mô phỏng: xe nhận đơn đã bàn giao, chạy thẳng tới điểm giao (nhanh `factor` lần), rồi giao xong.
    Xe rảnh đi lòng vòng quanh cửa hàng. Chỉ để xem thử; vị trí không đi theo đường thật."""
    rnd, tick = random.Random(), 2.0
    while True:
        time.sleep(tick)
        try:
            c = connf()
            try:
                for v in c.execute("SELECT * FROM vehicles WHERE active=1").fetchall():
                    pos = (v["lat"], v["lng"]) if v["lat"] is not None else (STORE[0] + rnd.uniform(-.003, .003), STORE[1] + rnd.uniform(-.003, .003))
                    target, tid = None, None
                    for o in c.execute("SELECT id,status,dest_lat,dest_lng FROM orders WHERE vehicle_id=? AND status IN "
                                       "('Đã bàn giao vận chuyển','Đang giao') ORDER BY created_at", (v["id"],)).fetchall():
                        if o["status"] == "Đã bàn giao vận chuyển":
                            try:
                                act(o["id"], "pick", "Tài xế %s" % v["plate"], v["id"])
                            except Exception:
                                continue
                        if o["dest_lat"] is not None:
                            target, tid = (o["dest_lat"], o["dest_lng"]), o["id"]
                            break
                    if target:
                        speed = 30.0 if v["kind"] == "bike" else 24.0
                        step = speed / 3.6 * tick * factor / 1000.0  # km mỗi nhịp
                        d = haversine(pos, target)
                        if d <= max(step, 0.06):
                            new = target
                            try:
                                act(tid, "deliver", "Tài xế %s" % v["plate"], v["id"])
                            except Exception:
                                pass
                            speed = 0.0
                        else:
                            f = step / d
                            new = (pos[0] + (target[0] - pos[0]) * f + rnd.uniform(-1e-5, 1e-5), pos[1] + (target[1] - pos[1]) * f + rnd.uniform(-1e-5, 1e-5))
                    else:
                        speed = rnd.uniform(0, 12)
                        pull = 0.3 if haversine(pos, STORE) > 1.5 else 0.0
                        new = (pos[0] + rnd.uniform(-.0004, .0004) + (STORE[0] - pos[0]) * pull * .1, pos[1] + rnd.uniform(-.0004, .0004) + (STORE[1] - pos[1]) * pull * .1)
                    set_location(c, v["id"], new[0], new[1], speed)
            finally:
                c.close()
        except Exception:
            pass
