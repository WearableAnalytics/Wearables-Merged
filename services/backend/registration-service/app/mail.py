import asyncio
import logging
import secrets
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmailService:

    @staticmethod
    def create_registration_mail(
            token_id: str,
            appointment_date: datetime,
    ) -> str:

        formatted_date = f"{appointment_date}"

        logger.debug(
            f"Creating registration email - Token: {token_id[:8]}..., "
            f"Date: {formatted_date}"
        )

        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    padding: 20px;
                }}
            </style>
        </head>
        <body>
            <p>&lt;TOKEN&gt;<br>
            {token_id}</p>
            <p>Appointment: {formatted_date}</p>
        </body>
        </html>"""

        return html_content

    @staticmethod
    async def send_registration_mail(
            receiver_mail: str,
            token_id: str,
            appointment_date: datetime,
            max_retries: int = 3,
    ) -> bool:
        logger.info(
            f"Attempting to send registration email - "
            f"Recipient: {receiver_mail}, "
            f"Token: {token_id[:8]}..., "
            f"Appointment: {appointment_date}"
        )

        for attempt in range(1, max_retries + 1):
            try:

                settings = get_settings()
                if not all([settings.smtp_host, settings.smtp_port,
                            settings.sender_email, settings.app_password]):
                    logger.error("Email configuration incomplete - missing SMTP settings")
                    return False


                html_content = EmailService.create_registration_mail(
                    token_id, appointment_date
                )


                message = MIMEMultipart("alternative")
                message["Subject"] = (
                    f"Registration Token - Appointment on "
                    f"{appointment_date}"
                )
                message["From"] = formataddr(("Event Registration", settings.sender_email))
                message["To"] = receiver_mail

                txt = MIMEText(html_content, "html")
                message.attach(txt)

                logger.debug(
                    f"Sending email via SMTP - "
                    f"Host: {settings.smtp_host}:{settings.smtp_port}, "
                    f"Attempt: {attempt}/{max_retries}"
                )


                await asyncio.get_event_loop().run_in_executor(
                    None,
                    EmailService._send_smtp_email,
                    message,
                    receiver_mail,
                )

                logger.info(
                    f"✓ Email sent successfully - "
                    f"Recipient: {receiver_mail}, "
                    f"Token: {token_id[:8]}..., "
                    f"Attempt: {attempt}"
                )
                return True

            except smtplib.SMTPAuthenticationError as e:
                logger.error(
                    f"SMTP authentication failed - "
                    f"Host: {get_settings().smtp_host}, "
                    f"From: {get_settings().sender_email}, "
                    f"Error: {str(e)}"
                )
                return False

            except smtplib.SMTPRecipientsRefused as e:
                logger.error(
                    f"Recipient rejected - "
                    f"Recipient: {receiver_mail}, "
                    f"Error: {str(e)}"
                )
                return False

            except smtplib.SMTPException as e:
                logger.warning(
                    f"SMTP error on attempt {attempt}/{max_retries} - "
                    f"Recipient: {receiver_mail}, "
                    f"Error: {str(e)}"
                )
                if attempt == max_retries:
                    logger.error(
                        f"✗ Failed to send email after {max_retries} attempts - "
                        f"Recipient: {receiver_mail}, "
                        f"Token: {token_id[:8]}..."
                    )
                    return False
                await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(
                    f"Unexpected error sending email - "
                    f"Recipient: {receiver_mail}, "
                    f"Token: {token_id[:8]}..., "
                    f"Attempt: {attempt}/{max_retries}, "
                    f"Error type: {type(e).__name__}, "
                    f"Error: {str(e)}",
                    exc_info=True
                )
                if attempt == max_retries:
                    return False
                await asyncio.sleep(2 ** attempt)

        return False

    @staticmethod
    def _send_smtp_email(
            message: MIMEMultipart,
            receiver_mail: str,
    ):
        settings = get_settings()

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            logger.debug(f"Connected to SMTP server: {settings.smtp_host}:{settings.smtp_port}")

            server.starttls()
            logger.debug("TLS handshake completed")

            server.login(settings.sender_email, settings.app_password)
            logger.debug(f"SMTP authentication successful for {settings.sender_email}")

            server.sendmail(settings.sender_email, receiver_mail, message.as_string())
            logger.debug(f"Message transmitted to {receiver_mail}")


def configure_logging(log_level: str = "INFO", log_file: Optional[str] = None):
    handlers = [logging.StreamHandler()]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    logger.info(f"Logging configured - Level: {log_level}, File: {log_file or 'console only'}")