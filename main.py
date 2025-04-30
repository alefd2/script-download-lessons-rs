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
from datetime import datetime

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


class DownloadReport:
    def __init__(self):
        self.successful_downloads = []
        self.failed_downloads = []
        self.start_time = None
        self.end_time = None
    
    def start(self):
        self.start_time = datetime.now()
        print(f"Início do download: {self.start_time.strftime('%d/%m/%Y %H:%M:%S')}")
    
    def add_success(self, module_title, lesson_title):
        self.successful_downloads.append({
            'module': module_title,
            'lesson': lesson_title,
            'timestamp': datetime.now()
        })
        print(f"✓ Aula baixada com sucesso: {module_title} - {lesson_title}")
    
    def add_failure(self, module_title, lesson_title, error):
        self.failed_downloads.append({
            'module': module_title,
            'lesson': lesson_title,
            'error': str(error),
            'timestamp': datetime.now()
        })
        print(f"✗ Erro ao baixar aula: {module_title} - {lesson_title}")
        print(f"   Erro: {str(error)}")
    
    def finish(self):
        self.end_time = datetime.now()
        self.generate_report()
    
    def generate_report(self):
        if not self.start_time or not self.end_time:
            return "Relatório incompleto - download não finalizado"
        
        duration = self.end_time - self.start_time
        total_attempts = len(self.successful_downloads) + len(self.failed_downloads)
        
        report = [
            "=== RELATÓRIO DE DOWNLOAD ===",
            f"Data: {self.end_time.strftime('%d/%m/%Y %H:%M:%S')}",
            f"Duração total: {duration}",
            f"Total de aulas: {total_attempts}",
            f"Aulas baixadas com sucesso: {len(self.successful_downloads)}",
            f"Aulas com erro: {len(self.failed_downloads)}",
            "\n=== AULAS BAIXADAS COM SUCESSO ==="
        ]
        
        for download in self.successful_downloads:
            report.append(f"- Módulo: {download['module']}")
            report.append(f"  Aula: {download['lesson']}")
            report.append(f"  Horário: {download['timestamp'].strftime('%H:%M:%S')}")
        
        if self.failed_downloads:
            report.append("\n=== AULAS COM ERRO ===")
            for download in self.failed_downloads:
                report.append(f"- Módulo: {download['module']}")
                report.append(f"  Aula: {download['lesson']}")
                report.append(f"  Erro: {download['error']}")
                report.append(f"  Horário: {download['timestamp'].strftime('%H:%M:%S')}")
        
        report_text = "\n".join(report)
        
        # Salvar relatório em arquivo
        report_path = Path("relatorios") / f"relatorio_{self.end_time.strftime('%Y%m%d_%H%M%S')}.txt"
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        
        # Imprimir relatório no console
        print("\n" + "="*50)
        print(report_text)
        print("="*50)
        print(f"\nRelatório salvo em: {report_path}")


class PandaVideo:
    def __init__(self, video_id: str, save_path: str, threads_count=10):
        self.video_id = video_id
        self.domain = "b-vz-762f4670-e04.tv.pandavideo.com.br"
        self.session = requests.session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://app.rocketseat.com.br",
            "Referer": "https://app.rocketseat.com.br/",
        })
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


class CDNVideo:
    def __init__(self, video_id: str, save_path: str, threads_count=10):
        self.video_id = video_id
        self.domain = "vz-dc851587-83d.b-cdn.net"
        self.session = requests.session()
        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7,it;q=0.6",
            "dnt": "1",
            "origin": "https://iframe.mediadelivery.net",
            "priority": "u=1, i",
            "referer": "https://iframe.mediadelivery.net/",
            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        })
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
        
        try:
            # Baixar a playlist principal
            response = self.session.get(playlist_url)
            response.raise_for_status()
            playlist_content = response.text
            print(f"Conteúdo da playlist principal:\n{playlist_content}")
            
            # Carregar a playlist principal
            main_playlist = m3u8.loads(playlist_content)
            
            # Se for uma playlist master (contém outras playlists)
            if main_playlist.playlists:
                print("Playlist master encontrada, selecionando segunda melhor qualidade...")
                # Ordenar as playlists por qualidade
                sorted_playlists = sorted(
                    main_playlist.playlists,
                    key=lambda x: x.stream_info.resolution[0] * x.stream_info.resolution[1],
                    reverse=True
                )
                
                # Selecionar a segunda melhor qualidade
                if len(sorted_playlists) > 1:
                    second_best_playlist = sorted_playlists[1]
                    print(f"Selecionada segunda melhor qualidade: {second_best_playlist.stream_info.resolution[0]}x{second_best_playlist.stream_info.resolution[1]}")
                else:
                    # Se só tiver uma qualidade, usa ela
                    second_best_playlist = sorted_playlists[0]
                    print(f"Usando única qualidade disponível: {second_best_playlist.stream_info.resolution[0]}x{second_best_playlist.stream_info.resolution[1]}")
                
                # Baixar a playlist de qualidade específica
                quality_playlist_url = second_best_playlist.uri
                if not quality_playlist_url.startswith('http'):
                    quality_playlist_url = f"https://{self.domain}/{self.video_id}/{quality_playlist_url}"
                
                print(f"Baixando playlist de qualidade: {quality_playlist_url}")
                response = self.session.get(quality_playlist_url)
                response.raise_for_status()
                quality_playlist_content = response.text
                print(f"Conteúdo da playlist de qualidade:\n{quality_playlist_content}")
                
                playlist = m3u8.loads(quality_playlist_content)
            else:
                # Se já for uma playlist de segmentos
                playlist = main_playlist
            
            print(f"Playlist carregada com {len(playlist.segments)} segmentos")
            
            # Salvar a playlist final
            with open(self.temp_folder / "playlist.m3u8", "w") as file:
                file.write(playlist.dumps())
            
            threads = []
            segment_queue = queue.Queue()
            self.downloaded_segments = 0
            self.total_segments = len(playlist.segments)
            
            # Ordenar os segmentos para garantir a ordem correta
            def get_segment_number(segment):
                filename = segment.uri.split('/')[-1]
                if filename.startswith('video'):
                    try:
                        return int(filename[5:-3])
                    except:
                        return 0
                return 0
            
            sorted_segments = sorted(playlist.segments, key=get_segment_number)
            for segment in sorted_segments:
                segment_queue.put(segment)

            def worker():
                while not segment_queue.empty():
                    segment = segment_queue.get()
                    try:
                        # Atualizar headers para cada segmento
                        segment_headers = {
                            "sec-ch-ua-platform": '"Linux"',
                            "Referer": "https://iframe.mediadelivery.net/",
                            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                            "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
                            "DNT": "1",
                            "sec-ch-ua-mobile": "?0"
                        }
                        self.session.headers.update(segment_headers)
                        
                        segment_url = segment.uri
                        if not segment_url.startswith('http'):
                            segment_url = f"https://{self.domain}/{self.video_id}/1080p/{segment_url}"
                        
                        print(f"Baixando segmento: {segment_url}")
                        response = self.session.get(segment_url)
                        response.raise_for_status()
                        filename = segment.uri.split("/")[-1]
                        file_path = self.temp_folder / filename
                        with open(file_path, "wb") as file:
                            file.write(response.content)
                        print(f"Segmento {filename} baixado com sucesso")
                        segment_queue.task_done()
                        self.downloaded_segments += 1
                        print(
                            f"\rBaixando segmento {self.downloaded_segments} de {self.total_segments}... ",
                            end="",
                            flush=True,
                        )
                    except Exception as e:
                        print(f"\nErro ao baixar segmento {segment_url}: {str(e)}")
                        segment_queue.task_done()

            for _ in range(self.threads_count):
                thread = threading.Thread(target=worker)
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

            segment_queue.join()

            print("\nDownload concluído!\n")
            print(f"Verificando arquivos baixados em {self.temp_folder}")
            for f in os.listdir(self.temp_folder):
                print(f"Arquivo encontrado: {f}")

            self.__convert_segments()
            return True
            
        except Exception as e:
            print(f"Erro ao processar playlist: {str(e)}")
            return False

    def download(self):
        if os.path.exists(self.save_path):
            print("\tArquivo já existe. Pulando download.")
            return

        print(f"Iniciando download do vídeo: {self.video_id}")
        
        # Tentar primeiro a playlist direta
        playlists_url = f"https://{self.domain}/{self.video_id}/playlist.m3u8"
        success = self.__download_playlist(playlists_url)
        
        if not success:
            print("Não foi possível baixar o vídeo do CDN.")

class VideoDownloader:
    def __init__(self, video_id: str, save_path: str, threads_count=10):
        self.video_id = video_id
        self.save_path = save_path
        self.threads_count = threads_count
        self.panda = PandaVideo(video_id, save_path, threads_count)
        self.cdn = CDNVideo(video_id, save_path, threads_count)

    def __check_video_duration(self):
        try:
            cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{self.save_path}"'
            duration = float(os.popen(cmd).read().strip())
            return duration
        except:
            return 0

    def download(self):
        if os.path.exists(self.save_path):
            print("\tArquivo já existe. Pulando download.")
            return

        # Tentar primeiro com o Panda
        print("Tentando download com Panda...")
        self.panda.download()
        
        # Verificar duração do vídeo
        duration = self.__check_video_duration()
        if duration > 10:  # Se o vídeo tem mais de 10 segundos, consideramos válido
            print(f"Vídeo baixado com sucesso! Duração: {duration:.2f} segundos")
            return
        
        print(f"Vídeo muito curto ({duration:.2f} segundos). Tentando CDN...")
        if os.path.exists(self.save_path):
            os.remove(self.save_path)
        
        # Tentar com o CDN
        print("Tentando download com CDN...")
        self.cdn.download()
        
        # Verificar duração novamente
        duration = self.__check_video_duration()
        if duration > 10:
            print(f"Vídeo baixado com sucesso! Duração: {duration:.2f} segundos")
        else:
            print("Não foi possível baixar o vídeo de nenhum dos provedores disponíveis.")


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
        self.download_report = DownloadReport()

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
        
        # type: 'challenge', e que o title começe com Quiz
        # challenge: {slug: 'quiz-formacao-desenvolvimento-ia-estatistica'}

        try:
            progress_data = res.json()
            modules_data = progress_data.get("nodes", [])

            journey_url = f"https://app.rocketseat.com.br/journey/{specialization_slug}/contents"
            html_content = self.session.get(journey_url).text

            for module in modules_data:
                if module.get("type") == "cluster":
                    search_pattern = f'<a class="w-full" href="/classroom/'
                    html_pos = html_content.find(search_pattern)
                    if html_pos != -1:
                        start_pos = html_pos + len(search_pattern)
                        end_pos = html_content.find('"', start_pos)
                        cluster_slug = html_content[start_pos:end_pos]
                        print(f"Encontrado cluster_slug para módulo {module['title']}: {cluster_slug}")
                        module["cluster_slug"] = cluster_slug
                        html_content = html_content[end_pos:]
                    else:
                        print(f"Não encontrado cluster_slug para módulo {module['title']}")
                        module["cluster_slug"] = None
                else:
                    print(f"Módulo {module['title']} não é do tipo cluster")
                    module["cluster_slug"] = None

            print(f"Encontrados {len(modules_data)} módulos.")
        except Exception as e:
            print(f"Erro ao processar os módulos: {e}")

        elapsed_time = time.time() - start_time
        print(f"Início: {time.strftime('%H:%M:%S')} | Busca pelos módulos concluída! | Número de módulos encontrados: {len(modules_data)} | Tempo executado: {elapsed_time:.2f} segundos")
        return modules_data

    def __load_lessons_from_cluster(self, cluster_slug: str):
        # Carrega as aulas de um cluster específico
        print(f"Buscando lições para o cluster: {cluster_slug}")
        url = f"{BASE_API}/journey-nodes/{cluster_slug}"
        
        try:
            res = self.session.get(url)
            res.raise_for_status()
            
            module_data = res.json()
            print(f"Resposta da API para o cluster {cluster_slug}:")
            print(json.dumps(module_data, indent=2))
            
            # Salva estrutura para debug se diretório logs existir
            if os.path.exists("logs"):
                with open(f"logs/{sanitize_string(cluster_slug)}_cluster_details.json", "w") as f:
                    json.dump(module_data, f, indent=2)
            
            groups = []
            if "cluster" in module_data and module_data["cluster"]:
                cluster = module_data["cluster"]
                
                # Navegar pelos grupos de lições
                for group in cluster.get("groups", []):
                    group_title = group.get('title', 'Sem Grupo')
                    print(f"\nProcessando grupo: {group_title}")
                    
                    group_lessons = []
                    for lesson in group.get("lessons", []):
                        if "last" in lesson and lesson["last"]:
                            lesson_data = lesson["last"]
                            lesson_data["group_title"] = group_title
                            print(f"Adicionando aula: {lesson_data.get('title', 'Sem título')}")
                            group_lessons.append(lesson_data)
                    
                    if group_lessons:
                        groups.append({
                            "title": group_title,
                            "lessons": group_lessons
                        })
            
            print(f"\nEncontrados {len(groups)} grupos com um total de {sum(len(g['lessons']) for g in groups)} lições")
            return groups
        except Exception as e:
            print(f"Erro ao buscar lições do cluster {cluster_slug}: {e}")
            return []

    def _download_video(self, video_id: str, save_path: Path):
        VideoDownloader(video_id, str(save_path / "aulinha.mp4")).download()

    def _download_lesson(self, lesson: dict, save_path: Path, group_index: int, lesson_index: int):
        if isinstance(lesson, dict) and 'title' in lesson:
            title = lesson.get('title', 'Sem título')
            group_title = lesson.get('group_title', 'Sem Grupo')
            print(f"\tBaixando aula {group_index}.{lesson_index}: {title} (Grupo: {group_title})")
            
            try:
                # Criar pasta do grupo se não existir
                group_folder = save_path / f"{group_index:02d}. {sanitize_string(group_title)}"
                group_folder.mkdir(exist_ok=True)
                
                # Criar arquivo base com número sequencial do grupo
                base_name = f"{lesson_index:02d}. {sanitize_string(title)}"
                
                # Salvar metadados em arquivo .txt
                with open(group_folder / f"{base_name}.txt", "w", encoding="utf-8") as f:
                    f.write(f"Grupo: {group_title}\n")
                    f.write(f"Aula: {title}\n\n")
                    
                    # Adicionar descrição se existir
                    if 'description' in lesson and lesson['description']:
                        f.write(f"Descrição:\n{lesson['description']}\n\n")
                    
                    # Adicionar outras informações se existirem
                    if 'duration' in lesson:
                        minutes = lesson['duration'] // 60
                        seconds = lesson['duration'] % 60
                        f.write(f"Duração: {minutes}min {seconds}s\n")
                    
                    if 'author' in lesson and lesson['author'] and isinstance(lesson['author'], dict):
                        author_name = lesson['author'].get('name', '')
                        if author_name:
                            f.write(f"Autor: {author_name}\n")
                
                # Baixar o vídeo se tiver resource
                if 'resource' in lesson and lesson['resource']:
                    resource = lesson["resource"].split("/")[-1] if "/" in lesson["resource"] else lesson["resource"]
                    VideoDownloader(resource, str(group_folder / f"{base_name}.mp4")).download()
                    self.download_report.add_success(group_title, title)
                else:
                    print(f"\tAula '{title}' não tem recurso de vídeo")
                    self.download_report.add_success(group_title, title)  # Considera sucesso mesmo sem vídeo
                
                # Baixar arquivos adicionais
                if 'downloads' in lesson and lesson['downloads']:
                    downloads_dir = group_folder / f"{base_name}_arquivos"
                    downloads_dir.mkdir(exist_ok=True)
                    
                    for download in lesson['downloads']:
                        if 'file_url' in download and download['file_url']:
                            download_url = download['file_url']
                            download_title = download.get('title', 'arquivo')
                            file_ext = os.path.splitext(download_url)[1]
                            
                            download_path = downloads_dir / f"{sanitize_string(download_title)}{file_ext}"
                            print(f"\t\tBaixando material: {download_title}")
                            
                            try:
                                response = requests.get(download_url)
                                response.raise_for_status()
                                
                                with open(download_path, 'wb') as f:
                                    f.write(response.content)
                                    
                                print(f"\t\tMaterial salvo em: {download_path}")
                            except Exception as e:
                                print(f"\t\tErro ao baixar material: {e}")
            except Exception as e:
                self.download_report.add_failure(group_title, title, e)
                print(f"\tErro ao baixar aula: {str(e)}")
        else:
            print(f"\tFormato de aula não reconhecido: {lesson}")

    def _download_courses(self, specialization_slug: str, specialization_name: str):
        print(f"Baixando cursos da especialização: {specialization_name}")
        self.download_report.start()
        
        try:
            modules = self.__load_modules(specialization_slug)

            print("\nEscolha os módulos que você quer baixar:")
            print("[0] - Baixar todos os módulos")
            for i, module in enumerate(modules, 1):
                print(f"[{i}] - {module['title']}")

            choices = input("Digite 0 para baixar todos os módulos ou os números dos módulos separados por vírgula (ex: 1, 3, 5): ")
            
            if choices.strip() == "0":
                selected_modules = modules
                print("\nBaixando todos os módulos...")
            else:
                selected_modules = [modules[int(choice.strip()) - 1] for choice in choices.split(",")]

            for module in selected_modules:
                module_title = module["title"]
                course_name = module.get("course", {}).get("title", "Sem Nome")
                print(f"\nBaixando módulo: {module_title} do curso: {course_name}")
                save_path = Path("Cursos") / specialization_name / sanitize_string(course_name) / sanitize_string(module_title)
                save_path.mkdir(parents=True, exist_ok=True)

                # Verifica se o módulo tem um cluster_slug
                if "cluster_slug" in module and module["cluster_slug"]:
                    cluster_slug = module["cluster_slug"]
                    print(f"Usando cluster_slug: {cluster_slug}")
                    
                    # Obter grupos e aulas a partir do cluster_slug
                    groups = self.__load_lessons_from_cluster(cluster_slug)
                    
                    if not groups:
                        print(f"Nenhum grupo encontrado para o módulo: {module_title}")
                        continue
                    
                    # Baixa cada grupo sequencialmente
                    for group_index, group in enumerate(groups, 1):
                        group_title = group["title"]
                        print(f"\nProcessando grupo {group_index}: {group_title}")
                        
                        # Baixa cada aula do grupo
                        for lesson_index, lesson in enumerate(group["lessons"], 1):
                            self._download_lesson(lesson, save_path, group_index, lesson_index)
                        
                        print(f"Grupo {group_index} ({group_title}) concluído!")
                else:
                    print(f"Módulo não possui cluster_slug: {module_title}. Pulando.")
                    continue
        finally:
            self.download_report.finish()

    def select_specializations(self):
        print("Buscando especializações disponíveis...")
        params = {
            "types[0]": "SPECIALIZATION",
            "types[1]": "COURSE",
            "types[2]": "EXTRA",
            "limit": "60",
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
