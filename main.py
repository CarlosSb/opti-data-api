from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.image import router as image_router

app = FastAPI(
    title="OptiProcess API",
    description="API inteligente para processos de receitas medicas, otimizações de imagens e normalização de dados importados em excel.",
    version="1.0.0",
    contact={
        "name": "Antonio Carlos",
        "email": "antoniocarlossbcdd@gmail.com",
    }
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,)

app.include_router(image_router, prefix="/api/image", tags=["Imagens"])
# app.include_router(customer_router, prefix="/api/customers", tags=["Clientes"])

@app.get("/")
async def root():
    return {
        "message": "Bem-vindo à API OptiProcess!",
        "description": [
            "Processamento de imagens de receitas (OCR + LLM)",
            "Upload e mormalização de dados em Excel",
        ]
    }  


