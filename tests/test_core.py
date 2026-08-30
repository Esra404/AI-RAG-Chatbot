import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import faiss
import numpy as np

from app.documents import build_document, chunk_text, file_sha256
from app.rag import build_web_queries
from app.storage import JsonStore
from app.web_search import search_web_queries


def fake_embed_documents(texts):
    return np.asarray(
        [[float(len(text) % 7 + 1), float(position + 1), 1.0, 0.5] for position, text in enumerate(texts)],
        dtype="float32",
    )


class CoreTests(unittest.TestCase):
    def test_web_query_planner_falls_back_when_structured_output_is_invalid(self):
        class BrokenResponses:
            def parse(self, **kwargs):
                raise ValueError("truncated json")

        class BrokenClient:
            responses = BrokenResponses()

        sources = [{
            "document_name": "Necip_CV.pdf",
            "chunk": "Necip Sahamettin Kucuk Senior Artificial Intelligence Engineer",
        }]
        queries = build_web_queries(BrokenClient(), "bu kişi hakkında daha fazla bilgi", [], sources)
        self.assertEqual(len(queries), 3)
        self.assertTrue(all("Necip Sahamettin Kucuk" in query for query in queries))

    @patch("app.web_search.search_web")
    def test_multiple_web_queries_are_deduplicated(self, mocked_search):
        mocked_search.side_effect = [
            [{"url": "https://example.com/a", "title": "A", "score": 0.8, "number": 1}],
            [
                {"url": "https://example.com/a", "title": "A2", "score": 0.9, "number": 1},
                {"url": "https://example.com/b", "title": "B", "score": 0.7, "number": 2},
            ],
        ]
        results = search_web_queries(["sorgu bir", "sorgu iki"])
        self.assertEqual([result["url"] for result in results], ["https://example.com/a", "https://example.com/b"])
        self.assertEqual([result["number"] for result in results], [1, 2])

    def test_json_store_persists_update(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonStore(Path(directory) / "store.json", {"items": []})
            store.update(lambda data: data["items"].append("kalıcı"))
            self.assertEqual(JsonStore(Path(directory) / "store.json", {}).read()["items"], ["kalıcı"])

    def test_chunk_text_has_overlap_and_content(self):
        text = "Birinci bölüm. " * 200
        chunks = chunk_text(text, size=220, overlap=40)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(chunks))

    def test_document_id_maps_to_faiss_and_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uploads, indexes, chunks = root / "data/uploads", root / "data/indexes", root / "data/chunks"
            for path in (uploads, indexes, chunks):
                path.mkdir(parents=True)
            incoming = root / "incoming.txt"
            incoming.write_text("Luna RAG test belgesi. " * 150, encoding="utf-8")
            digest = file_sha256(incoming)
            with (
                patch("app.documents.UPLOAD_DIR", uploads),
                patch("app.documents.INDEX_DIR", indexes),
                patch("app.documents.CHUNK_DIR", chunks),
                patch("app.documents.embed_documents", fake_embed_documents),
            ):
                document = build_document(incoming, "test.txt", digest)
            self.assertEqual(document["sha256"], digest)
            self.assertEqual(document["embedding_model"], "jinaai/jina-embeddings-v5-text-nano")
            index_path = root / document["index_path"]
            chunks_path = root / document["chunks_path"]
            self.assertTrue(index_path.exists())
            self.assertTrue(chunks_path.exists())
            self.assertEqual(faiss.read_index(str(index_path)).ntotal, document["chunk_count"])
            self.assertTrue(index_path.with_suffix(".json").exists())


if __name__ == "__main__":
    unittest.main()
