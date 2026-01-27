"""
Email Webhook API

Sprint 5A: Endpoint to receive and process inbound emails.
Enables SDK to receive emails and trigger signal actions.
"""
import json
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.clients.comms_service_client import get_email_integration_service
from app.core.logging import log_error, log_info

router = APIRouter(prefix="/api/v2/signals/email", tags=["email-webhook"])

# Get webhook secret from environment
expected_secret = os.getenv('EMAIL_WEBHOOK_SECRET')


class EmailWebhookRequest(BaseModel):
    """Inbound email webhook payload."""
    from_email: str = Field(..., description="Sender email address")
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body_plain: str = Field(..., description="Plain text body")
    body_html: str | None = Field(None, description="HTML body")
    headers: dict[str, str] | None = Field(None, description="Email headers")
    attachments: list[dict[str, Any]] | None = Field(None, description="Email attachments")
    timestamp: str | None = Field(None, description="Email timestamp")


@router.post("/webhook")
async def process_email_webhook(
    request: EmailWebhookRequest,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret")
) -> dict[str, Any]:
    """
    Process inbound email webhook.

    This endpoint receives emails sent to signal-specific addresses and
    processes them as commands or triggers.

    Sprint 5A: Enables SDK to receive and process emails.
    """
    try:
        if expected_secret and x_webhook_secret != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        log_info(f"Processing email webhook from {request.from_email}: {request.subject}")

        # Get email integration service
        email_service = await get_email_integration_service()

        # Process the inbound email
        result = await email_service.process_inbound_email(
            from_email=request.from_email,
            subject=request.subject,
            body=request.body_plain,
            headers=request.headers
        )

        return {
            "success": result.get("success", False),
            "message": "Email processed",
            "command": result.get("command"),
            "result": result.get("result")
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error processing email webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/webhook/sendgrid")
async def process_sendgrid_webhook(request: Request) -> dict[str, Any]:
    """
    Process SendGrid inbound parse webhook.

    SendGrid-specific format for inbound emails.
    """
    try:
        # Parse SendGrid format
        form_data = await request.form()

        email_data = EmailWebhookRequest(
            from_email=form_data.get("from", ""),
            to_email=form_data.get("to", ""),
            subject=form_data.get("subject", ""),
            body_plain=form_data.get("text", ""),
            body_html=form_data.get("html"),
            headers=json.loads(form_data.get("headers", "{}")),
            timestamp=form_data.get("timestamp")
        )

        return await process_email_webhook(email_data)

    except Exception as e:
        log_error(f"Error processing SendGrid webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/webhook/mailgun")
async def process_mailgun_webhook(request: Request) -> dict[str, Any]:
    """
    Process Mailgun inbound route webhook.

    Mailgun-specific format for inbound emails.
    """
    try:
        # Parse Mailgun format
        form_data = await request.form()

        email_data = EmailWebhookRequest(
            from_email=form_data.get("sender", ""),
            to_email=form_data.get("recipient", ""),
            subject=form_data.get("subject", ""),
            body_plain=form_data.get("body-plain", ""),
            body_html=form_data.get("body-html"),
            headers={
                "Message-Id": form_data.get("Message-Id", ""),
                "Date": form_data.get("Date", "")
            },
            timestamp=form_data.get("timestamp")
        )

        return await process_email_webhook(email_data)

    except Exception as e:
        log_error(f"Error processing Mailgun webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/webhook/status")
async def get_webhook_status() -> dict[str, Any]:
    """
    Get email webhook configuration and status.

    Returns information about configured email endpoints.
    """
    try:
        await get_email_integration_service()

        return {
            "status": "active",
            "endpoints": {
                "generic": "/api/v2/signals/email/webhook",
                "sendgrid": "/api/v2/signals/email/webhook/sendgrid",
                "mailgun": "/api/v2/signals/email/webhook/mailgun"
            },
            "supported_commands": [
                "subscribe",
                "unsubscribe",
                "status",
                "pause",
                "resume",
                "execute",
                "help"
            ],
            "example_addresses": [
                "signals@notify.stocksblitz.com",
                "signal-{signal_id}@notify.stocksblitz.com"
            ]
        }

    except Exception as e:
        log_error(f"Error getting webhook status: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
