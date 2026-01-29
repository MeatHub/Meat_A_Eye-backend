-- 웹 푸시 알림 상태 관리 테이블
USE meathub;

-- web_notifications: 알림 발송 이력 및 예약
CREATE TABLE IF NOT EXISTS web_notifications (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  member_id BIGINT NOT NULL,
  fridge_item_id BIGINT NULL COMMENT '냉장고 아이템 ID (유통기한 알림)',
  notification_type VARCHAR(50) NOT NULL COMMENT 'expiry_alert, custom 등',
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  scheduled_at DATETIME NOT NULL COMMENT '알림 예약 시간',
  sent_at DATETIME NULL COMMENT '실제 발송 시간',
  status VARCHAR(20) NOT NULL DEFAULT 'pending' COMMENT 'pending, sent, failed',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_notification_member
    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE,
  CONSTRAINT fk_notification_fridge
    FOREIGN KEY (fridge_item_id) REFERENCES fridge_items(id) ON DELETE SET NULL,
  CONSTRAINT chk_notification_status
    CHECK (status IN ('pending', 'sent', 'failed')),
  INDEX idx_notification_member_scheduled (member_id, scheduled_at),
  INDEX idx_notification_status (status, scheduled_at)
) ENGINE=InnoDB;
