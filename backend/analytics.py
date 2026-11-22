"""Phân tích dữ liệu và học máy cho dashboard quản trị (chỉ dùng thư viện chuẩn Python).

Các thuật toán:
  - Dự báo doanh thu: Holt-Winters (xu hướng tắt dần + mùa vụ 7 ngày), hồi quy OLS (xu hướng + thứ trong tuần),
    trung bình theo thứ; chọn mô hình có sai số WAPE thấp nhất trên tập kiểm tra (backtest 14 ngày).
  - Phát hiện bất thường: độ lệch so với trung vị cùng thứ, chuẩn hóa bằng MAD (robust z-score).
  - Phân khúc khách hàng: RFM + K-means (k-means++), chọn k bằng hệ số Silhouette.
  - Dự đoán khả năng mua lại trong 30 ngày: hồi quy logistic (Newton-Raphson, L2), đánh giá bằng AUC.
  - Gợi ý mua kèm: luật kết hợp dạng cặp (support, confidence, lift).
  - Dự báo nhu cầu và tồn kho: san mượt mũ (EWMA) + điểm đặt hàng lại theo tồn kho an toàn.
"""
import datetime as dt
import math
import random
import re
import statistics
import zlib
from collections import Counter, defaultdict

LOCAL = dt.timezone(dt.timedelta(hours=7))
ST = ["Chờ xác nhận", "Đã xác nhận", "Đang đóng gói", "Đã bàn giao vận chuyển", "Đang giao", "Đã giao"]
CANCEL = "Đã hủy"
FREESHIP = 399000
LEAD_DAYS = 7  # thời gian chờ nhập hàng giả định
DOW = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
_CACHE = {}


def _dt(s):
    return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(LOCAL)


def _mask(p):
    p = str(p)
    return p[:4] + "***" + p[-3:] if len(p) >= 8 else p


def _pct(a, b):
    return None if not b else round((a - b) * 100.0 / b, 1)


def _base(name):
    return re.sub(r"\s*\(.*?\)\s*$", "", name).strip()


# ---------------------------------------------------------------- dữ liệu
def load(c):
    orders, byid = [], {}
    names = {r["phone"]: r["name"] for r in c.execute("SELECT phone,name FROM customers")}
    for o in c.execute("SELECT * FROM orders"):
        x = dict(id=o["id"], t=_dt(o["created_at"]), phone=o["customer_phone"], name=names.get(o["customer_phone"], ""),
                 total=o["total"], fee=o["ship_fee"], pay=o["pay_method"], paid=bool(o["paid"]), disc=o["discount"],
                 voucher=o["voucher"] or "", st=o["status"], ship=o["ship_method"], items=[], hist=[])
        orders.append(x)
        byid[x["id"]] = x
    for i in c.execute("SELECT * FROM order_items"):
        if i["order_id"] in byid:
            byid[i["order_id"]]["items"].append((i["product_id"], i["name"], i["price"], i["qty"]))
    for h in c.execute("SELECT * FROM order_history ORDER BY rowid"):
        if h["order_id"] in byid:
            byid[h["order_id"]]["hist"].append((h["status"], _dt(h["at"])))
    for x in orders:
        x["sub"] = sum(p * q for _, _, p, q in x["items"])
    products = [dict(id=r["id"], name=r["name"], cat=r["category"], price=r["price"], stock=r["stock"], on=bool(r["active"]))
                for r in c.execute("SELECT * FROM products ORDER BY rowid")]
    demo = c.execute("SELECT value FROM settings WHERE key='demo_data'").fetchone()
    return dict(orders=orders, products=products, demo=bool(demo))


def _series(valid, start, end, key=lambda o: o["total"]):
    rev, cnt = defaultdict(float), defaultdict(int)
    for o in valid:
        d = o["t"].date()
        rev[d] += key(o)
        cnt[d] += 1
    days, d = [], start
    while d <= end:
        days.append(d)
        d += dt.timedelta(days=1)
    return days, [rev[d] for d in days], [cnt[d] for d in days]


# ---------------------------------------------------------------- đại số nhỏ
def solve(A, b):
    n = len(A)
    M = [A[i][:] + [b[i]] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            continue
        pv = M[i][i]
        M[i] = [v / pv for v in M[i]]
        for r in range(n):
            if r != i and M[r][i]:
                f = M[r][i]
                M[r] = [x - f * y for x, y in zip(M[r], M[i])]
    return [M[i][n] for i in range(n)]


def auc(scores, labels):
    n1 = sum(labels)
    n0 = len(labels) - n1
    if not n1 or not n0:
        return None
    pairs = sorted(zip(scores, labels))
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        r = (i + j) / 2.0 + 1
        rank_sum += r * sum(1 for k in range(i, j + 1) if pairs[k][1] == 1)
        i = j + 1
    return (rank_sum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


# ---------------------------------------------------------------- dự báo doanh thu
def _hw_run(y, m, a, b, g, phi):
    l = sum(y[:m]) / m
    bt = (sum(y[m:2 * m]) - sum(y[:m])) / float(m * m)
    s = [y[i] - l for i in range(m)]
    sse = 0.0
    for t in range(len(y)):
        st = s[t % m]
        e = y[t] - (l + phi * bt + st)
        if t >= m:
            sse += e * e
        ln = a * (y[t] - st) + (1 - a) * (l + phi * bt)
        bt = b * (ln - l) + (1 - b) * phi * bt
        s[t % m] = g * (y[t] - ln) + (1 - g) * st
        l = ln
    return sse, (l, bt, s, len(y))


def m_hw(train, h, m=7, phi=0.95):
    best = None
    for a in (0.1, 0.2, 0.35, 0.5):
        for b in (0.01, 0.05, 0.1):
            for g in (0.1, 0.25, 0.4):
                sse, state = _hw_run(train, m, a, b, g, phi)
                if best is None or sse < best[0]:
                    best = (sse, state, (a, b, g))
    l, bt, s, n = best[1]
    out, damp = [], 0.0
    for k in range(1, h + 1):
        damp += phi ** k
        out.append(max(0.0, l + damp * bt + s[(n + k - 1) % m]))
    return out


def m_seasonal_mean(train, h, m=7, weeks=4):
    n, out = len(train), []
    for k in range(1, h + 1):
        t = n + k - 1
        j = (t - n) // m + 1
        vals = []
        while len(vals) < weeks and t - m * j >= 0:
            vals.append(train[t - m * j])
            j += 1
        out.append(sum(vals) / len(vals) if vals else (sum(train) / n))
    return out


def m_ols(train, h, m=7, window=112):
    y = train[-window:]
    n0 = len(train) - len(y)
    n = len(y)

    def row(t):
        dow = (n0 + t) % m
        return [1.0, t / float(max(1, n))] + [1.0 if dow == d else 0.0 for d in range(1, m)]

    X = [row(t) for t in range(n)]
    d = len(X[0])
    A = [[sum(x[i] * x[j] for x in X) + (1e-3 if i == j else 0) for j in range(d)] for i in range(d)]
    bv = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(d)]
    w = solve(A, bv)
    return [max(0.0, sum(wi * xi for wi, xi in zip(w, row(n + k)))) for k in range(h)]


MODELS = [("Holt-Winters (xu hướng + mùa vụ tuần)", m_hw), ("Hồi quy OLS (xu hướng + thứ trong tuần)", m_ols),
          ("Trung bình theo thứ (4 tuần gần nhất)", m_seasonal_mean)]


def forecast(days, y, horizon=30):
    if len(y) < 42:
        return dict(ok=False, reason="Cần ít nhất 42 ngày dữ liệu để dự báo (hiện có %d ngày)." % len(y))
    hold = 14
    train, test = y[:-hold], y[-hold:]
    res = []
    for name, fn in MODELS:
        try:
            p = fn(train, hold)
        except Exception:
            continue
        err = [a - b for a, b in zip(test, p)]
        tot = max(1.0, sum(test))
        res.append(dict(model=name, fn=fn, wape=round(sum(abs(e) for e in err) * 100 / tot, 1),
                        mae=round(sum(abs(e) for e in err) / hold), rmse=round(math.sqrt(sum(e * e for e in err) / hold)),
                        bias=round(sum(err) * 100 / tot, 1)))
    best = min(res, key=lambda r: r["wape"])
    pred = best["fn"](y, horizon)
    sigma = max(best["rmse"], 0.08 * (sum(y[-28:]) / 28.0))
    last = days[-1]
    pts = []
    for k, v in enumerate(pred, 1):
        w = 1.96 * sigma * (1 + 0.012 * k)
        pts.append(dict(d=(last + dt.timedelta(days=k)).isoformat(), yhat=round(v, -3), lo=round(max(0, v - w), -3), hi=round(v + w, -3)))
    last7 = sum(y[-7:])
    return dict(ok=True, model=best["model"], horizon=horizon, points=pts,
                backtest=[dict(model=r["model"], wape=r["wape"], mae=r["mae"], rmse=r["rmse"], bias=r["bias"], best=r is best) for r in res],
                next7=round(sum(p["yhat"] for p in pts[:7]), -3), next14=round(sum(p["yhat"] for p in pts[:14]), -3),
                next30=round(sum(p["yhat"] for p in pts[:30]), -3), last7=round(last7), last30=round(sum(y[-30:])),
                growth7=_pct(sum(p["yhat"] for p in pts[:7]), last7), sigma=round(sigma, -3), holdout=hold,
                history=[dict(d=d.isoformat(), v=round(v)) for d, v in zip(days[-60:], y[-60:])])


def anomalies(days, y, limit=90):
    exp, res = [], []
    for i in range(len(y)):
        same = [y[i - 7 * j] for j in range(1, 5) if i - 7 * j >= 0]
        e = statistics.median(same) if len(same) >= 2 else None
        exp.append(e)
        res.append(None if e is None else y[i] - e)
    r = [v for v in res if v is not None]
    if len(r) < 14:
        return []
    med = statistics.median(r)
    mad = statistics.median([abs(v - med) for v in r]) * 1.4826
    mad = max(mad, 0.05 * (sum(y) / len(y)), 1.0)
    out = []
    for i in range(max(0, len(y) - limit), len(y)):
        if res[i] is None:
            continue
        z = (res[i] - med) / mad
        if abs(z) >= 3.0:
            out.append(dict(d=days[i].isoformat(), actual=round(y[i]), expected=round(exp[i]), z=round(z, 1),
                            diff=_pct(y[i], exp[i]), kind="Đột biến tăng" if z > 0 else "Sụt giảm bất thường"))
    out.sort(key=lambda a: -abs(a["z"]))
    return out[:8]


# ---------------------------------------------------------------- khách hàng
def _d2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(X, k, seed=7):
    rng, best = random.Random(seed), None
    for _ in range(6):
        C = [list(rng.choice(X))]
        while len(C) < k:
            d = [min(_d2(x, c) for c in C) for x in X]
            s = sum(d)
            if s <= 0:
                C.append(list(rng.choice(X)))
                continue
            r, a = rng.random() * s, 0.0
            for x, w in zip(X, d):
                a += w
                if a >= r:
                    C.append(list(x))
                    break
            else:
                C.append(list(X[-1]))
        lab = [-1] * len(X)
        for it in range(60):
            nl = [min(range(k), key=lambda j: _d2(x, C[j])) for x in X]
            if nl == lab:
                break
            lab = nl
            for j in range(k):
                m = [x for x, l in zip(X, lab) if l == j]
                if m:
                    C[j] = [sum(col) / len(m) for col in zip(*m)]
        inertia = sum(_d2(x, C[l]) for x, l in zip(X, lab))
        if best is None or inertia < best[0]:
            best = (inertia, lab[:], [c[:] for c in C])
    return best


def silhouette(X, lab, k, cap=300):
    step = max(1, len(X) // cap)
    idx = list(range(0, len(X), step))
    Xs, ls = [X[i] for i in idx], [lab[i] for i in idx]
    out = []
    for i in range(len(Xs)):
        ds, cn = [0.0] * k, [0] * k
        for j in range(len(Xs)):
            if i != j:
                ds[ls[j]] += math.sqrt(_d2(Xs[i], Xs[j]))
                cn[ls[j]] += 1
        if not cn[ls[i]]:
            continue
        a = ds[ls[i]] / cn[ls[i]]
        b = min((ds[j] / cn[j] for j in range(k) if j != ls[i] and cn[j]), default=0)
        out.append((b - a) / max(a, b) if max(a, b) > 0 else 0)
    return sum(out) / len(out) if out else 0.0


SEG_ACTION = {
    "VIP trung thành": "Ưu đãi độc quyền, quà tặng sinh nhật, mời dùng thử sản phẩm mới trước.",
    "Tiềm năng": "Gợi ý combo mua kèm, ưu đãi đơn thứ 3 để tăng tần suất mua.",
    "Khách mới": "Chuỗi chào mừng và mã giảm cho đơn thứ hai trong 14 ngày.",
    "Nguy cơ rời bỏ": "Gửi mã win-back có hạn dùng, nhắc mua lại đúng chu kỳ.",
}


def _name_segments(stats):
    """stats: list of dict(R,F,M) theo từng cụm. Trả về tên cho từng cụm."""
    names, left = {}, set(range(len(stats)))
    z = lambda key, rev=False: sorted(left, key=lambda j: stats[j][key], reverse=rev)
    if len(left) >= 2:
        best = max(left, key=lambda j: stats[j]["F"] * stats[j]["M"] / (1 + stats[j]["R"] / 30.0))
        names[best] = "VIP trung thành"
        left.discard(best)
    if len(left) >= 2:
        worst = max(left, key=lambda j: stats[j]["R"])
        names[worst] = "Nguy cơ rời bỏ"
        left.discard(worst)
    if len(left) >= 2:
        new = min(left, key=lambda j: (stats[j]["F"], stats[j]["R"]))
        names[new] = "Khách mới"
        left.discard(new)
    for j in left:
        names[j] = "Tiềm năng"
    return [names[j] for j in range(len(stats))]


FEATS = ["Độ gần đây (Recency)", "Tần suất mua", "Tổng chi tiêu", "Thời gian gắn bó", "Chu kỳ mua trung bình", "Đã từng mua lại"]


def _feat(lst, T):
    h = [o for o in lst if o["t"] <= T]
    if not h:
        return None
    n, last, first = len(h), h[-1]["t"], h[0]["t"]
    rec = (T - last).total_seconds() / 86400.0
    ten = (T - first).total_seconds() / 86400.0
    mon = sum(o["total"] for o in h)
    ai = ten / (n - 1) if n > 1 else 0.0
    return [math.log1p(rec), math.log1p(n), math.log1p(mon / 1000.0), math.log1p(ten), math.log1p(ai), 1.0 if n > 1 else 0.0], \
        dict(rec=rec, n=n, mon=mon, ai=ai, ten=ten)


def _logit(X, y, l2=1.0, it=15):
    d = len(X[0]) + 1
    w = [0.0] * d
    for _ in range(it):
        g, H = [0.0] * d, [[0.0] * d for _ in range(d)]
        for xi, yi in zip(X, y):
            v = [1.0] + xi
            z = max(-30, min(30, sum(a * b for a, b in zip(w, v))))
            p = 1 / (1 + math.exp(-z))
            r, s = p - yi, p * (1 - p) + 1e-6
            for i in range(d):
                g[i] += r * v[i]
                for j in range(d):
                    H[i][j] += s * v[i] * v[j]
        for i in range(1, d):
            g[i] += l2 * w[i]
            H[i][i] += l2
        step = solve(H, g)
        w = [a - b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-6:
            break
    return w


def _prob(w, x):
    z = max(-30, min(30, w[0] + sum(a * b for a, b in zip(w[1:], x))))
    return 1 / (1 + math.exp(-z))


def customers(valid, now):
    by = defaultdict(list)
    for o in valid:
        by[o["phone"]].append(o)
    for v in by.values():
        v.sort(key=lambda o: o["t"])
    out = dict(total=len(by))
    if len(by) < 8:
        out.update(ok=False, reason="Cần ít nhất 8 khách hàng đã mua để phân khúc (hiện có %d)." % len(by))
        return out
    # --- mô hình dự đoán mua lại 30 ngày
    samples = []
    for off in (30, 60, 90, 120, 150, 180):
        T = now - dt.timedelta(days=off)
        for ph, lst in by.items():
            f = _feat(lst, T)
            if not f:
                continue
            lab = 1 if any(T < o["t"] <= T + dt.timedelta(days=30) for o in lst) else 0
            samples.append((ph, f[0], lab))
    model, w, mu, sd = None, None, None, None
    if len(samples) >= 60 and 0 < sum(s[2] for s in samples) < len(samples):
        cols = list(zip(*[s[1] for s in samples]))
        mu = [sum(c) / len(c) for c in cols]
        sd = [max(1e-6, math.sqrt(sum((v - m) ** 2 for v in c) / len(c))) for c, m in zip(cols, mu)]
        norm = lambda x: [(v - m) / s for v, m, s in zip(x, mu, sd)]
        tr = [(norm(s[1]), s[2]) for s in samples if zlib.crc32(s[0].encode()) % 4 != 0]
        te = [(norm(s[1]), s[2]) for s in samples if zlib.crc32(s[0].encode()) % 4 == 0]
        if tr and len({y for _, y in tr}) == 2:
            w = _logit([x for x, _ in tr], [y for _, y in tr])
            a_te = auc([_prob(w, x) for x, _ in te], [y for _, y in te]) if len(te) >= 20 else None
            a_tr = auc([_prob(w, x) for x, _ in tr], [y for _, y in tr])
            model = dict(auc_test=None if a_te is None else round(a_te, 3), auc_train=None if a_tr is None else round(a_tr, 3),
                         n_train=len(tr), n_test=len(te), base_rate=round(sum(s[2] for s in samples) * 100.0 / len(samples), 1),
                         coef=[dict(name=n, w=round(v, 3)) for n, v in zip(FEATS, w[1:])])
    # --- đặc trưng hiện tại, RFM
    rows = []
    for ph, lst in by.items():
        x, raw = _feat(lst, now)
        p = _prob(w, [(v - m) / s for v, m, s in zip(x, mu, sd)]) if w else math.exp(-raw["rec"] / max(30.0, raw["ai"] or 45.0))
        rows.append(dict(phone=ph, name=lst[-1]["name"], x=x, p=p, **raw))
    X = []
    cols = list(zip(*[[math.log1p(r["rec"]), math.log1p(r["n"]), math.log1p(r["mon"] / 1000.0)] for r in rows]))
    cm = [sum(c) / len(c) for c in cols]
    cs = [max(1e-6, math.sqrt(sum((v - m) ** 2 for v in c) / len(c))) for c, m in zip(cols, cm)]
    X = [[(math.log1p(r["rec"]) - cm[0]) / cs[0], (math.log1p(r["n"]) - cm[1]) / cs[1],
          (math.log1p(r["mon"] / 1000.0) - cm[2]) / cs[2]] for r in rows]
    ks, best = [], None
    for k in range(2, min(5, len(rows) - 1) + 1):
        inertia, lab, C = kmeans(X, k)
        sil = silhouette(X, lab, k)
        ks.append(dict(k=k, sil=round(sil, 3), inertia=round(inertia, 1)))
        if best is None or sil > best[0]:
            best = (sil, k, lab, C)
    # ưu tiên k=4 nếu chất lượng gần ngang để có 4 nhóm hành động rõ ràng
    sil, k, lab, C = best
    four = next((e for e in ks if e["k"] == 4), None)
    if four and four["sil"] >= sil - 0.06 and k != 4:
        inertia, lab, C = kmeans(X, 4)
        k, sil = 4, four["sil"]
    stats = []
    for j in range(k):
        m = [r for r, l in zip(rows, lab) if l == j]
        stats.append(dict(n=len(m), R=sum(r["rec"] for r in m) / len(m), F=sum(r["n"] for r in m) / len(m),
                          M=sum(r["mon"] for r in m) / len(m), rev=sum(r["mon"] for r in m),
                          p=sum(r["p"] for r in m) / len(m)))
    names = _name_segments(stats)
    for r, l in zip(rows, lab):
        r["seg"] = names[l]
    total_rev = sum(s["rev"] for s in stats) or 1
    order = ["VIP trung thành", "Tiềm năng", "Khách mới", "Nguy cơ rời bỏ"]
    segs = sorted([dict(name=names[j], n=s["n"], share=round(s["n"] * 100.0 / len(rows), 1), recency=round(s["R"], 1),
                        freq=round(s["F"], 2), avg_spend=round(s["M"]), rev_share=round(s["rev"] * 100.0 / total_rev, 1),
                        p30=round(s["p"] * 100, 1), action=SEG_ACTION[names[j]]) for j, s in enumerate(stats)],
                  key=lambda s: order.index(s["name"]))
    multi = [r for r in rows if r["n"] > 1]
    risk = sorted([r for r in multi if r["rec"] > max(14.0, r["ai"])], key=lambda r: -r["mon"] * (1 - r["p"]))[:8]
    likely = sorted(multi, key=lambda r: -r["p"])[:8]
    fmt = lambda r: dict(name=r["name"], phone=_mask(r["phone"]), seg=r["seg"], n=r["n"], mon=round(r["mon"]),
                         rec=round(r["rec"]), interval=round(r["ai"]), p30=round(r["p"] * 100))
    pts = [dict(r=round(r["rec"], 1), m=round(r["mon"]), s=r["seg"], n=r["n"], t="%s · %s" % (r["name"], _mask(r["phone"])))
           for r in rows[:: max(1, len(rows) // 400)]]
    gaps = [r["ai"] for r in multi if r["ai"] > 0]
    out.update(ok=True, k=k, silhouette=round(sil, 3), kselect=ks, segments=segs, points=pts, model=model,
               at_risk=[fmt(r) for r in risk], likely=[fmt(r) for r in likely],
               repeat_rate=round(len(multi) * 100.0 / len(rows), 1),
               median_interval=round(statistics.median(gaps)) if gaps else None,
               avg_p30=round(sum(r["p"] for r in rows) * 100.0 / len(rows), 1))
    return out


def cohorts(valid, today):
    first, months = {}, defaultdict(set)
    for o in sorted(valid, key=lambda o: o["t"]):
        m = o["t"].year * 12 + o["t"].month - 1
        first.setdefault(o["phone"], m)
        months[o["phone"]].add(m)
    cur = today.year * 12 + today.month - 1
    groups = defaultdict(list)
    for ph, m in first.items():
        groups[m].append(ph)
    rows = []
    for m in sorted(groups)[-6:]:
        size = len(groups[m])
        ret = []
        for k in range(6):
            if m + k > cur:
                ret.append(None)
            else:
                ret.append(round(sum(1 for ph in groups[m] if (m + k) in months[ph]) * 100.0 / size))
        rows.append(dict(cohort="%02d/%d" % (m % 12 + 1, m // 12), size=size, ret=ret))
    return rows


# ---------------------------------------------------------------- sản phẩm, tồn kho, mua kèm
def basket(valid, products):
    grp, rep, units = {}, {}, Counter()
    for p in products:
        grp[p["id"]] = _base(p["name"])
    for o in valid:
        for pid, name, pr, q in o["items"]:
            units[pid] += q
    best_by_group = {}
    for p in products:
        g = grp[p["id"]]
        if g not in best_by_group or units[p["id"]] > units[best_by_group[g]]:
            best_by_group[g] = p["id"]
    baskets = []
    for o in valid:
        s = {grp.get(pid, _base(n)) for pid, n, _, _ in o["items"]}
        baskets.append(s)
    N = len(baskets)
    single, pair = Counter(), Counter()
    for s in baskets:
        for a in s:
            single[a] += 1
        for a in s:
            for b in s:
                if a != b:
                    pair[(a, b)] += 1
    min_cnt = max(3, int(round(N * 0.01)))
    rules = []
    for (a, b), n in pair.items():
        if n >= min_cnt:
            conf = n / single[a]
            lift = conf / (single[b] / float(N))
            if lift < 1.05:
                continue
            rules.append(dict(a=a, b=b, count=n, support=round(n * 100.0 / N, 1), conf=round(conf * 100, 1), lift=round(lift, 2),
                              b_id=best_by_group[b]))
    rules.sort(key=lambda r: (-r["lift"], -r["count"]))
    multi = sum(1 for s in baskets if len(s) > 1)
    return dict(rules=rules, n=N, multi_rate=round(multi * 100.0 / N, 1) if N else 0, min_count=min_cnt,
                top=[g for g, _ in single.most_common(5)], rep=best_by_group)


def recommend(c, ids, limit=3):
    d = load(c)
    valid = [o for o in d["orders"] if o["st"] != CANCEL]
    prods = {p["id"]: p for p in d["products"]}
    in_cart = {_base(prods[i]["name"]) for i in ids if i in prods}
    B = basket(valid, d["products"]) if len(valid) >= 20 else None
    out, seen = [], set()
    if B:
        for r in B["rules"]:
            if r["a"] in in_cart and r["b"] not in in_cart and r["b"] not in seen:
                p = prods.get(r["b_id"])
                if p and p["on"] and p["stock"] > 0:
                    seen.add(r["b"])
                    out.append(dict(id=p["id"], name=p["name"], price=p["price"], why="%d%% đơn có %s cũng mua sản phẩm này" % (round(r["conf"]), r["a"])))
    if len(out) < limit:  # bổ sung bán chạy nhất
        units = Counter()
        for o in valid:
            for pid, _, _, q in o["items"]:
                units[pid] += q
        for pid, _ in units.most_common():
            p = prods.get(pid)
            g = _base(p["name"]) if p else None
            if p and p["on"] and p["stock"] > 0 and g not in in_cart and g not in seen and len(out) < limit:
                seen.add(g)
                out.append(dict(id=p["id"], name=p["name"], price=p["price"], why="Đang được nhiều khách chọn"))
    return out[:limit]


def products_and_stock(valid, products, today):
    start = today - dt.timedelta(days=55)
    days = [start + dt.timedelta(days=i) for i in range(56)]
    daily = {p["id"]: defaultdict(int) for p in products}
    for o in valid:
        for pid, _, _, q in o["items"]:
            if pid in daily:
                daily[pid][o["t"].date()] += q
    stock = []
    for p in products:
        series = [daily[p["id"]][d] for d in days]
        alpha = 2 / 15.0
        s = sum(series[:7]) / 7.0
        for v in series[7:]:
            s = alpha * v + (1 - alpha) * s
        last28 = series[-28:]
        sd = statistics.pstdev(last28) if len(last28) > 1 else 0
        cover = p["stock"] / s if s > 0.01 else None
        rop = s * LEAD_DAYS + 1.65 * sd * math.sqrt(LEAD_DAYS)
        need = max(0, math.ceil(s * (LEAD_DAYS + 30) + 1.65 * sd * math.sqrt(LEAD_DAYS) - p["stock"]))
        if p["stock"] == 0:
            status = "Hết hàng"
        elif cover is None:
            status = "Tồn chậm" if p["stock"] > 0 else "Ổn định"
        elif cover < LEAD_DAYS:
            status = "Khẩn cấp"
        elif cover < 14:
            status = "Sắp hết"
        elif cover > 90:
            status = "Tồn chậm"
        else:
            status = "Ổn định"
        stock.append(dict(id=p["id"], name=p["name"], stock=p["stock"], rate=round(s, 2), cover=None if cover is None else round(cover, 1),
                          rop=math.ceil(rop), order_qty=need if status in ("Hết hàng", "Khẩn cấp", "Sắp hết") else 0, status=status,
                          spark=series[-28:]))
    rank = {"Hết hàng": 0, "Khẩn cấp": 1, "Sắp hết": 2, "Tồn chậm": 3, "Ổn định": 4}
    stock.sort(key=lambda r: (rank[r["status"]], r["cover"] if r["cover"] is not None else 1e9))
    return stock


def product_table(valid, products, today, R):
    w0 = today - dt.timedelta(days=R - 1)
    cur, prev = Counter(), Counter()
    rev = Counter()
    t28, p28 = Counter(), Counter()
    for o in valid:
        d = o["t"].date()
        for pid, _, pr, q in o["items"]:
            if d >= w0:
                cur[pid] += q
                rev[pid] += pr * q
            if d >= today - dt.timedelta(days=27):
                t28[pid] += q
            elif d >= today - dt.timedelta(days=55):
                p28[pid] += q
    total = sum(rev.values()) or 1
    rows, acc = [], 0.0
    for p in sorted(products, key=lambda p: -rev[p["id"]]):
        share = rev[p["id"]] * 100.0 / total
        abc = "A" if acc < 70 else ("B" if acc < 90 else "C")
        acc += share
        rows.append(dict(id=p["id"], name=p["name"], cat=p["cat"], units=cur[p["id"]], revenue=rev[p["id"]], share=round(share, 1),
                         abc=abc if rev[p["id"]] else "C", trend=_pct(t28[p["id"]], p2) if (p2 := p28[p["id"]]) else None))
    return rows


# ---------------------------------------------------------------- tổng hợp
def compute(c, R=90):
    now = dt.datetime.now(LOCAL)
    today = now.date()
    D = load(c)
    orders, products = D["orders"], D["products"]
    valid = [o for o in orders if o["st"] != CANCEL]
    out = dict(meta=dict(generated_at=now.isoformat(), n_orders=len(orders), n_valid=len(valid), range=R, demo=D["demo"],
                         n_customers=len({o["phone"] for o in valid}), today=today.isoformat()))
    if not valid:
        out["meta"]["empty"] = True
        return out
    first_day = min(o["t"].date() for o in valid)
    out["meta"]["first_day"] = first_day.isoformat()
    days, rev, cnt = _series(valid, first_day, today)
    out["meta"]["n_days"] = len(days)
    # --- KPI theo kỳ
    w0, p0 = today - dt.timedelta(days=R - 1), today - dt.timedelta(days=2 * R - 1)
    inw = lambda o, a, b: a <= o["t"].date() <= b
    cur = [o for o in valid if inw(o, w0, today)]
    prv = [o for o in valid if inw(o, p0, w0 - dt.timedelta(days=1))]
    allc = [o for o in orders if inw(o, w0, today)]
    allp = [o for o in orders if inw(o, p0, w0 - dt.timedelta(days=1))]
    fd = {}
    for o in sorted(valid, key=lambda o: o["t"]):
        fd.setdefault(o["phone"], o["t"].date())

    def kp(vo, ao, a, b):
        r = sum(o["total"] for o in vo)
        ph = {o["phone"] for o in vo}
        new = sum(1 for p in ph if a <= fd[p] <= b)
        units = sum(q for o in vo for *_, q in o["items"])
        return dict(revenue=r, orders=len(vo), aov=round(r / len(vo)) if vo else 0, customers=len(ph), new=new,
                    returning=round((len(ph) - new) * 100.0 / len(ph), 1) if ph else 0,
                    cancel=round(sum(1 for o in ao if o["st"] == CANCEL) * 100.0 / len(ao), 1) if ao else 0, units=units,
                    upo=round(units / len(vo), 2) if vo else 0)
    kc, kpv = kp(cur, allc, w0, today), kp(prv, allp, p0, w0 - dt.timedelta(days=1))
    out["kpi"] = {k: dict(cur=kc[k], prev=kpv[k] if prv else None, delta=_pct(kc[k], kpv[k]) if prv else None) for k in kc}
    wd, wr, wc = _series(cur, w0, today)
    ma = [round(sum(wr[max(0, i - 6):i + 1]) / len(wr[max(0, i - 6):i + 1])) for i in range(len(wr))]
    out["daily"] = [dict(d=d.isoformat(), rev=round(r), orders=n, ma7=m) for d, r, n, m in zip(wd, wr, wc, ma)]
    # --- dự báo, bất thường
    out["forecast"] = forecast(days, rev)
    out["anomalies"] = anomalies(days, rev)
    # --- nhiệt độ giờ x thứ
    heat = [[0] * 24 for _ in range(7)]
    for o in cur:
        heat[o["t"].weekday()][o["t"].hour] += 1
    out["heatmap"] = heat
    # --- cơ cấu
    cat = {p["id"]: p["cat"] for p in products}
    cc = Counter()
    for o in cur:
        for pid, _, pr, q in o["items"]:
            cc[cat.get(pid, "Khác")] += pr * q
    out["mix"] = dict(category=[dict(name=k, value=v) for k, v in cc.most_common()])
    pay = []
    for m in ("cod", "qr", "wallet", "card"):
        al = [o for o in allc if o["pay"] == m]
        if al:
            pay.append(dict(method=m, orders=len(al), revenue=sum(o["total"] for o in al if o["st"] != CANCEL),
                            cancel=round(sum(1 for o in al if o["st"] == CANCEL) * 100.0 / len(al), 1),
                            share=round(len(al) * 100.0 / len(allc), 1)))
    out["mix"]["payment"] = pay
    sh = []
    for m in ("std", "exp"):
        al = [o for o in cur if o["ship"] == m]
        if al:
            sh.append(dict(method=m, orders=len(al), revenue=sum(o["total"] for o in al), share=round(len(al) * 100.0 / len(cur), 1),
                           fee=sum(o["fee"] for o in al)))
    out["mix"]["ship"] = sh
    # --- phễu và thời gian xử lý
    funnel = []
    for i, s in enumerate(ST):
        n = sum(1 for o in allc if (o["st"] != CANCEL and ST.index(o["st"]) >= i) or (o["st"] == CANCEL and any(h[0] == s for h in o["hist"])))
        funnel.append(dict(stage=s, n=n))
    out["funnel"] = funnel
    out["funnel_cancel"] = sum(1 for o in allc if o["st"] == CANCEL)
    trans = defaultdict(list)
    e2e = defaultdict(list)
    for o in cur:
        h = {}
        for s, t in o["hist"]:
            if s in ST and s not in h:
                h[s] = t
        for a, b in zip(ST, ST[1:]):
            if a in h and b in h:
                trans[(a, b)].append((h[b] - h[a]).total_seconds() / 3600.0)
        if ST[0] in h and ST[-1] in h:
            e2e[o["ship"]].append((h[ST[-1]] - h[ST[0]]).total_seconds() / 3600.0)
    out["stages"] = [dict(frm=a, to=b, median=round(statistics.median(v), 1), mean=round(sum(v) / len(v), 1), n=len(v))
                     for (a, b), v in sorted(trans.items(), key=lambda kv: ST.index(kv[0][0]))]
    out["delivery"] = [dict(method=m, median=round(statistics.median(v), 1), p90=round(sorted(v)[int(len(v) * 0.9) - 1 if len(v) > 1 else 0], 1), n=len(v))
                       for m, v in e2e.items()]
    # --- giá trị đơn, mã giảm giá, ngưỡng freeship
    edges = [0, 100000, 200000, 300000, 400000, 500000, 700000, 1000000, 10 ** 12]
    labels = ["<100k", "100–200k", "200–300k", "300–400k", "400–500k", "500–700k", "0,7–1tr", ">1tr"]
    hist = [0] * len(labels)
    for o in cur:
        for i in range(len(labels)):
            if edges[i] <= o["sub"] < edges[i + 1]:
                hist[i] += 1
                break
    out["aov_hist"] = [dict(label=l, n=n) for l, n in zip(labels, hist)]
    near = [o for o in cur if 0.7 * FREESHIP <= o["sub"] < FREESHIP and o["fee"] > 0]
    out["freeship"] = dict(threshold=FREESHIP, near=len(near), near_share=round(len(near) * 100.0 / len(cur), 1) if cur else 0,
                           avg_gap=round(sum(FREESHIP - o["sub"] for o in near) / len(near)) if near else 0,
                           potential=round(sum(FREESHIP - o["sub"] for o in near)),
                           ship_paid=sum(o["fee"] for o in cur), free_rate=round(sum(1 for o in cur if o["fee"] == 0) * 100.0 / len(cur), 1) if cur else 0)
    vc = defaultdict(list)
    for o in cur:
        if o["voucher"]:
            vc[o["voucher"]].append(o)
    no_v = [o for o in cur if not o["voucher"]]
    aov_no = sum(o["total"] for o in no_v) / len(no_v) if no_v else 0
    out["vouchers"] = dict(aov_without=round(aov_no), used_rate=round(sum(len(v) for v in vc.values()) * 100.0 / len(cur), 1) if cur else 0,
                           rows=[dict(code=k, uses=len(v), discount=sum(o["disc"] for o in v), aov=round(sum(o["total"] for o in v) / len(v)),
                                      revenue=sum(o["total"] for o in v), uplift=_pct(sum(o["total"] for o in v) / len(v), aov_no) if aov_no else None)
                                 for k, v in sorted(vc.items(), key=lambda kv: -len(kv[1]))])
    # --- sản phẩm, tồn kho, mua kèm, khách hàng, cohort
    out["products"] = product_table(valid, products, today, R)
    out["stock"] = products_and_stock(valid, products, today)
    out["basket"] = basket(valid, products) if len(valid) >= 20 else dict(rules=[], n=len(valid), multi_rate=0, min_count=3, top=[])
    out["basket"].pop("rep", None)
    out["customers"] = customers(valid, now)
    out["cohorts"] = cohorts(valid, today)
    return out


def get(c, R=90):
    sig = c.execute("SELECT (SELECT COUNT(*) FROM orders),(SELECT IFNULL(MAX(rowid),0) FROM order_history),"
                    "(SELECT IFNULL(SUM(stock),0) FROM products)").fetchone()
    key = (tuple(sig), R, dt.datetime.now(LOCAL).strftime("%Y-%m-%d %H"))
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = compute(c, R)
    return _CACHE[key]
