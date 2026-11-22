/* Trang tài xế: gửi vị trí GPS và cập nhật trạng thái đơn bằng mã thiết bị của xe. */
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const vnd = n => Number(n).toLocaleString("vi-VN") + "đ";
  let tok = "", watch = null, lastSent = 0, wake = null, V = null;
  try { tok = localStorage.getItem("hl_vtok") || ""; } catch (e) { /* bỏ qua */ }

  async function api(path, body) {
    const r = await fetch(path, { method: body === undefined ? "GET" : "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + tok }, body: body === undefined ? undefined : JSON.stringify(body) });
    let j = {}; try { j = await r.json(); } catch (e) { /* không phải JSON */ }
    if (!r.ok) throw Object.assign(new Error(j.error || "Lỗi kết nối"), { status: r.status });
    return j;
  }
  const err = m => { $("#err").textContent = m || ""; };

  async function refresh() {
    if (!tok) return;
    try {
      const j = await api("/api/vehicle/me"); V = j.vehicle; err("");
      $("#login").hidden = true; $("#main").hidden = false;
      $("#who").textContent = V.plate + " · " + V.driver;
      $("#orders").innerHTML = j.orders.length ? j.orders.map(o => `<div class="card"><div class="row"><b>${esc(o.id)}</b><span class="tag">${esc(o.st)}</span></div>
<p style="margin:6px 0">${esc(o.name)} · <a href="tel:${esc(o.phone)}">${esc(o.phone)}</a><br>${esc(o.addr)}</p>
<p class="mute" style="margin:6px 0">${esc(o.items)}</p>${o.collect ? `<p class="bad" style="margin:6px 0">Thu hộ (COD): ${vnd(o.collect)}</p>` : `<p class="ok" style="margin:6px 0">Đã thanh toán</p>`}${o.call ? `<p class="mute">Gọi xác nhận trước khi giao.</p>` : ""}
<p class="row">${o.dest ? `<a href="https://www.google.com/maps/dir/?api=1&destination=${o.dest[0]},${o.dest[1]}" target="_blank" rel="noopener">Chỉ đường (ước lượng)</a>` : ""}
${o.st === "Đã bàn giao vận chuyển" ? `<button data-a="pick" data-id="${esc(o.id)}">Bắt đầu giao</button>` : ""}${o.st === "Đang giao" ? `<button data-a="deliver" data-id="${esc(o.id)}">Đã giao xong</button>` : ""}</p></div>`).join("") : `<p class="mute">Chưa có đơn nào được giao cho xe này.</p>`;
    } catch (e) {
      if (e.status === 401 || e.status === 403) { stop(); $("#main").hidden = true; $("#login").hidden = false; tok = ""; try { localStorage.removeItem("hl_vtok"); } catch (x) { /* bỏ qua */ } }
      err(e.message);
    }
  }

  // Trình duyệt chỉ báo GPS khi vị trí đổi: giới hạn tần suất nhưng luôn gửi bản mới nhất,
  // và gửi lại vị trí cuối mỗi 20 giây khi xe đứng yên để quản trị không báo nhầm là mất tín hiệu.
  let last = null, timer = null;
  function flush(stale) {
    clearTimeout(timer); timer = null; if (!last) return;
    lastSent = Date.now(); const c = last.coords;
    api("/api/vehicle/location", { lat: c.latitude, lng: c.longitude, speed: stale || c.speed == null ? (stale ? 0 : null) : c.speed * 3.6, heading: c.heading })
      .then(() => { $("#gps").innerHTML = `<span class="ok">● Đang chia sẻ vị trí</span> · cập nhật ${new Date().toLocaleTimeString("vi-VN")} (±${Math.round(c.accuracy)} m)`; err(""); })
      .catch(e => err(e.message));
  }
  function send(pos) {
    last = pos; const wait = 4000 - (Date.now() - lastSent);
    if (wait <= 0) flush(); else if (!timer) timer = setTimeout(flush, wait);
  }
  setInterval(() => { if (watch != null && last && !timer && Date.now() - lastSent > 20000) flush(true); }, 5000);
  async function start() {
    if (!navigator.geolocation) return err("Thiết bị không hỗ trợ GPS");
    watch = navigator.geolocation.watchPosition(send, e => err(e.code === 1 ? "Bạn chưa cho phép truy cập vị trí. GPS chỉ hoạt động trên HTTPS hoặc localhost." : "Không lấy được vị trí: " + e.message), { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 });
    $("#go").textContent = "Dừng chia sẻ"; $("#gps").textContent = "Đang chờ tín hiệu GPS…";
    try { wake = await navigator.wakeLock?.request("screen"); } catch (e) { /* không bắt buộc */ }
  }
  function stop() {
    if (watch != null) navigator.geolocation.clearWatch(watch); watch = null; last = null; clearTimeout(timer); timer = null;
    try { wake && wake.release(); } catch (e) { /* bỏ qua */ } wake = null;
    $("#go").textContent = "Bắt đầu chia sẻ vị trí"; $("#gps").textContent = "Chưa chia sẻ vị trí";
  }

  $("#save").onclick = () => { tok = $("#tok").value.trim(); try { localStorage.setItem("hl_vtok", tok); } catch (e) { /* bỏ qua */ } $("#tok").value = ""; refresh(); };
  $("#go").onclick = () => (watch == null ? start() : stop());
  $("#out").onclick = () => { stop(); tok = ""; try { localStorage.removeItem("hl_vtok"); } catch (e) { /* bỏ qua */ } $("#main").hidden = true; $("#login").hidden = false; $("#orders").innerHTML = ""; };
  $("#orders").onclick = async e => {
    const b = e.target.closest("button[data-a]"); if (!b) return;
    b.disabled = true;
    try { await api("/api/vehicle/orders/" + b.dataset.id + "/" + b.dataset.a, {}); } catch (x) { err(x.message); }
    refresh();
  };
  refresh(); setInterval(refresh, 10000);
})();
