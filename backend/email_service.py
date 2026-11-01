"""
Email service for sending inquiry notifications
Supports multiple providers: Gmail SMTP, SendGrid, Brevo, Mailgun, custom SMTP
"""
import asyncio
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib
from config import get_settings
from models import (
    get_service_label,
    get_budget_label,
    get_timeline_label
)

settings = get_settings()


class EmailService:
    """Email service for sending inquiry notifications"""

    def __init__(self):
        self.provider = settings.EMAIL_PROVIDER.lower()

    async def send_inquiry_notification(self, inquiry_data: dict) -> bool:
        """
        Send inquiry notification email

        Args:
            inquiry_data: Dictionary with inquiry details

        Returns:
            bool: True if sent successfully
        """
        try:
            if self.provider == "sendgrid":
                return await self._send_via_sendgrid(inquiry_data)
            elif self.provider in ["gmail", "brevo", "mailgun", "custom"]:
                return await self._send_via_smtp(inquiry_data)
            else:
                # Default to SMTP
                return await self._send_via_smtp(inquiry_data)
        except Exception as e:
            print(f"Email sending failed: {e}")
            return False

    async def _send_via_smtp(self, data: dict) -> bool:
        """Send email via SMTP (Gmail, Brevo, Mailgun, custom)"""
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            print("SMTP credentials not configured")
            return False

        message = self._create_email_message(data)

        try:
            # Gmail uses STARTTLS on port 587, implicit TLS on port 465
            use_tls = settings.SMTP_USE_TLS
            start_tls = False

            # For Gmail on port 587, use STARTTLS
            if settings.SMTP_HOST == "smtp.gmail.com" and settings.SMTP_PORT == 587:
                use_tls = False
                start_tls = True
            # For Gmail on port 465, use implicit TLS
            elif settings.SMTP_HOST == "smtp.gmail.com" and settings.SMTP_PORT == 465:
                use_tls = True
                start_tls = False

            await aiosmtplib.send(
                message,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME,
                password=settings.SMTP_PASSWORD,
                use_tls=use_tls,
                start_tls=start_tls,
            )
            print(f"Email sent successfully via {self.provider} SMTP")
            return True
        except Exception as e:
            print(f"SMTP send failed: {e}")
            return False

    async def _send_via_sendgrid(self, data: dict) -> bool:
        """Send email via SendGrid API"""
        if not settings.SENDGRID_API_KEY:
            print("SendGrid API key not configured")
            return False

        import httpx

        message = self._create_email_message(data)

        # Convert to SendGrid format
        payload = {
            "personalizations": [{
                "to": [{"email": settings.TO_EMAIL}],
                "subject": message["Subject"]
            }],
            "from": {
                "email": settings.FROM_EMAIL,
                "name": settings.FROM_NAME
            },
            "content": [{
                "type": "text/html",
                "value": self._get_html_content(data)
            }],
            "reply_to": {
                "email": data.get("email", settings.FROM_EMAIL)
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {settings.SENDGRID_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0
                )
                if response.status_code in [200, 202]:
                    print("Email sent successfully via SendGrid")
                    return True
                else:
                    print(f"SendGrid error: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            print(f"SendGrid send failed: {e}")
            return False

    def _create_email_message(self, data: dict) -> MIMEMultipart:
        """Create email message"""
        message = MIMEMultipart("alternative")
        message["Subject"] = f"New Inquiry: {get_service_label(data.get('service', ''))} from {data.get('name', 'Unknown')}"
        message["From"] = f"{settings.FROM_NAME} <{settings.FROM_EMAIL}>"
        message["To"] = settings.TO_EMAIL
        message["Reply-To"] = data.get("email", settings.FROM_EMAIL)

        # Add both plain text and HTML versions
        text_content = self._get_text_content(data)
        html_content = self._get_html_content(data)

        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        return message

    def _get_text_content(self, data: dict) -> str:
        """Generate plain text email content"""
        return f"""
New Project Inquiry - A2M Digital Solutions
=============================================

From: {data.get('name', 'N/A')} ({data.get('email', 'N/A')})
Phone: {data.get('phone', 'Not provided')}
Service: {get_service_label(data.get('service', ''))}
Budget: {get_budget_label(data.get('budget'))}
Timeline: {get_timeline_label(data.get('timeline'))}

Project Details:
{data.get('message', 'No details provided')}

---
Reply directly to this email to respond to the client.
        """.strip()

    def _get_html_content(self, data: dict) -> str:
        """Generate HTML email content"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #334155; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #2563eb, #06b6d4); padding: 30px; border-radius: 12px 12px 0 0;">
        <h1 style="color: white; margin: 0; font-size: 24px;">📩 New Project Inquiry</h1>
        <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0;">A2M Digital Solutions</p>
    </div>

    <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0; border-top: none;">
        <div style="background: white; padding: 24px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 20px; color: #0f172a; font-size: 18px;">Client Information</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600; width: 120px;">Name:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{data.get('name', 'N/A')}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600;">Email:</td>
                    <td style="padding: 8px 0;"><a href="mailto:{data.get('email', '')}" style="color: #2563eb; text-decoration: none;">{data.get('email', 'N/A')}</a></td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600;">Phone:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{data.get('phone', 'Not provided')}</td>
                </tr>
            </table>
        </div>

        <div style="background: white; padding: 24px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 20px; color: #0f172a; font-size: 18px;">Project Details</h2>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600; width: 120px;">Service:</td>
                    <td style="padding: 8px 0; color: #0f172a;">
                        <span style="background: #dbeafe; color: #1d4ed8; padding: 4px 12px; border-radius: 20px; font-size: 14px; font-weight: 500;">
                            {get_service_label(data.get('service', ''))}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600;">Budget:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{get_budget_label(data.get('budget'))}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 0; color: #64748b; font-weight: 600;">Timeline:</td>
                    <td style="padding: 8px 0; color: #0f172a;">{get_timeline_label(data.get('timeline'))}</td>
                </tr>
            </table>
        </div>

        <div style="background: white; padding: 24px; border-radius: 8px; border: 1px solid #e2e8f0;">
            <h2 style="margin: 0 0 16px; color: #0f172a; font-size: 18px;">Project Description</h2>
            <div style="background: #f8fafc; padding: 16px; border-radius: 6px; border-left: 4px solid #2563eb; white-space: pre-wrap; color: #334155;">{data.get('message', 'No details provided')}</div>
        </div>

        <div style="margin-top: 24px; padding-top: 20px; border-top: 1px solid #e2e8f0; text-align: center;">
            <p style="margin: 0; color: #64748b; font-size: 14px;">
                Reply directly to this email to respond to <strong>{data.get('name', 'the client')}</strong>
            </p>
        </div>
    </div>

    <div style="text-align: center; margin-top: 20px; color: #94a3b8; font-size: 12px;">
        <p>A2M Digital Solutions - Automated Inquiry Notification</p>
    </div>
</body>
</html>
        """.strip()


# Singleton instance
email_service = EmailService()


async def send_inquiry_email(inquiry_data: dict) -> bool:
    """Convenience function to send inquiry email"""
    return await email_service.send_inquiry_notification(inquiry_data)