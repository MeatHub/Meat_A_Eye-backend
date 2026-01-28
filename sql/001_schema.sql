-- Meat-A-Eye MySQL Schema (사용자 제공 스키마)
CREATE DATABASE IF NOT EXISTS meathub
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE meathub;

CREATE TABLE members (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL,
  nickname VARCHAR(50) NOT NULL,
  web_push_subscription TEXT NULL COMMENT 'JSON format',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE meat_info (
  id INT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  category VARCHAR(20) NOT NULL,
  calories INT NULL COMMENT 'per 100g',
  protein DECIMAL(5,2) NULL COMMENT 'per 100g',
  fat DECIMAL(5,2) NULL COMMENT 'per 100g',
  storage_guide TEXT NULL,
  CONSTRAINT chk_meat_category
    CHECK (category IN ('beef', 'pork'))
) ENGINE=InnoDB;

CREATE TABLE recognition_logs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  image_url VARCHAR(500) NOT NULL,
  part_name VARCHAR(100) NOT NULL,
  confidence_score DECIMAL(5,2) NOT NULL COMMENT '0.00 ~ 100.00',
  illuminance_status VARCHAR(20) NULL COMMENT 'Low / Normal / High',
  browser_agent VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_recognition_member
    FOREIGN KEY (member_id)
    REFERENCES members(id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE fridge_items (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  meat_info_id INT NOT NULL,
  storage_date DATE NOT NULL,
  expiry_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL,
  CONSTRAINT fk_fridge_member
    FOREIGN KEY (member_id)
    REFERENCES members(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_fridge_meat
    FOREIGN KEY (meat_info_id)
    REFERENCES meat_info(id),
  CONSTRAINT chk_fridge_status
    CHECK (status IN ('stored', 'consumed'))
) ENGINE=InnoDB;

CREATE TABLE market_prices (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  part_name VARCHAR(100) NOT NULL,
  current_price INT NOT NULL COMMENT 'KRW',
  price_date DATE NOT NULL,
  region VARCHAR(50) NOT NULL
) ENGINE=InnoDB;
