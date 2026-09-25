import threading
import warnings
import logging
from datetime import datetime, timezone

import numpy as np

from .config import BASE_DIR, EMBEDDING_DIMENSION, EMBEDDING_MODEL, EMBEDDING_REVISION, MODEL_DIR, MODEL_STATE_FILE
from .storage import JsonStore


model_state_store = JsonStore(
    MODEL_STATE_FILE,
    {
        "downloaded": False,
        "model": EMBEDDING_MODEL,
        "revision": EMBEDDING_REVISION,
        "local_path": str(MODEL_DIR.relative_to(BASE_DIR)).replace("\\", "/"),
        "verified_at": None,
    },
)


def _required_model_files_exist() -> bool:
    required = ("config.json", "model.safetensors", "modules.json", "tokenizer.json")
    return MODEL_DIR.is_dir() and all((MODEL_DIR / filename).is_file() for filename in required)


def _set_model_state(downloaded: bool) -> None:
    model_state_store.write({
        "downloaded": downloaded,
        "model": EMBEDDING_MODEL,
        "revision": EMBEDDING_REVISION,
        "local_path": str(MODEL_DIR.relative_to(BASE_DIR)).replace("\\", "/"),
        "verified_at": datetime.now(timezone.utc).isoformat() if downloaded else None,
    })


def model_downloaded() -> bool:
    files_ready = _required_model_files_exist()
    state = model_state_store.read()
    valid = (
        files_ready
        and state.get("downloaded") is True
        and state.get("model") == EMBEDDING_MODEL
        and state.get("revision") == EMBEDDING_REVISION
    )
    if files_ready and not valid:
        _set_model_state(True)
        return True
    if not files_ready and state.get("downloaded"):
        _set_model_state(False)
    return files_ready


def ensure_model_available() -> str:
    """Modeli proje klasöründe hazırlar; hazırsa hiçbir Hub isteği yapmaz."""
    if model_downloaded():
        return str(MODEL_DIR)
    from huggingface_hub import snapshot_download

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _set_model_state(False)
    try:
        snapshot_download(
            repo_id=EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            local_dir=MODEL_DIR,
            local_files_only=True,
        )
    except Exception:
        snapshot_download(
            repo_id=EMBEDDING_MODEL,
            revision=EMBEDDING_REVISION,
            local_dir=MODEL_DIR,
        )
    if not _required_model_files_exist():
        raise RuntimeError("Yerel embedding modeli eksik indirildi.")
    _set_model_state(True)
    return str(MODEL_DIR)


class LocalJinaEmbedder:
    """Modeli ilk kullanımda yükler ve süreç boyunca bellekte tutar."""

    def __init__(self):
        self._model = None
        self._lock = threading.RLock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    warnings.filterwarnings("ignore", category=FutureWarning, module=r"transformers\..*")
                    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
                    import torch
                    from sentence_transformers import SentenceTransformer
                    from transformers.utils import logging as transformers_logging

                    transformers_logging.set_verbosity_error()
                    transformers_logging.disable_progress_bar()
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                    local_model_path = ensure_model_available()
                    self._model = SentenceTransformer(
                        local_model_path,
                        trust_remote_code=True,
                        local_files_only=True,
                        device=device,
                    )
        return self._model

    def encode(self, texts: list[str], prompt_name: str, batch_size: int = 16) -> np.ndarray:
        if not texts:
            return np.empty((0, EMBEDDING_DIMENSION), dtype="float32")
        model = self._load()
        with self._lock:
            vectors = model.encode(
                inputs=texts,
                task="retrieval",
                prompt_name=prompt_name,
                truncate_dim=EMBEDDING_DIMENSION,
                batch_size=batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return np.asarray(vectors, dtype="float32")


local_embedder = LocalJinaEmbedder()


def embed_documents(texts: list[str]) -> np.ndarray:
    return local_embedder.encode(texts, prompt_name="document")


def embed_query(text: str) -> np.ndarray:
    return local_embedder.encode([text], prompt_name="query")
