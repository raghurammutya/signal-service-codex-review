"""
Email Webhook API

Sprint 5A: Endpoint to receive and process inbound emails.
Enables SDK to receive emails and trigger signal actions.
"""
import os
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel, Field

from app.clients.comms_service_client import get_email_integration_service
from app.core.logging import log_info, log_error

router = APIRouter(prefix="/api/v2/signals/email", tags=["email-webhook"])


class EmailWebhookRequest(BaseModel):
    """Inbound email webhook payload."""
    from_email: str = Field(..., description="Sender email address")
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body_plain: str = Field(..., description="Plain text body")
    body_html: Optional[str] = Field(None, description="HTML body")
    headers: Optional[Dict[str, str]] = Field(None, description="Email headers")
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="Email attachments")
    timestamp: Optional[str] = Field(None, description="Email timestamp")


@router.post("/webhook")
async def process_email_webhook(
    request: EmailWebhookRequest,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret")
) -> Dict[str, Any]:
    """
    Process inbound email webhook.
    
    This endpoint receives emails sent to signal-specific addresses and
    processes them as commands or triggers.
    
    Sprint 5A: Enables SDK to receive and process emails.
    """
    try:
<<<<<<< HEAD
        # Verify webhook secret from config_service (Architecture Principle #1: Config service exclusivity)
        try:
            from common.config_service.client import ConfigServiceClient
            from app.core.config import settings
            
            config_client = ConfigServiceClient(
                service_name="signal_service",
                environment=settings.environment,
                timeout=5
            )
            expected_secret = config_client.get_secret("EMAIL_WEBHOOK_SECRET")
            if not expected_secret:
                raise ValueError("EMAIL_WEBHOOK_SECRET not found in config_service")
        except Exception as e:
            raise RuntimeError(f"Failed to get email webhook secret from config_service: {e}. No environment fallbacks allowed per architecture.")
=======
        # Verify webhook secret from config_service  
        from app.core.config import settings
        expected_secret = getattr(settings, 'EMAIL_WEBHOOK_SECRET', None)
>>>>>>> compliance-violations-fixed
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/sendgrid")
async def process_sendgrid_webhook(request: Request) -> Dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook/mailgun")
async def process_mailgun_webhook(request: Request) -> Dict[str, Any]:
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/status")
async def get_webhook_status() -> Dict[str, Any]:
    """
    Get email webhook configuration and status.
    
    Returns information about configured email endpoints.
    """
    try:
        email_service = await get_email_integration_service()
        
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
        raise HTTPException(status_code=500, detail=str(e))