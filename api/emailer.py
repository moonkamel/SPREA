"""Transactional emails through Resend (https://resend.com).

Optional: without RESEND_API_KEY nothing is sent and the features that use
email (DPE alerts) stay available in the app. ALERTS_FROM is the sender,
e.g. "SPREA <alertes@mondomaine.fr>" (domain verified in Resend).
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


def email_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY", "").strip() and os.getenv("ALERTS_FROM", "").strip())


async def send_email(to: str, subject: str, html: str, text: str,
                     transport: Optional[httpx.AsyncBaseTransport] = None) -> bool:
    if not email_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            res = await client.post(RESEND_URL, headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY'].strip()}"},
                                    json={"from": os.environ["ALERTS_FROM"].strip(), "to": [to], "subject": subject,
                                          "html": html, "text": text})
        if res.status_code >= 300:
            logger.error(f"Resend error {res.status_code}: {res.text[:200]}")
            return False
        return True
    except httpx.HTTPError as e:
        logger.error(f"Resend call failed: {type(e).__name__}")
        return False
