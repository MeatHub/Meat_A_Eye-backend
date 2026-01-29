-- 게스트 기능을 위한 컬럼 추가
USE meathub;

-- members 테이블에 게스트 관련 컬럼 추가
ALTER TABLE members 
  ADD COLUMN IF NOT EXISTS is_guest TINYINT(1) NOT NULL DEFAULT 0 AFTER nickname,
  ADD COLUMN IF NOT EXISTS guest_id VARCHAR(36) NULL UNIQUE AFTER is_guest;

-- guest_id 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_member_guest_id ON members(guest_id);

