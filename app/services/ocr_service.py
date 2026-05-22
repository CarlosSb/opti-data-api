from __future__ import annotations

import base64
import io
import re
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.schemas import ImageProcessResponse, ImageSource, PrescriptionData, PrescriptionEyeData


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}


@lru_cache(maxsize=1)
def get_ocr_reader() -> Any:
    import easyocr

    return easyocr.Reader(["pt", "en"], gpu=False)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_eye_data(text: str, marker: str) -> PrescriptionEyeData:
    aliases = {
        "spherical": r"(?:esf(?:erico)?|sph|sférico)",
        "cylindrical": r"(?:cil(?:indrico)?|cyl|cilíndrico)",
        "axis": r"(?:eixo|axis|ax)",
        "addition": r"(?:adi[cç][aã]o|add|ad)",
    }
    result: dict[str, str] = {}
    marker_pattern = rf"(?:{marker}|olho\s+{marker})"
    segment_match = re.search(
        rf"{marker_pattern}(.{{0,180}}?)(?:\b(?:od|oe|olho direito|olho esquerdo)\b|$)",
        text,
        re.IGNORECASE,
    )
    segment = segment_match.group(1) if segment_match else text

    for field, alias in aliases.items():
        match = re.search(rf"{alias}\s*[:=]?\s*([+-]?\d+(?:[,.]\d+)?|\d{{1,3}})", segment, re.IGNORECASE)
        if match:
            result[field] = match.group(1).replace(",", ".")

    return PrescriptionEyeData(**result)


def parse_prescription_text(text: str) -> PrescriptionData:
    normalized = _clean_text(text)
    crm_match = re.search(r"\bCRM\s*[:\-]?\s*([A-Z]{0,2}\s*\d{3,8})\b", normalized, re.IGNORECASE)
    date_match = re.search(r"\b(\d{2}[/-]\d{2}[/-]\d{2,4})\b", normalized)
    patient_match = re.search(
        r"(?:paciente|nome)\s*[:\-]\s*([A-Za-zÀ-ÿ\s]{3,80})(?=\s+(?:dr\.?|dra\.?|m[eé]dico|crm|data|od|oe|olho)|$)",
        normalized,
        re.IGNORECASE,
    )
    doctor_match = re.search(
        r"(?:m[eé]dico|dr\.?|dra\.?)\s*[:\-]?\s*([A-Za-zÀ-ÿ\s]{3,80})(?=\s+(?:crm|data|od|oe|olho)|$)",
        normalized,
        re.IGNORECASE,
    )

    notes: list[str] = []
    if "progressiv" in normalized.lower():
        notes.append("Lente progressiva mencionada")
    if "longe" in normalized.lower() or "perto" in normalized.lower():
        notes.append("Receita menciona grau para longe/perto")

    return PrescriptionData(
        patient_name=_clean_text(patient_match.group(1)) if patient_match else None,
        doctor_name=_clean_text(doctor_match.group(1)) if doctor_match else None,
        crm=_clean_text(crm_match.group(1)) if crm_match else None,
        date=date_match.group(1) if date_match else None,
        right_eye=_extract_eye_data(normalized, "od|olho direito"),
        left_eye=_extract_eye_data(normalized, "oe|olho esquerdo"),
        notes=notes,
    )


async def read_image_upload(file: UploadFile, settings: Settings) -> tuple[bytes, Image.Image]:
    if not file.content_type or file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Arquivo deve ser uma imagem valida")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo de imagem vazio")

    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Imagem excede o limite de {settings.max_upload_mb}MB")

    try:
        image = Image.open(io.BytesIO(contents)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Nao foi possivel ler a imagem enviada") from exc

    return contents, image


def run_easyocr(image: Image.Image) -> tuple[str, float]:
    import numpy as np

    image_array = np.array(image)
    ocr_result = get_ocr_reader().readtext(image_array, detail=1, paragraph=False)

    texts: list[str] = []
    confidences: list[float] = []
    for item in ocr_result:
        if len(item) == 3:
            _, text, confidence = item
            texts.append(str(text))
            confidences.append(float(confidence))
        elif len(item) == 2:
            _, text = item
            texts.append(str(text))
            confidences.append(0.5)

    extracted_text = _clean_text(" ".join(texts))
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return extracted_text, avg_confidence


def run_openai_vision(contents: bytes, content_type: str, settings: Settings) -> str:
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY nao configurada")

    from openai import OpenAI

    base64_image = base64.b64encode(contents).decode("utf-8")
    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Voce e um especialista em leitura de receitas oftalmologicas. "
                    "Extraia as informacoes com clareza: paciente, medico, CRM, data, "
                    "OD/olho direito, OE/olho esquerdo, esferico, cilindrico, eixo, adicao e observacoes."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Leia esta receita medica com maxima precisao."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{base64_image}"},
                    },
                ],
            },
        ],
        max_tokens=700,
        temperature=0.0,
    )

    return (response.choices[0].message.content or "").strip()


async def process_prescription_image(file: UploadFile, settings: Settings) -> ImageProcessResponse:
    contents, image = await read_image_upload(file, settings)
    text, confidence = run_easyocr(image)

    if confidence >= settings.ocr_min_confidence and len(text) >= settings.ocr_min_text_length:
        return ImageProcessResponse(
            text=text,
            source=ImageSource.ocr,
            confidence=round(confidence, 3),
            message="Texto extraido com sucesso usando OCR",
            prescription=parse_prescription_text(text),
        )

    llm_text = run_openai_vision(contents, file.content_type or "image/jpeg", settings)
    return ImageProcessResponse(
        text=llm_text,
        source=ImageSource.llm,
        confidence=0.92,
        message="Texto extraido usando LLM com visao; OCR local teve baixa confianca",
        prescription=parse_prescription_text(llm_text),
    )
