"""
Email tools for sending analysis and recommended fix. Config via env (no hardcoded secrets).
Supports SMTP (local) and AWS SES (AgentCore). Use DEFAULT_EMAIL_TO or pass to_email.
"""

import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from strands import tool

logger = logging.getLogger(__name__)

# SMTP (local)
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# Or AWS SES (AgentCore): set EMAIL_FROM and optionally AWS_REGION
USE_SES = os.environ.get("EMAIL_USE_SES", "").lower() in ("1", "true", "yes")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
DEFAULT_EMAIL_TO = os.environ.get("DEFAULT_EMAIL_TO", "")


def _send_smtp(to: str, subject: str, body: str) -> str:
    if not all([SMTP_HOST, EMAIL_FROM, to]):
        return json.dumps({"error": "SMTP_HOST, EMAIL_FROM, and to_email (or DEFAULT_EMAIL_TO) must be set"})
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.sendmail(EMAIL_FROM, [to], msg.as_string())
        return json.dumps({"status": "sent", "to": to})
    except Exception as e:
        logger.warning("SMTP send failed: %s", e)
        return json.dumps({"error": str(e)})


def _send_ses(to: str, subject: str, body: str) -> str:
    if not EMAIL_FROM or not to:
        return json.dumps({"error": "EMAIL_FROM and to_email (or DEFAULT_EMAIL_TO) must be set for SES"})
    try:
        import boto3
        client = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        client.send_email(
            Source=EMAIL_FROM,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        return json.dumps({"status": "sent", "to": to})
    except Exception as e:
        logger.warning("SES send failed: %s", e)
        return json.dumps({"error": str(e)})


@tool
def send_analysis_email(report_body: str, to_email: str = "", subject: str = "K8s Alert – Analysis and Recommended Fix") -> str:
    """
    Send an email with the analysis report and recommended fix. Use report_body for the full text (summary, logs summary, root cause, recommended actions).
    If to_email is empty, uses DEFAULT_EMAIL_TO from environment. Subject can be overridden.
    """
    to = (to_email or DEFAULT_EMAIL_TO).strip()
    if not to:
        return json.dumps({"error": "Provide to_email or set DEFAULT_EMAIL_TO in environment"})
    if not report_body:
        return json.dumps({"error": "report_body is required"})
    if USE_SES:
        return _send_ses(to, subject, report_body)
    return _send_smtp(to, subject, report_body)
