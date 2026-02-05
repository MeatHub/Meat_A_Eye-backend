select * from members;

-- 1. 외래 키 체크 해제
SET FOREIGN_KEY_CHECKS = 0;

-- 2. 기존 테이블 삭제 (순서 무관)
DROP TABLE IF EXISTS web_notifications;
DROP TABLE IF EXISTS web_push_subscriptions;
DROP TABLE IF EXISTS market_price_history;
DROP TABLE IF EXISTS market_prices;
DROP TABLE IF EXISTS meat_nutrition;
DROP TABLE IF EXISTS fridge_items;
DROP TABLE IF EXISTS recognition_logs;
DROP TABLE IF EXISTS meat_info;
DROP TABLE IF EXISTS members;

-- 3. 외래 키 체크 재설정
SET FOREIGN_KEY_CHECKS = 1;

-- meathub 데이터베이스 사용 확인
USE meathub;

-- 1. members 테이블 생성
CREATE TABLE members (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NULL UNIQUE,
  password VARCHAR(255) NULL,
  nickname VARCHAR(50) NOT NULL,
  web_push_subscription TEXT NULL,
  is_guest TINYINT(1) NOT NULL DEFAULT 0,
  guest_id VARCHAR(36) NULL UNIQUE,
  last_login_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. meat_info 테이블 생성
CREATE TABLE meat_info (
  id INT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  category VARCHAR(20) NOT NULL,
  calories INT NULL,
  protein DECIMAL(5,2) NULL,
  fat DECIMAL(5,2) NULL,
  storage_guide TEXT NULL
) ENGINE=InnoDB;

-- 3. recognition_logs 테이블 생성
CREATE TABLE recognition_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  image_url VARCHAR(500) NOT NULL,
  part_name VARCHAR(100) NOT NULL,
  confidence_score DECIMAL(5,2) NOT NULL,
  illuminance_status VARCHAR(20) NULL,
  browser_agent VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 4. fridge_items 테이블 생성
CREATE TABLE fridge_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  meat_info_id INT NOT NULL,
  storage_date DATE NOT NULL,
  expiry_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'stored',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  slaughter_date DATE NULL,
  grade VARCHAR(50) NULL,
  trace_number VARCHAR(100) NULL,
  origin VARCHAR(100) NULL,
  company_name VARCHAR(200) NULL,
  FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  FOREIGN KEY (meat_info_id) REFERENCES meat_info(id)
) ENGINE=InnoDB;

-- 5. meat_nutrition 테이블 생성 (중요!)
CREATE TABLE meat_nutrition (
    id INT AUTO_INCREMENT PRIMARY KEY,
    food_nm VARCHAR(255) NOT NULL,
    calories FLOAT NULL,
    protein FLOAT NULL,
    fat FLOAT NULL,
    carbs FLOAT NULL,
    INDEX idx_food_nm (food_nm)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. market_prices 테이블 생성
CREATE TABLE market_prices (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  current_price INT NOT NULL,
  price_date DATE NOT NULL,
  region VARCHAR(50) NOT NULL,
  UNIQUE KEY uq_market_price (part_name, region, price_date)
) ENGINE=InnoDB;

-- 7. market_price_history 테이블 생성
CREATE TABLE market_price_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  price INT NOT NULL,
  price_date DATE NOT NULL,
  region VARCHAR(50) NOT NULL,
  source VARCHAR(50) NULL DEFAULT 'KAMIS',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 8. web_push_subscriptions 테이블 생성
CREATE TABLE web_push_subscriptions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  endpoint VARCHAR(1024) NOT NULL,
  p256dh_key TEXT NOT NULL,
  auth_key TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 9. web_notifications 테이블 생성
CREATE TABLE web_notifications (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  fridge_item_id BIGINT NULL,
  notification_type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  scheduled_at DATETIME NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  FOREIGN KEY (fridge_item_id) REFERENCES fridge_items(id) ON DELETE SET NULL
) ENGINE=InnoDB;

INSERT INTO meat_info (part_name, category, calories, protein, fat, storage_guide) VALUES
('삼겹살', 'pork', 331, 17.0, 28.0, '냉장 3일, 냉동 3개월'),
('목살', 'pork', 250, 18.0, 19.0, '냉장 3일, 냉동 3개월'),
('등심', 'beef', 240, 19.0, 17.0, '냉장 5일, 냉동 6개월'),
('안심', 'beef', 200, 22.0, 11.0, '냉장 5일, 냉동 6개월'),
('갈비', 'beef', 280, 18.0, 22.0, '냉장 3일, 냉동 6개월'),
('채끝', 'beef', 230, 20.0, 15.0, '냉장 5일, 냉동 6개월');

select * from meat_nutrition;
