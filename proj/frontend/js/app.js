const $=s=>document.querySelector(s),esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])),vnd=n=>Number(n).toLocaleString("vi-VN")+"đ";
const ST=["Chờ xác nhận","Đã xác nhận","Đang đóng gói","Đã bàn giao vận chuyển","Đang giao","Đã giao"],CANCEL="Đã hủy";
const SHIP={std:{n:"Tiêu chuẩn (SPX, J&T) 2–4 ngày",f:25000},exp:{n:"Hỏa tốc nội thành 2 giờ (GrabExpress)",f:45000}};
const PAY={cod:"Thanh toán khi nhận hàng (COD)",qr:"Chuyển khoản VietQR",wallet:"Ví điện tử (MoMo, ZaloPay, ShopeePay)",card:"Thẻ nội địa / quốc tế"};
const FREESHIP=300000,SEED=[
["Granola yến mạch nguyên chất 250g","Granola",89000,40,"🥣","Yến mạch nướng cùng hạt, không đường tinh luyện."],
["Granola yến mạch nguyên chất 500g","Granola",159000,30,"🥣","Túi lớn tiết kiệm cho cả tuần."],
["Hạnh nhân rang mộc 250g","Hạt",135000,25,"🌰","Rang mộc, không muối, không dầu."],
["Óc chó tách vỏ 250g","Hạt",145000,20,"🥜","Nhân óc chó sấy tự nhiên."],
["Hạt điều rang 500g","Hạt",189000,18,"🥜","Rang củi, giòn bùi."],
["Hạt macca 250g","Hạt",199000,12,"🌰","Macca nứt vỏ, béo ngậy."],
["Hạt chia 250g","Hạt chia & yến mạch",79000,50,"⚫","Ngâm qua đêm hoặc trộn sữa chua."],
["Yến mạch cán dẹt 500g","Hạt chia & yến mạch",65000,45,"🌾","Nấu cháo nhanh, làm overnight oats."],
["Xoài sấy dẻo ít đường 200g","Trái cây sấy",95000,30,"🥭","Giữ vị ngọt tự nhiên của xoài."],
["Chuối sấy giòn 150g","Trái cây sấy",69000,35,"🍌","Giòn nhẹ, ăn vặt không lo béo."],
["Nho sấy dẻo 250g","Trái cây sấy",99000,28,"🍇","Không thêm đường hóa học."],
["Hạt bí rang 200g","Hạt",85000,5,"🎃","Giàu kẽm, rang mộc."]];
let DB;
function load(){try{DB=JSON.parse(localStorage.getItem("hl_db"))}catch(e){DB=null}
 if(!DB||!DB.products){DB={products:SEED.map((p,i)=>({id:"P"+(i+1),name:p[0],cat:p[1],price:p[2],stock:p[3],emoji:p[4],desc:p[5],on:true})),orders:[],log:[],cart:[],seq:100}}}
let API=false,pushT;
function save(){try{localStorage.setItem("hl_db",JSON.stringify(DB))}catch(e){}
 if(API){clearTimeout(pushT);pushT=setTimeout(()=>fetch("/api/state",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({products:DB.products,orders:DB.orders,log:DB.log,seq:DB.seq})}).catch(()=>{}),300)}}
async function sync(){try{const r=await fetch("/api/state");if(!r.ok)return;const s=await r.json();DB.products=s.products;DB.orders=s.orders;DB.log=s.log;DB.seq=s.seq;API=true;render()}catch(e){}}
function log(m){DB.log.unshift({at:new Date().toISOString(),m});DB.log=DB.log.slice(0,60)}
load();
let cat="Tất cả",admin=false,stage=0,tries=0,tab="over",edit=null,note="",q="",sort="",onlyWish=false,vc=null;
const HERO="assets/hero.jpg";const IMG={"P1": "assets/products/P1.jpg", "P2": "assets/products/P2.jpg", "P3": "assets/products/P3.jpg", "P4": "assets/products/P4.jpg", "P5": "assets/products/P5.jpg", "P7": "assets/products/P7.jpg", "P9": "assets/products/P9.jpg"};let tf="";const W=()=>DB.wish??=[],FLASH=["P7","P9","P10"],FPCT=15,pr=p=>FLASH.includes(p.id)?Math.round(p.price*(100-FPCT)/100/500)*500:p.price;
const VC={HEALTHY10:{min:150000,pct:10,max:50000},NEWUSER:{min:100000,off:20000},FREESHIP:{min:200000,free:1}};
function calc(sub,f){const v=VC[vc];let d=0,free=sub>=FREESHIP;if(v&&sub>=v.min){d=v.pct?Math.min(v.max,Math.round(sub*v.pct/100)):(v.off||0);if(v.free)free=true}return{d,fee:free?0:SHIP[f].f}}
function rk(){const ids=["n","ph","ad","pm"],k=ids.map(i=>$("#"+i)?.value);render();ids.forEach((i,j)=>{if($("#"+i)&&k[j]!=null)$("#"+i).value=k[j]})}
const P=id=>DB.products.find(p=>p.id===id),dt=s=>new Date(s).toLocaleString("vi-VN");
const cartTotal=()=>DB.cart.reduce((s,c)=>s+(P(c.id)?pr(P(c.id)):0)*c.qty,0);
function toast(m,err){note=`<div class="msg ${err?"err":""}" role="status">${esc(m)}</div>`}

/* ---------- Khách hàng ---------- */
function shop(){const icons={"Tất cả":"🛒","Granola":"🥣","Hạt":"🌰","Hạt chia & yến mạch":"🌾","Trái cây sấy":"🥭"},cats=["Tất cả",...new Set(DB.products.map(p=>p.cat))];
 let list=DB.products.filter(p=>p.on&&(cat==="Tất cả"||p.cat===cat)&&(tf!=="wish"||W().includes(p.id))&&(tf!=="hot"||FLASH.includes(p.id))&&(tf!=="u100"||pr(p)<100000)&&p.name.toLowerCase().includes(q.trim().toLowerCase()));
 if(sort)list=[...list].sort((a,b)=>sort==="asc"?pr(a)-pr(b):pr(b)-pr(a));
 const tabs=[["","Tất cả"],["hot","Khuyến mãi HOT"],["u100","Dưới 100K"],["wish",`♥ Yêu thích (${W().length})`]];
 return `${note}<div class="strip"><span>Giao toàn quốc qua SPX, J&amp;T · Hỏa tốc nội thành 2 giờ</span><span>Miễn phí vận chuyển từ ${vnd(FREESHIP)}</span></div><div class="new">Đặc quyền khách mới: nhập mã NEWUSER giảm 20.000đ cho đơn từ 100.000đ</div>
 <div class="shell"><aside class="side" aria-label="Danh mục">${cats.map(c=>`<button class="cat ${c===cat?"on":""}" data-cat="${esc(c)}"><i aria-hidden="true">${icons[c]||"🥜"}</i>${esc(c)}</button>`).join("")}</aside>
 <div><img class="heroimg" src="${HERO}" alt="NUTRI-MIX ngũ cốc và hạt dinh dưỡng – Khởi đầu ngày mới năng lượng" width="1024" height="572"><div class="flash"><span>⚡ Siêu Sale 11.11: giảm đến ${FPCT}% · kết thúc sau <b id="cd">--:--:--</b></span><button class="cta" data-tf="hot">MUA NGAY ›</button></div>
 <div class="tabs">${tabs.map(t=>`<button class="${t[0]===tf?"on":""}" data-tf="${t[0]}">${t[1]}</button>`).join("")}</div>
 <div class="row" style="margin-bottom:12px"><span class="mute">${list.length} sản phẩm</span><select id="so" aria-label="Sắp xếp" style="width:auto"><option value="">Mặc định</option><option value="asc" ${sort==="asc"?"selected":""}>Giá thấp đến cao</option><option value="desc" ${sort==="desc"?"selected":""}>Giá cao đến thấp</option></select></div>
 <div class="grid">${list.map(p=>{const f=FLASH.includes(p.id),w=W().includes(p.id);return `<article class="card ${f?"hot":""}"><div class="pic">${IMG[p.id]?`<img src="${IMG[p.id]}" alt="${esc(p.name)}" loading="lazy">`:`<span aria-hidden="true">${esc(p.emoji)}</span>`}<button class="heart" data-w="${p.id}" aria-pressed="${w}" aria-label="Yêu thích ${esc(p.name)}">${w?"♥":"♡"}</button>${f?`<span class="tag sale">-${FPCT}%</span>`:""}</div><div class="price">${vnd(pr(p))}</div><div class="mute" style="min-height:22px">${f?`<s>${vnd(p.price)}</s> Tiết kiệm ${((p.price-pr(p))/1000).toFixed(1).replace(/\.0$/,"")}K`:""}</div><h3>${esc(p.name)}</h3><p class="mute">${esc(p.desc)}</p>${p.stock>0?`<button class="btn buy" data-add="${p.id}">🛒 Mua</button>`:`<span class="tag bad">Hết hàng</span>`}${p.stock>0&&p.stock<=10?`<p class="mute">Chỉ còn ${p.stock} sản phẩm</p>`:""}</article>`}).join("")||"<p>Không có sản phẩm phù hợp.</p>"}</div></div></div>`}
function cart(){const items=DB.cart.filter(c=>P(c.id));
 if(!items.length)return `${note}<h2>Giỏ hàng</h2><p>Giỏ hàng đang trống. <a href="#shop">Chọn sản phẩm</a> để bắt đầu.</p>`;
 const sub=cartTotal(),f=window._ship||"std",cl=calc(sub,f),fee=cl.fee,left=Math.max(0,FREESHIP-sub);
 return `${note}<h2>Giỏ hàng và thanh toán</h2><div class="card" style="margin-bottom:14px">${left?`Mua thêm <b>${vnd(left)}</b> để được miễn phí vận chuyển`:"Đơn của bạn được miễn phí vận chuyển"}<div class="prog" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.min(100,Math.round(sub*100/FREESHIP))}"><i style="width:${Math.min(100,sub*100/FREESHIP)}%"></i></div></div><div class="two"><div class="card tbl"><table><tr><th>Sản phẩm</th><th>Số lượng</th><th>Thành tiền</th><th></th></tr>${items.map(c=>{const p=P(c.id);return `<tr><td>${esc(p.name)}<br><span class="mute">${vnd(pr(p))}</span></td><td><button class="btn alt sm" data-q="${c.id}:-1" aria-label="Giảm">−</button> ${c.qty} <button class="btn alt sm" data-q="${c.id}:1" aria-label="Tăng">+</button></td><td>${vnd(pr(p)*c.qty)}</td><td><button class="btn alt sm" data-rm="${c.id}">Xóa</button></td></tr>`}).join("")}</table></div>
 <form class="card" id="co" autocomplete="on"><h3>Thông tin nhận hàng</h3><label for="n">Họ tên</label><input id="n" required maxlength="60" autocomplete="name"><label for="ph">Số điện thoại</label><input id="ph" required pattern="0[0-9]{9}" title="10 số, bắt đầu bằng 0" inputmode="tel" autocomplete="tel"><label for="ad">Địa chỉ</label><textarea id="ad" required rows="2" maxlength="200" autocomplete="street-address"></textarea>
 <label for="sh">Vận chuyển</label><select id="sh">${Object.entries(SHIP).map(([k,v])=>`<option value="${k}" ${k===f?"selected":""}>${v.n} – ${vnd(v.f)}</option>`).join("")}</select>
 <label for="pm">Thanh toán</label><select id="pm">${Object.entries(PAY).map(([k,v])=>`<option value="${k}">${v}</option>`).join("")}</select>
 <label for="vi">Mã giảm giá</label><div class="row" style="flex-wrap:nowrap"><input id="vi" value="${esc(vc||"")}" placeholder="HEALTHY10" autocomplete="off"><button type="button" class="btn alt" id="va">Áp dụng</button></div><p class="mute">HEALTHY10: giảm 10% (tối đa 50.000đ, đơn từ 150.000đ) · NEWUSER: giảm 20.000đ (đơn từ 100.000đ) · FREESHIP: miễn phí vận chuyển (đơn từ 200.000đ)</p><p class="row"><span>Tạm tính</span><b>${vnd(sub)}</b></p>${cl.d?`<p class="row"><span>Giảm giá (${esc(vc)})</span><b>-${vnd(cl.d)}</b></p>`:""}<p class="row"><span>Phí vận chuyển</span><b>${fee?vnd(fee):"Miễn phí"}</b></p><p class="row"><span>Tổng cộng</span><b class="price">${vnd(sub-cl.d+fee)}</b></p><p class="mute">Bạn sẽ nhận ${Math.floor((sub-cl.d+fee)/10000)} điểm tích lũy cho đơn này.</p><button class="btn" style="width:100%">Đặt hàng</button></form></div><h2>Thường mua cùng</h2><div class="grid">${DB.products.filter(p=>p.on&&p.stock>0&&!DB.cart.some(c=>c.id===p.id)).slice(0,3).map(p=>`<article class="card"><h3>${esc(p.emoji)} ${esc(p.name)}</h3><div class="row"><span class="price">${vnd(pr(p))}</span><button class="btn sm" data-add="${p.id}">Thêm vào giỏ</button></div></article>`).join("")}</div>`}
function track(){return `${note}<h2>Tra cứu đơn hàng</h2><form class="card" id="tk" style="max-width:480px"><label for="tc">Mã đơn hàng</label><input id="tc" required placeholder="Ví dụ HL000101"><label for="tp">Số điện thoại đặt hàng</label><input id="tp" required inputmode="tel"><p><button class="btn">Tra cứu</button></p></form><div id="tr">${window._tr||""}</div>`}
function timeline(o){const idx=ST.indexOf(o.st);if(o.st===CANCEL)return `<p><span class="tag bad">Đã hủy</span></p>`;
 return `<ul class="tl">${ST.map((s,i)=>`<li class="${i<=idx?"done":""}">${s}${o.hist.find(h=>h.st===s)?` <span class="mute">– ${dt(o.hist.find(h=>h.st===s).at)}</span>`:""}</li>`).join("")}</ul>`}
function orderView(o){return `<div class="card"><div class="row"><h3>Đơn ${esc(o.id)}</h3><span class="tag">${esc(o.st)}</span></div><p class="mute">${dt(o.at)} · ${esc(PAY[o.pay.m])} · ${o.pay.paid?"Đã thanh toán":"Chưa thanh toán"}</p>${o.track?`<p>Mã vận đơn: <b>${esc(o.track)}</b></p>`:""}${timeline(o)}<p>${o.items.map(i=>`${esc(i.name)} × ${i.qty}`).join("<br>")}</p>${o.disc?`<p class="mute">Đã giảm ${vnd(o.disc)} (mã ${esc(o.voucher)})</p>`:""}<p><b>Tổng: ${vnd(o.total)}</b></p>${o.pts?`<p class="mute">Điểm tích lũy: ${o.pts}</p>`:""}</div>`}

/* ---------- Quản trị ---------- */
function adminLogin(){return `${note}<h2>Đăng nhập quản trị</h2><form class="card" id="lg" style="max-width:380px">${stage===0?`<label for="pw">Mật khẩu</label><input id="pw" type="password" required autocomplete="current-password"><p class="mute">Bản demo: mật khẩu admin123</p>`:`<label for="ot">Mã xác thực 2 lớp (2FA)</label><input id="ot" inputmode="numeric" required maxlength="6"><p class="mute">Bản demo: mã 123456. Bản thật dùng ứng dụng xác thực (TOTP).</p>`}<button class="btn">${stage===0?"Tiếp tục":"Đăng nhập"}</button></form>`}
function adminPage(){const tabs=[["over","Tổng quan"],["prod","Sản phẩm"],["ord","Đơn hàng"],["cus","Khách hàng"],["sys","Hệ thống"]];
 return `${note}<div class="row"><h2>Quản trị</h2><button class="btn alt sm" id="out">Đăng xuất</button></div><div class="chips">${tabs.map(t=>`<button class="chip ${t[0]===tab?"on":""}" data-tab="${t[0]}">${t[1]}</button>`).join("")}</div>${({over:aOver,prod:aProd,ord:aOrd,cus:aCus,sys:aSys})[tab]()}`}
const valid=()=>DB.orders.filter(o=>o.st!==CANCEL);
function aOver(){const v=valid(),rev=v.reduce((s,o)=>s+o.total,0),low=DB.products.filter(p=>p.stock<=10),cnt=ST.map(s=>[s,DB.orders.filter(o=>o.st===s).length]).concat([[CANCEL,DB.orders.filter(o=>o.st===CANCEL).length]]),mx=Math.max(1,...cnt.map(c=>c[1]));
 return `<div class="kpis"><div class="card kpi"><span class="mute">Doanh thu (trừ đơn hủy)</span><b>${vnd(rev)}</b></div><div class="card kpi"><span class="mute">Số đơn</span><b>${DB.orders.length}</b></div><div class="card kpi"><span class="mute">Giá trị đơn trung bình</span><b>${vnd(v.length?Math.round(rev/v.length):0)}</b></div><div class="card kpi"><span class="mute">Tỷ lệ COD</span><b>${DB.orders.length?Math.round(DB.orders.filter(o=>o.pay.m==="cod").length*100/DB.orders.length):0}%</b></div></div>
 <h2>Đơn theo trạng thái</h2><div class="card bars">${cnt.map(c=>`<div><span style="width:200px">${c[0]}</span><i style="width:${c[1]*100/mx*.5+1}%"></i> ${c[1]}</div>`).join("")}</div>
 <h2>Cảnh báo tồn kho thấp</h2><div class="card">${low.map(p=>`<p>${esc(p.name)}: <span class="tag ${p.stock?"warn":"bad"}">${p.stock?`còn ${p.stock}`:"hết hàng"}</span></p>`).join("")||"Tồn kho ổn định."}</div>`}
function aProd(){const e=edit?P(edit):{};
 return `<form class="card" id="pf"><h3>${edit?"Sửa sản phẩm":"Thêm sản phẩm"}</h3><div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(160px,1fr))"><div><label for="pn">Tên</label><input id="pn" required maxlength="80" value="${esc(e.name)}"></div><div><label for="pc">Nhóm</label><input id="pc" required value="${esc(e.cat)}"></div><div><label for="pp">Giá (đ)</label><input id="pp" type="number" min="1000" step="500" required value="${e.price??""}"></div><div><label for="ps">Tồn kho</label><input id="ps" type="number" min="0" required value="${e.stock??""}"></div><div><label for="pe">Biểu tượng</label><input id="pe" maxlength="4" value="${esc(e.emoji||"🥜")}"></div></div><label for="pd">Mô tả</label><input id="pd" maxlength="160" value="${esc(e.desc)}"><p><button class="btn">${edit?"Lưu thay đổi":"Thêm sản phẩm"}</button> ${edit?`<button type="button" class="btn alt" data-tab="prod" data-cancel="1">Hủy sửa</button>`:""}</p></form>
 <div class="card tbl" style="margin-top:14px"><table><tr><th>Sản phẩm</th><th>Giá</th><th>Tồn kho</th><th>Hiển thị</th><th></th></tr>${DB.products.map(p=>`<tr><td>${esc(p.emoji)} ${esc(p.name)}</td><td>${vnd(p.price)}</td><td><input type="number" min="0" value="${p.stock}" data-stk="${p.id}" style="width:80px" aria-label="Tồn kho ${esc(p.name)}"></td><td>${p.on?"Đang bán":"Ẩn"}</td><td><button class="btn alt sm" data-ed="${p.id}">Sửa</button> <button class="btn alt sm" data-tg="${p.id}">${p.on?"Ẩn":"Hiện"}</button> <button class="btn bad sm" data-del="${p.id}">Xóa</button></td></tr>`).join("")}</table></div>`}
function aOrd(){if(!DB.orders.length)return `<p>Chưa có đơn hàng. Hãy đặt thử một đơn ở trang Cửa hàng.</p>`;
 return `<div class="card tbl"><table><tr><th>Đơn</th><th>Khách</th><th>Giao nhận</th><th>Tổng</th><th>Trạng thái</th></tr>${DB.orders.map(o=>{const next=ST[ST.indexOf(o.st)+1],fin=o.st===CANCEL||o.st==="Đã giao";
 return `<tr><td><b>${esc(o.id)}</b><br><span class="mute">${dt(o.at)}</span></td><td>${esc(o.cust.name)}<br>${esc(o.cust.phone)}<br><span class="mute">${esc(o.cust.addr)}</span></td><td>${esc(SHIP[o.ship.m].n)}<br>${o.track?`Vận đơn ${esc(o.track)}`:"Chưa có vận đơn"}<br>${esc(PAY[o.pay.m])} – ${o.pay.paid?"đã thu":"chưa thu"}${o.flag?`<br><span class="tag warn">Gọi xác nhận trước khi giao</span>`:""}</td><td>${vnd(o.total)}</td><td><span class="tag ${o.st===CANCEL?"bad":""}">${o.st}</span><br>${fin?"":`<button class="btn sm" data-next="${o.id}" style="margin-top:6px">→ ${next}</button> <button class="btn alt sm" data-cancel-o="${o.id}" style="margin-top:6px">Hủy đơn</button>`}</td></tr>`}).join("")}</table></div>`}
function aCus(){const m={};DB.orders.forEach(o=>{const c=m[o.cust.phone]??={name:o.cust.name,phone:o.cust.phone,n:0,sum:0,pts:0};c.n++;if(o.st!==CANCEL){c.sum+=o.total;c.pts+=o.pts||0}});const l=Object.values(m);
 return l.length?`<div class="card tbl"><table><tr><th>Khách hàng</th><th>Điện thoại</th><th>Số đơn</th><th>Tổng chi tiêu</th><th>Điểm tích lũy</th><th>Loại</th></tr>${l.map(c=>`<tr><td>${esc(c.name)}</td><td>${esc(c.phone)}</td><td>${c.n}</td><td>${vnd(c.sum)}</td><td>${c.pts}</td><td>${c.n>=2?"Khách quay lại":"Khách mới"}</td></tr>`).join("")}</table></div>`:`<p>Chưa có khách hàng. Danh sách được tạo từ đơn hàng.</p>`}
function aSys(){return `<div class="card"><h3>Sao lưu và khôi phục</h3><p class="mute">Xuất toàn bộ dữ liệu ra tệp JSON, hoặc nạp lại từ bản sao lưu.</p><button class="btn" id="bk">Tải bản sao lưu</button> <input type="file" id="rs" accept=".json" style="width:auto;display:inline-block" aria-label="Khôi phục từ tệp"> <button class="btn bad sm" id="rst">Đặt lại dữ liệu mẫu</button></div>
 <div class="card" style="margin-top:14px"><h3>Nhật ký hoạt động</h3>${DB.log.slice(0,12).map(l=>`<p class="mute">${dt(l.at)} – ${esc(l.m)}</p>`).join("")||"<p class='mute'>Chưa có hoạt động.</p>"}</div>
 <div class="card" style="margin-top:14px"><h3>Triển khai, mở rộng và rủi ro</h3><p class="mute">Bản này là giao diện chạy trên trình duyệt. Khi lên môi trường thật cần:</p><p>• Triển khai: máy chủ API + PostgreSQL, HTTPS, tên miền, CI/CD.<br>• Sao lưu: dump cơ sở dữ liệu hằng ngày, giữ 30 ngày, lưu ra kho riêng.<br>• Giám sát: log lỗi, cảnh báo tồn kho và đơn treo, theo dõi thời gian phản hồi.<br>• Mở rộng: tách dịch vụ đơn hàng/kho, dùng cache và hàng đợi cho đợt Siêu Sale; đồng bộ tồn kho với Shopee, TikTok Shop qua Sapo.<br>• Rủi ro chính: lệch tồn kho giữa các kênh, nghẽn khi sale, COD hoàn đơn, phụ thuộc phí và chính sách sàn, giá hạt nhập khẩu biến động.</p></div>`}

/* ---------- Định tuyến ---------- */
function render(){const r=(location.hash||"#shop").slice(1);document.querySelectorAll("#nav a").forEach(a=>a.classList.toggle("on",a.dataset.r===r));
 $("#cc").textContent=DB.cart.reduce((s,c)=>s+c.qty,0);
 $("#app").innerHTML=r==="cart"?cart():r==="track"?track():r==="admin"?(admin?adminPage():adminLogin()):shop();note=""}
addEventListener("hashchange",()=>{note="";render();scrollTo(0,0)});

document.addEventListener("click",e=>{const t=e.target.closest("button");if(!t)return;const d=t.dataset;
 if(d.cat){cat=d.cat;render()}
 else if(d.add){const p=P(d.add),c=DB.cart.find(x=>x.id===d.add);if(c){if(c.qty<p.stock)c.qty++;else return toast("Đã đạt số lượng tồn kho",1),render()}else DB.cart.push({id:d.add,qty:1});save();toast(`Đã thêm "${p.name}" vào giỏ hàng`);render()}
 else if(d.q){const[id,n]=d.q.split(":"),c=DB.cart.find(x=>x.id===id);c.qty+=+n;if(c.qty>P(id).stock){c.qty=P(id).stock;toast("Đã đạt số lượng tồn kho",1)}if(c.qty<1)DB.cart=DB.cart.filter(x=>x!==c);save();render()}
 else if(d.rm){DB.cart=DB.cart.filter(x=>x.id!==d.rm);save();render()}
 else if(d.tab){tab=d.tab;if(d.cancel)edit=null;render()}
 else if(d.ed){edit=d.ed;render();scrollTo(0,0)}
 else if(d.tg){const p=P(d.tg);p.on=!p.on;log(`${p.on?"Hiện":"Ẩn"} sản phẩm ${p.name}`);save();render()}
 else if(d.del){const p=P(d.del);if(!confirm(`Xóa "${p.name}"?`))return;DB.products=DB.products.filter(x=>x!==p);DB.cart=DB.cart.filter(x=>x.id!==p.id);log("Xóa sản phẩm "+p.name);save();render()}
 else if(d.next){const o=DB.orders.find(x=>x.id===d.next),s=ST[ST.indexOf(o.st)+1];
  if(o.flag&&o.st==="Đang đóng gói"&&!confirm("Đơn COD giá trị cao: bạn đã gọi xác nhận với khách chưa?"))return;
  o.st=s;o.hist.push({st:s,at:new Date().toISOString()});
  if(s==="Đã bàn giao vận chuyển")o.track=(o.ship.m==="exp"?"GRAB":"SPXVN")+Math.floor(Math.random()*9e9+1e9);
  if(s==="Đã giao"&&o.pay.m==="cod")o.pay.paid=true;log(`Đơn ${o.id} → ${s}`);save();render()}
 else if(d.cancelO){const o=DB.orders.find(x=>x.id===d.cancelO);if(!confirm(`Hủy đơn ${o.id}? Tồn kho sẽ được hoàn lại.`))return;o.items.forEach(i=>{const p=P(i.id);if(p)p.stock+=i.qty});o.st=CANCEL;o.hist.push({st:CANCEL,at:new Date().toISOString()});log("Hủy đơn "+o.id);save();render()}
 else if(d.w){const w=W(),i=w.indexOf(d.w);i<0?w.push(d.w):w.splice(i,1);save();render()}
 else if(d.tf!==undefined){tf=d.tf;render()}
 else if(t.id==="th"){const r=document.documentElement,dk=matchMedia("(prefers-color-scheme:dark)").matches,cur=r.dataset.theme||(dk?"dark":"light");r.dataset.theme=cur==="dark"?"light":"dark";try{localStorage.setItem("hl_th",r.dataset.theme)}catch(x){}}
 else if(t.id==="va"){const c=$("#vi").value.trim().toUpperCase(),s=cartTotal();if(!c){vc=null}else if(!VC[c]){vc=null;toast("Mã giảm giá không hợp lệ",1)}else if(s<VC[c].min){vc=null;toast(`Mã ${c} áp dụng cho đơn từ ${vnd(VC[c].min)}`,1)}else{vc=c;toast(`Đã áp dụng mã ${c}`)}rk()}
 else if(t.id==="out"){admin=false;stage=0;render()}
 else if(t.id==="bk"){const b=new Blob([JSON.stringify(DB,null,1)],{type:"application/json"}),a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="healthy-life-backup.json";a.click();log("Sao lưu dữ liệu");save()}
 else if(t.id==="rst"){if(confirm("Xóa toàn bộ đơn hàng và đặt lại dữ liệu mẫu?")){try{localStorage.removeItem("hl_db")}catch(x){}load();toast("Đã đặt lại dữ liệu mẫu");render()}}});
document.addEventListener("change",e=>{const t=e.target;
 if(t.dataset.stk){const p=P(t.dataset.stk);p.stock=Math.max(0,parseInt(t.value)||0);log(`Cập nhật tồn kho ${p.name}: ${p.stock}`);save()}
 else if(t.id==="so"){sort=t.value;render()}
 else if(t.id==="sh"){window._ship=t.value;const keep={n:$("#n").value,ph:$("#ph").value,ad:$("#ad").value,pm:$("#pm").value};render();$("#n").value=keep.n;$("#ph").value=keep.ph;$("#ad").value=keep.ad;$("#pm").value=keep.pm}
 else if(t.id==="rs"&&t.files[0]){const r=new FileReader();r.onload=()=>{try{const d=JSON.parse(r.result);if(!Array.isArray(d.products)||!Array.isArray(d.orders))throw 0;DB=d;log("Khôi phục từ bản sao lưu");save();toast("Đã khôi phục dữ liệu");render()}catch(x){toast("Tệp sao lưu không hợp lệ",1);render()}};r.readAsText(t.files[0])}});
document.addEventListener("submit",e=>{e.preventDefault();const id=e.target.id;
 if(id==="co"){const items=DB.cart.filter(c=>P(c.id)).map(c=>({...c,p:P(c.id)}));
  const bad=items.find(i=>i.qty>i.p.stock);if(bad){toast(`"${bad.p.name}" chỉ còn ${bad.p.stock} sản phẩm`,1);return render()}
  const sh=$("#sh").value,sub=cartTotal(),cl=calc(sub,sh),fee=cl.fee,pm=$("#pm").value,total=sub-cl.d+fee;
  const o={id:"HL"+String(++DB.seq).padStart(6,"0"),at:new Date().toISOString(),cust:{name:$("#n").value.trim(),phone:$("#ph").value.trim(),addr:$("#ad").value.trim()},items:items.map(i=>({id:i.id,name:i.p.name,price:pr(i.p),qty:i.qty})),ship:{m:sh,fee},pay:{m:pm,paid:pm!=="cod"},total,disc:cl.d,voucher:cl.d?vc:"",pts:Math.floor(total/10000),st:ST[0],track:"",flag:pm==="cod"&&total>=500000,hist:[{st:ST[0],at:new Date().toISOString()}]};
  items.forEach(i=>i.p.stock-=i.qty);DB.orders.unshift(o);DB.cart=[];vc=null;log(`Đơn mới ${o.id} – ${vnd(total)}`);save();
  window._tr=orderView(o);location.hash="#track";setTimeout(()=>{toast(`Đặt hàng thành công. Mã đơn của bạn: ${o.id}. Hãy lưu mã này để tra cứu. Bạn nhận được ${o.pts} điểm tích lũy.`);render()},0)}
 else if(id==="tk"){const o=DB.orders.find(x=>x.id===$("#tc").value.trim().toUpperCase()&&x.cust.phone===$("#tp").value.trim());window._tr=o?orderView(o):`<div class="msg err">Không tìm thấy đơn. Kiểm tra lại mã đơn và số điện thoại.</div>`;render()}
 else if(id==="lg"){if(tries>=5){toast("Đăng nhập sai quá 5 lần. Tải lại trang để thử lại.",1);return render()}
  if(stage===0){if($("#pw").value==="admin123"){stage=1}else{tries++;toast("Mật khẩu không đúng",1)}}
  else{if($("#ot").value==="123456"){admin=true;stage=0;tries=0;log("Quản trị đăng nhập")}else{tries++;toast("Mã xác thực không đúng",1)}}render()}
 else if(id==="pf"){const v={name:$("#pn").value.trim(),cat:$("#pc").value.trim(),price:+$("#pp").value,stock:parseInt($("#ps").value),emoji:$("#pe").value||"🥜",desc:$("#pd").value.trim()};
  if(edit){Object.assign(P(edit),v);log("Sửa sản phẩm "+v.name)}else{DB.products.push({id:"P"+Date.now().toString(36),on:true,...v});log("Thêm sản phẩm "+v.name)}
  edit=null;save();toast("Đã lưu sản phẩm");render()}});
document.addEventListener("input",e=>{if(e.target.id==="sq"){q=e.target.value;if((location.hash||"#shop")!=="#shop"){location.hash="#shop";return}render()}});
try{const t=localStorage.getItem("hl_th");if(t)document.documentElement.dataset.theme=t}catch(x){}
setInterval(()=>{const e=$("#cd");if(!e)return;const n=new Date(),end=new Date(n);end.setHours(23,59,59,999);const s=Math.max(0,Math.floor((end-n)/1000));e.textContent=[Math.floor(s/3600),Math.floor(s%3600/60),s%60].map(x=>String(x).padStart(2,"0")).join(":")},1000);
render();
sync();
