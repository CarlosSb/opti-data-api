from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from thefuzz import process

from app.core.config import Settings
from app.schemas import CustomerImportResponse, CustomerImportSummary, NormalizedCustomer


EXPECTED_COLUMNS = {
    "name": ["nome", "cliente", "paciente", "nome completo", "razao social"],
    "phone": ["telefone", "celular", "whatsapp", "fone", "contato"],
    "email": ["email", "e-mail", "mail"],
    "cpf": ["cpf", "documento", "cpf/cnpj", "cnpj"],
    "birth_date": ["nascimento", "data nascimento", "data de nascimento", "aniversario"],
    "address": ["endereco", "endereço", "logradouro", "rua"],
    "neighborhood": ["bairro"],
    "city": ["cidade", "municipio", "município"],
    "state": ["estado", "uf"],
    "zip_code": ["cep", "codigo postal", "código postal"],
}


def _normalize_label(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[_\-]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value


def _clean_optional(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _digits(value: Any) -> str | None:
    cleaned = _clean_optional(value)
    if not cleaned:
        return None
    digits = re.sub(r"\D+", "", cleaned)
    return digits or None


def map_columns(columns: list[str]) -> dict[str, str]:
    normalized_lookup = {_normalize_label(column): column for column in columns}
    candidates = list(normalized_lookup.keys())
    mapped: dict[str, str] = {}

    for target, aliases in EXPECTED_COLUMNS.items():
        best_alias = None
        best_score = 0
        for alias in aliases:
            match = process.extractOne(alias, candidates)
            if match and match[1] > best_score:
                best_alias = match[0]
                best_score = match[1]

        if best_alias and best_score >= 82:
            mapped[target] = normalized_lookup[best_alias]

    return mapped


def _normalize_row(row: pd.Series, mapped_columns: dict[str, str]) -> NormalizedCustomer:
    def value(field: str) -> Any:
        column = mapped_columns.get(field)
        return row.get(column) if column else None

    raw = {str(column): _clean_optional(row.get(column)) for column in row.index}
    return NormalizedCustomer(
        name=_clean_optional(value("name")),
        phone=_digits(value("phone")),
        email=_clean_optional(value("email")),
        cpf=_digits(value("cpf")),
        birth_date=_clean_optional(value("birth_date")),
        address=_clean_optional(value("address")),
        neighborhood=_clean_optional(value("neighborhood")),
        city=_clean_optional(value("city")),
        state=_clean_optional(value("state")),
        zip_code=_digits(value("zip_code")),
        raw=raw,
    )


async def normalize_customer_excel(file: UploadFile, settings: Settings, limit: int = 200) -> CustomerImportResponse:
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="Envie uma planilha .xlsx, .xls ou .csv")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Arquivo vazio")

    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"Arquivo excede o limite de {settings.max_upload_mb}MB")

    try:
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(BytesIO(contents))
        else:
            df = pd.read_excel(BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Nao foi possivel ler a planilha enviada") from exc

    df = df.dropna(how="all")
    columns = [str(column) for column in df.columns]
    mapped_columns = map_columns(columns)
    warnings: list[str] = []

    if "name" not in mapped_columns:
        warnings.append("Coluna de nome nao identificada; revise o mapeamento antes de importar.")
    if "phone" not in mapped_columns and "email" not in mapped_columns:
        warnings.append("Nenhuma coluna de contato foi identificada.")

    customers: list[NormalizedCustomer] = []
    skipped_rows = 0
    for _, row in df.head(limit).iterrows():
        customer = _normalize_row(row, mapped_columns)
        if not any([customer.name, customer.phone, customer.email, customer.cpf]):
            skipped_rows += 1
            continue
        customers.append(customer)

    if len(df) > limit:
        warnings.append(f"Retorno limitado aos primeiros {limit} registros para pre-visualizacao.")

    summary = CustomerImportSummary(
        total_rows=len(df),
        imported_rows=len(customers),
        skipped_rows=skipped_rows,
        columns=columns,
        mapped_columns=mapped_columns,
        warnings=warnings,
    )
    return CustomerImportResponse(summary=summary, customers=customers)
