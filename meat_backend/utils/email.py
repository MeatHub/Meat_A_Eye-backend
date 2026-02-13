"""이메일 발송 유틸리티 (SMTP)."""
import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..config.settings import settings

logger = logging.getLogger(__name__)


def _send_smtp(msg: MIMEMultipart, to_email: str) -> bool:
    """동기 SMTP 발송 (스레드 내에서 실행)."""
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("임시 비밀번호 이메일 발송 성공: %s", to_email)
        return True
    except Exception as e:
        logger.exception("이메일 발송 실패 (%s): %s", to_email, e)
        return False


async def send_temp_password_email(to_email: str, temp_password: str) -> bool:
    """임시 비밀번호를 이메일로 발송.

    Returns:
        True: 발송 성공, False: 발송 실패
    """
    if not settings.smtp_user or not settings.smtp_password:
        logger.error("SMTP 설정이 없습니다. .env에 SMTP_USER, SMTP_PASSWORD를 설정해주세요.")
        return False

    subject = "[Meat-A-Eye] 임시 비밀번호 안내"
    html_body = f"""
    <div style="max-width: 480px; margin: 0 auto; font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;">
        <div style="background: linear-gradient(135deg, #800000, #a02020); padding: 32px 24px; text-align: center; border-radius: 12px 12px 0 0;">
            <h1 style="color: #fff; font-size: 22px; margin: 0;">🥩 Meat-A-Eye</h1>
            <p style="color: rgba(255,255,255,0.85); font-size: 13px; margin: 8px 0 0 0;">임시 비밀번호 안내</p>
        </div>
        <div style="background: #fff; padding: 32px 24px; border: 1px solid #e8e4dd; border-top: none;">
            <p style="color: #333; font-size: 14px; line-height: 1.7;">
                안녕하세요,<br/>
                요청하신 임시 비밀번호를 안내드립니다.
            </p>
            <div style="background: #faf5f0; border: 2px dashed #800000; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                <p style="color: #666; font-size: 12px; margin: 0 0 8px 0;">임시 비밀번호</p>
                <p style="color: #800000; font-size: 24px; font-weight: bold; margin: 0; letter-spacing: 2px;">{temp_password}</p>
            </div>
            <p style="color: #666; font-size: 13px; line-height: 1.6;">
                위 임시 비밀번호로 로그인한 후,<br/>
                <strong>마이페이지</strong>에서 비밀번호를 변경해주세요.
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
            <p style="color: #999; font-size: 11px; text-align: center;">
                본인이 요청하지 않은 경우 이 메일을 무시하세요.<br/>
                © Meat-A-Eye
            </p>
        </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # 동기 SMTP를 별도 스레드에서 실행하여 이벤트 루프 블로킹 방지
    return await asyncio.to_thread(_send_smtp, msg, to_email)
