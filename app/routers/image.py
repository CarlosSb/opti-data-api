from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional

import easyocr
import PIL.Image as Image
from openai import OpenAI
import os
import io
from dotenv import load_dotenv
import base64

load_dotenv()

router = APIRouter()

client  = OpenAI(api_key = os.getenv("OPENAI_API_KEY")) 

class ImageProcessResponse(BaseModel):
    text:str
    source: str # ocr ou llm
    confidence: float
    message:str

@router.post("/process-image", response_model=ImageProcessResponse)
async def process_image(file: UploadFile = File(...)):

    """
    Recebe image de receita médica oftomologica:
    - Tenta OCR primeiro usando o EasyOCR
    - Se OCR falhar ou tiver baixa confiança, tenta LLM usando OpenAI
    """

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, defail="Arquivo deve ser uma imagem")
    
    # aqui ler a imagem
    contents = await file.read()
    imagem  = Image.open(io.BytesIO(contents))

    try:

        # passo 1: Tenta usando OCR diretamente
        reader = easyocr.Reader(['pt', 'en'], gpu=False)
        
        # Usamos detail=1 e paragraph=False para garantir formato consistente (3 valores)
        ocr_result = reader.readtext(contents, detail=1, paragraph=False)
        
        if not ocr_result:
            extracted_text = ""
            avg_confidence = 0.0
        else:
            # Tratamento seguro para diferentes formatos de retorno
            texts = []
            confidences = []
            
            for item in ocr_result:
                if len(item) == 3:                    # formato normal: (bbox, text, conf)
                    bbox, text, conf = item
                    texts.append(text)
                    confidences.append(conf)
                elif len(item) == 2:                  # formato com paragraph=True ou variante
                    bbox, text = item
                    texts.append(text)
                    confidences.append(0.5)           # confiança média quando não vem
            
            extracted_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        print("confiança ocr", avg_confidence)

        # Se o OCR for razoavelmente bom, retorna direto
        if avg_confidence > 0.75 and len(extracted_text.strip()) > 15:
            return ImageProcessResponse(
                text=extracted_text.strip(),
                source="ocr",
                confidence=round(avg_confidence, 3),
                message="Texto extraído com sucesso usando OCR"
            )

        # passo 2= se o OCR padrao falar ou a confiança for baixa, usar LLM com visão
        if not os.getenv("OPENAI_API_KEY"):
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY não configurada")

        # Converte imagem para base64
        base64_image = base64.b64encode(contents).decode('utf-8')

        response = client.chat.completions.create(
            model=os.getenv("OPEMAI_MODEL"),        
            messages=[
                {
                    "role": "system",
                    "content": """Você é um especialista em leitura de receitas médicas de óticas.
                    Extraia todas as informações de forma clara e organizada:
                    - Nome do paciente
                    - Nome do médico / CRM
                    - Data
                    - Olho Direito (OD): Esférico, Cilíndrico, Eixo, Adição
                    - Olho Esquerdo (OE): Esférico, Cilíndrico, Eixo, Adição
                    - Qualquer observação importante"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Por favor, leia esta receita médica com máxima precisão:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=600,
            temperature=0.0
        )

        llm_text = response.choices[0].message.content.strip()

        return ImageProcessResponse(
            text=llm_text,
            source="llm",
            confidence=0.92,
            message="Texto extraído usando LLM com visão (OCR não foi suficiente)"
        )

    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Erro ao processar a imagem: {str(error)}")