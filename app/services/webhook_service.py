from __future__ import annotations

import hashlib
import hmac
import logging
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.schemas import JobRecord, JobStatus, JobWebhookEvent
from app.services.job_service import utc_now


logger = logging.getLogger("optiprocess.webhook")


def build_job_event(job: JobRecord) -> JobWebhookEvent:
    event_name = "optiprocess.job.completed" if job.status == JobStatus.completed else "optiprocess.job.failed"
    return JobWebhookEvent(
        event=event_name,
        event_id=str(uuid4()),
        occurred_at=utc_now(),
        job_id=job.job_id,
        type=job.type,
        status=job.status,
        tenant_id=job.tenant_id,
        correlation_id=job.correlation_id,
        data={
            "result": job.result,
            "error": job.error,
        },
    )


async def dispatch_job_webhook(job: JobRecord, settings: Settings) -> None:
    if not job.callback_url:
        logger.info("Webhook ignorado | job_id=%s | motivo=sem_callback", job.job_id)
        return

    event = build_job_event(job)
    payload = event.model_dump_json()
    timestamp = str(int(event.occurred_at.timestamp()))
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event.event,
        "X-Webhook-Event-Id": event.event_id,
        "X-Webhook-Timestamp": timestamp,
    }

    if settings.webhook_signing_secret:
        headers["X-Webhook-Signature"] = sign_payload(payload, timestamp, settings.webhook_signing_secret)

    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        logger.info(
            "Webhook enviando | job_id=%s | evento=%s | destino=%s",
            job.job_id,
            event.event,
            job.callback_url,
        )
        response = await client.post(job.callback_url, content=payload, headers=headers)
        response.raise_for_status()
        logger.info(
            "Webhook entregue | job_id=%s | evento=%s | status=%s",
            job.job_id,
            event.event,
            response.status_code,
        )


def sign_payload(payload: str, timestamp: str, secret: str) -> str:
    normalized_secret = normalize_webhook_secret(secret)
    signed_payload = f"{timestamp}.{payload}".encode("utf-8")
    digest = hmac.new(normalized_secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def normalize_webhook_secret(secret: str) -> str:
    normalized = secret.strip()
    if (normalized.startswith('"') and normalized.endswith('"')) or (
        normalized.startswith("'") and normalized.endswith("'")
    ):
        normalized = normalized[1:-1].strip()
    return normalized
