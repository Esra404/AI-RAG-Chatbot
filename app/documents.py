import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import faiss
from docx import Document
from pypdf import PdfReader

from .config import CHUNK_DIR, EMBEDDING_MODEL, INDEX_DIR, UPLOAD_DIR
from .embeddings import embed_documents
from .faiss_export import export_faiss_json


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_filename(name: str) -> str:
    clean = re.sub(r"[^\w.\- ()\[\]]", "_", Path(name).name, flags=re.UNICODE)
    return clean[:180] or "document.txt"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    raise ValueError("Desteklenmeyen dosya türü. PDF, DOCX, TXT veya MD yükleyin.")


def chunk_text(text: str, size: int = 1400, overlap: int = 220) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            candidates = [text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end)]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def build_document(source_path: Path, original_name: str, sha256: str) -> dict:
    document_id = str(uuid.uuid4())
    suffix = source_path.suffix.lower()
    stored_name = f"{document_id}{suffix}"
    stored_path = UPLOAD_DIR / stored_name
    shutil.move(str(source_path), stored_path)
    try:
        chunks = chunk_text(extract_text(stored_path))
        if not chunks:
            raise ValueError("Belgeden okunabilir metin çıkarılamadı.")
        vectors = embed_documents(chunks)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        index_path = INDEX_DIR / f"{document_id}.faiss"
        chunks_path = CHUNK_DIR / f"{document_id}.json"
        faiss.write_index(index, str(index_path))
        export_faiss_json(index_path)
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    return {
        "id": document_id,
        "name": safe_filename(original_name),
        "sha256": sha256,
        "active": True,
        "status": "ready",
        "chunk_count": len(chunks),
        "embedding_model": EMBEDDING_MODEL,
        "embedding_provider": "local-jina",
        "file_path": str(stored_path.relative_to(stored_path.parents[2])).replace("\\", "/"),
        "index_path": str(index_path.relative_to(index_path.parents[2])).replace("\\", "/"),
        "index_json_path": str(index_path.with_suffix(".json").relative_to(index_path.parents[2])).replace("\\", "/"),
        "chunks_path": str(chunks_path.relative_to(chunks_path.parents[2])).replace("\\", "/"),
        "created_at": utc_now(),
    }
