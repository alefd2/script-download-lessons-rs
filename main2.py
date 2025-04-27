import json
import os
import pickle
import queue
import random
import re
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

import m3u8
import requests
from bs4 import BeautifulSoup

BASE_API = "https://skylab-api.rocketseat.com.br"
BASE_URL = "https://app.rocketseat.com.br"
SESSION_PATH = Path(".session.pkl")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def sanitize_string(string: str):
    return re.sub(r'[@#$%&*/:^{}<>?"]', "", string).strip()


class PandaVideo:
    def __init__(self, url: str, save_path: str, threads_count=10):
        def create_session(headers: dict = {}):
            session = requests.session()
            session.headers.update(
                {
                    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                    **headers,
                }
            )
            return session

        qs = parse_qs(url.split("?")[-1])
        if "v" not in qs:
            raise Exception("ID do vídeo não encontrado na querystring")
        self.video_id = qs["v"][0]

        _match = re.search(r"https://([^/]+)/", url)
        if not _match:
            raise Exception("Domínio não encontrado na URL")

        self.domain = _match.group(1).replace("player", "b")
        self.session = create_session(
            {"referer": url, "origin": f"https://{self.domain}"}
        )
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
        for filename in os.listdir(self.temp_folder):  # type: ignore [StrPath is str :D]
            os.remove(self.temp_folder / filename)
        os.removedirs(self.temp_folder)

    def __download_playlist(self, playlist_url: str):
        self._create_temp_folder()
        playlist_content = self.session.get(playlist_url).text
        # writing the local playlist
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
                    "\r\t\t\t\t\tBaixando segmento %d de %d"
                    % (self.downloaded_segments, self.total_segments),
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

        print("\n\t\t\t\t\tConcluído!", flush=True)

        self.__convert_segments()

    def download(self):
        if os.path.exists(self.save_path):
            print("\t\t\t\tArquivo já existe (PANDA)")
            return
        playlists_url = f"https://{self.domain}/{self.video_id}/playlist.m3u8"
        playlists_content = self.session.get(playlists_url).text
        playlists_loaded = m3u8.loads(playlists_content)

        best_playlist = max(
            playlists_loaded.playlists,
            key=lambda x: x.stream_info.resolution[0] * x.stream_info.resolution[1],
        )
        best_playlist_url = (
            (f"https://{self.domain}/{self.video_id}/{best_playlist.uri}")
            if not best_playlist.uri.startswith("http")
            else best_playlist.uri
        )

        self.__download_playlist(best_playlist_url)


class RocketseatProperties:
    specialization: dict
    module: dict
    levels: list
    level: dict
    groups: list
    group: dict = dict()
    lesson: dict

    @property
    def specialization_name(self) -> str:
        return self.specialization["title"]

    @property
    def specialization_uri(self) -> str:
        return self.specialization["uri"]

    @property
    def specialization_slug(self) -> str:
        return self.specialization["slug"]

    @property
    def modules(self) -> list[dict]:
        return self.level["contents"]

    @modules.setter
    def modules(self, value: list[dict]):
        self.level["contents"] = value

    @property
    def modules_count(self) -> int:
        return len(self.modules)

    @property
    def module_name(self) -> str:
        return self.module["title"]

    @property
    def module_index(self) -> int:
        return self.module["script_index"]

    @property
    def f_module_name(self) -> str:
        return f"{self.module_index} - {sanitize_string(self.module_name)}"

    @property
    def module_slug(self) -> str:
        return self.module["slug"]

    @property
    def levels_count(self) -> int:
        return len(self.levels)

    @property
    def level_name(self) -> str:
        return self.level["title"]

    @property
    def level_type(self) -> str:
        return self.level["type"]

    @property
    def level_index(self) -> int:
        return self.level["script_index"]

    @property
    def f_level_name(self) -> str:
        return f"{self.level_index} - {sanitize_string(self.level_name)}"

    @property
    def group_name(self) -> str:
        return self.group["title"]

    @property
    def group_index(self) -> int:
        return self.group["script_index"]

    @property
    def f_group_name(self) -> str:
        return f"{self.group_index} - {sanitize_string(self.group_name)}"

    @property
    def groups_count(self) -> int:
        return len(self.groups)

    @property
    def lessons(self) -> list:
        return self.group["lessons"]

    @lessons.setter
    def lessons(self, value: list):
        self.group["lessons"] = value

    @property
    def lessons_count(self) -> int:
        return len(self.lessons)

    @property
    def lesson_name(self) -> str:
        return self.lesson["last"]["title"]

    @property
    def lesson_index(self) -> int:
        return self.lesson["script_index"]

    @property
    def f_lesson_name(self) -> str:
        return f"{self.lesson_index} - {sanitize_string(self.lesson_name)}"

    @property
    def lesson_type(self) -> str:
        return self.lesson["type"]

    @property
    def lesson_video_id(self) -> str:
        return self.lesson["last"]["resource"]

    @property
    def lesson_description(self) -> Optional[str]:
        return self.lesson["last"].get("description")

    @property
    def lesson_attachments(self) -> list[dict]:
        return self.lesson["last"].get("downloads", []) or []

    @property
    def save_path(self) -> Path:
        _path = Path("Cursos") / self.specialization_name / self.f_level_name
        if self.level_type != "lesson":
            _path /= self.f_module_name

            if self.modules_count == 1 or self.groups_count == 1:
                _path /= self.f_lesson_name
            else:
                _path /= self.f_group_name
                _path /= self.f_lesson_name

        _path.mkdir(exist_ok=True, parents=True)
        return _path


class Rocketseat(RocketseatProperties):
    def __init__(self):
        self._session_exists = SESSION_PATH.exists()
        if self._session_exists:
            print(
                f"Carregando sessão salva (se ocorrer algum erro, considere apagar o arquivo {SESSION_PATH})..."
            )
            self.session = pickle.load(SESSION_PATH.open("rb"))
        else:
            self.session = requests.session()
            self.session.headers["User-Agent"] = (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            self.session.headers["Referer"] = "https://app.rocketseat.com.br/"

    def _download_video(self):
        """essa disgraça vai baixar o video, vai basicamente pegar o módulo id e instanciar a classe de download passando como argumento o save_path"""

        PandaVideo(
            f"https://player-vz-762f4670-e04.tv.pandavideo.com.br/embed/?v={self.lesson_video_id}",
            str(self.save_path / "aulinha.mp4"),
        ).download()

    def _save_lesson_description(self):
        """Salva a descrição da aula se houver num aquivo txt"""
        if self.lesson_description:
            with (self.save_path / "descricao.txt").open("w") as file:
                file.write(self.lesson_description)

    def _download_lesson_attachments(self):
        """Baixa, se houver, anexos para a aula (só iterar sobre downloads e dar get em file_url)"""
        for attach in self.lesson_attachments:
            filename = f"{sanitize_string(attach['title'])} - {attach['file']}"
            file_path = self.save_path / filename
            if file_path.exists():
                print(f"\t\t\t\tAnexo {filename} já existe. Pulando...")
                continue
            with (self.save_path / filename).open("wb") as f:
                f.write(self.session.get(attach["file_url"]).content)
            print(f"\t\t\t\tAnexo baixado: {filename}")

    def _download_lesson(self):
        """finalmente sapoha vai indentifcicar o tipo de conteúdo e chamar a função que trata do tipo específico da entrega de copnteúdo da lessson"""
        print(
            f"\t\t\t\tBaixando aula {self.lesson_index} de {self.lessons_count}: {self.lesson_name}"
        )

        factory = {
            "video": self._download_video,
        }

        factory.get(
            self.lesson_type,
            lambda: print(f"Tipo de aula desconhecido: {self.lesson_type}"),
        )()

        self._save_lesson_description()

        self._download_lesson_attachments()

    def _download_group(self):
        """Só itera sobre as lessons de dentro do grupo e chama o downloader"""
        print(
            f"\t\t\tBaixando grupo {self.group_index} de {self.groups_count}: {self.group_name}"
        )

        for i, self.lesson in enumerate(self.lessons, 1):
            self.lesson.update(script_index=i)
            self._download_lesson()

    def _download_module(self):
        """essa disgraça lista os grupos, itera sobre eles e chama o downloader group"""
        print(
            f"\t\tBaixando módulo {self.module_index} de {self.modules_count}: {self.module_name}"
        )

        data = self.session.get(f"{BASE_API}/journey-nodes/{self.module_slug}").json()

        if data["cluster"] is None:
            self.groups = [data["group"]]
        else:
            self.groups = data["cluster"]["groups"]

        for i, self.group in enumerate(self.groups, 1):
            self.group.update(script_index=i)
            self._download_group()

    def _download_level(self):
        """Itera sobre os níveis e seus módulos e bota pra baixar topado"""
        print(
            f"\tBaixando level {self.level_index} de {self.levels_count}: {self.level_name}"
        )

        if self.level_type == "lesson":
            self.lessons = [self.level["lesson"]]
            self.lesson = self.lessons[0]
            self.lesson.update(script_index=1)
            self._download_lesson()
        elif self.level_type == "cluster":
            self.modules = [self.level]
            self.module = self.modules[0]
            self._download_module()
        else:
            print(
                f"\tO tipo de level é {self.level_type} o qual não foi (talvez nem será) implementado neste script."
            )

    def __load_nodes(self) -> list[dict]:
        """Esta função (agora) vai carregar o json vindo em embedding num javascript renderizado no html pelo servidor."""

        res = self.session.get(f"{BASE_URL}/{self.specialization_uri}/contents")
        soup = BeautifulSoup(res.text, "html.parser")

        try:
            script_tag = next(
                script
                for script in soup.find_all("script")
                if "journeyId" in script.text
            )
        except StopIteration:
            print("O script contendo as aulas não foi encontrado...")
            with open("server_response.html", "wb") as f:
                f.write(res.content)
            exit(1)
        script_text = script_tag.text.strip().replace('\\"', '"').replace("\\\\", "\\")

        start = script_text.index('{"journey')

        json_content = json.loads(script_text[start:].split(',"children')[0] + "}")

        with open("json_content.json", "w", encoding="utf-8") as f:
            json.dump(json_content, f, indent=4, ensure_ascii=False)

        return json_content["journey"]["nodes"]

    def _download_courses(self):
        """Lista levels (são nodes agora) e itera sobre elas chamando download modules"""
        clear_screen()
        print(f"Baixando especialização {self.specialization_name}")
        self.levels = self.__load_nodes()

        for i, self.level in enumerate(self.levels, 1):
            self.level.update(script_index=i)

            self._download_level()

    def login(self, username: str, password: str):
        """Faz login setando a sessão utilizando username e password fornecidos na instancialização"""
        payload = {"email": username, "password": password}

        res = self.session.post(f"{BASE_API}/sessions", json=payload).json()

        self.session.headers["Authorization"] = (
            f"{res['type'].capitalize()} {res['token']}"
        )
        self.session.cookies.update(
            {
                "skylab_next_access_token_v3": res["token"],
                "skylab_next_refresh_token_v3": res["refreshToken"],
            }
        )

        account_infos = self.session.get(f"{BASE_API}/account").json()

        print("Welcome, {}!".format(account_infos["name"]))
        pickle.dump(self.session, SESSION_PATH.open("wb"))

    def select_specializations(self):
        """Permite seleconar uma ou todas as especializações para download dos cursos"""
        params = {
            "types[0]": "SPECIALIZATION",
            "limit": "12",
            "offset": "0",
            "page": "1",
            "sort_by": "relevance",
        }
        specializations = self.session.get(
            f"{BASE_API}/catalog/list", params=params
        ).json()["items"]

        clear_screen()

        print("Selecione uma formação ou 0 para selecionar todas:")
        for i, specialization in enumerate(specializations, 1):
            print(f"[{i}] - {specialization['title']}")

        choice = int(input(">> "))
        if choice == 0:
            for self.specialization in specializations:
                self._download_courses()
        else:
            self.specialization = specializations[choice - 1]
            self._download_courses()

    def run(self):
        """Inicia a execução do script"""
        if not self._session_exists:
            self.login(
                username=input("Seu email Rocketseat: "), password=input("Sua senha: ")
            )
        self.select_specializations()


if __name__ == "__main__":
    agent = Rocketseat()
    agent.run()