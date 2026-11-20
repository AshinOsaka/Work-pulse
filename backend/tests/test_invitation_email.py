"""The invitation e-mail: password set-up link, then the desktop agent download link."""

from __future__ import annotations

import asyncio
from typing import Any

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


def test_welcome_email_sends_download_link_steps_and_a_fresh_code(
    ws: Any, email_sender: CapturingEmailSender, settings: Settings, monkeypatch: Any
) -> None:
    from tests.test_agent_api import device_info

    monkeypatch.setattr(settings, "agent_download_url", URL)
    employee = ws.employee("Athira Osaka")  # no invitation: she never needs the website
    issued = ws.post(f"/employees/{employee['id']}/devices", {"name": "Athira laptop"}).json()
    sent = ws.post(f"/devices/{issued['id']}/welcome-email", {})
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["welcome_sent_at"] and body["enrollment_code"] != issued["enrollment_code"]
    mail = email_sender.messages[-1]
    assert mail.to == employee["email"] and mail.subject == "Welcome to WorkPulse"
    assert URL in mail.text and body["enrollment_code"] in mail.text
    # The first code no longer works; the e-mailed one does, once.
    old = ws.client.post("/api/agent/enroll", json={"enrollment_code": issued["enrollment_code"], "device": device_info()})
    assert old.status_code == 400
    new = ws.client.post("/api/agent/enroll", json={"enrollment_code": body["enrollment_code"], "device": device_info()})
    assert new.status_code == 200, new.text
    # Once the computer is set up there's nothing left to send.
    again = ws.post(f"/devices/{issued['id']}/welcome-email", {})
    assert again.status_code == 400 and again.json()["error"]["code"] == "device_not_pending"
