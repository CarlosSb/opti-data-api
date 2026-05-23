from __future__ import annotations

import base64
import io
import logging
import re
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import Settings
from app.schemas import ImageProcessResponse, ImageSource, PrescriptionData, PrescriptionEyeData


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff"}
logger = logging.getLogger("optiprocess.ocr")


@lru_cache(maxsize=1)
def get_ocr_reader() -> Any:
    import easyocr

    return easyocr.Reader(["pt", "en"], gpu=False)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_eye_data(text: str, marker: str) -> PrescriptionEyeData:
    aliases = {
        "spherical": r"(?:esf[eé]rico|esf|sphere|sph|sphera|sférico)",
        "cylindrical": r"(?:cil[ií]ndrico|cil|cyl)",
        "axis": r"(?:eixo|axis|ax)",
        "addition": r"(?:adi[cç][aã]o|add|ad)",
        "dnp": r"(?:dnp|dp|dist[aâ]ncia\s+naso\s+pupilar|dist[aâ]ncia\s+pupilar)",
        "height": r"(?:altura|alt)",
    }
    result: dict[str, str | float | int] = {}

    if marker == "right":
        marker_pattern = r"(?:\bOD\b|\bolho\s+direito\b)"
        next_eye_pattern = r"(?:\bOE\b|\bolho\s+esquerdo\b)"
    elif marker == "left":
        marker_pattern = r"(?:\bOE\b|\bolho\s+esquerdo\b)"
        next_eye_pattern = r"(?:\bOD\b|\bolho\s+direito\b)"
    else:
        marker_pattern = rf"(?:{marker})"
        next_eye_pattern = r"(?:\bOD\b|\bOE\b|\bolho\s+direito\b|\bolho\s+esquerdo\b)"

    segment_match = re.search(rf"{marker_pattern}(.{{0,280}}?)(?={next_eye_pattern}|$)", text, re.IGNORECASE)
    segment = segment_match.group(1) if segment_match else text

    for field, alias in aliases.items():
        match = re.search(rf"{alias}\s*[:=]?\s*([+-]?\d+(?:[,.]\d+)?|\d{{1,3}})", segment, re.IGNORECASE)
        if match:
            raw_value = match.group(1).replace(",", ".")
            result[field] = raw_value

            if field in {"spherical", "cylindrical", "addition", "dnp", "height"}:
                parsed = _parse_decimal(raw_value)
                if parsed is not None:
                    result[f"{field}_value"] = parsed
            if field == "axis":
                parsed_axis = _parse_axis(raw_value)
                if parsed_axis is not None:
                    result["axis_value"] = parsed_axis

    return PrescriptionEyeData(**result)


def _parse_decimal(value: str) -> float | None:
    try:
        return round(float(value.replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


def _parse_axis(value: str) -> int | None:
    try:
        parsed = int(round(float(value.replace(",", "."))))
    except (TypeError, ValueError):
        return None
    return parsed


def _validate_eye_data(label: str, eye: PrescriptionEyeData) -> list[str]:
    issues: list[str] = []
    if eye.spherical_value is not None and not -30 <= eye.spherical_value <= 30:
        issues.append(f"{label}.spherical fora da faixa esperada")
    if eye.cylindrical_value is not None and not -15 <= eye.cylindrical_value <= 15:
        issues.append(f"{label}.cylindrical fora da faixa esperada")
    if eye.axis_value is not None and not 0 <= eye.axis_value <= 180:
        issues.append(f"{label}.axis fora da faixa esperada")
    if eye.addition_value is not None and not 0 <= eye.addition_value <= 6:
        issues.append(f"{label}.addition fora da faixa esperada")
    if eye.dnp_value is not None and not 15 <= eye.dnp_value <= 45:
        issues.append(f"{label}.dnp fora da faixa esperada")
    if eye.height_value is not None and not 5 <= eye.height_value <= 45:
        issues.append(f"{label}.height fora da faixa esperada")
    return issues


def _extract_optional_field(text: str, alias: str, max_chars: int = 80) -> str | None:
    next_label = (
        r"(?=\s+(?:curva\s+base|base\s+curve|bc|di[aâ]metro|diameter|dia|descarte|troca|replacement|"
        r"quantidade|qtde|qtd|quantity|olho\s+dominante|dominant\s+eye|OD\b|OE\b|observa[cç][oõ]es)|$)"
    )
    match = re.search(
        rf"{alias}\s*[:=]?\s*([A-Za-zÀ-ÿ0-9.,/+ -]{{1,{max_chars}}}?){next_label}",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = _clean_text(match.group(1)).strip(" -,:;")
    return value or None


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

    right_eye = _extract_eye_data(normalized, "right")
    left_eye = _extract_eye_data(normalized, "left")
    contact_lens_base_curve = _extract_optional_field(normalized, r"(?:curva\s+base|base\s+curve|bc)")
    contact_lens_diameter = _extract_optional_field(normalized, r"(?:di[aâ]metro|diameter|dia)")
    contact_lens_replacement = _extract_optional_field(normalized, r"(?:descarte|troca|replacement)")
    contact_lens_quantity = _extract_optional_field(normalized, r"(?:quantidade|qtde|qtd|quantity)")
    contact_lens_dominant_eye = _extract_optional_field(normalized, r"(?:olho\s+dominante|dominant\s+eye)")
    validation_issues = [
        *_validate_eye_data("right_eye", right_eye),
        *_validate_eye_data("left_eye", left_eye),
    ]

    return PrescriptionData(
        patient_name=_clean_text(patient_match.group(1)) if patient_match else None,
        doctor_name=_clean_text(doctor_match.group(1)) if doctor_match else None,
        crm=_clean_text(crm_match.group(1)) if crm_match else None,
        date=date_match.group(1) if date_match else None,
        right_eye=right_eye,
        left_eye=left_eye,
        contact_lens_base_curve=contact_lens_base_curve,
        contact_lens_diameter=contact_lens_diameter,
        contact_lens_replacement=contact_lens_replacement,
        contact_lens_quantity=contact_lens_quantity,
        contact_lens_dominant_eye=contact_lens_dominant_eye,
        notes=notes,
        validation_issues=validation_issues,
    )


def _native_ocr_data(prescription: PrescriptionData) -> dict[str, str]:
    def value(raw: str | int | float | None) -> str:
        return "" if raw is None else str(raw).strip()

    return {
        "od_esferico": value(prescription.right_eye.spherical),
        "od_cilindrico": value(prescription.right_eye.cylindrical),
        "od_eixo": value(prescription.right_eye.axis),
        "od_adicao": value(prescription.right_eye.addition),
        "od_dnp": value(prescription.right_eye.dnp),
        "od_altura": value(prescription.right_eye.height),
        "oe_esferico": value(prescription.left_eye.spherical),
        "oe_cilindrico": value(prescription.left_eye.cylindrical),
        "oe_eixo": value(prescription.left_eye.axis),
        "oe_adicao": value(prescription.left_eye.addition),
        "oe_dnp": value(prescription.left_eye.dnp),
        "oe_altura": value(prescription.left_eye.height),
        "lenteContatoCurvaBase": value(prescription.contact_lens_base_curve),
        "lenteContatoDiametro": value(prescription.contact_lens_diameter),
        "lenteContatoDescarte": value(prescription.contact_lens_replacement),
        "lenteContatoQuantidade": value(prescription.contact_lens_quantity),
        "lenteContatoOlhoDominante": value(prescription.contact_lens_dominant_eye),
        "medico": value(prescription.doctor_name),
        "crm": value(prescription.crm),
    }


def _filled_fields_count(extracted_data: dict[str, str]) -> int:
    return sum(1 for value in extracted_data.values() if value)


def estimate_field_confidence(prescription: PrescriptionData, source: ImageSource, base_confidence: float) -> dict[str, float]:
    source_weight = 0.95 if source == ImageSource.llm else max(0.4, min(base_confidence, 0.95))

    fields = {
        "patient_name": prescription.patient_name,
        "doctor_name": prescription.doctor_name,
        "crm": prescription.crm,
        "date": prescription.date,
        "right_eye.spherical": prescription.right_eye.spherical,
        "right_eye.cylindrical": prescription.right_eye.cylindrical,
        "right_eye.axis": prescription.right_eye.axis,
        "right_eye.addition": prescription.right_eye.addition,
        "right_eye.dnp": prescription.right_eye.dnp,
        "right_eye.height": prescription.right_eye.height,
        "left_eye.spherical": prescription.left_eye.spherical,
        "left_eye.cylindrical": prescription.left_eye.cylindrical,
        "left_eye.axis": prescription.left_eye.axis,
        "left_eye.addition": prescription.left_eye.addition,
        "left_eye.dnp": prescription.left_eye.dnp,
        "left_eye.height": prescription.left_eye.height,
        "contact_lens_base_curve": prescription.contact_lens_base_curve,
        "contact_lens_diameter": prescription.contact_lens_diameter,
        "contact_lens_replacement": prescription.contact_lens_replacement,
        "contact_lens_quantity": prescription.contact_lens_quantity,
        "contact_lens_dominant_eye": prescription.contact_lens_dominant_eye,
    }

    confidence: dict[str, float] = {}
    for field, value in fields.items():
        confidence[field] = round(source_weight if value else 0.0, 3)
    return confidence


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
    try:
        import easyocr  # noqa: F401
        import numpy as np
    except ImportError:
        return "", 0.0

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
                    "OD/olho direito, OE/olho esquerdo, esferico, cilindrico, eixo, adicao, "
                    "DNP/DP, altura, dados de lente de contato (curva base, diametro, descarte, "
                    "quantidade e olho dominante). Nao inclua observacoes gerais."
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
    logger.info(
        "OCR iniciado | arquivo=%s | content_type=%s",
        file.filename or "image",
        file.content_type or "unknown",
    )
    contents, image = await read_image_upload(file, settings)
    logger.info(
        "Imagem recebida | arquivo=%s | tamanho=%skb | dimensoes=%sx%s",
        file.filename or "image",
        round(len(contents) / 1024, 1),
        image.width,
        image.height,
    )

    text, confidence = run_easyocr(image)
    logger.info(
        "OCR local concluido | confianca=%.3f | caracteres=%s",
        confidence,
        len(text),
    )

    if confidence >= settings.ocr_min_confidence and len(text) >= settings.ocr_min_text_length:
        prescription = parse_prescription_text(text)
        extracted_data = _native_ocr_data(prescription)
        logger.info(
            "OCR finalizado via EasyOCR | campos=%s | confianca=%.3f",
            _filled_fields_count(extracted_data),
            confidence,
        )
        return ImageProcessResponse(
            text=text,
            source=ImageSource.ocr,
            confidence=round(confidence, 3),
            message="Texto extraido com sucesso usando OCR",
            prescription=prescription,
            extracted_data=extracted_data,
            field_confidence=estimate_field_confidence(prescription, ImageSource.ocr, confidence),
        )

    logger.info(
        "OCR local abaixo do limiar | usando IA visual | min_conf=%.2f | min_chars=%s",
        settings.ocr_min_confidence,
        settings.ocr_min_text_length,
    )
    llm_text = run_openai_vision(contents, file.content_type or "image/jpeg", settings)
    prescription = parse_prescription_text(llm_text)
    extracted_data = _native_ocr_data(prescription)
    logger.info(
        "OCR finalizado via IA visual | campos=%s | caracteres=%s | confianca=%.2f",
        _filled_fields_count(extracted_data),
        len(llm_text),
        0.92,
    )
    return ImageProcessResponse(
        text=llm_text,
        source=ImageSource.llm,
        confidence=0.92,
        message="Texto extraido usando LLM com visao; OCR local teve baixa confianca",
        prescription=prescription,
        extracted_data=extracted_data,
        field_confidence=estimate_field_confidence(prescription, ImageSource.llm, 0.92),
    )
