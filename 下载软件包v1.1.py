# coding: utf-8
import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
import colorama
from colorama import Fore, Style


# 初始化 colorama
colorama.init()

# 目录路径
DIRECTORY_PATH = './npm_changes/'
print("将程序放在npm_changes同级目录下运行")

# 保存路径
SAVE_PATH = './文件保存/'
if not os.path.exists(SAVE_PATH):
    os.mkdir(SAVE_PATH)

# 状态文件路径
STATUS_FILE_PATH = 'processed_files.txt'
print("processed_files.txt文件保存处理过的JSON文件，再次运行程序将不处理这些JSON文件")

# 读取已处理文件列表
processed_files = set()
if os.path.exists(STATUS_FILE_PATH):
    with open(STATUS_FILE_PATH, 'r', encoding='utf-8') as f:
        processed_files = set(f.read().splitlines())

# 线程池大小
MAX_WORKERS = 5  # 解析json文件线程数
FILEDOWN_MAX_WORKERS = 10  # 下载文件线程数

print(f"线程数：处理JSON（{Fore.GREEN}{MAX_WORKERS}{Style.RESET_ALL}）,下载文件（{Fore.GREEN}{FILEDOWN_MAX_WORKERS}{Style.RESET_ALL}）")

# 重试次数
MAX_RETRIES = 3

# 状态文件锁
status_file_lock = threading.Lock()

def process_json_file(file_path):
    # 检查文件是否已处理过
    if file_path in processed_files:
        print(f'JSON文件已处理过 {file_path}')
        return

    # 解析 JSON 文件,获取下载链接
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)


    package_id = data['id']
    versions = data['doc']['versions']
    latest_version = data['doc']['dist-tags']['latest']

    download_link = versions[latest_version]['dist']['tarball']
    # 是否已经下载此文件
    if os.path.exists(SAVE_PATH + download_link.split('/')[-1]):
        print(f'{Fore.GREEN}下载文件已存在: {download_link.split("/")[-1]}{Style.RESET_ALL}')
    else:
        # 下载文件
        filedown_executor.submit(download_file, download_link)

    # 更新已处理文件列表
    processed_files.add(file_path)
    status_file_lock.acquire()
    with open(STATUS_FILE_PATH, 'a', encoding='utf-8') as f:
        f.write(f'{file_path}\n')
    status_file_lock.release()

filedown_executor = ThreadPoolExecutor(max_workers=FILEDOWN_MAX_WORKERS)

def download_file(url):
    retries = 0
    while retries < MAX_RETRIES:
        try:
            response = requests.get(url)
            response.raise_for_status()
            with open(SAVE_PATH + url.split('/')[-1], 'wb') as f:
                f.write(response.content)
            print(f'{Fore.GREEN}下载文件: {url}{Style.RESET_ALL}')
            return
        except requests.exceptions.RequestException as e:
            print(f'{Fore.RED}下载文件错误 {url}: {e}{Style.RESET_ALL}')
            retries += 1
            if retries < MAX_RETRIES:
                print(f'{Fore.YELLOW}重试下载, 尝试 {retries + 1}/{MAX_RETRIES} 次...{Style.RESET_ALL}')
    print(f'{Fore.RED}失败下载文件 {url} 共尝试 {MAX_RETRIES} 次.{Style.RESET_ALL}')

class JsonFileEventHandler(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith('.json'):
            return
        # # 等待一段时间,确保文件完全写入
        # time.sleep(1)
        # 等待文件大小不再变化
        prev_size = 0
        while True:
            current_size = os.path.getsize(event.src_path)
            if current_size == prev_size:
                break
            prev_size = current_size
            time.sleep(0.1)
        # process_json_file(event.src_path)
        self.executor.submit(process_json_file, event.src_path)

if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for file_name in os.listdir(DIRECTORY_PATH):
            if file_name.endswith('.json'):
                file_path = os.path.join(DIRECTORY_PATH, file_name)
                executor.submit(process_json_file, file_path)

    observer = Observer()
    event_handler = JsonFileEventHandler()
    observer.schedule(event_handler, path=DIRECTORY_PATH, recursive=False)
    observer.start()


    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
