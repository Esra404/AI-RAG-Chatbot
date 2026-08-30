import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from .config import BASE_DIR, CHAT_MODEL, CONFIG_DIR, EMBEDDING_MODEL, MAX_FILE_MB, MODEL_DIR, STATIC_DIR, TAVILY_API_KEY, ensure_directories
from .documents import ALLOWED_EXTENSIONS, build_document, file_sha256, safe_filename
from .embeddings import model_downloaded
from .rag import answer, build_web_queries, retrieve
from .storage import JsonStore
from .web_search import WebSearchConfigurationError, search_web_queries


ensure_directories()
documents_store = JsonStore(CONFIG_DIR / "document_registry.json", {"documents": []})
chats_store = JsonStore(CONFIG_DIR / "chats.json", {"chats": []})

app = FastAPI(title="Luna RAG Chat", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def openai_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(503, "OPENAI_API_KEY tanımlı değil. .env dosyasını yapılandırın.")
    return OpenAI()


class ChatCreate(BaseModel):
    title: str = Field(default="Yeni sohbet", max_length=100)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=30000)
    web_search: bool = False


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/status")
def status():
    return {
        "ready": bool(os.getenv("OPENAI_API_KEY")),
        "model": CHAT_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_provider": "local",
        "embedding_downloaded": model_downloaded(),
        "embedding_local_path": str(MODEL_DIR.relative_to(BASE_DIR)).replace("\\", "/"),
        "web_search_ready": bool(TAVILY_API_KEY),
    }


@app.get("/api/documents")
def list_documents():
    return documents_store.read()["documents"]


@app.post("/api/documents")
def upload_document(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "PDF, DOCX, TXT veya MD dosyası yükleyin.")
    total = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temp_path = Path(temporary.name)
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_FILE_MB * 1024 * 1024:
                    raise HTTPException(413, f"Dosya {MAX_FILE_MB} MB sınırını aşıyor.")
                temporary.write(chunk)
        sha256 = file_sha256(temp_path)
        existing = next((doc for doc in documents_store.read()["documents"] if doc["sha256"] == sha256), None)
        if existing:
            temp_path.unlink(missing_ok=True)
            return {"document": existing, "duplicate": True}
        document = build_document(temp_path, safe_filename(file.filename or "document"), sha256)
        documents_store.update(lambda data: data["documents"].insert(0, document))
        return {"document": document, "duplicate": False}
    except HTTPException:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if temp_path:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(500, f"Belge işlenemedi: {exc}") from exc


@app.patch("/api/documents/{document_id}/toggle")
def toggle_document(document_id: str):
    def mutate(data):
        for document in data["documents"]:
            if document["id"] == document_id:
                document["active"] = not document["active"]
                return document
        return None
    document = documents_store.update(mutate)
    if not document:
        raise HTTPException(404, "Belge bulunamadı.")
    return document


@app.get("/api/chats")
def list_chats():
    chats = chats_store.read()["chats"]
    return [{key: chat[key] for key in ("id", "title", "created_at", "updated_at")} for chat in chats]


@app.post("/api/chats")
def create_chat(payload: ChatCreate):
    chat = {"id": str(uuid.uuid4()), "title": payload.title.strip() or "Yeni sohbet", "messages": [], "created_at": now(), "updated_at": now()}
    chats_store.update(lambda data: data["chats"].insert(0, chat))
    return chat


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str):
    chat = next((item for item in chats_store.read()["chats"] if item["id"] == chat_id), None)
    if not chat:
        raise HTTPException(404, "Sohbet bulunamadı.")
    return chat


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str):
    removed = chats_store.update(lambda data: _remove_chat(data, chat_id))
    if not removed:
        raise HTTPException(404, "Sohbet bulunamadı.")
    return {"ok": True}


def _remove_chat(data, chat_id: str) -> bool:
    before = len(data["chats"])
    data["chats"] = [chat for chat in data["chats"] if chat["id"] != chat_id]
    return len(data["chats"]) < before


@app.post("/api/chats/{chat_id}/messages")
def send_message(chat_id: str, payload: MessageCreate):
    data = chats_store.read()
    chat = next((item for item in data["chats"] if item["id"] == chat_id), None)
    if not chat:
        raise HTTPException(404, "Sohbet bulunamadı.")
    question = payload.content.strip()
    try:
        client = openai_client()
        sources = retrieve(question, documents_store.read()["documents"])
        web_queries = build_web_queries(client, question, chat["messages"], sources) if payload.web_search else []
        web_sources = search_web_queries(web_queries) if payload.web_search else []
        response_text = answer(client, question, chat["messages"], sources, web_sources)
    except WebSearchConfigurationError as exc:
        raise HTTPException(503, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"OpenAI isteği başarısız: {exc}") from exc
    timestamp = now()
    user_message = {"id": str(uuid.uuid4()), "role": "user", "content": question, "created_at": timestamp}
    assistant_message = {
        "id": str(uuid.uuid4()), "role": "assistant", "content": response_text,
        "sources": [
            {
                "number": position,
                "document_id": source["document_id"],
                "document_name": source["document_name"],
                "chunk_position": source["chunk_position"],
                "chunk": source["chunk"],
                "score": round(source["score"], 4),
            }
            for position, source in enumerate(sources, 1)
        ],
        "created_at": now(),
        "web_sources": web_sources,
        "web_search_used": payload.web_search,
        "web_queries": web_queries,
    }
    def save(data):
        target = next(item for item in data["chats"] if item["id"] == chat_id)
        target["messages"].extend([user_message, assistant_message])
        if len(target["messages"]) == 2:
            target["title"] = question[:48] + ("…" if len(question) > 48 else "")
        target["updated_at"] = now()
        data["chats"].sort(key=lambda item: item["updated_at"], reverse=True)
    chats_store.update(save)
    return {"user": user_message, "assistant": assistant_message}
