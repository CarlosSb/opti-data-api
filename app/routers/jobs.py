from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from starlette.datastructures import Headers

from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.schemas import JobAcceptedResponse, JobRecord
from app.services.job_service import create_job, get_job, list_jobs, mark_completed, mark_failed, mark_processing
from app.services.ocr_service import ALLOWED_IMAGE_TYPES, process_prescription_image
from app.services.webhook_service import dispatch_job_webhook


router = APIRouter(dependencies=[Depends(require_api_key)])
logger = logging.getLogger("optiprocess.jobs")


@router.post("/image-process", response_model=JobAcceptedResponse)
async def create_image_process_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    callback_url: str | None = Form(default=None),
    tenant_id: str | None = Form(default=None),
    correlation_id: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
):
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem valida")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio")
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Imagem excede o limite de {settings.max_upload_mb}MB")

    effective_callback_url = callback_url or settings.default_webhook_url

    job = create_job(
        job_type="image_process",
        callback_url=effective_callback_url,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
    )
    logger.info(
        "Job criado | job_id=%s | tipo=%s | tenant=%s | correlation=%s | callback=%s",
        job.job_id,
        job.type,
        tenant_id or "-",
        correlation_id or "-",
        "sim" if effective_callback_url else "nao",
    )
    background_tasks.add_task(
        run_image_process_job,
        job.job_id,
        file.filename or "image",
        file.content_type,
        contents,
        settings,
    )

    return JobAcceptedResponse(
        job_id=job.job_id,
        status=job.status,
        type=job.type,
        created_at=job.created_at,
        callback_url=job.callback_url,
    )


@router.get("", response_model=list[JobRecord])
async def get_jobs(limit: int = Query(default=50, ge=1, le=200)):
    return list_jobs(limit)


@router.get("/{job_id}", response_model=JobRecord)
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nao encontrado")
    return job


async def run_image_process_job(
    job_id: str,
    filename: str,
    content_type: str,
    contents: bytes,
    settings: Settings,
) -> None:
    logger.info("Job iniciado | job_id=%s | arquivo=%s | content_type=%s", job_id, filename, content_type)
    mark_processing(job_id)
    try:
        upload = InMemoryUploadFile(filename=filename, content_type=content_type, contents=contents)
        result = await process_prescription_image(upload, settings)  # type: ignore[arg-type]
        job = mark_completed(job_id, result.model_dump(mode="json"))
        logger.info(
            "Job concluido | job_id=%s | origem=%s | confianca=%.3f",
            job_id,
            result.source,
            result.confidence,
        )
    except Exception as error:
        job = mark_failed(job_id, str(getattr(error, "detail", error)))
        logger.exception("Job falhou | job_id=%s | erro=%s", job_id, getattr(error, "detail", error))

    if job:
        try:
            await dispatch_job_webhook(job, settings)
        except Exception:
            # O job ja foi concluido/falhou. Falha de webhook deve ser observada
            # em logs da plataforma e futuramente em uma fila de retry.
            logger.exception("Webhook do job falhou | job_id=%s", job_id)


class InMemoryUploadFile:
    def __init__(self, filename: str, content_type: str, contents: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file = BytesIO(contents)
        self.headers = Headers({"content-type": content_type})

    async def read(self, size: int = -1) -> bytes:
        return self.file.read(size)

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
