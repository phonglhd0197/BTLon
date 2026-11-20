# Healthy Life – Website thương mại điện tử

## Cấu trúc
- `frontend/` – giao diện: `index.html` (HTML), `css/style.css` (CSS), `js/app.js` (JavaScript), `assets/` (ảnh)
- `backend/server.py` – máy chủ web và REST API (Python, chỉ dùng thư viện chuẩn)
- `database/schema.sql` – cấu trúc và dữ liệu mẫu (SQL, SQLite); file `healthy_life.db` được tạo khi chạy

## Chạy trên máy
Cần Python 3.8 trở lên (không cần cài thêm gói nào):

    cd backend
    python server.py

Mở http://localhost:8000. Quản trị: tab "Quản trị", mật khẩu `admin123`, mã 2FA `123456` (chỉ là demo).

Nếu mở thẳng `frontend/index.html` bằng trình duyệt, trang vẫn chạy nhưng lưu dữ liệu trong trình duyệt thay vì SQLite.

## API
- `GET /api/state` – đọc sản phẩm, đơn hàng, nhật ký
- `PUT /api/state` – ghi dữ liệu (kiểm tra rồi lưu vào các bảng trong một giao dịch)
- `GET /api/backup` – tải bản sao lưu `.db`. Máy chủ cũng tự sao lưu mỗi ngày vào `database/backups/`

## Cần làm trước khi dùng thật
Đăng nhập quản trị và 2FA hiện chạy ở trình duyệt; cần chuyển sang máy chủ (phiên đăng nhập, TOTP, băm mật khẩu), kiểm tra giá và tồn kho khi tạo đơn ở phía máy chủ, thêm HTTPS, và tích hợp cổng thanh toán, đơn vị vận chuyển thật.
