# OptiProcess API

API FastAPI independente e dedicada para processamento de imagens, OCR, IA visual e exportacao SVG.

## Funcionalidades

- `GET /health`: status simples da API.
- `POST /api/image/process-image`: recebe imagem de receita, tenta OCR local com EasyOCR e usa OpenAI Vision como fallback quando a confianca for baixa.
- `POST /api/image/optimize`: redimensiona e recomprime imagens para OCR, IA, storage ou preview.
- `POST /api/image/preprocess`: prepara imagens com modos `clean`, `ocr` e `document`.
- `POST /api/image/batch/process-images`: processa multiplas imagens com limite por lote.
- `POST /api/image/export-svg`: gera SVG incorporando a imagem original, criando um cartao SVG limpo a partir de texto/OCR/IA ou vetorizando contornos da imagem.
- `POST /api/customers/normalize-excel`: utilitario auxiliar legado para normalizar `.xlsx`, `.xls` ou `.csv`, sem gravar dados.

## Configuracao

Crie um `.env` a partir de `.env.example`.

```bash
cp .env.example .env
```

Variaveis principais:

- `OPENAI_API_KEY`: chave usada apenas quando o OCR local nao for suficiente.
- `API_KEY`: chave opcional para proteger endpoints de processamento via header `X-API-Key`.
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

Se a porta `8000` estiver ocupada:

```bash
make dev PORT=8001
```

Por padrao, `make install` instala o perfil leve, bom para FastAPI Cloud e demos. Para OCR local com EasyOCR, use:

```bash
make install-full
```

Se a pasta do projeto for movida e a `.venv` ficar com comandos quebrados, recrie o ambiente:

```bash
make reset-venv
make dev
```

Para recriar com EasyOCR local:

```bash
make reset-venv-full
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

## Seguranca

Se `API_KEY` estiver vazia, os endpoints ficam abertos para facilitar demo local/cloud. Se `API_KEY` estiver configurada, envie:

```http
X-API-Key: sua-chave
```

O endpoint `/health` continua publico.
