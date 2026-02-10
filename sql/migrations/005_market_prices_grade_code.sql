-- market_prices 캐시 키에 등급 반영: 국내 소고기 등급별로 다른 가격 저장/조회
-- 등급별 캐시 구분 (국내 소: 01/02/03, 돼지/수입: '' 또는 '00')
ALTER TABLE market_prices ADD COLUMN grade_code VARCHAR(10) NOT NULL DEFAULT '';
