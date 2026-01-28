-- 기존 DB에 게스트 확장 컬럼 추가
USE meathub;

-- members 테이블에 is_guest, last_login_at 추가
ALTER TABLE members 
  ADD COLUMN is_guest TINYINT(1) NOT NULL DEFAULT 0 AFTER nickname,
  ADD COLUMN last_login_at DATETIME NULL AFTER is_guest,
  MODIFY COLUMN email VARCHAR(255) NULL UNIQUE,
  MODIFY COLUMN password VARCHAR(255) NULL;

-- fridge_items에 alert_before, use_web_push 추가
ALTER TABLE fridge_items
  ADD COLUMN alert_before INT NULL DEFAULT 3 COMMENT 'D-Day 알림 n일 전' AFTER status,
  ADD COLUMN use_web_push TINYINT(1) NULL DEFAULT 0 AFTER alert_before,
  ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER use_web_push;

-- web_push_subscriptions 테이블 생성
CREATE TABLE IF NOT EXISTS web_push_subscriptions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  endpoint VARCHAR(1024) NOT NULL,
  p256dh_key TEXT NOT NULL,
  auth_key TEXT NOT NULL,
  user_agent VARCHAR(512) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_push_member
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  UNIQUE KEY uq_push_member_endpoint (member_id, endpoint(255)),
  INDEX idx_push_member (member_id)
) ENGINE=InnoDB;

-- market_price_history 테이블 생성
CREATE TABLE IF NOT EXISTS market_price_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  price INT NOT NULL COMMENT 'KRW',
  price_date DATE NOT NULL,
  region VARCHAR(50) NOT NULL,
  source VARCHAR(50) NULL DEFAULT 'KAMIS',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_history_part_region_date (part_name, region, price_date)
) ENGINE=InnoDB;
