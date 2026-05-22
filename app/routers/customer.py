from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.schemas import CustomerImportResponse
from app.services.excel_service import normalize_customer_excel


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/normalize-excel", response_model=CustomerImportResponse)
async def normalize_excel(
    file: UploadFile = File(...),
    limit: int = Query(default=200, ge=1, le=1000),
    settings: Settings = Depends(get_settings),
):
    """
    Normaliza uma planilha de clientes para um contrato unico.

    O endpoint nao grava dados: ele retorna uma pre-visualizacao normalizada
    para que outro sistema valide e decida como importar.
    """
    return await normalize_customer_excel(file, settings, limit=limit)
