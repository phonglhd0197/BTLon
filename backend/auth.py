"""Tài khoản người dùng (đăng ký, đăng nhập, phiên) và xác thực quản trị. Chỉ dùng thư viện chuẩn.

- Mật khẩu băm PBKDF2-HMAC-SHA256 (200.000 vòng, muối ngẫu nhiên), so sánh hằng thời gian.
- Phiên: mã ngẫu nhiên 256 bit gửi qua cookie HttpOnly; trong CSDL chỉ lưu SHA-256 của mã.
- Giới hạn đăng nhập sai theo tài khoản và theo IP (lưu trong bộ nhớ, mất khi khởi động lại).
- Quản trị: mật khẩu (HL_ADMIN_PASSWORD) + mã TOTP (HL_ADMIN_TOTP_SECRET). Không có mật khẩu mặc định:
  chưa đặt biến môi trường thì quản trị tắt. HL_DEMO=1 chỉ bật tài khoản demo để trình diễn.
- Đăng nhập quản trị sai bị khóa theo IP (5 lần / 15 phút), không khóa chung cho mọi người.
"""
import base64
import datetime
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import struct
import threading
import time

ITER = 200_000
COOKIE = "hl_session"
CUSTOMER_TTL = 14 * 86400
ADMIN_TTL = 8 * 3600
PHONE_RE = re.compile(r"0\d{9}")
EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+")
DEMO_ADMIN_PW, DEMO_OTP = "admin123", "123456"


class RateLimited(Exception):
    pass


class Limiter:
    """Cho phép tối đa `limit` lần trong `window` giây cho mỗi khóa."""

    def __init__(self, limit, window):
        self.limit, self.window, self.hits, self.lock = limit, window, {}, threading.Lock()

    def _live(self, key, now):
        lst = [t for t in self.hits.get(key, []) if now - t < self.window]
        if lst:
            self.hits[key] = lst
        else:
            self.hits.pop(key, None)
        return lst

    def blocked(self, key):
        with self.lock:
            return len(self._live(key, time.time())) >= self.limit

    def wait(self, key):
        with self.lock:
            lst = self._live(key, time.time())
            return max(1, int((lst[0] + self.window - time.time()) / 60) + 1) if lst else 0

    def hit(self, key):
        with self.lock:
            now = time.time()
            if len(self.hits) > 20000:
                for k in list(self.hits):
                    self._live(k, now)
            self._live(key, now)
            self.hits.setdefault(key, []).append(now)

    def clear(self, key):
        with self.lock:
            self.hits.pop(key, None)


LOGIN_ID, LOGIN_IP, REGISTER = Limiter(5, 900), Limiter(40, 900), Limiter(10, 3600)
ADMIN_IP = Limiter(5, 900)  # quản trị: khóa theo IP, không khóa theo tên để tránh bị khóa hàng loạt


def now_s():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def hash_pw(pw):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, ITER)
    return "pbkdf2_sha256$%d$%s$%s" % (ITER, salt.hex(), dk.hex())


def check_pw(pw, stored):
    try:
        _, it, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


DUMMY = hash_pw("khong-co-nguoi-dung")  # băm giả để thời gian phản hồi không lộ tài khoản có tồn tại hay không


def pub(r):
    return dict(id=r["id"], name=r["name"], phone=r["phone"], email=r["email"] or "", addr=r["address"] or "", role=r["role"])


# ------------------------------------------------------------------ phiên
def _th(token):
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(c, uid, ttl):
    token = secrets.token_urlsafe(32)
    c.execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
    c.execute("INSERT INTO sessions(token_hash,user_id,expires) VALUES(?,?,?)", (_th(token), uid, int(time.time()) + ttl))
    c.commit()
    return token


def session_user(c, token):
    if not token:
        return None
    r = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?",
                  (_th(token), int(time.time()))).fetchone()
    return pub(r) if r else None


def destroy_session(c, token):
    if token:
        c.execute("DELETE FROM sessions WHERE token_hash=?", (_th(token),))
        c.commit()


# ------------------------------------------------------------------ khách hàng
def _clean_pw(pw):
    if not isinstance(pw, str) or not 8 <= len(pw) <= 128:
        raise ValueError("Mật khẩu phải từ 8 đến 128 ký tự")
    return pw


def _email(v):
    v = str(v or "").strip().lower()[:120]
    if v and not EMAIL_RE.fullmatch(v):
        raise ValueError("Email không hợp lệ")
    return v


def register(c, d, ip):
    if REGISTER.blocked(ip):
        raise RateLimited("Bạn đăng ký quá nhiều lần. Hãy thử lại sau.")
    REGISTER.hit(ip)
    name = str(d.get("name") or "").strip()[:80]
    phone = str(d.get("phone") or "").strip()
    email = _email(d.get("email"))
    addr = str(d.get("addr") or "").strip()[:250]
    pw = _clean_pw(d.get("password"))
    if len(name) < 2:
        raise ValueError("Vui lòng nhập họ tên")
    if not PHONE_RE.fullmatch(phone):
        raise ValueError("Số điện thoại phải gồm 10 số, bắt đầu bằng 0")
    if pw == phone:
        raise ValueError("Mật khẩu không được trùng số điện thoại")
    if c.execute("SELECT 1 FROM users WHERE phone=?", (phone,)).fetchone():
        raise ValueError("Số điện thoại này đã có tài khoản. Hãy đăng nhập.")
    if email and c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ValueError("Email này đã có tài khoản")
    try:
        cur = c.execute("INSERT INTO users(phone,email,name,address,pw_hash,role,created_at) VALUES(?,?,?,?,?,'customer',?)",
                        (phone, email or None, name, addr, hash_pw(pw), now_s()))
        c.execute("INSERT OR IGNORE INTO customers(phone,name,address) VALUES(?,?,?)", (phone, name, addr))
        c.commit()
    except sqlite3.IntegrityError:
        raise ValueError("Số điện thoại hoặc email đã có tài khoản")
    u = pub(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
    return u, create_session(c, u["id"], CUSTOMER_TTL)


def _guard(ident, ip):
    for lim, key in ((LOGIN_ID, "id:" + ident), (LOGIN_IP, "ip:" + ip)):
        if lim.blocked(key):
            raise RateLimited("Đăng nhập sai quá nhiều lần. Thử lại sau khoảng %d phút." % lim.wait(key))


def _fail(ident, ip):
    LOGIN_ID.hit("id:" + ident)
    LOGIN_IP.hit("ip:" + ip)


def login(c, ident, pw, ip):
    ident = str(ident or "").strip().lower()[:120]
    pw = str(pw or "")[:200]
    _guard(ident, ip)
    r = c.execute("SELECT * FROM users WHERE role='customer' AND (phone=? OR email=?)", (ident, ident)).fetchone()
    ok = check_pw(pw, r["pw_hash"] if r else DUMMY)
    if not (r and ok):
        _fail(ident, ip)
        raise ValueError("Sai số điện thoại/email hoặc mật khẩu")
    LOGIN_ID.clear("id:" + ident)
    return pub(r), create_session(c, r["id"], CUSTOMER_TTL)


def update_profile(c, uid, d):
    name = str(d.get("name") or "").strip()[:80]
    addr = str(d.get("addr") or "").strip()[:250]
    email = _email(d.get("email"))
    if len(name) < 2:
        raise ValueError("Vui lòng nhập họ tên")
    if email and c.execute("SELECT 1 FROM users WHERE email=? AND id!=?", (email, uid)).fetchone():
        raise ValueError("Email này đã có tài khoản khác")
    c.execute("UPDATE users SET name=?,address=?,email=? WHERE id=?", (name, addr, email or None, uid))
    c.commit()
    return pub(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())


def change_password(c, uid, old, new, keep_token):
    r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not r or not check_pw(str(old or ""), r["pw_hash"]):
        raise ValueError("Mật khẩu hiện tại không đúng")
    c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(_clean_pw(new)), uid))
    c.execute("DELETE FROM sessions WHERE user_id=? AND token_hash!=?", (uid, _th(keep_token or "")))
    c.commit()


# ------------------------------------------------------------------ quản trị
def totp(secret, t=None, step=30, digits=6):
    s = secret.upper().replace(" ", "")
    key = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(key, struct.pack(">Q", int((t or time.time()) // step)), "sha1").digest()
    o = h[-1] & 15
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits).zfill(digits)


def verify_totp(secret, code):
    code, ok = str(code or "").strip(), False
    for k in (-1, 0, 1):
        ok |= hmac.compare_digest(totp(secret, time.time() + 30 * k), code)
    return ok


DISABLED = "!tat"  # không phải chuỗi băm hợp lệ: quản trị tắt cho tới khi đặt HL_ADMIN_PASSWORD


def demo_mode():
    return os.environ.get("HL_DEMO") == "1"


def ensure_admin(c):
    """Thiết lập tài khoản quản trị từ biến môi trường (không còn mật khẩu mặc định trong mã nguồn):
    - HL_ADMIN_PASSWORD (kèm HL_ADMIN_TOTP_SECRET) bật quản trị;
    - chưa đặt biến nào thì quản trị tắt;
    - HL_DEMO=1 bật tài khoản demo admin123 / 123456, chỉ dùng để trình diễn.
    Trả về (đang_demo, đã_đủ_cấu_hình).
    """
    env_pw = os.environ.get("HL_ADMIN_PASSWORD", "")
    demo = demo_mode()
    target = env_pw or (DEMO_ADMIN_PW if demo else "")
    r = c.execute("SELECT * FROM users WHERE role='admin'").fetchone()
    if r is None:
        c.execute("INSERT INTO users(phone,name,pw_hash,role,created_at) VALUES('admin','Quản trị viên',?,'admin',?)",
                  (hash_pw(target) if target else DISABLED, now_s()))
    elif not target:
        if r["pw_hash"] != DISABLED:  # xóa mật khẩu cũ (kể cả mật khẩu demo) khi không còn được cấu hình
            c.execute("UPDATE users SET pw_hash=? WHERE id=?", (DISABLED, r["id"]))
            c.execute("DELETE FROM sessions WHERE user_id=?", (r["id"],))
    elif not check_pw(target, r["pw_hash"]):
        c.execute("UPDATE users SET pw_hash=? WHERE id=?", (hash_pw(target), r["id"]))
        c.execute("DELETE FROM sessions WHERE user_id=?", (r["id"],))
    c.commit()
    return demo, bool(env_pw and os.environ.get("HL_ADMIN_TOTP_SECRET", "").strip())


def admin_login(c, pw, otp, ip):
    key = "ip:" + ip
    if ADMIN_IP.blocked(key):
        raise RateLimited("Đăng nhập quản trị sai quá nhiều lần. Thử lại sau 15 phút.")
    r = c.execute("SELECT * FROM users WHERE role='admin'").fetchone()
    secret = os.environ.get("HL_ADMIN_TOTP_SECRET", "").strip()
    try:
        if secret:
            ok_otp = verify_totp(secret, otp)
        else:  # không có TOTP thì chỉ chấp nhận mã demo, và chỉ khi bật HL_DEMO=1
            ok_otp = demo_mode() and hmac.compare_digest(str(otp or "").strip(), DEMO_OTP)
    except Exception:  # khóa TOTP cấu hình sai thì không cho đăng nhập
        ok_otp = False
    ok_pw = check_pw(str(pw or "")[:200], r["pw_hash"] if r else DUMMY)
    if not (r and ok_pw and ok_otp):  # không cho biết sai yếu tố nào
        ADMIN_IP.hit(key)
        raise ValueError("Sai mật khẩu hoặc mã xác thực")
    ADMIN_IP.clear(key)
    return pub(r), create_session(c, r["id"], ADMIN_TTL)
