"""
Custom email backend for Resend API
"""
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail import EmailMessage


class ResendEmailBackend(BaseEmailBackend):
    """
    Email backend that uses Resend API instead of SMTP
    """

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', None)
        if not self.api_key:
            raise ValueError("RESEND_API_KEY must be set in settings")

    def send_messages(self, email_messages):
        """
        Send one or more EmailMessage objects and return the number of emails sent.
        """
        if not email_messages:
            return 0

        num_sent = 0
        for message in email_messages:
            if self._send(message):
                num_sent += 1
        return num_sent

    def _send(self, email_message):
        """Send a single email message using Resend API"""
        try:
            # Build the email data for Resend API
            from_email = email_message.from_email or settings.DEFAULT_FROM_EMAIL

            # Extract email address from "Name <email@example.com>" format
            if '<' in from_email and '>' in from_email:
                from_email = from_email.split('<')[1].split('>')[0].strip()

            data = {
                'from': from_email,
                'to': email_message.to,
                'subject': email_message.subject,
            }

            # Add CC and BCC if present
            if email_message.cc:
                data['cc'] = email_message.cc
            if email_message.bcc:
                data['bcc'] = email_message.bcc

            # Add body (HTML or plain text)
            if email_message.content_subtype == 'html':
                data['html'] = email_message.body
            else:
                data['text'] = email_message.body

            # Send the email via Resend API
            response = requests.post(
                'https://api.resend.com/emails',
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                },
                json=data,
                timeout=10,
            )

            if response.status_code in (200, 201):
                print(f"✅ Email sent via Resend to {email_message.to}")
                return True
            else:
                error_msg = f"Resend API error: {response.status_code} - {response.text}"
                print(f"⚠️ {error_msg}")
                if not self.fail_silently:
                    raise Exception(error_msg)
                return False

        except Exception as e:
            print(f"⚠️ Failed to send email via Resend: {str(e)}")
            if not self.fail_silently:
                raise
            return False
