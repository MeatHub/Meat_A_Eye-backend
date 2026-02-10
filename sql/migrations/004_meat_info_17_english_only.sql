-- meat_info를 영문 17개만 남기기 (한글 part_name 또는 중복 제거)
-- 냉장고 부위 드롭다운 중복(소/안심 + 안심) 방지
-- 실행: mysql -u 사용자 -p meathub < sql/migrations/004_meat_info_17_english_only.sql
-- 주의: 실행 후 fridge_items.meat_info_id가 기존 id를 참조하면 무효가 됩니다. 필요 시 냉장고에서 부위를 다시 선택해 주세요.

SET FOREIGN_KEY_CHECKS = 0;

DELETE FROM meat_info;

INSERT INTO meat_info (part_name, category, calories, protein, fat, storage_guide) VALUES
('Beef_Tenderloin', 'beef', NULL, NULL, NULL, '냉장 5일, 냉동 6개월'),
('Beef_Ribeye', 'beef', NULL, NULL, NULL, '냉장 5일, 냉동 6개월'),
('Beef_Sirloin', 'beef', NULL, NULL, NULL, '냉장 5일, 냉동 6개월'),
('Beef_Chuck', 'beef', NULL, NULL, NULL, '냉장 3일, 냉동 6개월'),
('Beef_Round', 'beef', NULL, NULL, NULL, '냉장 5일, 냉동 6개월'),
('Beef_BottomRound', 'beef', NULL, NULL, NULL, '냉장 5일, 냉동 6개월'),
('Beef_Brisket', 'beef', NULL, NULL, NULL, '냉장 3일, 냉동 6개월'),
('Beef_Shank', 'beef', NULL, NULL, NULL, '냉장 3일, 냉동 6개월'),
('Beef_Rib', 'beef', NULL, NULL, NULL, '냉장 3일, 냉동 6개월'),
('Beef_Shoulder', 'beef', NULL, NULL, NULL, '냉장 3일, 냉동 6개월'),
('Pork_Tenderloin', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Loin', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Neck', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_PicnicShoulder', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Ham', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Belly', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Ribs', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월');

SET FOREIGN_KEY_CHECKS = 1;
