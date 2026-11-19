"""The invitation e-mail: password set-up link, then the desktop agent download link."""

from __future__ import annotations

import asyncio

from app.core.config import Settings
from app.services.email_service import EmailService
from tests.conftest import CapturingEmailSender

URL = "https://github.com/example/releases/download/v1.0.2/WorkPulseAgentSetup-1.0.2.exe"


def invite(settings: Settings) -> str:
    sender = CapturingEmailSender()
    service = EmailService(sender, settings)
    asyncio.run(
        service.send_invitation(to="a@example.com", name="Anu", company_name="Acme", inviter_name="Maya", token="t0k")
    )
    return sender.messages[-1].text


def test_the_agent_download_link_follows_the_password_link(settings: Settings) -> None:
    text = invite(settings.model_copy(update={"agent_download_url": URL}))
    assert text.index("set your password") < text.index(URL)
    assert "sign in with this e-mail address and the password you set above" in text
    assert "token=t0k\n" in text  # the set-up link is unchanged


def test_no_download_section_without_a_published_installer(settings: Settings) -> None:
    text = invite(settings.model_copy(update={"agent_download_url": ""}))
    assert "Install WorkPulse" not in text
