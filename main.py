import json
import os
import pickle
import queue
import random
import re
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

import m3u8
import requests
from bs4 import BeautifulSoup

BASE_API = "https://skylab-api.rocketseat.com.br"
BASE_URL = "https://app.rocketseat.com.br"
SESSION_PATH = Path(os.getenv("SESSION_DIR", ".")) / ".session.pkl"
SESSION_PATH.parent.mkdir(exist_ok=True)


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def sanitize_string(string: str):
    return re.sub(r'[@#$%&*/:^{}<>?"]', "", string).strip()


class PandaVideo:
    def __init__(self, video_id: str, save_path: str, threads_count=10):
        self.video_id = video_id
        self.domain = f"b-vz-762f4670-e04.tv.pandavideo.com.br"
        self.session = requests.session()
        self.save_path = save_path
        self.threads_count = threads_count

    def _create_temp_folder(self):
        foldername = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5))
        self.temp_folder = Path(".temp") / foldername
        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder)
        return self.temp_folder

    def __convert_segments(self):
        ffmpeg_cmd = f'ffmpeg -hide_banner -loglevel error -stats -y -i "{self.temp_folder}/playlist.m3u8" -c copy -bsf:a aac_adtstoasc "{self.save_path}"'
        os.system(ffmpeg_cmd)
        for filename in os.listdir(self.temp_folder):
            os.remove(self.temp_folder / filename)
        os.removedirs(self.temp_folder)

    def __download_playlist(self, playlist_url: str):
        print("Iniciando o download dos segmentos...")
        self._create_temp_folder()
        playlist_content = self.session.get(playlist_url).text
        with open(self.temp_folder / "playlist.m3u8", "w") as file:
            for line in playlist_content.splitlines():
                line = line.split("/")[-1] if line.startswith("https") else line
                file.write(f"{line}\n")
        playlist = m3u8.loads(playlist_content)

        threads = []
        segment_queue = queue.Queue()
        self.downloaded_segments = 0
        self.total_segments = len(playlist.segments)
        for segment in playlist.segments:
            segment_queue.put(segment)

        def worker():
            while not segment_queue.empty():
                segment = segment_queue.get()
                filename = segment.uri.split("/")[-1]
                with open(self.temp_folder / filename, "wb") as file:
                    file.write(self.session.get(segment.uri).content)
                segment_queue.task_done()
                self.downloaded_segments += 1
                print(
                    f"\rBaixando segmento {self.downloaded_segments} de {self.total_segments}... ",
                    end="",
                    flush=True,
                )

        for _ in range(self.threads_count):
            thread = threading.Thread(target=worker)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        segment_queue.join()

        print("\nDownload concluído!\n")

        self.__convert_segments()

    def download(self):
        if os.path.exists(self.save_path):
            print("\tArquivo já existe. Pulando download.")
            return
        print(f"Iniciando download do vídeo: {self.video_id}")
        playlists_url = f"https://{self.domain}/{self.video_id}/playlist.m3u8"
        playlists_content = self.session.get(playlists_url).text
        playlists_loaded = m3u8.loads(playlists_content)

        best_playlist = max(
            playlists_loaded.playlists,
            key=lambda x: x.stream_info.resolution[0] * x.stream_info.resolution[1],
        )
        best_playlist_url = (
            best_playlist.uri
            if best_playlist.uri.startswith("http")
            else f"https://{self.domain}/{self.video_id}/{best_playlist.uri}"
        )

        self.__download_playlist(best_playlist_url)


class Rocketseat:
    def __init__(self):
        self._session_exists = SESSION_PATH.exists()
        if self._session_exists:
            print("Carregando sessão salva...")
            self.session = pickle.load(SESSION_PATH.open("rb"))
        else:
            self.session = requests.session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": BASE_URL,
            })

    def login(self, username: str, password: str):
        print("Realizando login...")
        payload = {"email": username, "password": password}
        res = self.session.post(f"{BASE_API}/sessions", json=payload)
        res.raise_for_status()
        data = res.json()

        self.session.headers["Authorization"] = f"{data['type'].capitalize()} {data['token']}"
        self.session.cookies.update({
            "skylab_next_access_token_v3": data["token"],
            "skylab_next_refresh_token_v3": data["refreshToken"],
        })

        account_infos = self.session.get(f"{BASE_API}/account").json()
        print(f"Bem-vindo, {account_infos['name']}!")
        pickle.dump(self.session, SESSION_PATH.open("wb"))

    def __load_modules(self, specialization_slug: str):
        print(f"Buscando módulos para a formação: {specialization_slug}")
        start_time = time.time()
        
        # Get modules data from API
        url = f"{BASE_API}/v2/journeys/{specialization_slug}/progress/temp"
        res = self.session.get(url)
        res.raise_for_status()

        modules_data = []

        try:
            progress_data = res.json()
            modules_data = progress_data.get("nodes", [])

            # Get HTML content from journey page to extract cluster_slugs
            journey_url = f"https://app.rocketseat.com.br/journey/{specialization_slug}/contents"
            html_content = self.session.get(journey_url).text

            # Extract cluster slugs from HTML
            for module in modules_data:
                # Only process if type is cluster
                if module.get("type") == "cluster":
                    # Search for module link pattern in HTML
                    search_pattern = f'<a class="w-full" href="/classroom/'
                    html_pos = html_content.find(search_pattern)
                    if html_pos != -1:
                        # Extract cluster slug from href
                        start_pos = html_pos + len(search_pattern)
                        end_pos = html_content.find('"', start_pos)
                        cluster_slug = html_content[start_pos:end_pos].split(">")[0].strip()
                        module["cluster_slug"] = cluster_slug
                        # Move search position forward
                        html_content = html_content[end_pos:]
                    else:
                        module["cluster_slug"] = None
                else:
                    module["cluster_slug"] = None

            print(f"Encontrados {len(modules_data)} módulos.")
        except Exception as e:
            print(f"Erro ao processar os módulos: {e}")

        elapsed_time = time.time() - start_time
        print(f"Início: {time.strftime('%H:%M:%S')} | Busca pelos módulos concluída! | Número de módulos encontrados: {len(modules_data)} | Tempo executado: {elapsed_time:.2f} segundos")
        return modules_data

    def __load_lessons_from_cluster(self, cluster_slug: str):
        """
        Carrega as aulas de um cluster específico
        """
        print(f"Buscando lições para o cluster: {cluster_slug}")
        url = f"{BASE_API}/journey-nodes/{cluster_slug}"
        
        try:
            res = self.session.get(url)
            res.raise_for_status()
            
            module_data = res.json()
            
            # Salva estrutura para debug se diretório logs existir
            if os.path.exists("logs"):
                with open(f"logs/{sanitize_string(cluster_slug)}_cluster_details.json", "w") as f:
                    json.dump(module_data, f, indent=2)
            
            lessons = []
            if "cluster" in module_data and module_data["cluster"]:
                cluster = module_data["cluster"]
                
                # Navegar pelos grupos de lições
                for group in cluster.get("groups", []):
                    for lesson in group.get("lessons", []):
                        if "last" in lesson and lesson["last"]:
                            lessons.append(lesson["last"])
            
            print(f"Encontradas {len(lessons)} lições no cluster")
            return lessons
        except Exception as e:
            print(f"Erro ao buscar lições do cluster {cluster_slug}: {e}")
            return []

    def _download_video(self, video_id: str, save_path: Path):
        print(f"Iniciando download do vídeo {video_id}")
        PandaVideo(video_id, str(save_path / "aulinha.mp4")).download()

    def _download_lesson(self, lesson: dict, save_path: Path):
        if isinstance(lesson, dict) and 'title' in lesson and 'resource' in lesson:
            print(f"\tBaixando aula: {lesson['title']}")
            resource = lesson["resource"].split("/")[-1] if "/" in lesson["resource"] else lesson["resource"]
            PandaVideo(resource, str(save_path / f"{sanitize_string(lesson['title'])}.mp4")).download()
        else:
            print(f"\tFormato de aula não reconhecido: {lesson}")

    def _download_courses(self, specialization_slug: str, specialization_name: str):
        print(f"Baixando cursos da especialização: {specialization_name}")
        modules = self.__load_modules(specialization_slug)

        print("\nEscolha os módulos que você quer baixar:")
        for i, module in enumerate(modules, 1):
            print(f"[{i}] - {module['title']}")

        choices = input("Digite os números dos módulos separados por vírgula (ex: 1, 3, 5): ")
        selected_modules = [modules[int(choice.strip()) - 1] for choice in choices.split(",")]

        for module in selected_modules:
            module_title = module["title"]
            course_name = module.get("course", {}).get("title", "Sem Nome")
            print(f"Baixando módulo: {module_title} do curso: {course_name}")
            save_path = Path("Cursos") / specialization_name / sanitize_string(course_name) / sanitize_string(module_title)
            save_path.mkdir(parents=True, exist_ok=True)

            # Verifica se o módulo tem um cluster_slug
            if "cluster_slug" in module and module["cluster_slug"]:
                cluster_slug = module["cluster_slug"]
                print(f"Usando cluster_slug: {cluster_slug}")
                
                # Obter aulas a partir do cluster_slug
                lessons = self.__load_lessons_from_cluster(cluster_slug)
                
                if not lessons:
                    print(f"Nenhuma aula encontrada para o módulo: {module_title}")
                    continue
                
                # Baixa cada aula
                for lesson in lessons:
                    self._download_lesson(lesson, save_path)
            else:
                print(f"Módulo não possui cluster_slug: {module_title}. Pulando.")
                continue

    def select_specializations(self):
        print("Buscando especializações disponíveis...")
        params = {
            "types[0]": "SPECIALIZATION",
            "limit": "12",
            "offset": "0",
            "page": "1",
            "sort_by": "relevance",
        }
        specializations = self.session.get(f"{BASE_API}/catalog/list", params=params).json()["items"]
        clear_screen()
        print("Selecione uma formação ou 0 para selecionar todas:")
        for i, specialization in enumerate(specializations, 1):
            print(f"[{i}] - {specialization['title']}")

        choice = int(input(">> "))
        if choice == 0:
            for specialization in specializations:
                self._download_courses(specialization["slug"], specialization["title"])
        else:
            specialization = specializations[choice - 1]
            self._download_courses(specialization["slug"], specialization["title"])

    def run(self):
        if not self._session_exists:
            self.login(
                username=input("Seu email Rocketseat: "),
                password=input("Sua senha: ")
            )
        self.select_specializations()


if __name__ == "__main__":
    print("Iniciando o processo de download...")
    agent = Rocketseat()
    agent.run()
