# OptiProcess API

API FastAPI independente e dedicada para processamento de imagens, OCR, IA visual e exportacao SVG.

## Funcionalidades

- `GET /health`: status simples da API.
- `POST /api/image/process-image`: recebe imagem de receita, tenta OCR local com EasyOCR e usa OpenAI Vision como fallback quando a confianca for baixa.
- `POST /api/image/optimize`: redimensiona e recomprime imagens para OCR, IA, storage ou preview.
- `POST /api/image/export-svg`: gera SVG incorporando a imagem original, criando um cartao SVG limpo a partir de texto/OCR/IA ou vetorizando contornos da imagem.
- `POST /api/customers/normalize-excel`: utilitario auxiliar legado para normalizar `.xlsx`, `.xls` ou `.csv`, sem gravar dados.

## Configuracao

Crie um `.env` a partir de `.env.example`.

```bash
cp .env.example .env
```

Variaveis principais:

- `OPENAI_API_KEY`: chave usada apenas quando o OCR local nao for suficiente.
- `OPENAI_MODEL`: modelo com visao usado no fallback.
- `CORS_ORIGINS`: origens liberadas, separadas por virgula. Use `*` apenas em desenvolvimento.
- `MAX_UPLOAD_MB`: limite de upload para imagens e arquivos auxiliares.

## Rodando localmente

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload
```

Ou usando os atalhos do projeto:

```bash
make install
make dev
```

A documentacao interativa fica em:

- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

## Observacoes de arquitetura

- Routers ficam em `app/routers`.
- Servicos de dominio ficam em `app/services`.
- Contratos de entrada/saida ficam em `app/schemas`.
- Configuracoes ficam em `app/core/config.py`.

O projeto ainda nao esta integrado ao Otica Plus. A fronteira principal do modulo e receber imagens/textos e devolver resultados processados.
