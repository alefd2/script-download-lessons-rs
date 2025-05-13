# Documentação

Este script fornece instruções para configurar e executar uma aplicação Python Dockerizada para download de aulas. Abaixo está uma descrição dos comandos e seus propósitos:

1. **Construir a Imagem Docker**:
    - `docker-compose build`: Constrói a imagem Docker para a aplicação.

2. **Executar a Aplicação**:
    - `docker-compose run --rm rocket_download`: Executa a aplicação em um container temporário e remove o container após a execução.

3. **Iniciar a Aplicação em Modo Desanexado**:
    - `docker-compose up -d --build`: Inicia a aplicação em modo desanexado, reconstruindo a imagem se necessário.

4. **Acessar o Container em Execução**:
    - `docker compose exec rocket_download bash`: Abre um shell bash dentro do container em execução para depuração ou execução manual.

5. **Executar o Script Python**:
    - `python main.py`: Executa o script Python principal dentro do container.

6. **Configuração para Desenvolvimento Local**:
    - `RUN pip install --no-cache-dir -r requirements.txt`: Instala as dependências Python necessárias localmente sem cache.
    - `python main.py`: Executa o script Python localmente após configurar o ambiente.

7. **Executar Localmente**:
    - Para executar a aplicação localmente sem Docker, certifique-se de que todas as dependências estejam instaladas usando:
        - `pip install --no-cache-dir -r requirements.txt`
    - Em seguida, execute o script:
        - `python main.py`

8. **Configurar Ambiente Virtual**:
    - Para isolar dependências, crie e ative um ambiente virtual:
        - Em Unix/macOS:
            - `python3 -m venv venv`
            - `source venv/bin/activate`
        - Em Windows:
            - `python -m venv venv`
            - `venv\Scripts\activate`
    - Instale as dependências dentro do ambiente virtual:
        - `pip install --no-cache-dir -r requirements.txt`
    - Execute o script:
        - `python main.py`
