# HEALTHY LIFE – Website thương mại điện tử

## Cấu trúc
- `frontend/` – giao diện: `index.html` (HTML), `css/style.css` (CSS), `js/app.js` (JavaScript), `assets/` (ảnh)
- `backend/server.py` – máy chủ web và REST API (Python, chỉ dùng thư viện chuẩn)
- `backend/auth.py` – tài khoản, phiên đăng nhập, xác thực quản trị; `backend/fleet.py` – đội xe, vị trí, luồng thời gian thực
- `frontend/js/auth.js`, `frontend/js/tracking.js` – giao diện tài khoản và theo dõi trực tiếp; `frontend/driver.html` – trang cho tài xế
- `database/schema.sql` – cấu trúc và dữ liệu mẫu (SQL, SQLite); file `healthy_life.db` được tạo khi chạy

## Chạy trên máy

**Windows (dễ nhất):** mở thư mục `backend` rồi nhấp đúp:
- `chay_demo.bat`: chạy bản demo, quản trị bằng `admin123` / mã `123456`.
- `chay_that.bat`: chạy bản thật, máy sẽ hỏi mật khẩu quản trị và khóa TOTP.

Cách dùng dòng lệnh (không cần file .bat) nằm bên dưới.

Cần Python 3.8 trở lên (không cần cài thêm gói nào):

    cd backend
    python server.py

Mở http://localhost:8000. Quản trị: tab "Quản trị", cần đặt `HL_ADMIN_PASSWORD` và `HL_ADMIN_TOTP_SECRET` trước (xem mục Bảo mật). Để trình diễn nhanh: `HL_DEMO=1 python server.py` (tài khoản demo `admin123` / `123456`).

Nếu mở thẳng `frontend/index.html` bằng trình duyệt, trang vẫn chạy nhưng lưu dữ liệu trong trình duyệt thay vì SQLite.

## Tài khoản người dùng
- **Đăng ký / đăng nhập**: biểu tượng người ở thanh trên cùng (`#register`, `#login`). Đăng nhập bằng số điện thoại hoặc email. Sau khi đăng nhập, thông tin giao hàng được điền sẵn, đơn đặt được gắn vào tài khoản và xem lại ở `#account` (kèm sửa hồ sơ, đổi mật khẩu). Vẫn có thể mua hàng không cần tài khoản và tra cứu bằng mã đơn + số điện thoại.
- Mật khẩu băm PBKDF2-SHA256 (200.000 vòng); phiên là cookie `HttpOnly`, `SameSite=Lax` (14 ngày với khách, 8 giờ với quản trị); đăng nhập sai quá 5 lần/15 phút bị khóa tạm.
- **Quản trị** đăng nhập ở máy chủ (mật khẩu + mã 2FA). Các API `/api/state` (đầy đủ), `PUT /api/state`, `/api/analytics`, `/api/backup`, `/api/stream` và `/api/admin/*` yêu cầu phiên quản trị; khách chỉ thấy sản phẩm.
- Số điện thoại **chưa được xác minh** (chưa có OTP SMS). Vì vậy đơn chỉ gắn với tài khoản qua `user_id`, không gắn theo số điện thoại.

## Theo dõi xe và đơn hàng thời gian thực (Quản trị)
Vào **Quản trị > Theo dõi trực tiếp**: bản đồ OpenStreetMap hiện vị trí xe, vệt đường đi, điểm giao ước lượng (theo quận/huyện trong địa chỉ), khoảng cách và thời gian dự kiến; bảng đơn đang xử lý cho gán xe và chuyển trạng thái ngay tại chỗ; nhật ký sự kiện trực tiếp. Dữ liệu đẩy qua Server-Sent Events (`GET /api/stream`), không cần tải lại trang; mất kết nối thì tự nối lại và đồng bộ lại.

**Quản trị > Đội xe**: thêm xe (biển số, tài xế, loại xe), cấp lại mã thiết bị, tạm ngưng, xóa. Mã thiết bị chỉ hiện một lần lúc tạo.

**Gửi vị trí thật**: tài xế mở `/driver.html` trên điện thoại, dán mã thiết bị, bấm "Bắt đầu chia sẻ vị trí" (dùng GPS của trình duyệt, cần **HTTPS** trừ khi chạy ở localhost). Trang này cũng hiện đơn được giao, tiền COD cần thu, và nút "Bắt đầu giao" / "Đã giao xong". Thiết bị khác (GPS tracker) có thể gọi trực tiếp:

    curl -X POST https://<miền>/api/vehicle/location -H "Authorization: Bearer <mã xe>" \
         -H "Content-Type: application/json" -d '{"lat":10.78,"lng":106.69,"speed":28}'

**Xem thử khi chưa có thiết bị**: chạy với `HL_SIM=1` (Windows PowerShell: `$env:HL_SIM="1"`). Máy chủ tạo 3 xe mẫu và cho xe chạy giả lập tới điểm giao của đơn được gán (tăng tốc `HL_SIM_SPEED`, mặc định 10 lần; xe đi đường thẳng, không theo đường thật). Không bật khi chạy thật.

Giới hạn hiện tại: điểm giao chỉ là ước lượng theo quận/huyện, chưa có geocoding địa chỉ thật; lịch sử đường đi (vệt) lưu trong bộ nhớ máy chủ, mất khi khởi động lại (vị trí mới nhất vẫn lưu trong CSDL); khách chưa xem được vị trí xe của chính đơn mình.

## Dashboard quản trị (phân tích và dự báo)
Vào tab "Quản trị" > "Dashboard" (cần chạy bằng `server.py`). Gồm 6 nhóm: Tổng quan, Dự báo doanh thu, Khách hàng, Sản phẩm & kho, Vận hành, Phương pháp.

- `backend/analytics.py` – toàn bộ phép tính bằng Python thuần: dự báo (Holt-Winters, OLS, trung bình theo thứ; chọn bằng backtest), phát hiện ngày bất thường (robust z-score), phân khúc khách (RFM + K-means, chọn k bằng Silhouette), dự đoán mua lại 30 ngày (hồi quy logistic, AUC), luật mua kèm (support/confidence/lift), dự báo tồn kho (EWMA).
- `frontend/js/dashboard.js` – biểu đồ SVG tự vẽ, không cần thư viện ngoài.
- Gợi ý mua kèm trong giỏ hàng dùng chính các luật kết hợp trên (`GET /api/recommend`).

Xem thử với dữ liệu mô phỏng (dùng tệp riêng để không lẫn dữ liệu thật):

    cd backend
    python seed_demo.py --db ../database/demo.db
    HL_DB=../database/demo.db python server.py        (Windows PowerShell: $env:HL_DB="../database/demo.db"; python server.py)

Chưa dùng học sâu vì dữ liệu của một cửa hàng nhỏ quá ít; xem tab "Phương pháp" trong dashboard.

## API
Công khai:
- `POST /api/orders` – tạo đơn; máy chủ tự tính lại giá, tồn kho, mã giảm giá, phí ship; có đăng nhập thì gắn vào tài khoản
- `POST /api/orders/lookup`, `POST /api/orders/claim` – tra cứu đơn (mã đơn + SĐT), khách báo đã chuyển khoản
- `GET /api/state` – sản phẩm (phiên quản trị: kèm đơn hàng, nhật ký) · `GET /api/recommend?ids=P1,P2` – gợi ý mua kèm
- `POST /api/webhook/payment` – đối soát chuyển khoản tự động (SePay/Casso...). Đặt biến môi trường `PAYMENT_WEBHOOK_SECRET`, dịch vụ gửi header `Authorization: Apikey <khóa>`, nội dung chuyển khoản chứa mã đơn `HLxxxxxx`
- Đơn thanh toán online chưa thu tiền sau 30 phút tự hủy và hoàn tồn kho

Tài khoản: `POST /api/auth/register | login | logout | profile | password`, `GET /api/auth/me`, `GET /api/me/orders`, `POST /api/auth/admin-login`

Quản trị (cần phiên quản trị): `PUT /api/state` (chỉ ghi sản phẩm; thêm `?full=1` để khôi phục toàn bộ), `GET /api/analytics?range=90`, `GET /api/backup`, `POST /api/admin/orders/<mã>/<next|cancel|paid|assign>`, `GET /api/admin/live`, `GET /api/stream` (SSE), `GET|POST /api/admin/vehicles[...]`

Thiết bị xe (`Authorization: Bearer <mã xe>`): `POST /api/vehicle/location`, `GET /api/vehicle/me`, `POST /api/vehicle/orders/<mã>/<pick|deliver>`

Bản sao lưu `.db` tự động mỗi ngày vào `database/backups/` (chứa băm mật khẩu: giữ thư mục này riêng tư).

## Bảo mật

Đã xử lý trong bản này:
- Không còn mật khẩu quản trị mặc định trong mã nguồn. Đặt `HL_ADMIN_PASSWORD` và `HL_ADMIN_TOTP_SECRET` để bật quản trị. Khi chưa đặt, quản trị tắt và máy chủ in thông báo lúc khởi động.
- `HL_DEMO=1` chỉ bật tài khoản demo `admin123` / `123456` để trình diễn. Không dùng khi mở ra Internet.
- Đăng nhập quản trị sai bị khóa theo IP (5 lần / 15 phút). Không khóa chung cho mọi người, nên người khác không thể khóa tài khoản quản trị.
- Mọi phản hồi có Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy và Permissions-Policy. Khi chạy HTTPS có thêm Strict-Transport-Security.
- Không liệt kê nội dung thư mục tĩnh.
- Sản phẩm gửi lên được kiểm tra trước khi ghi: giá và tồn kho không âm, mã và tên hợp lệ.
- Tệp sao lưu tạm được xóa ngay sau khi tải về.

Trước khi mở ra Internet vẫn cần:
- Chạy sau HTTPS (Nginx hoặc Caddy), đặt `HL_COOKIE_SECURE=1`. Nếu có proxy thì đặt thêm `HL_TRUST_PROXY=1`.
- Tạo khóa TOTP: `python -c "import base64,os;print(base64.b32encode(os.urandom(20)).decode())"`.
- Giới hạn đăng nhập lưu trong bộ nhớ, mất khi khởi động lại và không chia sẻ giữa nhiều tiến trình. Khi chạy nhiều tiến trình cần Redis.
- Bản sao lưu `.db` chứa băm mật khẩu và dữ liệu khách hàng: giữ thư mục `database/backups/` riêng tư.
- Thêm xác minh số điện thoại bằng OTP SMS, quên mật khẩu qua email/SMS, cổng thanh toán và đơn vị vận chuyển thật.
- Ảnh bản đồ lấy từ máy chủ OpenStreetMap (phù hợp thử nghiệm). Dùng thật với lưu lượng lớn cần nhà cung cấp riêng.
- Hiện trang quản trị ghi lại toàn bộ danh sách sản phẩm. Nếu hai quản trị viên cùng sửa, tồn kho có thể bị ghi đè. Cần một API cập nhật tồn kho riêng.
