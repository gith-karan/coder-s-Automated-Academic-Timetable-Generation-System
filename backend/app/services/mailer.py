"""Outbound mail. ``console`` backend (dev) logs the message; ``smtp`` sends via STARTTLS."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("app.mail")


def send_mail(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if s.mail_backend == "console" or not s.smtp_host:
        if s.is_prod:
            log.error("Mail backend not configured in prod; message to %s dropped", to)
            return
        log.warning("[DEV MAIL] to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        smtp.send_message(msg)
