/* Dashboard quản trị: số liệu, dự báo và phân tích học máy (dữ liệu từ GET /api/analytics).
   Biểu đồ vẽ bằng SVG/HTML thuần, không dùng thư viện ngoài. Dùng chung esc() từ app.js. */
(function () {
  const nf = n => Number(n).toLocaleString("vi-VN");
  const f1 = n => Number(n).toLocaleString("vi-VN", { maximumFractionDigits: 1 });
  const full = n => nf(Math.round(n)) + "đ";
  const mny = n => { const a = Math.abs(n); return a >= 1e9 ? f1(n / 1e9) + " tỷ" : a >= 1e6 ? f1(n / 1e6) + " tr" : a >= 1e3 ? Math.round(n / 1e3) + "k" : String(Math.round(n)); };
  const dl = s => { const p = String(s).split("-"); return p[2] + "/" + p[1]; };
  const DOW = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];
  const PAL = ["#2F8F5B", "#D2802F", "#3B7DD8", "#8E5CC8", "#C94A6B", "#2AA6A0"];
  const SEGC = { "VIP trung thành": "#2F8F5B", "Tiềm năng": "#3B7DD8", "Khách mới": "#D2802F", "Nguy cơ rời bỏ": "#C94A6B" };
  const PAYN = { cod: "COD", qr: "VietQR", wallet: "Ví điện tử", card: "Thẻ" }, SHIPN = { std: "Tiêu chuẩn", exp: "Hỏa tốc" };
  const TABS = [["ov", "Tổng quan"], ["fc", "Dự báo doanh thu"], ["cu", "Khách hàng"], ["pr", "Sản phẩm & kho"], ["op", "Vận hành"], ["me", "Phương pháp"]];
  let X = null, XR = 90, XT = "ov", XERR = "", XLOAD = false;

  /* ---------- thành phần biểu đồ ---------- */
  function ticks(max, n) {
    if (!(max > 0)) return [0, 1];
    const raw = max / (n || 4), p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p, s = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p, o = [];
    for (let v = 0; v <= max + s * 0.999; v += s) o.push(v);
    return o;
  }
  const tip = lines => `data-tip="${esc(lines.join("\n"))}"`;
  function legend(items) { return `<div class="dx-leg">${items.map(i => `<span><i style="background:${i.color}${i.dash ? ";opacity:.55" : ""}"></i>${esc(i.name)}</span>`).join("")}</div>`; }

  function line(o) {
    const W = 720, H = o.h || 260, L = 56, R = 12, T = 12, B = 26, pw = W - L - R, ph = H - T - B, n = o.labels.length;
    let mx = 0;
    o.series.forEach(s => s.vals.forEach(v => { if (v != null && v > mx) mx = v; }));
    if (o.band) o.band.hi.forEach(v => { if (v != null && v > mx) mx = v; });
    const tk = ticks(mx, 4), top = tk[tk.length - 1] || 1;
    const px = i => L + (n < 2 ? pw / 2 : i * pw / (n - 1)), py = v => T + ph - (v / top) * ph;
    let g = "";
    tk.forEach(v => g += `<line x1="${L}" x2="${W - R}" y1="${py(v)}" y2="${py(v)}" class="dx-grid"/><text x="${L - 6}" y="${py(v) + 4}" class="dx-ax" text-anchor="end">${esc(mny(v))}</text>`);
    const step = Math.max(1, Math.round(n / 7));
    for (let i = 0; i < n; i += step) g += `<text x="${px(i)}" y="${H - 6}" class="dx-ax" text-anchor="middle">${dl(o.labels[i])}</text>`;
    if (o.band) {
      const idx = []; o.band.hi.forEach((v, i) => { if (v != null) idx.push(i); });
      if (idx.length) g += `<polygon points="${idx.map(i => px(i) + "," + py(o.band.hi[i])).concat(idx.slice().reverse().map(i => px(i) + "," + py(o.band.lo[i]))).join(" ")}" style="fill:${o.band.color};opacity:.2"/>`;
    }
    o.series.forEach(s => {
      let d = "", pen = false, first = -1, last = -1;
      s.vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? "L" : "M") + px(i).toFixed(1) + " " + py(v).toFixed(1); pen = true; if (first < 0) first = i; last = i; });
      if (s.area && first >= 0) g += `<path d="${d}L${px(last).toFixed(1)} ${py(0)}L${px(first).toFixed(1)} ${py(0)}Z" style="fill:${s.color};opacity:.12"/>`;
      g += `<path d="${d}" fill="none" style="stroke:${s.color}" stroke-width="${s.w || 2}" stroke-linejoin="round" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""}/>`;
    });
    const bw = Math.max(2, pw / Math.max(1, n - 1));
    for (let i = 0; i < n; i++) {
      const ls = [dl(o.labels[i])];
      o.series.forEach(s => { if (s.vals[i] != null) ls.push(s.name + ": " + (o.tipfmt || full)(s.vals[i])); });
      if (o.band && o.band.hi[i] != null) ls.push("Khoảng tin cậy 95%: " + full(o.band.lo[i]) + " – " + full(o.band.hi[i]));
      g += `<rect x="${px(i) - bw / 2}" y="${T}" width="${bw}" height="${ph}" class="dx-hit" ${tip(ls)}/>`;
    }
    return `<svg viewBox="0 0 ${W} ${H}" class="dx-svg" role="img" aria-label="${esc(o.aria || "Biểu đồ đường")}">${g}</svg>${legend(o.series.map(s => ({ name: s.name, color: s.color, dash: s.dash })).concat(o.band ? [{ name: "Khoảng tin cậy 95%", color: o.band.color }] : []))}`;
  }

  function cols(o) {
    const W = 720, H = o.h || 200, L = 44, R = 10, T = 10, B = 30, pw = W - L - R, ph = H - T - B, n = o.items.length;
    const tk = ticks(Math.max(...o.items.map(i => i.v), 1), 4), top = tk[tk.length - 1], bw = pw / n;
    let g = "";
    tk.forEach(v => g += `<line x1="${L}" x2="${W - R}" y1="${T + ph - v / top * ph}" y2="${T + ph - v / top * ph}" class="dx-grid"/><text x="${L - 6}" y="${T + ph - v / top * ph + 4}" class="dx-ax" text-anchor="end">${esc((o.yfmt || nf)(v))}</text>`);
    o.items.forEach((it, i) => {
      const h = it.v / top * ph;
      g += `<rect x="${L + i * bw + bw * .14}" y="${T + ph - h}" width="${bw * .72}" height="${Math.max(0, h)}" rx="3" style="fill:${it.color || "var(--pri-c)"}" ${tip([it.l, (o.tipfmt || nf)(it.v)])}/><text x="${L + i * bw + bw / 2}" y="${H - 10}" class="dx-ax" text-anchor="middle">${esc(it.l)}</text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="dx-svg" role="img" aria-label="${esc(o.aria || "Biểu đồ cột")}">${g}</svg>`;
  }

  function hbars(items) {
    const mx = Math.max(1, ...items.map(i => i.value));
    return `<div class="dx-hb">${items.map(i => `<div class="dx-hr" ${i.tip ? tip([].concat(i.tip)) : ""}><span class="dx-hl">${esc(i.label)}</span><span class="dx-ht"><i style="width:${Math.max(1.5, i.value * 100 / mx)}%;background:${i.color || "var(--pri-c)"}"></i></span><b class="dx-hv">${esc(i.text != null ? i.text : nf(i.value))}</b></div>`).join("")}</div>`;
  }

  function donut(items, fmt) {
    const tot = items.reduce((s, i) => s + i.value, 0) || 1, R = 54, C = 2 * Math.PI * R;
    let acc = 0;
    const arcs = items.map((it, i) => {
      const f = it.value / tot, len = f * C, off = -acc * C; acc += f;
      return `<circle r="${R}" cx="80" cy="80" fill="none" style="stroke:${PAL[i % PAL.length]}" stroke-width="24" stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${off.toFixed(2)}" transform="rotate(-90 80 80)" ${tip([it.name, fmt(it.value), f1(f * 100) + "%"])}/>`;
    }).join("");
    return `<div class="dx-donut"><svg viewBox="0 0 160 160" role="img" aria-label="Biểu đồ tròn">${arcs}<text x="80" y="78" text-anchor="middle" class="dx-big">${esc(fmt(tot))}</text><text x="80" y="95" text-anchor="middle" class="dx-ax">tổng</text></svg>
      <ul class="dx-dl">${items.map((it, i) => `<li><i style="background:${PAL[i % PAL.length]}"></i><span>${esc(it.name)}</span><b>${f1(it.value * 100 / tot)}%</b></li>`).join("")}</ul></div>`;
  }

  function heat(m) {
    const mx = Math.max(1, ...m.flat());
    let h = `<div></div>` + [...Array(24)].map((_, i) => `<div class="dx-hh">${i % 3 === 0 ? i : ""}</div>`).join("");
    m.forEach((row, d) => { h += `<div class="dx-hh">${DOW[d]}</div>` + row.map((v, hr) => `<div class="dx-hc" style="background:${v ? `color-mix(in srgb,var(--pri) ${Math.round(18 + v * 82 / mx)}%,var(--low))` : "var(--low)"}" ${tip([DOW[d] + " " + hr + "h", v + " đơn"])}></div>`).join(""); });
    return `<div class="dx-heat">${h}</div><p class="mute dx-note">Số đơn theo thứ và giờ đặt hàng (giờ Việt Nam). Màu đậm hơn là nhiều đơn hơn.</p>`;
  }

  function spark(vals, color) {
    const W = 96, H = 28, mx = Math.max(1, ...vals), n = vals.length;
    return `<svg viewBox="0 0 ${W} ${H}" class="dx-spark" aria-hidden="true"><polyline fill="none" style="stroke:${color || "var(--pri-c)"}" stroke-width="1.8" stroke-linejoin="round" points="${vals.map((v, i) => ((i * (W - 2) / Math.max(1, n - 1)) + 1).toFixed(1) + "," + (H - 3 - v / mx * (H - 6)).toFixed(1)).join(" ")}"/></svg>`;
  }

  function scatter(pts) {
    const W = 720, H = 300, L = 62, R = 14, T = 12, B = 40, pw = W - L - R, ph = H - T - B;
    const xm = Math.max(30, ...pts.map(p => p.r)) * 1.04, ys = pts.map(p => Math.log10(Math.max(1000, p.m)));
    const y0 = Math.floor(Math.min(...ys)), y1 = Math.ceil(Math.max(...ys)) || y0 + 1;
    const px = r => L + r / xm * pw, py = l => T + ph - (l - y0) / Math.max(.5, y1 - y0) * ph;
    let g = "";
    for (let k = y0; k <= y1; k++) g += `<line x1="${L}" x2="${W - R}" y1="${py(k)}" y2="${py(k)}" class="dx-grid"/><text x="${L - 6}" y="${py(k) + 4}" class="dx-ax" text-anchor="end">${mny(Math.pow(10, k))}</text>`;
    ticks(xm, 6).forEach(v => { if (v <= xm) g += `<text x="${px(v)}" y="${H - 20}" class="dx-ax" text-anchor="middle">${v}</text>`; });
    g += `<text x="${L + pw / 2}" y="${H - 4}" class="dx-ax" text-anchor="middle">Số ngày kể từ đơn gần nhất (Recency)</text><text x="12" y="${T + ph / 2}" class="dx-ax" transform="rotate(-90 12 ${T + ph / 2})" text-anchor="middle">Tổng chi tiêu (thang log)</text>`;
    pts.forEach(p => g += `<circle cx="${px(p.r).toFixed(1)}" cy="${py(Math.log10(Math.max(1000, p.m))).toFixed(1)}" r="${Math.min(8, 2.6 + Math.sqrt(p.n)).toFixed(1)}" style="fill:${SEGC[p.s] || "#888"};opacity:.7" ${tip([p.t, p.s, p.n + " đơn · " + full(p.m), "Cách đây " + Math.round(p.r) + " ngày"])}/>`);
    return `<svg viewBox="0 0 ${W} ${H}" class="dx-svg" role="img" aria-label="Biểu đồ phân tán khách hàng theo phân khúc">${g}</svg>${legend(Object.keys(SEGC).map(k => ({ name: k, color: SEGC[k] })))}`;
  }

  const chip = (d, up) => d == null ? `<span class="dx-d">—</span>` : `<span class="dx-d ${(up === false ? d < 0 : d > 0) ? "ok" : d === 0 ? "" : "bad"}">${d > 0 ? "▲" : d < 0 ? "▼" : "•"} ${f1(Math.abs(d))}%</span>`;
  const kpi = (label, val, d, o) => `<div class="card kpi dx-kpi"><span class="mute">${esc(label)}</span><b>${esc(val)}</b><div class="dx-kr">${chip(d, o && o.up)}<span class="mute">so với kỳ trước</span></div>${o && o.spark ? o.spark : ""}</div>`;
  const card = (title, body, o) => `<section class="card dx-card ${o && o.cls || ""}"><div class="dx-ch"><h3>${esc(title)}</h3>${o && o.sub ? `<span class="mute">${esc(o.sub)}</span>` : ""}</div>${body}</section>`;
  const insight = html => `<div class="dx-ins"><div>${html}</div></div>`;
  const tag = (t, cls) => `<span class="tag ${cls || ""}">${esc(t)}</span>`;
  const table = (head, rows, cls) => `<div class="tbl"><table class="${cls || ""}"><tr>${head.map(h => { const a = Array.isArray(h) ? h : [h, 0]; return `<th ${a[1] ? 'class="num"' : ""}>${esc(a[0])}</th>`; }).join("")}</tr>${rows.join("")}</table></div>`;
  const pbar = p => `<span class="dx-pb"><i style="width:${Math.max(2, Math.min(100, p))}%"></i></span> ${p}%`;

  /* ---------- các tab ---------- */
  function vOv() {
    const k = X.kpi, d = X.daily;
    const sp = d.map(r => r.rev), spo = d.map(r => r.orders);
    let h = `<div class="dx-kpis">${kpi("Doanh thu", full(k.revenue.cur), k.revenue.delta, { spark: spark(sp) })}${kpi("Số đơn hàng", nf(k.orders.cur), k.orders.delta, { spark: spark(spo) })}
      ${kpi("Giá trị đơn trung bình", full(k.aov.cur), k.aov.delta)}${kpi("Khách đã mua", nf(k.customers.cur), k.customers.delta)}
      ${kpi("Khách mới", nf(k.new.cur), k.new.delta)}${kpi("Khách quay lại", f1(k.returning.cur) + "%", k.returning.delta)}
      ${kpi("Tỷ lệ hủy đơn", f1(k.cancel.cur) + "%", k.cancel.delta, { up: false })}${kpi("Sản phẩm bán ra", nf(k.units.cur) + " (" + f1(k.upo.cur) + "/đơn)", k.units.delta)}</div>`;
    h += card("Doanh thu theo ngày", line({ labels: d.map(r => r.d), series: [{ name: "Doanh thu", color: "var(--pri-c)", vals: d.map(r => r.rev), area: 1, w: 1.5 }, { name: "Trung bình 7 ngày", color: "#D2802F", vals: d.map(r => r.ma7), w: 2.4 }], aria: "Doanh thu theo ngày" }), { sub: X.meta.range + " ngày gần nhất" });
    const an = X.anomalies;
    h += `<div class="dx-g2">${card("Ngày bất thường (phát hiện tự động)", an.length ? table(["Ngày", ["Thực tế", 1], ["Kỳ vọng", 1], ["Lệch", 1], "Loại"], an.map(a => `<tr><td>${dl(a.d)}</td><td class="num">${full(a.actual)}</td><td class="num">${full(a.expected)}</td><td class="num">${a.diff > 0 ? "+" : ""}${f1(a.diff)}%</td><td>${tag(a.kind, a.z > 0 ? "" : "bad")}</td></tr>`)) + `<p class="mute dx-note">Phương pháp: so với trung vị cùng thứ trong 4 tuần trước, chuẩn hóa bằng MAD; gắn cờ khi |z| ≥ 3. Nên đối chiếu với khuyến mãi, sự cố giao hàng hoặc lỗi hệ thống ngày đó.</p>` : `<p class="mute">Không có ngày nào lệch bất thường trong 90 ngày gần nhất.</p>`)}
      ${card("Khung giờ đặt hàng", heat(X.heatmap))}</div>`;
    const m = X.mix;
    h += `<div class="dx-g3">${card("Doanh thu theo danh mục", m.category.length ? donut(m.category.map(c => ({ name: c.name, value: c.value })), mny) : "<p class='mute'>Chưa có dữ liệu.</p>")}
      ${card("Phương thức thanh toán", m.payment.length ? donut(m.payment.map(p => ({ name: PAYN[p.method], value: p.orders })), v => nf(v) + " đơn") : "<p class='mute'>Chưa có dữ liệu.</p>", { sub: "gồm cả đơn hủy" })}
      ${card("Hình thức giao hàng", m.ship.length ? donut(m.ship.map(p => ({ name: SHIPN[p.method], value: p.orders })), v => nf(v) + " đơn") : "<p class='mute'>Chưa có dữ liệu.</p>")}</div>`;
    h += card("Phân bố giá trị đơn hàng", cols({ items: X.aov_hist.map(b => ({ l: b.label, v: b.n })), aria: "Phân bố giá trị đơn", tipfmt: v => v + " đơn" }), { sub: "Giá trị hàng trước giảm giá và phí ship" });
    return h;
  }

  function vFc() {
    const f = X.forecast;
    if (!f.ok) return card("Dự báo doanh thu", `<p class="mute">${esc(f.reason)}</p>`);
    const hist = f.history, pts = f.points, labels = hist.map(r => r.d).concat(pts.map(r => r.d));
    const hv = hist.map(r => r.v).concat(pts.map(() => null));
    const fv = hist.map((r, i) => i === hist.length - 1 ? r.v : null).concat(pts.map(r => r.yhat));
    const lo = hist.map(() => null).concat(pts.map(r => r.lo)), hi = hist.map(() => null).concat(pts.map(r => r.hi));
    const best = f.backtest.find(b => b.best), g = f.growth7;
    let h = insight(`Mô hình tốt nhất trên tập kiểm tra là <b>${esc(f.model)}</b> (WAPE ${f1(best.wape)}%). Dự kiến <b>${full(f.next7)}</b> trong 7 ngày tới${g == null ? "" : `, ${g >= 0 ? "tăng" : "giảm"} ${f1(Math.abs(g))}% so với 7 ngày vừa qua (${full(f.last7)})`}. Dự báo theo ngày dao động mạnh nên hãy đọc theo tổng tuần, không theo từng ngày.`);
    h += `<div class="dx-kpis">${[["7 ngày tới", f.next7], ["14 ngày tới", f.next14], ["30 ngày tới", f.next30]].map(a => `<div class="card kpi dx-kpi"><span class="mute">Doanh thu dự báo ${a[0]}</span><b>${full(a[1])}</b></div>`).join("")}<div class="card kpi dx-kpi"><span class="mute">30 ngày vừa qua (thực tế)</span><b>${full(f.last30)}</b></div></div>`;
    h += card("Doanh thu thực tế và dự báo 30 ngày", line({ labels, series: [{ name: "Thực tế", color: "var(--pri-c)", vals: hv, area: 1 }, { name: "Dự báo", color: "#D2802F", vals: fv, dash: "6 4", w: 2.4 }], band: { lo, hi, color: "#D2802F" }, aria: "Dự báo doanh thu" }), { sub: "Sai số chuẩn ước tính ±" + mny(f.sigma) + "/ngày" });
    h += `<div class="dx-g2">${card("So sánh mô hình (kiểm tra trên " + f.holdout + " ngày gần nhất)", table(["Mô hình", ["WAPE", 1], ["MAE", 1], ["RMSE", 1], ["Lệch (bias)", 1]], f.backtest.map(b => `<tr><td>${esc(b.model)} ${b.best ? tag("Được chọn") : ""}</td><td class="num">${f1(b.wape)}%</td><td class="num">${full(b.mae)}</td><td class="num">${full(b.rmse)}</td><td class="num">${b.bias > 0 ? "+" : ""}${f1(b.bias)}%</td></tr>`)) + `<p class="mute dx-note">Mỗi mô hình được huấn luyện trên dữ liệu trước ${f.holdout} ngày cuối rồi dự báo ${f.holdout} ngày đó để đo sai số thật (backtest). WAPE = tổng sai số tuyệt đối ÷ tổng doanh thu thực tế; càng thấp càng tốt. Bias dương nghĩa là mô hình đang dự báo thấp hơn thực tế.</p>`)}
      ${card("Dự báo 14 ngày tới", table(["Ngày", ["Dự báo", 1], ["Thấp", 1], ["Cao", 1]], pts.slice(0, 14).map(p => `<tr><td>${DOW[(new Date(p.d + "T00:00:00").getDay() + 6) % 7]} ${dl(p.d)}</td><td class="num">${full(p.yhat)}</td><td class="num">${full(p.lo)}</td><td class="num">${full(p.hi)}</td></tr>`)))}</div>`;
    return h;
  }

  function aucLabel(a) { return a == null ? "chưa đủ dữ liệu" : a < .6 ? "yếu" : a < .7 ? "trung bình" : a < .8 ? "khá" : "tốt"; }
  function vCu() {
    const c = X.customers;
    if (!c.ok) return card("Khách hàng", `<p class="mute">${esc(c.reason)}</p>`);
    const vip = c.segments.find(s => s.name === "VIP trung thành"), risk = c.segments.find(s => s.name === "Nguy cơ rời bỏ");
    let h = insight(`${vip ? `Nhóm <b>VIP trung thành</b> chỉ chiếm ${f1(vip.share)}% khách nhưng đem lại <b>${f1(vip.rev_share)}%</b> doanh thu. ` : ""}${risk ? `Có <b>${risk.n} khách</b> (${f1(risk.share)}%) thuộc nhóm nguy cơ rời bỏ, mua lại trung bình ${f1(risk.p30)}% trong 30 ngày tới. ` : ""}Tỷ lệ khách mua từ 2 lần trở lên: <b>${f1(c.repeat_rate)}%</b>${c.median_interval ? `, chu kỳ mua lại trung vị ${c.median_interval} ngày` : ""}.`);
    h += `<div class="dx-segs">${c.segments.map(s => `<div class="card dx-seg" style="border-top:4px solid ${SEGC[s.name]}"><div class="row"><b>${esc(s.name)}</b><span class="tag">${nf(s.n)} khách</span></div>
      <dl><div><dt>Tỷ trọng khách</dt><dd>${f1(s.share)}%</dd></div><div><dt>Tỷ trọng doanh thu</dt><dd>${f1(s.rev_share)}%</dd></div><div><dt>Chi tiêu TB/khách</dt><dd>${mny(s.avg_spend)}</dd></div><div><dt>Số đơn TB</dt><dd>${f1(s.freq)}</dd></div><div><dt>Ngày kể từ đơn cuối</dt><dd>${Math.round(s.recency)}</dd></div><div><dt>Khả năng mua lại 30 ngày</dt><dd>${f1(s.p30)}%</dd></div></dl>
      <p class="mute dx-act"><b>Hành động:</b> ${esc(s.action)}</p></div>`).join("")}</div>`;
    h += card("Bản đồ phân khúc khách hàng (RFM + K-means)", scatter(c.points), { sub: `k = ${c.k}, Silhouette = ${c.silhouette}` });
    const ks = c.kselect;
    h += `<div class="dx-g2">${card("Chọn số nhóm bằng hệ số Silhouette", cols({ h: 170, items: ks.map(e => ({ l: "k = " + e.k, v: Math.max(0, e.sil), color: e.k === c.k ? "var(--pri-c)" : "var(--outv)" })), yfmt: v => f1(v), tipfmt: v => "Silhouette " + f1(v) }) + `<p class="mute dx-note">Silhouette càng gần 1 thì các nhóm càng tách bạch. Nhóm được chọn có màu đậm. Khi chất lượng gần ngang nhau, hệ thống ưu tiên k = 4 để có 4 nhóm hành động rõ ràng.</p>`)}`;
    const m = c.model;
    if (m) {
      const mx = Math.max(...m.coef.map(e => Math.abs(e.w)), .01);
      h += card("Mô hình dự đoán mua lại trong 30 ngày (hồi quy logistic)", `<div class="dx-met"><div><span class="mute">AUC kiểm tra</span><b>${m.auc_test == null ? "—" : m.auc_test}</b><small>${aucLabel(m.auc_test)}</small></div><div><span class="mute">Tỷ lệ mua lại thực tế</span><b>${f1(m.base_rate)}%</b></div><div><span class="mute">Số mẫu huấn luyện / kiểm tra</span><b>${nf(m.n_train)} / ${nf(m.n_test)}</b></div></div>
        <div class="dx-co">${m.coef.map(e => `<div ${tip([e.name, "Hệ số chuẩn hóa: " + e.w])}><span>${esc(e.name)}</span><span class="dx-cb"><i class="${e.w < 0 ? "neg" : "pos"}" style="width:${Math.abs(e.w) / mx * 50}%;${e.w < 0 ? "right:50%" : "left:50%"}"></i></span><b>${e.w > 0 ? "+" : ""}${e.w}</b></div>`).join("")}</div>
        <p class="mute dx-note">Thanh xanh làm tăng khả năng mua lại, thanh đỏ làm giảm. AUC 0,5 là đoán ngẫu nhiên, trên 0,7 là khá. Mô hình huấn luyện từ lịch sử nhiều mốc thời gian, tách tập kiểm tra theo khách hàng để tránh rò rỉ dữ liệu.</p>`);
    } else h += card("Mô hình dự đoán mua lại", `<p class="mute">Chưa đủ dữ liệu lịch sử (cần khoảng 60 mẫu khách-tháng trở lên và có cả khách mua lại lẫn không mua lại).</p>`);
    h += `</div>`;
    const cr = r => `<tr><td>${esc(r.name)}<br><span class="mute">${esc(r.phone)}</span></td><td>${tag(r.seg)}</td><td class="num">${r.n}</td><td class="num">${mny(r.mon)}</td><td class="num">${r.rec} ngày</td><td class="num">${r.interval || "—"}${r.interval ? " ngày" : ""}</td><td>${pbar(r.p30)}</td></tr>`;
    const head = ["Khách hàng", "Nhóm", ["Số đơn", 1], ["Chi tiêu", 1], ["Từ đơn cuối", 1], ["Chu kỳ TB", 1], "Mua lại 30 ngày"];
    h += `<div class="dx-g2">${card("Khách giá trị cao có nguy cơ rời bỏ", c.at_risk.length ? table(head, c.at_risk.map(cr)) + `<p class="mute dx-note">Khách đã mua từ 2 đơn, quá chu kỳ mua thường lệ, xếp theo giá trị có thể mất. Phù hợp gửi mã win-back qua Zalo/SMS.</p>` : `<p class="mute">Chưa có khách nào quá chu kỳ mua.</p>`)}
      ${card("Khách có khả năng mua lại cao nhất", c.likely.length ? table(head, c.likely.map(cr)) + `<p class="mute dx-note">Nên gợi ý combo mua kèm hoặc nhắc nhẹ đúng thời điểm.</p>` : `<p class="mute">Chưa có dữ liệu.</p>`)}</div>`;
    const co = X.cohorts;
    h += card("Giữ chân khách theo tháng đầu tiên mua (cohort)", co.length ? table(["Tháng đầu", ["Số khách", 1], ...[0, 1, 2, 3, 4, 5].map(i => ["Tháng +" + i, 1])], co.map(r => `<tr><td>${r.cohort}</td><td class="num">${r.size}</td>${r.ret.map(v => v == null ? `<td class="num mute">—</td>` : `<td class="num dx-cc" style="background:color-mix(in srgb,var(--pri) ${Math.round(v * .85)}%,transparent)">${v}%</td>`).join("")}</tr>`)) + `<p class="mute dx-note">Mỗi ô là tỷ lệ khách của tháng đó có đặt hàng trong tháng tương ứng sau khi mua lần đầu.</p>` : `<p class="mute">Chưa đủ dữ liệu.</p>`);
    return h;
  }

  const stCls = s => s === "Hết hàng" || s === "Khẩn cấp" ? "bad" : s === "Sắp hết" || s === "Tồn chậm" ? "warn" : "";
  function vPr() {
    const st = X.stock, urgent = st.filter(s => ["Hết hàng", "Khẩn cấp"].includes(s.status)), soon = st.filter(s => s.status === "Sắp hết");
    let h = insight(urgent.length || soon.length ? `<b>${urgent.length}</b> sản phẩm cần nhập ngay${urgent.length ? " (" + urgent.map(s => esc(s.name)).join(", ") + ")" : ""}${soon.length ? `, <b>${soon.length}</b> sản phẩm sắp hết trong 2 tuần` : ""}. Số lượng gợi ý đủ bán ${30} ngày sau thời gian chờ nhập ${7} ngày, có tồn kho an toàn 95%.` : "Tồn kho hiện đủ cho nhu cầu dự báo.");
    h += card("Dự báo tồn kho và gợi ý nhập hàng", table(["Sản phẩm", ["Tồn", 1], ["Nhu cầu dự báo/ngày", 1], ["Đủ bán", 1], ["Điểm đặt lại", 1], ["Gợi ý nhập", 1], "28 ngày qua", "Trạng thái"], st.map(s => `<tr><td>${esc(s.name)}</td><td class="num">${s.stock}</td><td class="num">${f1(s.rate)}</td><td class="num">${s.cover == null ? "—" : f1(s.cover) + " ngày"}</td><td class="num">${s.rop}</td><td class="num">${s.order_qty ? "<b>" + s.order_qty + "</b>" : "—"}</td><td>${spark(s.spark)}</td><td>${tag(s.status, stCls(s.status))}</td></tr>`)) + `<p class="mute dx-note">Nhu cầu dự báo dùng san mượt mũ (EWMA, chu kỳ 14 ngày). Điểm đặt lại = nhu cầu × thời gian chờ nhập + tồn kho an toàn (z = 1,65). Thời gian chờ nhập giả định 7 ngày.</p>`);
    const pr = X.products;
    h += card("Hiệu quả sản phẩm", table(["Sản phẩm", "Phân loại ABC", ["Đã bán", 1], ["Doanh thu", 1], ["Tỷ trọng", 1], ["Xu hướng 28 ngày", 1]], pr.map(p => `<tr><td>${esc(p.name)}<br><span class="mute">${esc(p.cat)}</span></td><td>${tag(p.abc, p.abc === "A" ? "" : p.abc === "B" ? "warn" : "bad")}</td><td class="num">${nf(p.units)}</td><td class="num">${full(p.revenue)}</td><td class="num">${f1(p.share)}%</td><td class="num">${chip(p.trend)}</td></tr>`)) + `<p class="mute dx-note">ABC theo doanh thu cộng dồn: A là nhóm tạo 70% đầu, B là 20% tiếp theo, C là phần còn lại. Xu hướng so sánh số lượng bán 28 ngày gần nhất với 28 ngày trước đó.</p>`, { sub: X.meta.range + " ngày gần nhất" });
    const b = X.basket;
    h += card("Sản phẩm thường mua cùng nhau (luật kết hợp)", b.rules.length ? insight(`${f1(b.multi_rate)}% đơn có từ 2 nhóm sản phẩm trở lên. Các cặp bên dưới đang được dùng để <b>gợi ý mua kèm trong giỏ hàng</b> của khách.`) + table(["Nếu khách mua", "Thường mua thêm", ["Số đơn", 1], ["Support", 1], ["Confidence", 1], ["Lift", 1]], b.rules.slice(0, 12).map(r => `<tr><td>${esc(r.a)}</td><td>${esc(r.b)}</td><td class="num">${r.count}</td><td class="num">${f1(r.support)}%</td><td class="num">${f1(r.conf)}%</td><td class="num">${r.lift.toFixed(2).replace(".", ",")}${r.lift >= 1.2 ? " " + tag("mạnh") : ""}</td></tr>`)) + `<p class="mute dx-note">Support: tỷ lệ đơn chứa cả hai. Confidence: trong số đơn có sản phẩm đầu, bao nhiêu % có sản phẩm sau. Lift lớn hơn 1 nghĩa là hai sản phẩm được mua cùng nhau nhiều hơn ngẫu nhiên. Chỉ hiển thị cặp có từ ${b.min_count} đơn trở lên và lift từ 1,05 trở lên.</p>` : `<p class="mute">Cần ít nhất 20 đơn và các cặp xuất hiện từ ${b.min_count} lần để có luật kết hợp.</p>`);
    return h;
  }

  function vOp() {
    const fu = X.funnel, tot = fu[0].n || 1;
    let h = `<div class="dx-g2">${card("Phễu xử lý đơn hàng", hbars(fu.map(s => ({ label: s.stage, value: s.n, text: nf(s.n) + " (" + f1(s.n * 100 / tot) + "%)", tip: [s.stage, nf(s.n) + " đơn"] })).concat([{ label: "Đã hủy", value: X.funnel_cancel, color: "var(--err)", text: nf(X.funnel_cancel) + " (" + f1(X.funnel_cancel * 100 / tot) + "%)" }])), { sub: "Đơn tạo trong " + X.meta.range + " ngày" })}
      ${card("Thời gian giữa các bước xử lý", X.stages.length ? table(["Bước", ["Trung vị", 1], ["Trung bình", 1]], X.stages.map(s => `<tr><td>${esc(s.frm)} → ${esc(s.to)}</td><td class="num">${f1(s.median)} giờ</td><td class="num">${f1(s.mean)} giờ</td></tr>`)) + (X.delivery.length ? `<h4 class="dx-h4">Từ lúc đặt đến khi giao xong</h4>` + table(["Hình thức", ["Trung vị", 1], ["90% đơn trong", 1], ["Số đơn", 1]], X.delivery.map(s => `<tr><td>${SHIPN[s.method]}</td><td class="num">${f1(s.median)} giờ</td><td class="num">${f1(s.p90)} giờ</td><td class="num">${s.n}</td></tr>`)) : "") : `<p class="mute">Chưa có đơn nào hoàn tất các bước.</p>`)}</div>`;
    h += card("Thanh toán và tỷ lệ hủy theo phương thức", X.mix.payment.length ? table(["Phương thức", ["Đơn", 1], ["Tỷ trọng", 1], ["Doanh thu", 1], ["Tỷ lệ hủy", 1]], X.mix.payment.map(p => `<tr><td>${PAYN[p.method]}</td><td class="num">${nf(p.orders)}</td><td class="num">${f1(p.share)}%</td><td class="num">${full(p.revenue)}</td><td class="num">${p.cancel >= 6 ? tag(f1(p.cancel) + "%", "bad") : f1(p.cancel) + "%"}</td></tr>`)) : `<p class="mute">Chưa có dữ liệu.</p>`);
    const fs = X.freeship;
    h += `<div class="dx-g2">${card("Cơ hội nâng giá trị đơn (ngưỡng freeship " + full(fs.threshold) + ")", insight(`<b>${fs.near}</b> đơn (${f1(fs.near_share)}%) có giá trị từ 70% đến dưới ngưỡng miễn phí ship và vẫn trả phí vận chuyển. Chỉ cần khách thêm trung bình <b>${full(fs.avg_gap)}</b> là đạt freeship; nếu tất cả bổ sung, doanh thu tăng khoảng <b>${full(fs.potential)}</b>.`) + `<div class="dx-met"><div><span class="mute">Đơn được miễn phí ship</span><b>${f1(fs.free_rate)}%</b></div><div><span class="mute">Phí ship khách đã trả</span><b>${mny(fs.ship_paid)}</b></div></div><p class="mute dx-note">Đề xuất: hiển thị gợi ý mua kèm ngay trong giỏ hàng khi còn thiếu dưới 100.000đ (đã có trên website).</p>`)}
      ${card("Hiệu quả mã giảm giá", X.vouchers.rows.length ? `<p class="mute dx-note" style="margin-top:0">${f1(X.vouchers.used_rate)}% đơn dùng mã. Giá trị đơn trung bình khi không dùng mã: ${full(X.vouchers.aov_without)}.</p>` + table(["Mã", ["Lượt dùng", 1], ["Tiền giảm", 1], ["Giá trị đơn TB", 1], ["So với không mã", 1]], X.vouchers.rows.map(v => `<tr><td>${esc(v.code)}</td><td class="num">${v.uses}</td><td class="num">${full(v.discount)}</td><td class="num">${full(v.aov)}</td><td class="num">${chip(v.uplift)}</td></tr>`)) : `<p class="mute">Chưa có đơn nào dùng mã giảm giá.</p>`)}</div>`;
    return h;
  }

  function vMe() {
    const m = X.meta;
    const rows = [["Dự báo doanh thu", "Holt-Winters, hồi quy OLS, trung bình theo thứ", "Chọn mô hình có WAPE thấp nhất khi kiểm tra trên 14 ngày gần nhất; khoảng tin cậy 95% từ sai số kiểm tra."],
      ["Phát hiện bất thường", "Robust z-score (trung vị cùng thứ + MAD)", "Ít bị ảnh hưởng bởi ngày khuyến mãi lớn khi ước lượng mức bình thường."],
      ["Phân khúc khách hàng", "RFM + K-means (k-means++), chọn k bằng Silhouette", "Đặc trưng lấy log và chuẩn hóa; tự gán tên nhóm theo đặc điểm trung tâm cụm."],
      ["Khả năng mua lại 30 ngày", "Hồi quy logistic (Newton-Raphson, L2)", "Huấn luyện nhiều mốc thời gian, tách tập kiểm tra theo khách hàng, báo cáo AUC."],
      ["Sản phẩm mua cùng nhau", "Luật kết hợp dạng cặp (support, confidence, lift)", "Nhóm các phiên bản cùng tên (250g/500g/1kg); dùng gợi ý mua kèm trong giỏ hàng."],
      ["Dự báo tồn kho", "EWMA + tồn kho an toàn", "Điểm đặt lại = nhu cầu × thời gian chờ nhập + 1,65 × độ lệch chuẩn × √thời gian chờ."]];
    return card("Dữ liệu đang dùng", `<div class="dx-met"><div><span class="mute">Đơn hàng</span><b>${nf(m.n_orders)}</b></div><div><span class="mute">Đơn hợp lệ</span><b>${nf(m.n_valid)}</b></div><div><span class="mute">Khách đã mua</span><b>${nf(m.n_customers)}</b></div><div><span class="mute">Số ngày có dữ liệu</span><b>${nf(m.n_days || 0)}</b></div></div>`)
      + card("Thuật toán", table(["Chức năng", "Thuật toán", "Ghi chú"], rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td></tr>`)))
      + card("Vì sao chưa dùng học sâu (deep learning)?", `<p>Mạng nơ-ron như LSTM hay Transformer cần nhiều dữ liệu (thường từ vài năm lịch sử theo ngày hoặc hàng chục nghìn đơn) mới vượt được các mô hình thống kê. Với cửa hàng ở quy mô vài trăm đơn mỗi tháng, mô hình sâu dễ học thuộc nhiễu và cho dự báo kém ổn định hơn Holt-Winters hay hồi quy. Phần backtest ngay trong tab Dự báo cho thấy mô hình nào đang thắng trên dữ liệu thật của bạn.</p><p>Khi dữ liệu đủ lớn, có thể bổ sung LSTM/Temporal Fusion Transformer vào danh sách mô hình; cơ chế so sánh bằng backtest hiện có sẽ tự quyết định có dùng hay không.</p>`)
      + card("Lưu ý khi đọc kết quả", `<ul class="chk"><li>Dữ liệu ít thì kết quả dao động mạnh; hãy xem các chỉ số sai số và AUC đi kèm.</li><li>Số liệu tính theo giờ Việt Nam (UTC+7), loại trừ đơn đã hủy khỏi doanh thu.</li><li>Dự báo không biết trước khuyến mãi, ngày lễ hay sự cố sắp tới.</li><li>Cache kết quả theo thay đổi dữ liệu nên tải lại nhanh.</li></ul>`);
  }

  /* ---------- khung chính ---------- */
  function body() {
    if (XERR) return `<div class="msg err">${esc(XERR)}</div>`;
    if (!X) return `<p class="mute">Đang phân tích dữ liệu…</p>`;
    if (X.meta.empty) return card("Chưa có đơn hàng để phân tích", `<p class="mute">Dashboard cần dữ liệu đơn hàng. Để xem thử, chạy lệnh sau rồi tải lại trang (dùng cơ sở dữ liệu riêng để không lẫn với dữ liệu thật):</p><pre class="dx-pre">cd backend\npython seed_demo.py --db ../database/demo.db\nHL_DB=../database/demo.db python server.py</pre>`);
    return (X.meta.demo ? `<div class="msg dx-demo">Đang hiển thị <b>dữ liệu mô phỏng</b> tạo bởi seed_demo.py. Số liệu không phản ánh cửa hàng thật.</div>` : "") + ({ ov: vOv, fc: vFc, cu: vCu, pr: vPr, op: vOp, me: vMe })[XT]();
  }
  function view() {
    return `<div class="dx-bar"><div class="chips" role="tablist" aria-label="Nhóm phân tích">${TABS.map(t => `<button type="button" role="tab" aria-selected="${t[0] === XT}" class="chip ${t[0] === XT ? "on" : ""}" data-dx="${t[0]}">${t[1]}</button>`).join("")}</div>
      <div class="dx-ctl"><label for="dxr" class="mute">Kỳ phân tích</label><select id="dxr" aria-label="Kỳ phân tích">${[30, 90, 180, 365].map(r => `<option value="${r}" ${r === XR ? "selected" : ""}>${r} ngày</option>`).join("")}</select><button type="button" class="btn alt sm" data-dxrefresh="1">Làm mới</button></div></div>
      <div id="dxb" class="${XLOAD ? "dx-busy" : ""}">${body()}</div>`;
  }
  function paint() { const el = document.querySelector("#dx"); if (el) el.innerHTML = view(); }
  async function load() {
    if (XLOAD) return;
    XLOAD = true; XERR = ""; paint();
    try {
      const r = await fetch("/api/analytics?range=" + XR, { cache: "no-store" });
      if (!r.ok) throw new Error("http");
      X = await r.json();
    } catch (e) { XERR = "Không tải được số liệu phân tích. Hãy chạy máy chủ (cd backend && python server.py) và mở trang qua http://localhost:8000; mở trực tiếp tệp index.html không có dashboard."; }
    XLOAD = false; paint();
  }
  window.aDash = function () {
    if (!X || X.meta.range !== XR) setTimeout(load, 0);
    return `<div id="dx">${view()}</div>`;
  };

  document.addEventListener("click", e => {
    const t = e.target.closest("[data-dx],[data-dxrefresh]");
    if (!t || !document.querySelector("#dx")) return;
    if (t.dataset.dx) { XT = t.dataset.dx; paint(); scrollTo({ top: 0 }); } else { X = null; load(); }
  });
  document.addEventListener("change", e => {
    if (e.target.id === "dxr") { XR = +e.target.value; X = null; load(); }
  });
  let tipEl;
  document.addEventListener("mousemove", e => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "dx-tip"; tipEl.setAttribute("role", "tooltip"); document.body.appendChild(tipEl); }
    if (!t) { tipEl.style.display = "none"; return; }
    tipEl.innerHTML = t.dataset.tip.split("\n").map((l, i) => i ? esc(l) : `<b>${esc(l)}</b>`).join("<br>");
    tipEl.style.display = "block";
    const w = tipEl.offsetWidth, x = Math.min(e.clientX + 14, innerWidth - w - 8);
    tipEl.style.left = Math.max(6, x) + "px"; tipEl.style.top = (e.clientY + 16) + "px";
  });
})();
