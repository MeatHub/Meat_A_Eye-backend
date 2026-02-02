-- ============================================================
-- Meat-A-Eye Complete Database Schema
-- 프로젝트: AI 축산물 인식 서비스 (Meat-A-Eye)
-- 버전: 2.0 (2026-02-02 최종 업데이트)
-- 설명: 모든 마이그레이션이 반영된 완전한 스키마
-- ============================================================

-- 데이터베이스 생성 및 설정
CREATE DATABASE IF NOT EXISTS meathub
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE meathub;

-- ============================================================
-- 1. members (회원 정보)
-- 설명: 일반 회원 및 게스트 사용자 정보 관리
-- ============================================================
CREATE TABLE members (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NULL UNIQUE COMMENT '이메일 (게스트는 NULL)',
  password VARCHAR(255) NULL COMMENT '비밀번호 (게스트는 NULL)',
  nickname VARCHAR(50) NOT NULL COMMENT '닉네임',
  web_push_subscription TEXT NULL COMMENT 'Web Push JSON (Deprecated, web_push_subscriptions 사용 권장)',
  is_guest TINYINT(1) NOT NULL DEFAULT 0 COMMENT '게스트 여부 (0: 일반회원, 1: 게스트)',
  guest_id VARCHAR(36) NULL UNIQUE COMMENT '게스트 UUID (게스트만 사용)',
  last_login_at DATETIME NULL COMMENT '마지막 로그인 시간',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '회원가입 일시',
  INDEX idx_member_guest_id (guest_id),
  INDEX idx_member_email (email),
  INDEX idx_member_is_guest (is_guest)
) ENGINE=InnoDB COMMENT='회원 정보 (일반/게스트)';

-- ============================================================
-- 2. meat_info (고기 부위 정보)
-- 설명: 고기 부위별 기본 정보 (영양성분, 보관방법 등)
-- ============================================================
CREATE TABLE meat_info (
  id INT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL COMMENT '부위명 (예: 삼겹살, 등심)',
  category VARCHAR(20) NOT NULL COMMENT '카테고리 (beef, pork)',
  calories INT NULL COMMENT '칼로리 (100g당)',
  protein DECIMAL(5,2) NULL COMMENT '단백질 (100g당, g)',
  fat DECIMAL(5,2) NULL COMMENT '지방 (100g당, g)',
  storage_guide TEXT NULL COMMENT '보관 가이드',
  CONSTRAINT chk_meat_category CHECK (category IN ('beef', 'pork')),
  INDEX idx_meat_part_name (part_name),
  INDEX idx_meat_category (category)
) ENGINE=InnoDB COMMENT='고기 부위 기본 정보';

-- ============================================================
-- 3. recognition_logs (AI 인식 로그)
-- 설명: AI가 인식한 고기 부위 기록 (분석 이력)
-- ============================================================
CREATE TABLE recognition_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL COMMENT '회원 ID',
  image_url VARCHAR(500) NOT NULL COMMENT '분석한 이미지 URL',
  part_name VARCHAR(100) NOT NULL COMMENT '인식된 부위명',
  confidence_score DECIMAL(5,2) NOT NULL COMMENT '신뢰도 (0.00 ~ 100.00)',
  illuminance_status VARCHAR(20) NULL COMMENT '조도 상태 (Low, Normal, High)',
  browser_agent VARCHAR(255) NULL COMMENT '브라우저 정보',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '분석 일시',
  CONSTRAINT fk_recognition_member FOREIGN KEY (member_id) 
    REFERENCES members(id) ON DELETE CASCADE,
  INDEX idx_recognition_member (member_id),
  INDEX idx_recognition_part_name (part_name),
  INDEX idx_recognition_created_at (created_at)
) ENGINE=InnoDB COMMENT='AI 인식 로그';

-- ============================================================
-- 4. fridge_items (냉장고 보관 목록)
-- 설명: 사용자가 냉장고에 보관한 고기 목록 (유통기한 관리)
-- ============================================================
CREATE TABLE fridge_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL COMMENT '회원 ID',
  meat_info_id INT NOT NULL COMMENT '고기 정보 ID',
  storage_date DATE NOT NULL COMMENT '보관 시작일',
  expiry_date DATE NOT NULL COMMENT '유통기한',
  status VARCHAR(20) NOT NULL DEFAULT 'stored' COMMENT '상태 (stored: 보관중, consumed: 소비완료)',
  alert_before INT NULL DEFAULT 3 COMMENT 'D-Day 알림 n일 전',
  use_web_push TINYINT(1) NULL DEFAULT 0 COMMENT 'Web Push 알림 사용 여부',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '등록 일시',
  -- 축산물 이력제 정보 (API 연동)
  slaughter_date DATE NULL COMMENT '도축일자',
  grade VARCHAR(50) NULL COMMENT '등급 (1++, 1+, 1, 2, 3 등)',
  trace_number VARCHAR(100) NULL COMMENT '이력번호 (OCR로 추출)',
  origin VARCHAR(100) NULL COMMENT '원산지 (한우, 수입 등)',
  company_name VARCHAR(200) NULL COMMENT '업체명',
  CONSTRAINT fk_fridge_member FOREIGN KEY (member_id) 
    REFERENCES members(id) ON DELETE CASCADE,
  CONSTRAINT fk_fridge_meat FOREIGN KEY (meat_info_id) 
    REFERENCES meat_info(id),
  CONSTRAINT chk_fridge_status CHECK (status IN ('stored', 'consumed')),
  INDEX idx_fridge_member (member_id),
  INDEX idx_fridge_expiry_date (expiry_date),
  INDEX idx_fridge_status (status),
  INDEX idx_trace_number (trace_number)
) ENGINE=InnoDB COMMENT='냉장고 보관 목록';

-- ============================================================
-- 5. market_prices (시세 정보)
-- 설명: 고기 부위별 시장 가격 (KAMIS API 연동)
-- ============================================================
CREATE TABLE market_prices (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL COMMENT '부위명',
  current_price INT NOT NULL COMMENT '현재 가격 (원)',
  price_date DATE NOT NULL COMMENT '가격 기준일',
  region VARCHAR(50) NOT NULL COMMENT '지역 (서울, 부산 등)',
  INDEX idx_price_part_region_date (part_name, region, price_date)
) ENGINE=InnoDB COMMENT='시세 정보 (현재가)';

-- ============================================================
-- 6. market_price_history (시세 이력)
-- 설명: 시세 변동 이력 (추세 분석용)
-- ============================================================
CREATE TABLE market_price_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL COMMENT '부위명',
  price INT NOT NULL COMMENT '가격 (원)',
  price_date DATE NOT NULL COMMENT '가격 기준일',
  region VARCHAR(50) NOT NULL COMMENT '지역',
  source VARCHAR(50) NULL DEFAULT 'KAMIS' COMMENT '데이터 출처',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '등록 일시',
  INDEX idx_history_part_region_date (part_name, region, price_date)
) ENGINE=InnoDB COMMENT='시세 이력';

-- ============================================================
-- 7. web_push_subscriptions (Web Push 구독 정보)
-- 설명: 사용자별 Web Push 구독 정보 (VAPID 키 저장)
-- ============================================================
CREATE TABLE web_push_subscriptions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL COMMENT '회원 ID',
  endpoint VARCHAR(1024) NOT NULL COMMENT 'Push 엔드포인트 URL',
  p256dh_key TEXT NOT NULL COMMENT 'P256DH 공개키',
  auth_key TEXT NOT NULL COMMENT '인증 키',
  user_agent VARCHAR(512) NULL COMMENT '브라우저 정보',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '구독 일시',
  CONSTRAINT fk_push_member FOREIGN KEY (member_id) 
    REFERENCES members(id) ON DELETE CASCADE,
  UNIQUE KEY uq_push_member_endpoint (member_id, endpoint(255)),
  INDEX idx_push_member (member_id)
) ENGINE=InnoDB COMMENT='Web Push 구독 정보';

-- ============================================================
-- 8. web_notifications (알림 발송 이력)
-- 설명: 유통기한 알림 등 발송 이력 및 예약 관리
-- ============================================================
CREATE TABLE web_notifications (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL COMMENT '회원 ID',
  fridge_item_id BIGINT NULL COMMENT '냉장고 아이템 ID (유통기한 알림)',
  notification_type VARCHAR(50) NOT NULL COMMENT '알림 타입 (expiry_alert, custom 등)',
  title VARCHAR(255) NOT NULL COMMENT '알림 제목',
  body TEXT NOT NULL COMMENT '알림 내용',
  scheduled_at DATETIME NOT NULL COMMENT '알림 예약 시간',
  sent_at DATETIME NULL COMMENT '실제 발송 시간',
  status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT '상태 (pending, sent, failed)',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '등록 일시',
  CONSTRAINT fk_notification_member FOREIGN KEY (member_id) 
    REFERENCES members(id) ON DELETE CASCADE,
  CONSTRAINT fk_notification_fridge FOREIGN KEY (fridge_item_id) 
    REFERENCES fridge_items(id) ON DELETE SET NULL,
  CONSTRAINT chk_notification_status CHECK (status IN ('pending', 'sent', 'failed')),
  INDEX idx_notification_member_scheduled (member_id, scheduled_at),
  INDEX idx_notification_status (status, scheduled_at)
) ENGINE=InnoDB COMMENT='알림 발송 이력';

-- ============================================================
-- 초기 데이터 삽입 (옵션)
-- ============================================================

-- 고기 부위 샘플 데이터
INSERT INTO meat_info (part_name, category, calories, protein, fat, storage_guide) VALUES
('삼겹살', 'pork', 331, 17.0, 28.0, '냉장 3일, 냉동 3개월'),
('목살', 'pork', 250, 18.0, 19.0, '냉장 3일, 냉동 3개월'),
('등심', 'beef', 240, 19.0, 17.0, '냉장 5일, 냉동 6개월'),
('안심', 'beef', 200, 22.0, 11.0, '냉장 5일, 냉동 6개월'),
('갈비', 'beef', 280, 18.0, 22.0, '냉장 3일, 냉동 6개월'),
('채끝', 'beef', 230, 20.0, 15.0, '냉장 5일, 냉동 6개월');

-- ============================================================
-- 데이터베이스 스키마 정보
-- ============================================================
-- 총 테이블 수: 8개
-- 주요 테이블:
--   1. members: 회원 정보 (게스트 포함)
--   2. meat_info: 고기 부위 기본 정보
--   3. recognition_logs: AI 인식 로그
--   4. fridge_items: 냉장고 보관 목록 (이력제 정보 포함)
--   5. market_prices: 시세 정보
--   6. market_price_history: 시세 이력
--   7. web_push_subscriptions: Web Push 구독
--   8. web_notifications: 알림 발송 이력
--
-- 외부 API 연동:
--   - KAMIS API: 시세 정보
--   - 식품안전나라 API: 영양정보
--   - 축산물 이력제 API: 도축일자, 등급, 원산지
--   - 수입육 이력제 API: 수입육 이력 정보
-- ============================================================
