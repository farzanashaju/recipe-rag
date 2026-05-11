import multiprocessing
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

workers = 1
threads = 2
worker_class = "gthread"

bind = "127.0.0.1:8000"
timeout = 300
keepalive = 5

chdir = str(BASE_DIR)

accesslog = "-"
errorlog = "-"
loglevel = "info"
