-- saved_recipes 테이블 생성
CREATE TABLE IF NOT EXISTS saved_recipes (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    member_id BIGINT NOT NULL,
    title VARCHAR(200) NOT NULL COMMENT '레시피 제목',
    content TEXT NOT NULL COMMENT '레시피 내용 (마크다운)',
    source VARCHAR(50) NOT NULL COMMENT '레시피 출처 (ai_random, fridge_random, fridge_multi, part_specific)',
    used_meats TEXT NULL COMMENT '사용된 고기 목록 (JSON)',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    INDEX idx_member_id (member_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='저장된 레시피';
