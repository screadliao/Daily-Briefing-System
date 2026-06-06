from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from src.formatter import render_plain_text, to_html_email


def deliver(briefing: dict[str, Any]) -> list[str]:
    results: list[str] = []
    mode = os.getenv("DELIVERY_MODE", "").lower()

    if mode:
        if mode != "email":
            raise RuntimeError("DELIVERY_MODE only supports 'email'.")
        send_email(briefing)
        results.append("email")

    if os.getenv("TELEGRAM_BOT_TOKEN"):
        send_telegram(briefing, os.getenv("GITHUB_PAGES_URL", ""))
        results.append("telegram")

    return results


def send_email(briefing: dict[str, Any]) -> None:
    if os.getenv("SENDGRID_API_KEY"):
        send_via_sendgrid(briefing)
        return
    send_via_smtp(briefing)


def send_via_sendgrid(briefing: dict[str, Any]) -> None:
    recipient = require_env("RECIPIENT_EMAIL")
    sender = os.getenv("SENDER_EMAIL", recipient)
    subject = f"☀️ 早報 · {briefing['date']} · {briefing['headline']}"

    message = Mail(
        from_email=sender,
        to_emails=recipient,
        subject=subject,
        html_content=to_html_email(briefing),
        plain_text_content=render_plain_text(briefing),
    )
    client = SendGridAPIClient(os.environ["SENDGRID_API_KEY"])
    response = client.send(message)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid delivery failed with status {response.status_code}")


def send_via_smtp(briefing: dict[str, Any]) -> None:
    host = require_env("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = require_env("SMTP_USER")
    password = require_env("SMTP_PASS")
    recipient = require_env("RECIPIENT_EMAIL")
    subject = f"☀️ 早報 · {briefing['date']} · {briefing['headline']}"

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = user
    message["To"] = recipient
    message.set_content(render_plain_text(briefing))
    message.add_alternative(to_html_email(briefing), subtype="html")

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(message)


def send_telegram(briefing: dict[str, Any], url: str) -> None:
    token = require_env("TELEGRAM_BOT_TOKEN")
    chat_id = require_env("TELEGRAM_CHAT_ID")
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": format_telegram_message(briefing, url),
            "parse_mode": "HTML",
        },
        timeout=15.0,
    )
    response.raise_for_status()


def format_telegram_message(briefing: dict[str, Any], url: str) -> str:
    return f"☀️ {briefing['date']}\n{briefing['headline']}\n\n📖 {url}".strip()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
