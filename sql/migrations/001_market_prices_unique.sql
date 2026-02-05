-- market_prices 테이블에 UNIQUE 제약 추가 (기존 DB 마이그레이션)
-- 실행: mysql -u user -p meathub < sql/migrations/001_market_prices_unique.sql

-- 중복 데이터 정리 (같은 part_name, region, price_date 중 최신 1건만 유지)
DELETE p1 FROM market_prices p1
INNER JOIN market_prices p2
WHERE p1.id < p2.id
  AND p1.part_name = p2.part_name
  AND p1.region = p2.region
  AND p1.price_date = p2.price_date;

ALTER TABLE market_prices
ADD UNIQUE KEY uq_market_price (part_name, region, price_date);
