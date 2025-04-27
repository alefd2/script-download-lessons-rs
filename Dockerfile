# ------------------------------------------------------------
# Dockerfile otimizado para o downloader Rocketseat
# ------------------------------------------------------------
# 1. Imagem base minimalista (Debian slim) com Python 3.10
FROM python:3.10-slim-bullseye AS base

# 2. Variáveis de ambiente: timezone e UTF-8 para evitar warnings
ENV TZ=America/Fortaleza \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 3. Camada de dependências do sistema (ffmpeg + ca-certificates)
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 4. Diretório de trabalho
WORKDIR /app

# 5. Copiar requirements primeiro para aproveitar cache em rebuilds
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar código-fonte (aproveitando cache da etapa 5)
COPY . .

# 7. (Opcional) diretório para cachear a sessão
ENV SESSION_DIR=/app/cache
RUN mkdir -p "$SESSION_DIR"

# 8. Definir usuário não‑root por segurança
RUN useradd -m runner && chown -R runner:runner /app
USER runner

# 9. Executável padrão (aceita argumentos adicionais, ex: --help)
ENTRYPOINT ["python", "main.py"]
