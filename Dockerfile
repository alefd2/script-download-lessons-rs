# Use a imagem oficial do Python 3.10
FROM python:3.10-slim

# Instalar dependências do sistema e ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean

# Defina a variável de ambiente para o ffmpeg
ENV PATH="/usr/local/bin/ffmpeg:${PATH}"

# Defina o diretório de trabalho
WORKDIR /app

# Copie os arquivos do script para dentro do contêiner
COPY . /app

# Instalar as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Defina o comando padrão para rodar o script
CMD ["python", "main.py"]
