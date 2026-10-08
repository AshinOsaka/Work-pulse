"""Transactional e-mail.

Two backends:

* `console` writes messages to the API log, so the password-reset and verification flows can be exercised locally.
  It is refused in production (see `Settings`), because the log would hold one-time sign-in links.
* `smtp` delivers through any SMTP relay or provider (STARTTLS on 587, implicit TLS on 465, plain only for a local
  relay). Delivery failures raise `EmailDeliveryError`: a clear, retryable 503 instead of a silent loss.

Other providers plug in by implementing `EmailSender`.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.core.observability import EMAILS

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    async def send(self, message: EmailMessage) -> None:
        logger.info("[email:console] to=%s subject=%r\n%s", message.to, message.subject, message.text)
        EMAILS.labels(backend="console", outcome="sent").inc()


class EmailDeliveryError(ServiceUnavailableError):
    default_code = "email_unavailable"
    default_message = "We couldn't send the e-mail right now. Please try again in a few minutes."


class SmtpEmailSender:
    """Sends through SMTP. smtplib is blocking, so each message is sent on a worker thread."""

    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise ValueError("EMAIL_BACKEND=smtp needs SMTP_HOST.")
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._security = settings.smtp_security
        self._username = settings.smtp_username
        self._password = settings.smtp_password.get_secret_value() if settings.smtp_password else ""
        self._timeout = settings.smtp_timeout_seconds
        self._from = settings.email_from
        self._tls = ssl.create_default_context()

    def _build(self, message: EmailMessage) -> MimeMessage:
        mime = MimeMessage()
        mime["From"] = self._from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime["Date"] = formatdate(localtime=False)
        domain = parseaddr(self._from)[1].rpartition("@")[2] or None
        mime["Message-ID"] = make_msgid(domain=domain)
        mime.set_content(message.text)
        return mime

    def _send_blocking(self, mime: MimeMessage) -> None:
        smtp: smtplib.SMTP
        if self._security == "ssl":
            smtp = smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout, context=self._tls)
        else:
            smtp = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        with smtp:
            smtp.ehlo()
            if self._security == "starttls":
                smtp.starttls(context=self._tls)
                smtp.ehlo()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(mime)

    async def send(self, message: EmailMessage) -> None:
        try:
            await asyncio.to_thread(self._send_blocking, self._build(message))
        except (smtplib.SMTPException, OSError) as exc:
            # The recipient address is personal data and the body may hold a sign-in link: neither is logged.
            logger.warning(
                "E-mail delivery via %s:%s failed (%s)", self._host, self._port, type(exc).__name__
            )
            EMAILS.labels(backend="smtp", outcome="failed").inc()
            raise EmailDeliveryError() from exc
        EMAILS.labels(backend="smtp", outcome="sent").inc()
        logger.info("E-mail sent via SMTP: %r", message.subject)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "console":
        return ConsoleEmailSender()
    if settings.email_backend == "smtp":
        return SmtpEmailSender(settings)
    raise ValueError(f"Unsupported email backend: {settings.email_backend}")


class EmailService:
    def __init__(self, sender: EmailSender, settings: Settings) -> None:
        self._sender = sender
        self._settings = settings

    def _link(self, path: str, token: str) -> str:
        return f"{self._settings.frontend_url.rstrip('/')}{path}?{urlencode({'token': token})}"

    async def send_password_reset(self, *, to: str, name: str, token: str) -> None:
        minutes = self._settings.password_reset_token_expire_minutes
        await self._sender.send(
            EmailMessage(
                to=to,
                subject="Reset your WorkPulse password",
                text=(
                    f"Hi {name},\n\nUse the link below to choose a new password. "
                    f"It expires in {minutes} minutes.\n\n{self._link('/reset-password', token)}\n\n"
                    "If you did not request this, you can ignore this e-mail."
                ),
            )
        )

    async def send_email_verification(self, *, to: str, name: str, token: str) -> None:
        await self._sender.send(
            EmailMessage(
                to=to,
                subject="Verify your WorkPulse e-mail address",
                text=(
                    f"Hi {name},\n\nConfirm your e-mail address to secure your account:\n\n"
                    f"{self._link('/verify-email', token)}"
                ),
            )
        )

    async def send_invitation(
        self, *, to: str, name: str, company_name: str, inviter_name: str, token: str
    ) -> None:
        days = self._settings.invitation_token_expire_days
        await self._sender.send(
            EmailMessage(
                to=to,
                subject=f"{inviter_name} invited you to {company_name} on WorkPulse",
                text=(
                    f"Hi {name},\n\n{inviter_name} has invited you to join {company_name} on WorkPulse.\n\n"
                    f"Accept the invitation and set your password:\n\n{self._link('/accept-invite', token)}\n\n"
                    f"This link expires in {days} days."
                ),
            )
        )
