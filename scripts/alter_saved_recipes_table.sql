-- 기존 saved_recipes 테이블이 ENUM 타입으로 생성된 경우, VARCHAR로 변경
-- 주의: 테이블이 이미 존재하고 데이터가 있다면 백업 후 실행하세요

-- 방법 1: 테이블이 비어있는 경우 DROP 후 재생성
-- DROP TABLE IF EXISTS saved_recipes;

-- 방법 2: ALTER TABLE로 컬럼 타입 변경 (데이터 보존)
ALTER TABLE saved_recipes 
MODIFY COLUMN source VARCHAR(50) NOT NULL COMMENT '레시피 출처 (ai_random, fridge_random, fridge_multi, part_specific)';
