/* Theo dõi trực tiếp xe giao hàng và đơn hàng (trang quản trị).
   Bản đồ OpenStreetMap vẽ bằng JS thuần (không cần thư viện); dữ liệu cập nhật qua Server-Sent Events (/api/stream).
   Nạp TRƯỚC app.js; dùng các hàm/biến toàn cục của app.js tại thời điểm gọi. */
(function () {
  const T = { veh: {}, trail: {}, feed: [], sel: null, sim: false, es: null, live: false, down: false, fitted: false,
              z: 13, lat: 10.7746, lng: 106.6857, layer: null, tiles: {}, mk: {}, raf: 0, newTok: null, fleet: [] };
  const STORE = [10.7746, 106.6857], TS = 256;
  const KIND = { bike: "🛵", van: "🚐", truck: "🚚" }, KN = { bike: "Xe máy", van: "Xe van", truck: "Xe tải" };
  const act = o => o.st !== CANCEL && o.st !== "Đã giao";
  const q1 = s => document.querySelector(s);

  const hav = (a, b) => { const r = Math.PI / 180, dl = (b[0] - a[0]) * r, dn = (b[1] - a[1]) * r,
    x = Math.sin(dl / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dn / 2) ** 2; return 12742 * Math.asin(Math.sqrt(x)); };
  const lx = (g, z = T.z) => (g + 180) / 360 * 2 ** z * TS;
  const ly = (t, z = T.z) => { const s = Math.sin(t * Math.PI / 180); return (.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * 2 ** z * TS; };
  const xl = (x, z = T.z) => x / (TS * 2 ** z) * 360 - 180;
  const yl = (y, z = T.z) => { const n = Math.PI - 2 * Math.PI * y / (TS * 2 ** z); return 180 / Math.PI * Math.atan(.5 * (Math.exp(n) - Math.exp(-n))); };
  const ago = at => {
    if (!at) return "chưa có vị trí";
    const s = Math.max(0, Math.round((Date.now() - new Date(at)) / 1000));
    return s < 5 ? "vừa xong" : s < 60 ? s + " giây trước" : s < 3600 ? Math.round(s / 60) + " phút trước" : Math.round(s / 3600) + " giờ trước";
  };
  const isOnline = v => v.at && Date.now() - new Date(v.at) < 90000;

  /* ---------- bản đồ ---------- */
  function clearTiles() { if (T.layer) T.layer.innerHTML = ""; T.tiles = {}; }
  function tiles() {
    const el = q1("#lvmap"); if (!el || !T.layer) return;
    const W = el.clientWidth, H = el.clientHeight, z = T.z, n = 2 ** z, l = lx(T.lng) - W / 2, t = ly(T.lat) - H / 2, want = {};
    for (let ty = Math.floor(t / TS); ty <= Math.floor((t + H) / TS); ty++) {
      if (ty < 0 || ty >= n) continue;
      for (let tx = Math.floor(l / TS); tx <= Math.floor((l + W) / TS); tx++) want[z + "/" + (((tx % n) + n) % n) + "/" + ty + "@" + tx] = [tx * TS - l, ty * TS - t];
    }
    Object.keys(T.tiles).forEach(k => { if (!want[k]) { T.tiles[k].remove(); delete T.tiles[k]; } });
    Object.entries(want).forEach(([k, p]) => {
      let i = T.tiles[k];
      if (!i) {
        i = document.createElement("img"); i.alt = ""; i.draggable = false; i.className = "lv-t";
        i.onerror = () => { i.style.visibility = "hidden"; };
        i.src = "https://tile.openstreetmap.org/" + k.split("@")[0] + ".png";
        T.layer.appendChild(i); T.tiles[k] = i;
      }
      i.style.transform = "translate(" + p[0] + "px," + p[1] + "px)";
    });
  }

  function overlay() {
    const el = q1("#lvmap"); if (!el) return;
    const W = el.clientWidth, H = el.clientHeight, cx = lx(T.lng), cy = ly(T.lat), P = (la, lo) => [lx(lo) - cx + W / 2, ly(la) - cy + H / 2];
    const keep = new Set(), host = el.querySelector(".lv-mks");
    const mk = (key, cls, html, pos, title, vid) => {
      keep.add(key); let e = T.mk[key];
      if (!e || !e.isConnected) { e = document.createElement("button"); e.type = "button"; T.mk[key] = e; host.appendChild(e); }
      e.className = "lv-mk " + cls; e.innerHTML = html; e.title = title || ""; e.dataset.lvveh = vid || "";
      e.style.transform = "translate(" + pos[0] + "px," + pos[1] + "px)";
    };
    mk("store", "store", "🏬", P(STORE[0], STORE[1]), "Cửa hàng HEALTHY LIFE");
    let svg = "";
    DB.orders.filter(o => act(o) && o.dest).forEach(o => {
      const p = P(o.dest[0], o.dest[1]), v = T.veh[o.veh];
      mk("o:" + o.id, "pin" + (o.veh ? "" : " free") + (T.sel && o.veh === T.sel ? " sel" : ""), "📍<b>" + esc(o.id.slice(2)) + "</b>", p, o.id + " – " + o.cust.name + "\n" + o.cust.addr + (o.veh ? "\nXe " + o.veh : "\nChưa gán xe"));
      if (v && v.lat != null) { const a = P(v.lat, v.lng); svg += `<line x1="${a[0]}" y1="${a[1]}" x2="${p[0]}" y2="${p[1]}" class="lv-route${T.sel === v.id ? " sel" : ""}"/>`; }
    });
    Object.values(T.veh).forEach(v => {
      if (v.lat == null) return;
      const tr = T.trail[v.id] || [];
      if (tr.length > 1) svg += `<polyline class="lv-trail${T.sel === v.id ? " sel" : ""}" points="${tr.map(p => P(p[0], p[1]).map(n => n.toFixed(1)).join(",")).join(" ")}"/>`;
      mk("v:" + v.id, "veh" + (T.sel === v.id ? " sel" : "") + (isOnline(v) ? "" : " off") + (v.active === false ? " pause" : ""),
        `<span>${KIND[v.kind] || "🛵"}</span><b>${esc(v.plate || v.id)}</b>`, P(v.lat, v.lng),
        (v.plate || v.id) + " – " + (v.driver || "") + "\n" + (v.speed != null ? Math.round(v.speed) + " km/h · " : "") + ago(v.at), v.id);
    });
    Object.keys(T.mk).forEach(k => { if (!keep.has(k)) { T.mk[k].remove(); delete T.mk[k]; } });
    el.querySelector(".lv-svg").innerHTML = svg;
  }

  const redraw = () => { tiles(); overlay(); };
  function zoom(d) { T.z = Math.max(10, Math.min(18, T.z + d)); clearTiles(); redraw(); }
  function fit() {
    const el = q1("#lvmap"); if (!el) return;
    const pts = [STORE].concat(Object.values(T.veh).filter(v => v.lat != null).map(v => [v.lat, v.lng]), DB.orders.filter(o => act(o) && o.dest).map(o => o.dest));
    const la = pts.map(p => p[0]), lo = pts.map(p => p[1]);
    T.lat = (Math.min(...la) + Math.max(...la)) / 2; T.lng = (Math.min(...lo) + Math.max(...lo)) / 2;
    let z = 17;
    for (; z > 10; z--) { if (Math.abs(lx(Math.max(...lo), z) - lx(Math.min(...lo), z)) < el.clientWidth * .8 && Math.abs(ly(Math.min(...la), z) - ly(Math.max(...la), z)) < el.clientHeight * .8) break; }
    T.z = z; clearTiles(); redraw();
  }
  function bind(el) {
    let drag = null;
    el.onpointerdown = e => { if (e.target.closest("button,a")) return; drag = { x: e.clientX, y: e.clientY }; el.setPointerCapture(e.pointerId); el.classList.add("drag"); };
    el.onpointermove = e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag = { x: e.clientX, y: e.clientY };
      T.lng = xl(lx(T.lng) - dx); T.lat = yl(ly(T.lat) - dy); redraw();
    };
    el.onpointerup = el.onpointercancel = () => { drag = null; el.classList.remove("drag"); };
    el.addEventListener("wheel", e => { e.preventDefault(); zoom(e.deltaY < 0 ? 1 : -1); }, { passive: false });
  }

  /* ---------- danh sách ---------- */
  function vStatus(v) {
    if (v.active === false) return ["Tạm ngưng", "off"];
    if (v.lat == null) return ["Chưa có vị trí", "off"];
    if (!isOnline(v)) return ["Mất tín hiệu · " + ago(v.at), "bad"];
    return v.busy ? ["Đang giao " + v.busy + " đơn" + (v.speed != null ? " · " + Math.round(v.speed) + " km/h" : ""), "ok"] : ["Rảnh · " + ago(v.at), "idle"];
  }
  function paintVeh() {
    const el = q1("#lvveh"); if (!el) return;
    const list = Object.values(T.veh).filter(v => v.plate).sort((a, b) => a.id.localeCompare(b.id));
    el.innerHTML = list.length ? list.map(v => { const s = vStatus(v);
      return `<button type="button" class="lv-v ${T.sel === v.id ? "on" : ""}" data-lvveh="${esc(v.id)}"><span class="lv-ic">${KIND[v.kind] || "🛵"}</span><span class="lv-vi"><b>${esc(v.plate)}</b><small>${esc(v.driver)} · ${esc(v.id)}</small><small class="lv-s ${s[1]}">${esc(s[0])}</small></span></button>`; }).join("")
      : `<p class="mute">Chưa có xe nào. Thêm xe ở tab <b>Đội xe</b>.</p>`;
  }
  function eta(o) {
    const v = T.veh[o.veh];
    if (!o.dest) return o.veh ? `<span class="mute">Chưa xác định điểm giao</span>` : "";
    if (!v || v.lat == null) return o.veh ? `<span class="mute">Chờ vị trí xe</span>` : "";
    const d = hav([v.lat, v.lng], o.dest), sp = v.speed > 8 ? v.speed : 25;
    return d < .08 ? "<b>Đã tới nơi</b>" : `${d.toFixed(1).replace(".", ",")} km · ~${Math.max(1, Math.round(d / sp * 60))} phút`;
  }
  function paintOrd() {
    const el = q1("#lvord"); if (!el) return;
    const vs = Object.values(T.veh).filter(v => v.plate && v.active !== false).sort((a, b) => a.id.localeCompare(b.id));
    const list = DB.orders.filter(act).sort((a, b) => b.at.localeCompare(a.at));
    el.innerHTML = list.length ? `<table><tr><th>Đơn</th><th>Giao tới</th><th>Trạng thái</th><th>Xe</th><th>Còn lại</th><th></th></tr>${list.map(o => {
      const next = ST[ST.indexOf(o.st) + 1];
      return `<tr><td><b>${esc(o.id)}</b><br><span class="mute">${dt(o.at)}</span></td><td>${esc(o.cust.name)}<br><span class="mute">${esc(o.cust.addr)}</span></td>
<td><span class="tag">${esc(o.st)}</span>${o.pay.m !== "cod" && !o.pay.paid ? `<br><span class="tag warn">Chưa thu tiền</span>` : ""}</td>
<td><select data-lvassign="${esc(o.id)}" aria-label="Xe giao đơn ${esc(o.id)}"><option value="">— chưa gán —</option>${vs.map(v => `<option value="${esc(v.id)}" ${v.id === o.veh ? "selected" : ""}>${esc(v.plate)} · ${esc(v.driver)}</option>`).join("")}</select></td>
<td>${eta(o)}</td><td>${next ? `<button type="button" class="btn sm" data-next="${esc(o.id)}">→ ${next}</button>` : ""} ${!o.pay.paid && o.pay.m !== "cod" ? `<button type="button" class="btn alt sm" data-paid="${esc(o.id)}">Đã thu tiền</button>` : ""}</td></tr>`; }).join("")}</table>`
      : `<p class="mute">Không có đơn nào đang xử lý.</p>`;
  }
  function paintFeed() {
    const el = q1("#lvfeed"); if (!el) return;
    el.innerHTML = T.feed.length ? T.feed.map(f => `<p class="mute" style="margin:2px 0">${new Date(f.t).toLocaleTimeString("vi-VN")} – ${esc(f.m)}</p>`).join("") : `<p class="mute">Chưa có hoạt động mới. Sự kiện sẽ hiện ngay khi có đơn hoặc xe thay đổi.</p>`;
  }
  function status() {
    const el = q1("#lvst"); if (!el) return;
    el.innerHTML = (T.live ? `<span class="lv-dot on"></span> Đang nhận dữ liệu trực tiếp` : `<span class="lv-dot"></span> Mất kết nối, đang thử lại…`) + (T.sim ? ` · <span class="tag warn">Chế độ mô phỏng: vị trí xe là giả lập</span>` : "");
  }
  const paintAll = () => { redraw(); paintVeh(); paintOrd(); paintFeed(); status(); };
  const feed = m => { T.feed.unshift({ t: Date.now(), m }); T.feed = T.feed.slice(0, 25); paintFeed(); };
  const sched = () => { if (!T.raf) T.raf = requestAnimationFrame(() => { T.raf = 0; overlay(); paintVeh(); }); };

  /* ---------- dữ liệu và luồng thời gian thực ---------- */
  async function loadLive() {
    const j = await hlApi("/api/admin/live", undefined, "GET");
    T.sim = j.sim; const ids = new Set(j.vehicles.map(v => v.id));
    Object.keys(T.veh).forEach(id => { if (!ids.has(id)) delete T.veh[id]; });
    j.vehicles.forEach(v => { T.trail[v.id] = v.trail || []; T.veh[v.id] = v; });
    return j;
  }
  function onVeh(v) {
    const o = T.veh[v.id] || (T.veh[v.id] = { id: v.id }); Object.assign(o, v);
    const tr = T.trail[v.id] || (T.trail[v.id] = []); tr.push([v.lat, v.lng]); if (tr.length > 40) tr.shift();
    if (!o.plate) { loadLive().then(() => { paintVeh(); paintOrd(); }).catch(() => {}); return; }
    sched();
  }
  function onOrd(o) {
    const i = DB.orders.findIndex(x => x.id === o.id), prev = i < 0 ? null : DB.orders[i];
    if (i < 0) DB.orders.unshift(o); else DB.orders[i] = o;
    feed(!prev ? `Đơn mới ${o.id} – ${vnd(o.total)} (${o.cust.name})` : prev.st !== o.st ? `${o.id} → ${o.st}` : prev.veh !== o.veh ? `${o.id}: ${o.veh ? "gán xe " + o.veh : "gỡ xe"}` : `${o.id} được cập nhật`);
    if (!prev) {   // đơn mới: cập nhật tồn kho và báo trên tiêu đề tab
      sync(true); const t = document.title; document.title = "🔔 Đơn mới " + o.id; setTimeout(() => { document.title = t; }, 8000);
    }
    if (q1("#lvmap")) { overlay(); paintOrd(); }
    else if (admin && (tab === "ord" || tab === "over")) {
      clearTimeout(T.rt);
      T.rt = setTimeout(() => { if (!/INPUT|SELECT|TEXTAREA/.test((document.activeElement || {}).tagName || "")) render(); }, 400);
    }
  }
  window.startStream = function () {
    if (T.es || typeof API === "undefined" || !API) return;
    const es = new EventSource("/api/stream"); T.es = es;
    es.onopen = () => {
      T.live = true; status();
      if (T.down) { T.down = false; sync(true); loadLive().then(paintAll).catch(() => {}); }   // đồng bộ lại sau khi mất kết nối
    };
    es.onerror = () => {
      T.live = false; T.down = true; status();
      fetch("/api/auth/me").then(r => r.json()).then(j => { if (!j.user || j.user.role !== "admin") stopStream(); }).catch(() => {});
    };
    es.addEventListener("vehicle", e => onVeh(JSON.parse(e.data)));
    es.addEventListener("order", e => onOrd(JSON.parse(e.data)));
  };
  window.stopStream = function () { if (T.es) { T.es.close(); T.es = null; } T.live = false; };

  /* ---------- tab "Theo dõi trực tiếp" ---------- */
  function mount() {
    const el = q1("#lvmap"); if (!el) return;
    T.layer = el.querySelector(".lv-tiles"); T.tiles = {}; T.mk = {}; bind(el); startStream();
    paintAll();
    loadLive().then(() => { if (!T.fitted) { T.fitted = true; fit(); } paintAll(); }).catch(() => {});
  }
  window.aLive = function () {
    setTimeout(mount, 0);
    return `<p id="lvst" class="mute" style="margin:8px 0"></p>
<div class="lv-grid"><div class="card lv-mapcard"><div class="lv-tools"><button type="button" class="btn alt sm" data-lv="zin" aria-label="Phóng to">+</button><button type="button" class="btn alt sm" data-lv="zout" aria-label="Thu nhỏ">−</button><button type="button" class="btn alt sm" data-lv="fit">Xem tất cả</button></div>
<div id="lvmap" class="lv-map" role="application" aria-label="Bản đồ xe giao hàng"><div class="lv-tiles"></div><svg class="lv-svg" aria-hidden="true"></svg><div class="lv-mks"></div><a class="lv-attr" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a></div>
<p class="mute" style="margin:8px 0 0;font-size:12px">🏬 cửa hàng · 🛵 xe (mờ = mất tín hiệu) · 📍 điểm giao ước lượng theo quận/huyện trong địa chỉ. Kéo để di chuyển, cuộn để phóng to.</p></div>
<div class="card"><h3 style="margin-bottom:8px">Đội xe</h3><div id="lvveh" class="lv-list"></div></div></div>
<div class="card" style="margin-top:14px"><h3 style="margin-bottom:8px">Đơn đang xử lý và giao</h3><div id="lvord" class="tbl"></div></div>
<div class="card" style="margin-top:14px"><h3 style="margin-bottom:8px">Hoạt động trực tiếp</h3><div id="lvfeed"></div></div>`;
  };
  setInterval(() => { if (q1("#lvmap")) { paintVeh(); } }, 5000);   // cập nhật "x giây trước", trạng thái mất tín hiệu

  /* ---------- tab "Đội xe" ---------- */
  async function loadFleet() {
    try { T.fleet = (await hlApi("/api/admin/vehicles", undefined, "GET")).vehicles; paintFleet(); }
    catch (e) { const el = q1("#flt"); if (el) el.innerHTML = `<div class="msg err">${esc(e.message)}</div>`; }
  }
  function paintFleet() {
    const el = q1("#flt"); if (!el) return;
    const link = location.origin + "/driver.html", n = T.newTok;
    el.innerHTML = `${n ? `<div class="msg"><b>Mã thiết bị của xe ${esc(n.id)}</b> (chỉ hiện một lần, hãy lưu lại):<br><code class="lv-tok">${esc(n.token)}</code> <button type="button" class="link" data-copy="${esc(n.token)}">Sao chép</button><br>
Tài xế mở <b>${esc(link)}</b> trên điện thoại, dán mã này và bấm "Bắt đầu chia sẻ vị trí". Trình duyệt chỉ cho dùng GPS trên HTTPS (hoặc localhost).</div>` : ""}
<form class="card" id="vf"><h3>Thêm xe</h3><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))">
<div><label for="vp">Biển số</label><input id="vp" required maxlength="20" placeholder="59X1-123.45"></div>
<div><label for="vd">Tài xế</label><input id="vd" required maxlength="60"></div>
<div><label for="vph">Điện thoại tài xế</label><input id="vph" pattern="0[0-9]{9}" inputmode="tel"></div>
<div><label for="vk">Loại xe</label><select id="vk">${Object.entries(KN).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div></div>
<div id="verr" role="alert"></div><p><button class="btn">Thêm xe</button></p></form>
<div class="card tbl" style="margin-top:14px"><table><tr><th>Xe</th><th>Tài xế</th><th>Trạng thái</th><th>Vị trí cuối</th><th></th></tr>${T.fleet.map(v => { const s = vStatus(v);
      return `<tr><td>${KIND[v.kind] || ""} <b>${esc(v.plate)}</b><br><span class="mute">${esc(v.id)} · ${KN[v.kind] || ""}</span></td><td>${esc(v.driver)}<br><span class="mute">${esc(v.phone)}</span></td><td><span class="lv-s ${s[1]}">${esc(s[0])}</span></td><td>${v.lat != null ? v.lat.toFixed(5) + ", " + v.lng.toFixed(5) : "—"}<br><span class="mute">${ago(v.at)}</span></td>
<td><button type="button" class="btn alt sm" data-flt="token:${esc(v.id)}">Cấp lại mã</button> <button type="button" class="btn alt sm" data-flt="${v.active ? "off" : "on"}:${esc(v.id)}">${v.active ? "Tạm ngưng" : "Bật lại"}</button> <button type="button" class="btn bad sm" data-flt="del:${esc(v.id)}">Xóa</button></td></tr>`; }).join("") || `<tr><td colspan="5" class="mute">Chưa có xe nào.</td></tr>`}</table></div>`;
  }
  window.aFleet = function () { setTimeout(loadFleet, 0); return `<div id="flt"><p class="mute">Đang tải…</p></div>`; };

  /* ---------- xử lý thao tác ---------- */
  document.addEventListener("click", async e => {
    const t = e.target.closest("button"); if (!t) return;
    const d = t.dataset;
    if (d.lv) { d.lv === "zin" ? zoom(1) : d.lv === "zout" ? zoom(-1) : fit(); }
    else if (d.lvveh) {
      T.sel = T.sel === d.lvveh ? null : d.lvveh; const v = T.veh[T.sel];
      if (v && v.lat != null) { T.lat = v.lat; T.lng = v.lng; if (T.z < 14) T.z = 15; clearTiles(); }
      redraw(); paintVeh();
    } else if (d.flt) {
      const [a, id] = d.flt.split(":");
      try {
        if (a === "token") { if (!confirm("Cấp lại mã cho xe " + id + "? Mã cũ sẽ ngừng hoạt động.")) return; T.newTok = { id, token: (await hlApi("/api/admin/vehicles/" + id + "/token", {})).token }; }
        else if (a === "del") { if (!confirm("Xóa xe " + id + "?")) return; await hlApi("/api/admin/vehicles/" + id + "/delete", {}); }
        else await hlApi("/api/admin/vehicles/" + id + "/active", { on: a === "on" });
      } catch (x) { toast(x.message, 1); render(); return; }
      loadFleet();
    }
  });
  document.addEventListener("change", async e => {
    const s = e.target; if (!s.dataset || !s.dataset.lvassign) return;
    try { await hlApi("/api/admin/orders/" + s.dataset.lvassign + "/assign", { vehicle: s.value }); }
    catch (x) { toast(x.message, 1); paintOrd(); }
  });
  document.addEventListener("submit", async e => {
    if (e.target.id !== "vf") return;
    const err = m => { const el = q1("#verr"); if (el) el.innerHTML = `<div class="msg err">${esc(m)}</div>`; };
    try {
      const j = await hlApi("/api/admin/vehicles", { plate: $("#vp").value, driver: $("#vd").value, phone: $("#vph").value, kind: $("#vk").value });
      T.newTok = { id: j.id, token: j.token }; loadFleet();
    } catch (x) { err(x.message); }
  });
})();
