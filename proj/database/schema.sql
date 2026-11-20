-- Healthy Life: lược đồ cơ sở dữ liệu SQLite
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS products(
  id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
  price INTEGER NOT NULL CHECK(price>=0), stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0),
  emoji TEXT, description TEXT, active INTEGER NOT NULL DEFAULT 1);

CREATE TABLE IF NOT EXISTS customers(
  phone TEXT PRIMARY KEY, name TEXT NOT NULL, address TEXT);

CREATE TABLE IF NOT EXISTS orders(
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
  customer_phone TEXT NOT NULL REFERENCES customers(phone),
  ship_address TEXT, ship_method TEXT NOT NULL, ship_fee INTEGER NOT NULL DEFAULT 0,
  pay_method TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0,
  discount INTEGER NOT NULL DEFAULT 0, voucher TEXT, points INTEGER NOT NULL DEFAULT 0,
  total INTEGER NOT NULL CHECK(total>=0), status TEXT NOT NULL,
  tracking_code TEXT, needs_call INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS order_items(
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id TEXT NOT NULL, name TEXT NOT NULL, price INTEGER NOT NULL,
  qty INTEGER NOT NULL CHECK(qty>0), PRIMARY KEY(order_id,product_id));

CREATE TABLE IF NOT EXISTS order_history(
  order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  status TEXT NOT NULL, at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS vouchers(
  code TEXT PRIMARY KEY, min_order INTEGER NOT NULL, percent INTEGER, max_discount INTEGER,
  amount_off INTEGER, free_ship INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, message TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_phone);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);

-- Dữ liệu mẫu
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P1','Granola yến mạch nguyên chất 250g','Granola',89000,40,'🥣','Yến mạch nướng cùng hạt, không đường tinh luyện.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P2','Granola yến mạch nguyên chất 500g','Granola',159000,30,'🥣','Túi lớn tiết kiệm cho cả tuần.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P3','Hạnh nhân rang mộc 250g','Hạt',135000,25,'🌰','Rang mộc, không muối, không dầu.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P4','Óc chó tách vỏ 250g','Hạt',145000,20,'🥜','Nhân óc chó sấy tự nhiên.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P5','Hạt điều rang 500g','Hạt',189000,18,'🥜','Rang củi, giòn bùi.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P6','Hạt macca 250g','Hạt',199000,12,'🌰','Macca nứt vỏ, béo ngậy.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P7','Hạt chia 250g','Hạt chia & yến mạch',79000,50,'⚫','Ngâm qua đêm hoặc trộn sữa chua.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P8','Yến mạch cán dẹt 500g','Hạt chia & yến mạch',65000,45,'🌾','Nấu cháo nhanh, làm overnight oats.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P9','Xoài sấy dẻo ít đường 200g','Trái cây sấy',95000,30,'🥭','Giữ vị ngọt tự nhiên của xoài.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P10','Chuối sấy giòn 150g','Trái cây sấy',69000,35,'🍌','Giòn nhẹ, ăn vặt không lo béo.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P11','Nho sấy dẻo 250g','Trái cây sấy',99000,28,'🍇','Không thêm đường hóa học.',1);
INSERT OR IGNORE INTO products(id,name,category,price,stock,emoji,description,active) VALUES('P12','Hạt bí rang 200g','Hạt',85000,5,'🎃','Giàu kẽm, rang mộc.',1);
INSERT OR IGNORE INTO vouchers VALUES('HEALTHY10',150000,10,50000,NULL,0);
INSERT OR IGNORE INTO vouchers VALUES('NEWUSER',100000,NULL,NULL,20000,0);
INSERT OR IGNORE INTO vouchers VALUES('FREESHIP',200000,NULL,NULL,NULL,1);
INSERT OR IGNORE INTO settings VALUES('order_seq','100');
