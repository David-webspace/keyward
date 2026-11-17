"""寄通知信。收件人網域不在白名單就直接拒絕（示範環境只能寄到 .example，不會誤寄到真實信箱）。"""

import smtplib
from email.message import EmailMessage


class Mailer:
    def __init__(self, smtp_host: str | None, smtp_port: int, sender: str, allowed_suffix: str, web_base_url: str):
        self.smtp_host, self.smtp_port, self.sender = smtp_host, smtp_port, sender
        self.allowed_suffix, self.web_base_url = allowed_suffix, web_base_url

    def send(self, to: str, subject: str, body: str):
        if not to.lower().endswith(self.allowed_suffix):
            raise ValueError(f"收件人 {to} 不在允許的網域內")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        if self.smtp_host:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as s:
                s.send_message(msg)
