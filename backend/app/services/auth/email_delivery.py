"""Outbound auth email: SMTP when configured, otherwise log to the API process (local dev)."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def is_smtp_configured() -> bool:
    """True when real outbound email is available (enables login email 2FA)."""
    settings = get_settings()
    return bool(settings.smtp_host.strip())


def send_auth_email(*, to_email: str, subject: str, body_text: str) -> None:
    """Deliver an auth email via SMTP or log the body when SMTP is not configured."""
    settings = get_settings()
    if not is_smtp_configured():
        logger.info(
            "Auth email (SMTP not configured) to=%s subject=%s\n%s",
            to_email,
            subject,
            body_text,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from_email
    msg["To"] = to_email
    msg.set_content(body_text)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)

    logger.info("Auth email sent to=%s subject=%s", to_email, subject)


def send_login_otp_email(*, to_email: str, otp_code: str, expire_minutes: int) -> None:
    """Email the six-digit sign-in verification code."""
    body = (
        f"Your Spend Integrity sign-in code is: {otp_code}\n\n"
        f"This code expires in {expire_minutes} minutes. "
        "If you did not try to sign in, you can ignore this email."
    )
    send_auth_email(
        to_email=to_email,
        subject="Your sign-in code",
        body_text=body,
    )


def send_password_reset_email(*, to_email: str, reset_url: str, expire_minutes: int) -> None:
    """Email a single-use link to choose a new password."""
    body = (
        "You requested a password reset for Spend Integrity.\n\n"
        f"Reset your password here (link expires in {expire_minutes} minutes):\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    send_auth_email(
        to_email=to_email,
        subject="Reset your password",
        body_text=body,
    )
