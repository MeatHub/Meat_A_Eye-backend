-- 17개 부위 시드 (AI 학습·백엔드와 동일한 영문 part_name)
-- 소 10: Beef_Tenderloin, Beef_Ribeye, Beef_Sirloin, Beef_Chuck, Beef_Round, Beef_BottomRound, Beef_Brisket, Beef_Shank, Beef_Rib, Beef_Shoulder
-- 돼지 7: Pork_Tenderloin, Pork_Loin, Pork_Neck, Pork_PicnicShoulder, Pork_Ham, Pork_Belly, Pork_Ribs
-- 실행: mysql -u 사용자 -p DB명 < scripts/seed_meat_info_17.sql
-- (이미 영문 17개가 있으면 중복될 수 있음. part_name에 UNIQUE가 있으면 INSERT IGNORE 사용)

INSERT INTO meat_info (part_name, category, calories, protein, fat, storage_guide) VALUES
-- 소 10
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
-- 돼지 7
('Pork_Tenderloin', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Loin', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Neck', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_PicnicShoulder', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Ham', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Belly', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월'),
('Pork_Ribs', 'pork', NULL, NULL, NULL, '냉장 3일, 냉동 3개월');
