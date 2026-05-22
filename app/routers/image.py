from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.schemas import (
    BatchImageProcessResponse,
    BatchImageResult,
    ImageOptimizationResponse,
    ImageOutputFormat,
    ImagePreprocessMode,
    ImagePreprocessResponse,
    ImageProcessResponse,
    SvgExportMode,
    SvgExportResponse,
)
from app.services.image_service import optimize_image_upload, preprocess_image_upload
from app.services.ocr_service import parse_prescription_text, process_prescription_image, read_image_upload
from app.services.svg_service import build_embedded_image_svg, build_text_card_svg, build_vectorized_image_svg

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/process-image", response_model=ImageProcessResponse)
async def process_image(file: UploadFile = File(...), settings: Settings = Depends(get_settings)):

    """
    Recebe imagem de receita medica oftalmologica:
    - Tenta OCR primeiro usando o EasyOCR
    - Se OCR falhar ou tiver baixa confianca, tenta LLM usando OpenAI
    """
    return await process_prescription_image(file, settings)


@router.post("/optimize", response_model=ImageOptimizationResponse)
async def optimize_image(
    file: UploadFile = File(...),
    max_width: int = Query(default=1800, ge=320, le=6000),
    quality: int = Query(default=82, ge=40, le=95),
    output_format: ImageOutputFormat = Query(default=ImageOutputFormat.webp),
    settings: Settings = Depends(get_settings),
):
    """
    Normaliza uma imagem para uso posterior em OCR, IA, armazenamento ou preview.
    Retorna a imagem otimizada em base64, sem gravar arquivo.
    """
    return await optimize_image_upload(file, settings, max_width, quality, output_format)


@router.post("/preprocess", response_model=ImagePreprocessResponse)
async def preprocess_image(
    file: UploadFile = File(...),
    mode: ImagePreprocessMode = Query(default=ImagePreprocessMode.ocr),
    max_width: int = Query(default=1800, ge=320, le=6000),
    settings: Settings = Depends(get_settings),
):
    """
    Prepara a imagem para OCR/IA:
    - clean: remove ruido e melhora contraste.
    - ocr: binariza para leitura.
    - document: tenta corrigir inclinacao leve e melhorar contraste.
    """
    return await preprocess_image_upload(file, settings, mode, max_width)


@router.post("/batch/process-images", response_model=BatchImageProcessResponse)
async def batch_process_images(
    files: list[UploadFile] = File(...),
    max_files: int = Query(default=5, ge=1, le=20),
    settings: Settings = Depends(get_settings),
):
    """
    Processa varias imagens em lote, de forma sequencial e com limite explicito.
    """
    selected_files = files[:max_files]
    results: list[BatchImageResult] = []

    for file in selected_files:
        try:
            result = await process_prescription_image(file, settings)
            results.append(BatchImageResult(filename=file.filename or "image", ok=True, result=result))
        except HTTPException as error:
            results.append(BatchImageResult(filename=file.filename or "image", ok=False, error=str(error.detail)))
        except Exception as error:
            results.append(BatchImageResult(filename=file.filename or "image", ok=False, error=str(error)))

    succeeded = sum(1 for result in results if result.ok)
    return BatchImageProcessResponse(
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )


@router.post("/export-svg", response_model=SvgExportResponse)
async def export_svg(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    mode: SvgExportMode = Form(default=SvgExportMode.card),
    title: str = Form(default="Receita oftalmologica"),
    run_ocr: bool = Form(default=False),
    threshold: int = Form(default=180, ge=0, le=255),
    simplify: float = Form(default=0.01, ge=0.001, le=0.08),
    min_area: int = Form(default=24, ge=1, le=5000),
    max_paths: int = Form(default=600, ge=1, le=3000),
    settings: Settings = Depends(get_settings),
):
    """
    Exporta SVG em tres formatos:
    - embedded: SVG contendo a imagem original incorporada.
    - card: SVG textual limpo a partir de texto informado ou OCR/IA da imagem.
    - vector: SVG com contornos vetorizados da imagem.
    """
    if mode == SvgExportMode.embedded:
        if not file:
            raise HTTPException(status_code=400, detail="Envie uma imagem para exportar como SVG incorporado")

        contents, image = await read_image_upload(file, settings)
        filename = _svg_filename(file.filename, "image.svg")
        return build_embedded_image_svg(contents, image, file.content_type or "image/jpeg", filename)

    if mode == SvgExportMode.vector:
        if not file:
            raise HTTPException(status_code=400, detail="Envie uma imagem para vetorizar")

        _, image = await read_image_upload(file, settings)
        filename = _svg_filename(file.filename, "vector.svg")
        return build_vectorized_image_svg(image, filename, threshold, simplify, min_area, max_paths)

    source_text = text.strip() if text else ""
    prescription = parse_prescription_text(source_text) if source_text else None

    if run_ocr:
        if not file:
            raise HTTPException(status_code=400, detail="Envie uma imagem para gerar SVG com OCR/IA")
        processed = await process_prescription_image(file, settings)
        source_text = processed.text
        prescription = processed.prescription

    if not source_text:
        raise HTTPException(status_code=400, detail="Informe text ou envie file com run_ocr=true")

    filename = _svg_filename(file.filename if file else None, "ocr-card.svg")
    return build_text_card_svg(source_text, prescription, title=title, filename=filename)


def _svg_filename(filename: str | None, fallback: str) -> str:
    if not filename:
        return fallback
    base_name = filename.rsplit(".", 1)[0].strip() or fallback.rsplit(".", 1)[0]
    return f"{base_name}.svg"
