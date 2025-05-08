docker-compose build
docker-compose run --rm rocket_download


-----
docker-compose up -d --build

docker compose exec rocket_download bash
python main.py

## local
RUN pip install --no-cache-dir -r requirements.txt
python main.py