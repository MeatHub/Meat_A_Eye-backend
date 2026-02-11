-- 레시피 즐겨찾기 테이블 (MySQL)
-- 실행: mysql -u 사용자 -p 데이터베이스 < create_recipe_bookmarks_table.sql

CREATE TABLE IF NOT EXISTS recipe_bookmarks (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    member_id BIGINT NOT NULL,
    saved_recipe_id BIGINT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_recipe_bookmark_member_recipe (member_id, saved_recipe_id),
    CONSTRAINT fk_recipe_bookmark_member FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
    CONSTRAINT fk_recipe_bookmark_recipe FOREIGN KEY (saved_recipe_id) REFERENCES saved_recipes(id) ON DELETE CASCADE,
    INDEX idx_recipe_bookmarks_member_id (member_id),
    INDEX idx_recipe_bookmarks_saved_recipe_id (saved_recipe_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='레시피 즐겨찾기';
