from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers.customer import router as customer_router
from app.routers.image import router as image_router
from app.schemas import HealthResponse

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    contact={
        "name": "Antonio Carlos",
        "email": "antoniocarlossbcdd@gmail.com",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials="*" not in settings.cors_origins,
)

app.include_router(image_router, prefix="/api/image", tags=["Imagens"])
app.include_router(customer_router, prefix="/api/customers", tags=["Clientes"])


@app.get("/")
async def root():
    return {
        "message": "Bem-vindo à API OptiProcess!",
        "description": [
            "Processamento de imagens de receitas (OCR + LLM)",
            "Otimizacao de imagens",
            "Exportacao SVG a partir de imagem, texto ou OCR",
        ]
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", name=settings.app_name, version=settings.app_version)
