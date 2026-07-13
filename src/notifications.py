"""Email delivery — provider-agnostic, entirely optional.

If EMAIL_PROVIDER isn't set (or no recipients are configured), this module
logs a clear message and returns False. It never raises — the report is
always available as a committed file + workflow artifact regardless of
whether email is configured.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

log = logging.getLogger("notifications")


def _recipients() -> list[str]:
    raw = os.getenv("REPORT_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


def _send_smtp(subject: str, body_text: str, recipients: list[str]) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not all([host, user, password]):
        log.warning("EMAIL_PROVIDER=smtp but SMTP_HOST/SMTP_USER/SMTP_PASSWORD are incomplete.")
        return False

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body_text, "plain"))

    with smtplib.SMTP_SSL(host, port) as server:
        server.login(user, password)
        for recipient in recipients:
            server.sendmail(user, recipient, msg.as_string())
    return True


def _send_sendgrid(subject: str, body_text: str, recipients: list[str]) -> bool:
    api_key = os.getenv("SENDGRID_API_KEY")
    from_addr = os.getenv("SENDGRID_FROM")
    if not all([api_key, from_addr]):
        log.warning("EMAIL_PROVIDER=sendgrid but SENDGRID_API_KEY/SENDGRID_FROM are incomplete.")
        return False

    payload = {
        "personalizations": [{"to": [{"email": r} for r in recipients]}],
        "from": {"email": from_addr},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body_text}],
    }
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if resp.status_code >= 300:
        log.error("SendGrid send failed (%s): %s", resp.status_code, resp.text)
        return False
    return True


def _send_resend(subject: str, body_text: str, recipients: list[str]) -> bool:
    api_key = os.getenv("RESEND_API_KEY")
    from_addr = os.getenv("RESEND_FROM")
    if not all([api_key, from_addr]):
        log.warning("EMAIL_PROVIDER=resend but RESEND_API_KEY/RESEND_FROM are incomplete.")
        return False

    payload = {"from": from_addr, "to": recipients, "subject": subject, "text": body_text}
    resp = requests.post(
        "https://api.resend.com/emails",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    if resp.status_code >= 300:
        log.error("Resend send failed (%s): %s", resp.status_code, resp.text)
        return False
    return True


_PROVIDERS = {"smtp": _send_smtp, "sendgrid": _send_sendgrid, "resend": _send_resend}


def send_report(subject: str, body_text: str) -> bool:
    provider = os.getenv("EMAIL_PROVIDER", "").strip().lower()
    recipients = _recipients()

    if not provider or not recipients:
        log.info("Email not configured — report available as artifact/commit.")
        return False

    sender = _PROVIDERS.get(provider)
    if not sender:
        log.warning("Unknown EMAIL_PROVIDER '%s' — skipping email. Valid options: smtp, sendgrid, resend.", provider)
        return False

    try:
        sent = sender(subject, body_text, recipients)
        if sent:
            log.info("Report emailed via %s to: %s", provider, ", ".join(recipients))
        return sent
    except Exception as e:
        log.error("Email send via %s failed: %s", provider, e)
        return False
