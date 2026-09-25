import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
INDEX_DIR = DATA_DIR / "indexes"
CHUNK_DIR = DATA_DIR / "chunks"
STATIC_DIR = BASE_DIR / "static"
MODEL_DIR = BASE_DIR / os.getenv("LOCAL_EMBEDDING_PATH", "models/jina-embeddings-v5-text-nano")
MODEL_STATE_FILE = CONFIG_DIR / "model_state.json"

CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna")
EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "jinaai/jina-embeddings-v5-text-nano")
EMBEDDING_REVISION = os.getenv("LOCAL_EMBEDDING_REVISION", "8a7f00aac812071b69403df470f1038ec85f8925")
EMBEDDING_DIMENSION = int(os.getenv("LOCAL_EMBEDDING_DIMENSION", "256"))
TOP_K = int(os.getenv("RAG_TOP_K", "6"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "25"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


def ensure_directories() -> None:
    for path in (CONFIG_DIR, UPLOAD_DIR, INDEX_DIR, CHUNK_DIR, STATIC_DIR, MODEL_DIR.parent):
        path.mkdir(parents=True, exist_ok=True)
