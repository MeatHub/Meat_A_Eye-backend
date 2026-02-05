-- fridge_items 테이블의 meat_info_id 컬럼을 NULL 허용으로 변경
-- 실행: mysql -u user -p meathub < sql/migrations/002_fridge_items_meat_info_id_nullable.sql
-- 설명: 이력번호만 있고 부위 정보가 없을 때도 냉장고 아이템을 저장할 수 있도록 함

ALTER TABLE fridge_items 
MODIFY COLUMN meat_info_id INT NULL COMMENT '고기 정보 ID (NULL이면 부위 미선택, 프론트엔드에서 "부위 선택" 표시)';
