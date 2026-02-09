-- 냉장고 사용자 지정 이름 (레시피 LLM에 전달용)
-- 이미 custom_name 컬럼이 있으면 "Duplicate column" 에러가 나므로 무시하세요.

ALTER TABLE fridge_items
  ADD COLUMN custom_name VARCHAR(100) NULL COMMENT '사용자 지정 고기 이름'
  AFTER company_name;
