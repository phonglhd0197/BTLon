/* Tài khoản khách hàng (đăng ký, đăng nhập, trang tài khoản) và đăng nhập quản trị phía máy chủ.
   Cần chạy bằng server.py. Nạp TRƯỚC app.js; dùng các hàm/biến toàn cục của app.js tại thời điểm gọi. */
(function () {
  window.ME = null;      // người dùng hiện tại (khách hoặc quản trị) hoặc null
  window.MINE = [];      // đơn hàng của tài khoản đang đăng nhập

  async function hlApi(path, body, method) {
    const r = await fetch(path, {
      method: method || "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    let j = {};
    try { j = await r.json(); } catch (e) { /* phản hồi không phải JSON */ }
    if (!r.ok) throw Object.assign(new Error(j.error || "Có lỗi xảy ra, vui lòng thử lại"), { status: r.status });
    return j;
  }
  window.hlApi = hlApi;

  window.upsertOrder = function (o) {
    const i = DB.orders.findIndex(x => x.id === o.id);
    if (i < 0) DB.orders.unshift(o); else DB.orders[i] = o;
    save();
  };

  window.loadMine = async function () {
    try {
      const j = await hlApi("/api/me/orders", undefined, "GET");
      MINE = j.orders; MINE.forEach(upsertOrder);
    } catch (e) { MINE = []; }
  };

  async function whoami() {
    try { const j = await hlApi("/api/auth/me", undefined, "GET"); ME = j.user; admin = !!ME && ME.role === "admin"; } catch (e) { /* chạy không có máy chủ */ }
  }

  window.boot = async function () {
    await whoami();
    await sync();
    if (ME && ME.role === "customer") await loadMine();
    if (admin && window.startStream) startStream();
    render();
  };

  window.syncHeader = function () {
    const a = $("#acc"); if (!a) return;
    a.classList.toggle("on", !!ME);
    const t = ME ? "Tài khoản của " + ME.name : "Đăng nhập hoặc đăng ký";
    a.setAttribute("aria-label", t); a.title = t;
  };

  /* ---------- trang đăng nhập / đăng ký ---------- */
  window.authPage = function (r) {
    if (ME) { setTimeout(() => { location.hash = "#account"; }); return ""; }
    if (!API) return `${note}<section class="card authbox"><h1 style="font-size:28px">Tài khoản</h1><p class="mute">Đăng ký và đăng nhập cần chạy bằng máy chủ: <code>cd backend &amp;&amp; python server.py</code> rồi mở http://localhost:8000.</p></section>`;
    const reg = r === "register";
    return `${note}<section class="card authbox"><h1 style="font-size:28px;margin:0 0 4px">${reg ? "Tạo tài khoản" : "Đăng nhập"}</h1>
<p class="mute" style="margin:0 0 8px">${reg ? "Lưu địa chỉ, theo dõi đơn hàng và đặt lại nhanh hơn." : "Đăng nhập để xem đơn hàng và đặt hàng nhanh hơn."}</p>
<form id="${reg ? "rgf" : "lgf"}" autocomplete="on">
${reg ? `<label for="rn">Họ và tên</label><input id="rn" required maxlength="80" autocomplete="name">
<label for="rp">Số điện thoại</label><input id="rp" required pattern="0[0-9]{9}" inputmode="tel" autocomplete="tel" title="10 số, bắt đầu bằng 0">
<label for="re">Email (không bắt buộc)</label><input id="re" type="email" maxlength="120" autocomplete="email">
<label for="rw">Mật khẩu (tối thiểu 8 ký tự)</label><input id="rw" type="password" required minlength="8" maxlength="128" autocomplete="new-password">
<label for="rw2">Nhập lại mật khẩu</label><input id="rw2" type="password" required minlength="8" maxlength="128" autocomplete="new-password">`
 : `<label for="li">Số điện thoại hoặc email</label><input id="li" required autocomplete="username">
<label for="lw">Mật khẩu</label><input id="lw" type="password" required autocomplete="current-password">`}
<div id="aerr" role="alert"></div>
<p><button class="btn big-btn" style="width:100%">${reg ? "Đăng ký" : "Đăng nhập"}</button></p></form>
<p class="mute">${reg ? `Đã có tài khoản? <a href="#login">Đăng nhập</a>` : `Chưa có tài khoản? <a href="#register">Đăng ký</a>`}</p></section>`;
  };

  const say = (id, m, err) => { const e = $("#" + id); if (e) e.innerHTML = m ? `<div class="msg ${err ? "err" : ""}">${esc(m)}</div>` : ""; };

  async function afterAuth(u) {
    ME = u; admin = u.role === "admin"; DB.orders = []; save();
    if (admin) { await sync(); startStream && startStream(); } else await loadMine();
    const go = window._after || "#account"; window._after = "";
    if (location.hash === go) render(); else location.hash = go;
  }

  async function doLogin() {
    try { const j = await hlApi("/api/auth/login", { id: $("#li").value.trim(), password: $("#lw").value }); await afterAuth(j.user); }
    catch (e) { say("aerr", e.message, 1); }
  }
  async function doRegister() {
    if ($("#rw").value !== $("#rw2").value) return say("aerr", "Hai mật khẩu chưa giống nhau", 1);
    try {
      const j = await hlApi("/api/auth/register", { name: $("#rn").value.trim(), phone: $("#rp").value.trim(), email: $("#re").value.trim(), password: $("#rw").value });
      await afterAuth(j.user);
    } catch (e) { say("aerr", e.message, 1); }
  }

  /* ---------- trang tài khoản ---------- */
  window.accountPage = function () {
    if (!ME) { setTimeout(() => { location.hash = "#login"; }); return ""; }
    if (ME.role === "admin") return `${note}<h2>Tài khoản quản trị</h2><p><a class="btn" href="#admin">Vào trang quản trị</a> <button type="button" class="btn alt" data-hl="logout">Đăng xuất</button></p>`;
    return `${note}<div class="row"><h1 style="margin:0">Xin chào, ${esc(ME.name)}</h1><button type="button" class="btn alt sm" data-hl="logout">Đăng xuất</button></div>
<div class="two2 top" style="margin-top:16px"><div><h2 style="font-size:20px;margin-top:0">Đơn hàng của tôi</h2>
${MINE.length ? MINE.map(o => orderView(o)).join('<div style="height:12px"></div>') : `<p class="mute">Bạn chưa có đơn hàng nào. <a href="#shop">Mua sắm ngay</a></p>`}</div>
<div><form class="card" id="pff"><h3>Thông tin cá nhân</h3>
<label for="pn2">Họ và tên</label><input id="pn2" required maxlength="80" value="${esc(ME.name)}">
<label for="pp2">Số điện thoại</label><input id="pp2" value="${esc(ME.phone)}" disabled>
<label for="pe2">Email</label><input id="pe2" type="email" maxlength="120" value="${esc(ME.email)}">
<label for="pa2">Địa chỉ nhận hàng mặc định</label><input id="pa2" maxlength="200" value="${esc(ME.addr)}" autocomplete="street-address">
<div id="perr" role="alert"></div><p><button class="btn">Lưu thay đổi</button></p></form>
<form class="card" id="pwf" style="margin-top:16px"><h3>Đổi mật khẩu</h3>
<label for="po">Mật khẩu hiện tại</label><input id="po" type="password" required autocomplete="current-password">
<label for="pnw">Mật khẩu mới (tối thiểu 8 ký tự)</label><input id="pnw" type="password" required minlength="8" maxlength="128" autocomplete="new-password">
<div id="wmsg" role="alert"></div><p><button class="btn">Đổi mật khẩu</button></p></form></div></div>`;
  };

  /* ---------- gợi ý và điền sẵn khi thanh toán ---------- */
  window.prefillCheckout = function () {
    const f = $("#co"); if (!f) return;
    if (ME && ME.role === "customer") {
      [["n", ME.name], ["ph", ME.phone], ["ad", ME.addr]].forEach(([i, v]) => { const e = $("#" + i); if (e && !e.value) e.value = v || ""; });
    } else if (!ME && API) {
      f.insertAdjacentHTML("beforebegin", `<p class="msg">Bạn đã có tài khoản? <a href="#login" onclick="window._after='#cart'">Đăng nhập</a> hoặc <a href="#register" onclick="window._after='#cart'">đăng ký</a> để lưu đơn hàng và điền sẵn thông tin giao hàng.</p>`);
    }
  };

  /* ---------- các hàm gọi từ app.js ---------- */
  window.adminLoginApi = async function () {   // đăng nhập quản trị 2 bước: mật khẩu rồi mã 2FA, xác thực ở máy chủ
    if (stage === 0) {
      const v = $("#pw").value; if (!v) { toast("Nhập mật khẩu", 1); return render(); }
      window._apw = v; stage = 1; return render();
    }
    try {
      const j = await hlApi("/api/auth/admin-login", { password: window._apw || "", otp: ($("#ot").value || "").trim() });
      window._apw = ""; stage = 0; tries = 0; ME = j.user; admin = true; await sync(); startStream && startStream(); render();
    } catch (e) { window._apw = ""; stage = 0; toast(e.message, 1); render(); }
  };

  window.adminOrder = async function (id, action) {
    try { await hlApi("/api/admin/orders/" + id + "/" + action, {}); } catch (e) { toast(e.message, 1); }
    await sync(); render();
  };

  window.trackApi = async function () {
    const id = $("#tc").value.trim().toUpperCase(), ph = $("#tp").value.trim();
    try { const j = await hlApi("/api/orders/lookup", { id, phone: ph }); upsertOrder(j.order); window._tr = orderView(j.order); }
    catch (e) { window._tr = `<div class="msg err">${esc(e.message)}</div>`; }
    render();
  };

  window.claimApi = async function (id) {
    const o = DB.orders.find(x => x.id === id);
    try { const j = await hlApi("/api/orders/claim", { id, phone: o.cust.phone }); upsertOrder(j.order); } catch (e) { toast(e.message, 1); }
    render();
  };

  window.logoutApi = async function () {
    const wasAdmin = admin;
    try { await hlApi("/api/auth/logout", {}); } catch (e) { /* bỏ qua */ }
    ME = null; MINE = []; admin = false; stage = 0; DB.orders = []; DB.log = [];
    window.stopStream && stopStream(); save();
    if (wasAdmin || location.hash === "#home") render(); else location.hash = "#home";   // quản trị ở lại màn hình đăng nhập
  };

  document.addEventListener("submit", e => {
    const id = e.target.id;
    if (id === "lgf") doLogin();
    else if (id === "rgf") doRegister();
    else if (id === "pff") {
      hlApi("/api/auth/profile", { name: $("#pn2").value, email: $("#pe2").value, addr: $("#pa2").value })
        .then(j => { ME = j.user; syncHeader(); say("perr", "Đã lưu thay đổi"); }).catch(x => say("perr", x.message, 1));
    } else if (id === "pwf") {
      hlApi("/api/auth/password", { old: $("#po").value, new: $("#pnw").value })
        .then(() => { $("#po").value = ""; $("#pnw").value = ""; say("wmsg", "Đã đổi mật khẩu. Các thiết bị khác sẽ bị đăng xuất."); }).catch(x => say("wmsg", x.message, 1));
    }
  });
  document.addEventListener("click", e => {
    const t = e.target.closest("[data-hl]");
    if (t && t.dataset.hl === "logout") logoutApi();
  });

  // làm mới trạng thái đơn đang xem ở trang thanh toán (webhook có thể vừa ghi nhận tiền)
  setInterval(async () => {
    if (!API || admin) return;
    const m = location.hash.match(/^#pay\/(HL\d+)/); if (!m) return;
    const o = DB.orders.find(x => x.id === m[1]); if (!o) return;
    try {
      const j = await hlApi("/api/orders/lookup", { id: o.id, phone: o.cust.phone });
      if (JSON.stringify(j.order) !== JSON.stringify(o)) { upsertOrder(j.order); render(); }
    } catch (e) { /* bỏ qua */ }
  }, 10000);
})();
