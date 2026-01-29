-- 축산물 이력제 정보를 저장하기 위한 컬럼 추가
USE meathub;

-- fridge_items 테이블에 도축일자, 등급, 이력번호 컬럼 추가
ALTER TABLE fridge_items
  ADD COLUMN slaughter_date DATE NULL COMMENT '도축일자' AFTER expiry_date,
  ADD COLUMN grade VARCHAR(50) NULL COMMENT '등급' AFTER slaughter_date,
  ADD COLUMN trace_number VARCHAR(100) NULL COMMENT '이력번호' AFTER grade,
  ADD COLUMN origin VARCHAR(100) NULL COMMENT '원산지' AFTER trace_number,
  ADD COLUMN company_name VARCHAR(200) NULL COMMENT '업체명' AFTER origin,
  ADD INDEX idx_trace_number (trace_number);

